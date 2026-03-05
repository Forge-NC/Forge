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
