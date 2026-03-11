"""Tests for Shipwright — AI-powered release management."""
import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from forge.shipwright import Shipwright, ClassifiedCommit, _SEMVER_RE


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temp project with pyproject.toml and forge/__init__.py."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "test"\nversion = "1.2.3"\n', encoding="utf-8"
    )
    forge_dir = tmp_path / "forge"
    forge_dir.mkdir()
    init_py = forge_dir / "__init__.py"
    init_py.write_text('__version__ = "1.2.3"\n', encoding="utf-8")
    return tmp_path


@pytest.fixture
def sw(tmp_project):
    data_dir = tmp_project / ".shipwright_data"
    data_dir.mkdir()
    return Shipwright(project_dir=str(tmp_project), data_dir=data_dir)


# ── Version management ──

class TestVersionManagement:
    """Verifies Shipwright reads, writes, and bumps semantic versions across project files.

    get_current_version() reads from pyproject.toml. Missing file returns '0.0.0'.
    set_version() updates both pyproject.toml and forge/__init__.py, returning 2 modified files.
    bump_version(): major '1.2.3' → '2.0.0', minor → '1.3.0', patch → '1.2.4', none → unchanged.
    _SEMVER_RE matches '1.2.3', '0.9.0', pre-release '1.0.0-alpha', build metadata '1.0.0+build.42'.
    It does NOT match 'not-a-version' or '1.2' (missing patch component).
    """

    def test_get_current_version(self, sw, tmp_project):
        assert sw.get_current_version() == "1.2.3"

    def test_get_current_version_missing_file(self, tmp_path):
        sw = Shipwright(project_dir=str(tmp_path))
        assert sw.get_current_version() == "0.0.0"

    def test_set_version_updates_both_files(self, sw, tmp_project):
        modified = sw.set_version("2.0.0")
        assert len(modified) == 2
        pyproject = (tmp_project / "pyproject.toml").read_text(encoding="utf-8")
        assert '"2.0.0"' in pyproject
        init = (tmp_project / "forge" / "__init__.py").read_text(encoding="utf-8")
        assert '"2.0.0"' in init

    def test_bump_major(self):
        assert Shipwright.bump_version("1.2.3", "major") == "2.0.0"

    def test_bump_minor(self):
        assert Shipwright.bump_version("1.2.3", "minor") == "1.3.0"

    def test_bump_patch(self):
        assert Shipwright.bump_version("1.2.3", "patch") == "1.2.4"

    def test_bump_none(self):
        assert Shipwright.bump_version("1.2.3", "none") == "1.2.3"

    def test_semver_regex_valid(self):
        assert _SEMVER_RE.match("1.2.3") is not None
        assert _SEMVER_RE.match("0.9.0") is not None
        assert _SEMVER_RE.match("1.0.0-alpha") is not None
        assert _SEMVER_RE.match("1.0.0+build.42") is not None

    def test_semver_regex_invalid(self):
        assert _SEMVER_RE.match("not-a-version") is None
        assert _SEMVER_RE.match("1.2") is None


# ── Commit classification ──

class TestCommitClassification:
    """Verifies classify_commits() maps conventional commit prefixes to categories and bump types.

    'feat:' → category='feature', bump_type='minor'. 'fix:' → 'fix'/'patch'.
    'BREAKING CHANGE' → 'breaking'/'major'. 'docs:' → 'docs'/'none'.
    'test:' → 'test'/'none'. 'security:' → 'security'/'patch'.
    'refactor:' → 'refactor'/'patch'. 'Implement ...' (imperative) → 'feature'/'minor'.
    Unknown message → bump_type='patch' (safe default).
    """

    def test_feature_commit(self, sw):
        commits = [ClassifiedCommit(sha="abc", message="feat: add new tool", author="dev", date="2026-03-03")]
        sw.classify_commits(commits)
        assert commits[0].category == "feature"
        assert commits[0].bump_type == "minor"

    def test_fix_commit(self, sw):
        commits = [ClassifiedCommit(sha="abc", message="fix: resolve crash on startup", author="dev", date="2026-03-03")]
        sw.classify_commits(commits)
        assert commits[0].category == "fix"
        assert commits[0].bump_type == "patch"

    def test_breaking_change(self, sw):
        commits = [ClassifiedCommit(sha="abc", message="BREAKING CHANGE: remove old API", author="dev", date="2026-03-03")]
        sw.classify_commits(commits)
        assert commits[0].category == "breaking"
        assert commits[0].bump_type == "major"

    def test_docs_commit(self, sw):
        commits = [ClassifiedCommit(sha="abc", message="docs: update README", author="dev", date="2026-03-03")]
        sw.classify_commits(commits)
        assert commits[0].category == "docs"
        assert commits[0].bump_type == "none"

    def test_test_commit(self, sw):
        commits = [ClassifiedCommit(sha="abc", message="test: add unit tests for shipwright", author="dev", date="2026-03-03")]
        sw.classify_commits(commits)
        assert commits[0].category == "test"
        assert commits[0].bump_type == "none"

    def test_security_commit(self, sw):
        commits = [ClassifiedCommit(sha="abc", message="security: patch CVE-2026-1234", author="dev", date="2026-03-03")]
        sw.classify_commits(commits)
        assert commits[0].category == "security"
        assert commits[0].bump_type == "patch"

    def test_refactor_commit(self, sw):
        commits = [ClassifiedCommit(sha="abc", message="refactor: clean up engine.py", author="dev", date="2026-03-03")]
        sw.classify_commits(commits)
        assert commits[0].category == "refactor"
        assert commits[0].bump_type == "patch"

    def test_implement_commit(self, sw):
        commits = [ClassifiedCommit(sha="abc", message="Implement voice commands", author="dev", date="2026-03-03")]
        sw.classify_commits(commits)
        assert commits[0].category == "feature"
        assert commits[0].bump_type == "minor"

    def test_unknown_defaults_to_patch(self, sw):
        commits = [ClassifiedCommit(sha="abc", message="misc changes", author="dev", date="2026-03-03")]
        sw.classify_commits(commits)
        assert commits[0].bump_type == "patch"


# ── Version computation ──

class TestVersionComputation:
    """Verifies compute_next_version() picks the highest bump level across all commits.

    mix of patch+minor → minor wins, next version is bumped by minor.
    Empty commits → bump='none', version unchanged. Breaking change + patch → major wins.
    """

    def test_highest_bump_wins(self, sw):
        commits = [
            ClassifiedCommit(sha="a", message="fix: bug", author="d", date="2026-01-01",
                           category="fix", bump_type="patch"),
            ClassifiedCommit(sha="b", message="feat: new thing", author="d", date="2026-01-01",
                           category="feature", bump_type="minor"),
        ]
        next_ver, bump = sw.compute_next_version(commits)
        assert bump == "minor"
        assert next_ver == "1.3.0"

    def test_no_commits_no_bump(self, sw):
        next_ver, bump = sw.compute_next_version([])
        assert bump == "none"
        assert next_ver == "1.2.3"

    def test_major_overrides_all(self, sw):
        commits = [
            ClassifiedCommit(sha="a", message="fix: bug", author="d", date="2026-01-01",
                           category="fix", bump_type="patch"),
            ClassifiedCommit(sha="b", message="BREAKING CHANGE", author="d", date="2026-01-01",
                           category="breaking", bump_type="major"),
        ]
        next_ver, bump = sw.compute_next_version(commits)
        assert bump == "major"
        assert next_ver == "2.0.0"


# ── Changelog generation ──

class TestChangelogGeneration:
    """Verifies generate_changelog() produces properly structured Markdown with all commit categories.

    Output must include '## [version]', '### Features', '### Bug Fixes', and the commit messages.
    Empty commit list still produces a minimal '## [version]' header.
    """

    def test_generates_markdown(self, sw):
        commits = [
            ClassifiedCommit(sha="abc123", message="Add voice commands", author="d", date="2026-01-01",
                           category="feature", bump_type="minor"),
            ClassifiedCommit(sha="def456", message="Fix crash", author="d", date="2026-01-01",
                           category="fix", bump_type="patch"),
        ]
        changelog = sw.generate_changelog(commits, "1.3.0")
        assert "## [1.3.0]" in changelog
        assert "### Features" in changelog
        assert "### Bug Fixes" in changelog
        assert "Add voice commands" in changelog
        assert "Fix crash" in changelog

    def test_empty_commits_minimal_changelog(self, sw):
        changelog = sw.generate_changelog([], "1.2.4")
        assert "## [1.2.4]" in changelog


# ── History persistence ──

class TestHistoryPersistence:
    """Verifies release history is saved to disk and reloaded correctly by a new Shipwright instance.

    After appending a ReleaseInfo and calling _save_history(), a new Shipwright pointed at
    the same data_dir must load exactly 1 history entry with the correct version.
    """

    def test_save_load_roundtrip(self, tmp_project):
        from forge.shipwright import ReleaseInfo
        data_dir = tmp_project / ".hist_test"
        data_dir.mkdir()
        sw1 = Shipwright(project_dir=str(tmp_project), data_dir=data_dir)
        sw1._history.append(ReleaseInfo(
            version="1.3.0", previous_version="1.2.3",
            timestamp=1000000.0, tag="v1.3.0",
        ))
        sw1._save_history()
        sw2 = Shipwright(project_dir=str(tmp_project), data_dir=data_dir)
        assert len(sw2._history) == 1
        assert sw2._history[0].version == "1.3.0"


# ── Status display ──

class TestStatusDisplay:
    """Verifies format_status() shows the current version, format_history() handles empty, and to_audit_dict() is correct.

    format_status() must include the current version string '1.2.3'.
    format_history() for a fresh instance must include 'No releases'.
    to_audit_dict() must have schema_version==1 and current_version=='1.2.3'.
    """

    def test_format_status_no_git(self, sw):
        status = sw.format_status()
        assert "1.2.3" in status

    def test_format_history_empty(self, tmp_project):
        # Use fresh instance with its own data dir
        fresh_data = tmp_project / ".fresh_data"
        fresh_data.mkdir()
        fresh_sw = Shipwright(project_dir=str(tmp_project), data_dir=fresh_data)
        result = fresh_sw.format_history()
        assert "No releases" in result

    def test_audit_dict(self, sw):
        audit = sw.to_audit_dict()
        assert audit["schema_version"] == 1
        assert audit["current_version"] == "1.2.3"


# ── Push after release ──

class TestPushAfterRelease:
    """Verifies push_after_release controls whether git push is called during release().

    Default: _push_after_release=False. Explicitly setting push_after_release=True sets it True.
    When configured True: release() calls _git('push', ...) twice (branch + tag) with 'origin' in args.
    When disabled: no push calls. When push fails with RuntimeError: result['push_error'] captures
    the error message ('Permission denied') rather than raising.
    """

    def test_push_after_release_false_by_default(self, sw):
        assert sw._push_after_release is False

    def test_push_after_release_true_when_set(self, tmp_project):
        data_dir = tmp_project / ".sw_push_test"
        data_dir.mkdir()
        sw = Shipwright(project_dir=str(tmp_project), data_dir=data_dir,
                        push_after_release=True)
        assert sw._push_after_release is True

    def test_push_called_on_release_when_configured(self, tmp_project):
        """push_after_release=True must call git push for branch and tag."""
        import subprocess
        from unittest.mock import patch, call

        data_dir = tmp_project / ".sw_push_call_test"
        data_dir.mkdir()

        # Set up a minimal git repo with a commit so release() has something to work with
        env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1",
               "HOME": str(tmp_path_for := tmp_project),
               "GIT_TERMINAL_PROMPT": "0"}
        subprocess.run(["git", "init"], cwd=str(tmp_project),
                       capture_output=True, env=env)
        subprocess.run(["git", "config", "core.fsmonitor", "false"],
                       cwd=str(tmp_project), capture_output=True, env=env)
        subprocess.run(["git", "config", "user.email", "t@t.com"],
                       cwd=str(tmp_project), capture_output=True, env=env)
        subprocess.run(["git", "config", "user.name", "T"],
                       cwd=str(tmp_project), capture_output=True, env=env)
        subprocess.run(["git", "add", "."], cwd=str(tmp_project),
                       capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "feat: initial"],
                       cwd=str(tmp_project), capture_output=True, env=env)

        sw = Shipwright(project_dir=str(tmp_project), data_dir=data_dir,
                        push_after_release=True)

        push_calls = []

        original_git = sw._git
        def mock_git(*args, **kwargs):
            if args[0] == "push":
                push_calls.append(list(args))
                return ""
            return original_git(*args, **kwargs)

        sw._git = mock_git
        result = sw.release(dry_run=False)

        if result["status"] == "released":
            assert len(push_calls) == 2  # branch push + tag push
            assert any("origin" in c for c in push_calls)

    def test_push_not_called_when_disabled(self, tmp_project):
        """push_after_release=False must not call git push."""
        import subprocess

        data_dir = tmp_project / ".sw_nopush_test"
        data_dir.mkdir()

        env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1",
               "HOME": str(tmp_project), "GIT_TERMINAL_PROMPT": "0"}
        subprocess.run(["git", "init"], cwd=str(tmp_project),
                       capture_output=True, env=env)
        subprocess.run(["git", "config", "core.fsmonitor", "false"],
                       cwd=str(tmp_project), capture_output=True, env=env)
        subprocess.run(["git", "config", "user.email", "t@t.com"],
                       cwd=str(tmp_project), capture_output=True, env=env)
        subprocess.run(["git", "config", "user.name", "T"],
                       cwd=str(tmp_project), capture_output=True, env=env)
        subprocess.run(["git", "add", "."], cwd=str(tmp_project),
                       capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "feat: initial"],
                       cwd=str(tmp_project), capture_output=True, env=env)

        sw = Shipwright(project_dir=str(tmp_project), data_dir=data_dir,
                        push_after_release=False)

        push_calls = []
        original_git = sw._git
        def mock_git(*args, **kwargs):
            if args[0] == "push":
                push_calls.append(list(args))
                return ""
            return original_git(*args, **kwargs)

        sw._git = mock_git
        sw.release(dry_run=False)
        assert push_calls == []

    def test_push_error_captured_in_result(self, tmp_project):
        """A git push failure must be captured in result['push_error'], not raised."""
        import subprocess

        data_dir = tmp_project / ".sw_pusherr_test"
        data_dir.mkdir()

        env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1",
               "HOME": str(tmp_project), "GIT_TERMINAL_PROMPT": "0"}
        subprocess.run(["git", "init"], cwd=str(tmp_project),
                       capture_output=True, env=env)
        subprocess.run(["git", "config", "core.fsmonitor", "false"],
                       cwd=str(tmp_project), capture_output=True, env=env)
        subprocess.run(["git", "config", "user.email", "t@t.com"],
                       cwd=str(tmp_project), capture_output=True, env=env)
        subprocess.run(["git", "config", "user.name", "T"],
                       cwd=str(tmp_project), capture_output=True, env=env)
        subprocess.run(["git", "add", "."], cwd=str(tmp_project),
                       capture_output=True, env=env)
        subprocess.run(["git", "commit", "-m", "feat: initial"],
                       cwd=str(tmp_project), capture_output=True, env=env)

        sw = Shipwright(project_dir=str(tmp_project), data_dir=data_dir,
                        push_after_release=True)

        original_git = sw._git
        def mock_git(*args, **kwargs):
            if args[0] == "push":
                raise RuntimeError("remote: Permission denied")
            return original_git(*args, **kwargs)

        sw._git = mock_git
        result = sw.release(dry_run=False)

        if result["status"] == "released":
            assert "push_error" in result
            assert "Permission denied" in result["push_error"]
