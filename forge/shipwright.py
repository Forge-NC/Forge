"""Shipwright — AI-powered release management for Forge.

Reads version from pyproject.toml (single source of truth), classifies
commits via rule-based heuristics + optional LLM fallback, auto-bumps
semantic version, generates changelogs, and orchestrates releases.

Workflow:
  1. /ship status    — Show current version, unreleased commits, classification
  2. /ship dry       — Preview what a release would look like
  3. /ship preflight — Run tests + lint + verify before release
  4. /ship go        — Tag, bump version, push
  5. /ship changelog — Generate changelog from classified commits
  6. /ship history   — Show past releases
"""

import json
import logging
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── Semantic version regex ──

_SEMVER_RE = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:-(?P<pre>[a-zA-Z0-9.]+))?"
    r"(?:\+(?P<build>[a-zA-Z0-9.]+))?$"
)

# ── Commit classification rules ──

# Each rule: (regex_pattern, category, bump_type)
# bump_type: "major", "minor", "patch", "none"
_COMMIT_RULES = [
    # Breaking changes
    (re.compile(r"BREAKING[\s_-]CHANGE", re.IGNORECASE), "breaking", "major"),
    (re.compile(r"^!\s*:"), "breaking", "major"),
    # Features
    (re.compile(r"^feat(\(|:|\s)", re.IGNORECASE), "feature", "minor"),
    (re.compile(r"\badd(?:ed|s)?\b.*\b(?:feature|command|tool|endpoint)", re.IGNORECASE), "feature", "minor"),
    (re.compile(r"\bnew\b.*\b(?:feature|command|tool|module|subsystem)", re.IGNORECASE), "feature", "minor"),
    (re.compile(r"\bimplement(?:ed|s)?\b", re.IGNORECASE), "feature", "minor"),
    # Fixes
    (re.compile(r"^fix(\(|:|\s)", re.IGNORECASE), "fix", "patch"),
    (re.compile(r"\bfix(?:ed|es)?\b.*\b(?:bug|crash|error|issue|regression)", re.IGNORECASE), "fix", "patch"),
    (re.compile(r"\bhotfix\b", re.IGNORECASE), "fix", "patch"),
    # Refactoring
    (re.compile(r"^refactor(\(|:|\s)", re.IGNORECASE), "refactor", "patch"),
    (re.compile(r"\brefactor(?:ed|s|ing)?\b", re.IGNORECASE), "refactor", "patch"),
    (re.compile(r"\bclean\s*up\b", re.IGNORECASE), "refactor", "patch"),
    # Documentation
    (re.compile(r"^docs?(\(|:|\s)", re.IGNORECASE), "docs", "none"),
    (re.compile(r"\b(?:update|add|fix).*\b(?:readme|docs?|comment)", re.IGNORECASE), "docs", "none"),
    # Tests
    (re.compile(r"^test(\(|:|\s)", re.IGNORECASE), "test", "none"),
    (re.compile(r"\b(?:add|fix|update).*\btests?\b", re.IGNORECASE), "test", "none"),
    # Chore / CI
    (re.compile(r"^chore(\(|:|\s)", re.IGNORECASE), "chore", "none"),
    (re.compile(r"^ci(\(|:|\s)", re.IGNORECASE), "ci", "none"),
    (re.compile(r"\bversion\s*bump\b", re.IGNORECASE), "chore", "none"),
    # Security
    (re.compile(r"^security(\(|:|\s)", re.IGNORECASE), "security", "patch"),
    (re.compile(r"\bvuln(?:erability|erable)?\b", re.IGNORECASE), "security", "patch"),
    (re.compile(r"\bCVE-\d+", re.IGNORECASE), "security", "patch"),
    # Performance
    (re.compile(r"^perf(\(|:|\s)", re.IGNORECASE), "perf", "patch"),
    (re.compile(r"\boptimiz(?:e|ed|ation)\b", re.IGNORECASE), "perf", "patch"),
]


@dataclass
class ClassifiedCommit:
    """A git commit with its classification."""
    sha: str
    message: str
    author: str
    date: str
    category: str = "unknown"
    bump_type: str = "none"
    classified_by: str = "rules"  # "rules" or "llm"


@dataclass
class ReleaseInfo:
    """Metadata for a release."""
    version: str
    previous_version: str
    timestamp: float
    commits: list[dict] = field(default_factory=list)
    changelog: str = ""
    tag: str = ""


class Shipwright:
    """AI-powered release management."""

    def __init__(self, project_dir: str = None, llm_backend=None,
                 data_dir: Path = None):
        self._project_dir = Path(project_dir or os.getcwd())
        self._llm = llm_backend
        self._data_dir = data_dir or (Path.home() / ".forge" / "shipwright")
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._history_path = self._data_dir / "releases.json"
        self._history: list[ReleaseInfo] = []
        self._load_history()

    # ── Version management ──

    def get_current_version(self) -> str:
        """Read version from pyproject.toml (single source of truth)."""
        pyproject = self._project_dir / "pyproject.toml"
        if not pyproject.exists():
            return "0.0.0"
        text = pyproject.read_text(encoding="utf-8")
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        return m.group(1) if m else "0.0.0"

    def set_version(self, new_version: str) -> list[str]:
        """Update version in pyproject.toml and forge/__init__.py.

        Returns list of files modified.
        """
        modified = []

        # Update pyproject.toml
        pyproject = self._project_dir / "pyproject.toml"
        if pyproject.exists():
            text = pyproject.read_text(encoding="utf-8")
            updated = re.sub(
                r'^(version\s*=\s*)"[^"]+"',
                rf'\1"{new_version}"',
                text, count=1, flags=re.MULTILINE,
            )
            if updated != text:
                pyproject.write_text(updated, encoding="utf-8")
                modified.append(str(pyproject))

        # Update forge/__init__.py
        init_py = self._project_dir / "forge" / "__init__.py"
        if init_py.exists():
            text = init_py.read_text(encoding="utf-8")
            updated = re.sub(
                r'^(__version__\s*=\s*)"[^"]+"',
                rf'\1"{new_version}"',
                text, count=1, flags=re.MULTILINE,
            )
            if updated != text:
                init_py.write_text(updated, encoding="utf-8")
                modified.append(str(init_py))

        return modified

    @staticmethod
    def bump_version(version: str, bump_type: str) -> str:
        """Compute next semantic version."""
        m = _SEMVER_RE.match(version)
        if not m:
            return version
        major, minor, patch = int(m.group("major")), int(m.group("minor")), int(m.group("patch"))
        if bump_type == "major":
            return f"{major + 1}.0.0"
        elif bump_type == "minor":
            return f"{major}.{minor + 1}.0"
        elif bump_type == "patch":
            return f"{major}.{minor}.{patch + 1}"
        return version

    # ── Git operations ──

    def _git(self, *args, check: bool = True) -> str:
        """Run a git command in the project directory."""
        result = subprocess.run(
            ["git"] + list(args),
            cwd=str(self._project_dir),
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"git {args[0]} failed: {result.stderr.strip()}")
        return result.stdout.strip()

    def get_unreleased_commits(self) -> list[ClassifiedCommit]:
        """Get commits since the last version tag."""
        current = self.get_current_version()
        tag = f"v{current}"

        # Check if tag exists
        try:
            self._git("rev-parse", tag, check=True)
            log_range = f"{tag}..HEAD"
        except RuntimeError:
            # No tag — get last 50 commits
            log_range = "-50"

        try:
            output = self._git(
                "log", log_range,
                "--format=%H|%s|%an|%ai",
                "--no-merges",
            )
        except RuntimeError:
            return []

        commits = []
        for line in output.strip().splitlines():
            if not line:
                continue
            parts = line.split("|", 3)
            if len(parts) < 4:
                continue
            sha, message, author, date = parts
            commits.append(ClassifiedCommit(
                sha=sha[:12], message=message,
                author=author, date=date[:10],
            ))
        return commits

    def classify_commits(self, commits: list[ClassifiedCommit]) -> list[ClassifiedCommit]:
        """Classify commits using rule-based heuristics."""
        for commit in commits:
            commit.category, commit.bump_type = self._classify_message(commit.message)
            commit.classified_by = "rules"

            # If unknown and LLM available, try LLM classification
            if commit.category == "unknown" and self._llm:
                llm_cat, llm_bump = self._llm_classify(commit.message)
                if llm_cat != "unknown":
                    commit.category = llm_cat
                    commit.bump_type = llm_bump
                    commit.classified_by = "llm"

        return commits

    @staticmethod
    def _classify_message(message: str) -> tuple[str, str]:
        """Rule-based commit classification."""
        for pattern, category, bump in _COMMIT_RULES:
            if pattern.search(message):
                return category, bump
        return "unknown", "patch"  # Default to patch for unclassified

    def _llm_classify(self, message: str) -> tuple[str, str]:
        """LLM-based commit classification for ambiguous messages."""
        if not self._llm:
            return "unknown", "patch"
        try:
            prompt = (
                f"Classify this git commit message into ONE category:\n"
                f"  breaking, feature, fix, refactor, docs, test, chore, "
                f"ci, security, perf\n\n"
                f"Commit: {message}\n\n"
                f"Reply with just the category name, nothing else."
            )
            response = ""
            for chunk in self._llm.chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            ):
                if chunk.get("type") == "token" and chunk.get("content"):
                    response += chunk["content"]

            category = response.strip().lower().split()[0] if response.strip() else "unknown"
            bump_map = {
                "breaking": "major", "feature": "minor", "fix": "patch",
                "refactor": "patch", "security": "patch", "perf": "patch",
                "docs": "none", "test": "none", "chore": "none", "ci": "none",
            }
            bump = bump_map.get(category, "patch")
            return category, bump
        except Exception as ex:
            log.debug("LLM classification failed: %s", ex)
            return "unknown", "patch"

    def compute_next_version(self, commits: list[ClassifiedCommit]) -> tuple[str, str]:
        """Determine the next version based on classified commits.

        Returns (next_version, bump_type).
        """
        current = self.get_current_version()
        if not commits:
            return current, "none"

        # Highest bump wins
        bump_priority = {"major": 3, "minor": 2, "patch": 1, "none": 0}
        max_bump = "none"
        for c in commits:
            if bump_priority.get(c.bump_type, 0) > bump_priority.get(max_bump, 0):
                max_bump = c.bump_type

        if max_bump == "none":
            return current, "none"

        return self.bump_version(current, max_bump), max_bump

    # ── Changelog generation ──

    def generate_changelog(self, commits: list[ClassifiedCommit],
                           new_version: str) -> str:
        """Generate markdown changelog from classified commits."""
        from datetime import date
        lines = [f"## [{new_version}] - {date.today().isoformat()}\n"]

        # Group by category
        categories = {}
        for c in commits:
            categories.setdefault(c.category, []).append(c)

        # Ordered sections
        section_order = [
            ("breaking", "Breaking Changes"),
            ("feature", "Features"),
            ("fix", "Bug Fixes"),
            ("security", "Security"),
            ("perf", "Performance"),
            ("refactor", "Refactoring"),
            ("docs", "Documentation"),
            ("test", "Tests"),
            ("chore", "Chores"),
            ("ci", "CI/CD"),
            ("unknown", "Other"),
        ]

        for cat_key, cat_label in section_order:
            cat_commits = categories.get(cat_key, [])
            if not cat_commits:
                continue
            lines.append(f"\n### {cat_label}\n")
            for c in cat_commits:
                lines.append(f"- {c.message} ({c.sha})")

        return "\n".join(lines)

    # ── Preflight checks ──

    def run_preflight(self) -> list[tuple[str, bool, str]]:
        """Run preflight checks before release.

        Returns list of (check_name, passed, message).
        """
        results = []

        # Check clean working tree
        status = self._git("status", "--porcelain", check=False)
        clean = not status.strip()
        results.append((
            "Clean working tree",
            clean,
            "OK" if clean else f"{len(status.splitlines())} uncommitted changes",
        ))

        # Check on main/master branch
        branch = self._git("branch", "--show-current", check=False)
        on_main = branch in ("main", "master")
        results.append((
            "On main/master branch",
            on_main,
            f"On '{branch}'" if not on_main else "OK",
        ))

        # Check version consistency
        pyproject_ver = self.get_current_version()
        init_path = self._project_dir / "forge" / "__init__.py"
        init_ver = "unknown"
        if init_path.exists():
            text = init_path.read_text(encoding="utf-8")
            m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
            if m:
                init_ver = m.group(1)
        consistent = pyproject_ver == init_ver
        results.append((
            "Version consistency",
            consistent,
            f"OK ({pyproject_ver})" if consistent
            else f"pyproject.toml={pyproject_ver}, __init__.py={init_ver}",
        ))

        # Run tests
        try:
            test_result = subprocess.run(
                ["python", "-m", "pytest", "--tb=no", "-q"],
                cwd=str(self._project_dir),
                capture_output=True, text=True, timeout=300,
            )
            passed = test_result.returncode == 0
            # Extract summary line
            summary = test_result.stdout.strip().splitlines()[-1] if test_result.stdout.strip() else "No output"
            results.append(("Tests pass", passed, summary))
        except (subprocess.TimeoutExpired, FileNotFoundError) as ex:
            results.append(("Tests pass", False, str(ex)))

        return results

    # ── Release execution ──

    def release(self, dry_run: bool = False) -> dict:
        """Execute a release.

        Returns release summary dict.
        """
        current = self.get_current_version()
        commits = self.get_unreleased_commits()
        commits = self.classify_commits(commits)
        next_ver, bump_type = self.compute_next_version(commits)

        if bump_type == "none":
            return {"status": "no_release", "reason": "No version-bumping commits found"}

        changelog = self.generate_changelog(commits, next_ver)

        if dry_run:
            return {
                "status": "dry_run",
                "current": current,
                "next": next_ver,
                "bump": bump_type,
                "commits": len(commits),
                "changelog": changelog,
            }

        # Execute release
        modified = self.set_version(next_ver)
        if modified:
            self._git("add", *[os.path.relpath(f, self._project_dir) for f in modified])
            self._git("commit", "-m", f"chore: bump version to {next_ver}")

        tag = f"v{next_ver}"
        self._git("tag", "-a", tag, "-m", f"Release {next_ver}\n\n{changelog}")

        # Save release info
        release = ReleaseInfo(
            version=next_ver,
            previous_version=current,
            timestamp=time.time(),
            commits=[asdict(c) for c in commits],
            changelog=changelog,
            tag=tag,
        )
        self._history.append(release)
        self._save_history()

        return {
            "status": "released",
            "current": current,
            "next": next_ver,
            "bump": bump_type,
            "tag": tag,
            "commits": len(commits),
            "changelog": changelog,
            "files_modified": modified,
        }

    # ── Status display ──

    def format_status(self) -> str:
        """Format current release status for terminal display."""
        current = self.get_current_version()
        commits = self.get_unreleased_commits()
        commits = self.classify_commits(commits)
        next_ver, bump_type = self.compute_next_version(commits)

        lines = [f"Shipwright Release Status"]
        lines.append(f"  Current version:  {current}")
        lines.append(f"  Unreleased commits: {len(commits)}")

        if commits:
            lines.append(f"  Suggested bump:   {bump_type} -> {next_ver}")
            lines.append("")

            # Category counts
            cats = {}
            for c in commits:
                cats[c.category] = cats.get(c.category, 0) + 1
            for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
                lines.append(f"    {cat}: {count}")

            lines.append("")
            lines.append("  Recent commits:")
            for c in commits[:10]:
                indicator = {"major": "!!", "minor": "+", "patch": "~", "none": " "}
                bump_char = indicator.get(c.bump_type, "?")
                lines.append(f"    [{bump_char}] {c.sha} {c.message[:60]}")
            if len(commits) > 10:
                lines.append(f"    ... and {len(commits) - 10} more")
        else:
            lines.append("  No unreleased commits.")

        return "\n".join(lines)

    # ── History persistence ──

    def _load_history(self):
        if not self._history_path.exists():
            return
        try:
            data = json.loads(self._history_path.read_text(encoding="utf-8"))
            for entry in data.get("releases", []):
                self._history.append(ReleaseInfo(
                    version=entry.get("version", ""),
                    previous_version=entry.get("previous_version", ""),
                    timestamp=entry.get("timestamp", 0),
                    commits=entry.get("commits", []),
                    changelog=entry.get("changelog", ""),
                    tag=entry.get("tag", ""),
                ))
        except Exception as ex:
            log.debug("Failed to load release history: %s", ex)

    def _save_history(self):
        data = {
            "version": 1,
            "releases": [asdict(r) for r in self._history[-50:]],
        }
        fd, tmp = tempfile.mkstemp(dir=str(self._data_dir), suffix=".tmp")
        try:
            os.write(fd, json.dumps(data, indent=2).encode("utf-8"))
            os.close(fd)
            os.replace(tmp, str(self._history_path))
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def format_history(self, count: int = 5) -> str:
        """Format release history for display."""
        if not self._history:
            return "No releases recorded yet."
        lines = ["Release History"]
        from datetime import datetime
        for r in reversed(self._history[-count:]):
            ts = datetime.fromtimestamp(r.timestamp).strftime("%Y-%m-%d %H:%M")
            lines.append(f"  {r.tag:12} {ts}  ({len(r.commits)} commits)")
        return "\n".join(lines)

    def to_audit_dict(self) -> dict:
        """Return audit-friendly snapshot."""
        return {
            "schema_version": 1,
            "current_version": self.get_current_version(),
            "release_count": len(self._history),
            "last_release": asdict(self._history[-1]) if self._history else None,
        }
