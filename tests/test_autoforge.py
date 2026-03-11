"""Tests for AutoForge — Smart auto-commit system."""
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from forge.autoforge import AutoForge, PendingEdit, generate_hook_script


def _git_env(tmp_path):
    """Env dict that isolates git from user/system config."""
    return {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": str(tmp_path),
        "USERPROFILE": str(tmp_path),
        "GIT_TERMINAL_PROMPT": "0",
    }


@pytest.fixture
def git_project(tmp_path):
    """Create a temp git repository isolated from user/system git config."""
    env = _git_env(tmp_path)
    subprocess.run(
        ["git", "init"], cwd=str(tmp_path),
        capture_output=True, timeout=10, env=env,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=str(tmp_path), capture_output=True, timeout=10, env=env,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=str(tmp_path), capture_output=True, timeout=10, env=env,
    )
    # Create initial commit
    readme = tmp_path / "README.md"
    readme.write_text("# Test\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "."], cwd=str(tmp_path),
        capture_output=True, timeout=10, env=env,
    )
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(tmp_path), capture_output=True, timeout=10, env=env,
    )
    return tmp_path


@pytest.fixture
def af(git_project):
    af = AutoForge(project_dir=str(git_project),
                   git_env=_git_env(git_project))
    af.enable()
    return af


# ── Basic operations ──

class TestBasicOperations:
    """Verifies AutoForge enable/disable state, edit recording, and git repo detection.

    Default state is disabled. enable() sets enabled=True. disable() resets it.
    enable() on a directory without a git repo leaves enabled=False (no-op).
    record_edit() silently ignores files outside project_dir. Files inside project_dir
    are accepted when enabled. record_edit() is a no-op when disabled.
    """

    def test_enable_disable(self, git_project):
        af = AutoForge(project_dir=str(git_project),
                       git_env=_git_env(git_project))
        assert not af.enabled
        af.enable()
        assert af.enabled
        af.disable()
        assert not af.enabled

    def test_not_enabled_without_git(self, tmp_path):
        af = AutoForge(project_dir=str(tmp_path))
        af.enable()
        assert not af.enabled  # No git repo

    def test_record_edit_skips_out_of_repo_file(self, af, git_project, tmp_path):
        # A file on the desktop or any path outside project_dir must be silently ignored
        outside_file = tmp_path.parent / "random_list.txt"
        outside_file.write_text("hello\n", encoding="utf-8")
        af.record_edit(str(outside_file))
        assert len(af._pending) == 0

    def test_record_edit_accepts_in_repo_file(self, af, git_project):
        inside_file = git_project / "inside.py"
        inside_file.write_text("x = 1\n", encoding="utf-8")
        af.record_edit(str(inside_file))
        assert len(af._pending) == 1

    def test_record_edit_when_disabled(self, git_project):
        af = AutoForge(project_dir=str(git_project),
                       git_env=_git_env(git_project))
        af.record_edit("test.py")
        assert len(af._pending) == 0

    def test_record_edit_when_enabled(self, af, git_project):
        test_file = git_project / "test.py"
        test_file.write_text("print('hello')\n", encoding="utf-8")
        af.record_edit(str(test_file))
        assert len(af._pending) == 1
        assert af._pending[0].path == str(test_file)


# ── Committing ──

class TestCommitting:
    """Verifies AutoForge correctly batches edits and commits to git.

    A single recorded edit produces a commit with one file and a non-empty SHA.
    Five files in one batch produce a commit with '5 files' in the message.
    commit_pending() with nothing pending returns None.
    advance_turn() commits pending edits for that turn.
    on_session_end() commits remaining edits with 'session end' in the message.
    Duplicate file paths in the same batch are deduplicated before committing.
    """

    def test_commit_single_file(self, af, git_project):
        test_file = git_project / "new_file.py"
        test_file.write_text("x = 1\n", encoding="utf-8")
        af.record_edit(str(test_file), action="create")
        commit = af.commit_pending()
        assert commit is not None
        assert commit.sha
        assert len(commit.files) == 1
        assert len(af._pending) == 0

    def test_commit_multiple_files_batched(self, af, git_project):
        for i in range(5):
            f = git_project / f"file_{i}.py"
            f.write_text(f"x = {i}\n", encoding="utf-8")
            af.record_edit(str(f), action="create")
        commit = af.commit_pending()
        assert commit is not None
        assert len(commit.files) == 5
        assert "5 files" in commit.message

    def test_no_commit_when_nothing_pending(self, af):
        commit = af.commit_pending()
        assert commit is None

    def test_advance_turn_triggers_commit(self, af, git_project):
        test_file = git_project / "turn_file.py"
        test_file.write_text("y = 2\n", encoding="utf-8")
        af.record_edit(str(test_file), action="create")
        commit = af.advance_turn(1)
        assert commit is not None

    def test_session_end_commits_remaining(self, af, git_project):
        test_file = git_project / "final.py"
        test_file.write_text("z = 3\n", encoding="utf-8")
        af.record_edit(str(test_file), action="create")
        commit = af.on_session_end()
        assert commit is not None
        assert "session end" in commit.message

    def test_dedup_files_in_same_batch(self, af, git_project):
        test_file = git_project / "dup.py"
        test_file.write_text("a = 1\n", encoding="utf-8")
        af.record_edit(str(test_file), action="edit")
        af.record_edit(str(test_file), action="edit")
        af.record_edit(str(test_file), action="edit")
        commit = af.commit_pending()
        assert commit is not None
        assert len(commit.files) == 1  # Deduped


# ── Message generation ──

class TestMessageGeneration:
    """Verifies commit messages include the filename for single-file commits and the action verb.

    A single file edit commit includes the filename in the message.
    A 'create' action produces a message with 'add' (or equivalent) verb.
    """

    def test_single_file_message(self, af, git_project):
        f = git_project / "single.py"
        f.write_text("pass\n", encoding="utf-8")
        af.record_edit(str(f), action="create")
        commit = af.commit_pending()
        assert "single.py" in commit.message

    def test_create_action_message(self, af, git_project):
        f = git_project / "new.py"
        f.write_text("pass\n", encoding="utf-8")
        af.record_edit(str(f), action="create")
        commit = af.commit_pending()
        assert "add" in commit.message.lower()


# ── Status display ──

class TestStatusDisplay:
    """Verifies format_status() and to_audit_dict() correctly reflect enabled/disabled state.

    Disabled → 'disabled' in status string. Enabled → 'enabled' in status string.
    to_audit_dict() has schema_version==1 and enabled==True when enabled.
    """

    def test_format_status_disabled(self, git_project):
        af = AutoForge(project_dir=str(git_project),
                       git_env=_git_env(git_project))
        status = af.format_status()
        assert "disabled" in status

    def test_format_status_enabled(self, af):
        status = af.format_status()
        assert "enabled" in status

    def test_audit_dict(self, af):
        audit = af.to_audit_dict()
        assert audit["schema_version"] == 1
        assert audit["enabled"] is True


# ── Hook script generation ──

class TestHookScript:
    """Verifies generate_hook_script() produces syntactically valid Python containing the project path.

    The output must parse without errors via ast.parse(). The project_dir string must appear
    verbatim in the generated script so it hooks back to the correct project.
    """

    def test_generates_valid_python(self):
        script = generate_hook_script("/tmp/project")
        # Should be valid Python
        import ast
        ast.parse(script)

    def test_contains_project_dir(self):
        script = generate_hook_script("/my/project")
        assert "/my/project" in script
