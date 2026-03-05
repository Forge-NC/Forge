"""AutoForge — Smart auto-commit via Claude Code hooks.

Tracks file edits within a session, batches them into coherent commits,
and optionally pushes on session end. Designed to work both as a
standalone module (called from engine.py) and as a Claude Code hook
script (.claude/hooks/auto_commit.py).

Two modes:
  - **Stage mode**: After each file edit, stage the file (git add)
  - **Commit mode**: After each user turn or session end, commit staged
    changes with an auto-generated message

Smart batching: N file edits in one turn = 1 commit, not N commits.
"""

import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class PendingEdit:
    """A file edit waiting to be committed."""
    path: str
    action: str  # "create", "edit", "delete"
    timestamp: float = 0.0
    tool_name: str = ""


@dataclass
class AutoCommit:
    """Record of an auto-commit."""
    sha: str
    message: str
    files: list[str]
    timestamp: float
    turn: int


class AutoForge:
    """Smart auto-commit manager."""

    def __init__(self, project_dir: str = None, config_get=None,
                 git_env: dict = None):
        self._project_dir = Path(project_dir or os.getcwd())
        self._config_get = config_get or (lambda k, d=None: d)
        self._git_env = git_env  # Optional env override for git subprocess
        self._pending: list[PendingEdit] = []
        self._commits: list[AutoCommit] = []
        self._turn = 0
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled and self._is_git_repo()

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    def _is_git_repo(self) -> bool:
        """Check if project dir is inside a git repo."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=str(self._project_dir),
                capture_output=True, text=True, timeout=5,
                env=self._git_env,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _git(self, *args, check: bool = True) -> str:
        """Run git command."""
        result = subprocess.run(
            ["git"] + list(args),
            cwd=str(self._project_dir),
            capture_output=True, text=True, timeout=30,
            env=self._git_env or {**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if check and result.returncode != 0:
            raise RuntimeError(f"git {args[0]} failed: {result.stderr.strip()}")
        return result.stdout.strip()

    # ── Tracking ──

    def record_edit(self, file_path: str, action: str = "edit",
                    tool_name: str = ""):
        """Record a file edit for future commit."""
        if not self.enabled:
            return
        self._pending.append(PendingEdit(
            path=file_path, action=action,
            timestamp=time.time(), tool_name=tool_name,
        ))

    def advance_turn(self, turn: int):
        """Called when user input is received. Commits pending edits."""
        self._turn = turn
        if not self.enabled or not self._pending:
            return None
        return self.commit_pending()

    def on_session_end(self):
        """Called at session exit. Commits any remaining edits."""
        if not self.enabled or not self._pending:
            return None
        return self.commit_pending(session_end=True)

    # ── Committing ──

    def commit_pending(self, session_end: bool = False) -> Optional[AutoCommit]:
        """Stage and commit all pending file edits as a single commit."""
        if not self._pending:
            return None

        # Collect unique file paths
        files = []
        seen = set()
        actions = set()
        for edit in self._pending:
            if edit.path not in seen:
                files.append(edit.path)
                seen.add(edit.path)
            actions.add(edit.action)

        # Stage files
        staged = []
        for f in files:
            rel = os.path.relpath(f, self._project_dir)
            try:
                if os.path.exists(f):
                    self._git("add", rel)
                    staged.append(rel)
                else:
                    # File was deleted
                    self._git("add", rel, check=False)
                    staged.append(rel)
            except RuntimeError as ex:
                log.debug("Failed to stage %s: %s", rel, ex)

        if not staged:
            self._pending.clear()
            return None

        # Generate commit message
        message = self._generate_message(staged, actions, session_end)

        # Commit
        try:
            self._git("commit", "-m", message)
            sha = self._git("rev-parse", "--short", "HEAD")
        except RuntimeError as ex:
            log.debug("Auto-commit failed: %s", ex)
            self._pending.clear()
            return None

        commit = AutoCommit(
            sha=sha, message=message,
            files=staged, timestamp=time.time(),
            turn=self._turn,
        )
        self._commits.append(commit)
        self._pending.clear()
        return commit

    def _generate_message(self, files: list[str], actions: set[str],
                          session_end: bool = False) -> str:
        """Generate a descriptive commit message from staged files."""
        # Determine primary action
        if "create" in actions and len(actions) == 1:
            verb = "add"
        elif "delete" in actions and len(actions) == 1:
            verb = "remove"
        else:
            verb = "update"

        # Group files by directory
        dirs = set()
        extensions = set()
        for f in files:
            p = Path(f)
            if p.parent != Path("."):
                dirs.add(str(p.parent))
            if p.suffix:
                extensions.add(p.suffix)

        if len(files) == 1:
            subject = f"forge: {verb} {files[0]}"
        elif len(dirs) == 1:
            subject = f"forge: {verb} {len(files)} files in {next(iter(dirs))}"
        else:
            subject = f"forge: {verb} {len(files)} files across {len(dirs)} directories"

        if session_end:
            subject += " (session end)"

        # Truncate to 72 chars
        if len(subject) > 72:
            subject = subject[:69] + "..."

        return subject

    # ── Status ──

    def format_status(self) -> str:
        """Format current auto-commit status."""
        lines = [f"AutoForge: {'enabled' if self.enabled else 'disabled'}"]
        if self._pending:
            lines.append(f"  Pending edits: {len(self._pending)}")
            for edit in self._pending[-5:]:
                lines.append(f"    {edit.action}: {Path(edit.path).name}")
        if self._commits:
            lines.append(f"  Session commits: {len(self._commits)}")
            for c in self._commits[-3:]:
                lines.append(f"    [{c.sha}] {c.message[:50]}")
        return "\n".join(lines)

    def to_audit_dict(self) -> dict:
        """Return audit-friendly snapshot."""
        return {
            "schema_version": 1,
            "enabled": self.enabled,
            "pending_count": len(self._pending),
            "session_commits": [asdict(c) for c in self._commits],
        }


def generate_hook_script(project_dir: str) -> str:
    """Generate the .claude/hooks/auto_commit.py script content.

    This script is designed to be called by Claude Code's hook system:
      - PostToolUse: stage edited files
      - UserPromptSubmit: commit staged changes
      - SessionEnd: commit remaining changes
    """
    return f'''#!/usr/bin/env python3
"""AutoForge hook for Claude Code.

Place in .claude/hooks/auto_commit.py and register in .claude/settings.json:
  {{
    "hooks": {{
      "PostToolUse": ["python .claude/hooks/auto_commit.py stage"],
      "UserPromptSubmit": ["python .claude/hooks/auto_commit.py commit"],
      "SessionEnd": ["python .claude/hooks/auto_commit.py commit --final"]
    }}
  }}
"""
import json
import os
import subprocess
import sys

PROJECT_DIR = r"{project_dir}"


def git(*args):
    result = subprocess.run(
        ["git"] + list(args), cwd=PROJECT_DIR,
        capture_output=True, text=True, timeout=10,
    )
    return result.returncode == 0, result.stdout.strip()


def stage():
    """Stage any modified tracked files."""
    ok, status = git("diff", "--name-only")
    if ok and status:
        for f in status.splitlines():
            git("add", f.strip())


def commit(final=False):
    """Commit staged changes."""
    ok, staged = git("diff", "--cached", "--name-only")
    if not ok or not staged:
        return
    files = [f.strip() for f in staged.splitlines() if f.strip()]
    if not files:
        return
    n = len(files)
    msg = f"forge: update {{n}} file{{'s' if n > 1 else ''}}"
    if final:
        msg += " (session end)"
    git("commit", "-m", msg)


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "stage"
    if action == "stage":
        stage()
    elif action == "commit":
        commit(final="--final" in sys.argv)
'''
