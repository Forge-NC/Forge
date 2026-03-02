"""Git tools -- version control operations for the AI agent.

Provides tools for inspecting and managing git repositories:
  git_status  -- working tree status
  git_diff    -- show changes (staged or unstaged)
  git_log     -- commit history
  git_branch  -- list/create/switch/delete branches
  git_commit  -- stage and commit changes
  git_stash   -- stash management
  git_blame   -- per-line attribution
  git_show    -- inspect a commit

Safety: Never runs destructive commands (push, reset --hard, clean -f).
All commands run with a 10-second timeout.
"""

import os
import subprocess
import logging
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DEFAULT_TIMEOUT = 10


def _run_git(args: list[str], cwd: str, timeout: int = _DEFAULT_TIMEOUT) -> str:
    """Run a git command and return combined stdout/stderr.

    Args:
        args: Command arguments (without the leading 'git').
        cwd: Working directory.
        timeout: Seconds before the command is killed.

    Returns:
        A formatted string with the command output.
    """
    cmd = ["git"] + args

    extra = {}
    if os.name == "nt":
        extra["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            **extra,
        )
    except FileNotFoundError:
        return "Error: git is not installed or not on PATH."
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s: git {' '.join(args)}"

    parts = []
    if result.stdout:
        parts.append(result.stdout.rstrip())
    if result.stderr:
        # Some git commands write normal output to stderr (e.g. branch -d)
        parts.append(result.stderr.rstrip())
    if result.returncode != 0 and not parts:
        parts.append(f"git exited with code {result.returncode}")

    output = "\n".join(parts) if parts else "(no output)"

    # Truncate very long output to protect context window
    if len(output) > 15000:
        output = output[:15000] + f"\n... (truncated, {len(output)} chars total)"

    return output


def is_git_repo(path: str) -> bool:
    """Check if *path* is inside a git repository."""
    extra = {}
    if os.name == "nt":
        extra["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=path,
            **extra,
        )
        return result.returncode == 0
    except Exception:
        return False


_NOT_GIT = "Not a git repository. Run `git init` first."


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def git_status(cwd: str) -> str:
    """Run ``git status`` and return formatted output."""
    if not is_git_repo(cwd):
        return _NOT_GIT
    return _run_git(["status"], cwd)


def git_diff(cwd: str, staged: bool = False, file_path: str = "",
             context_lines: int = 3) -> str:
    """Show working-tree or staged changes.

    Args:
        staged: If True, show staged (--cached) diff.
        file_path: Restrict diff to a single file.
        context_lines: Lines of context around each hunk (default 3).
    """
    if not is_git_repo(cwd):
        return _NOT_GIT

    args = ["diff"]
    if staged:
        args.append("--cached")
    args.append(f"-U{context_lines}")
    if file_path:
        args.extend(["--", file_path])

    return _run_git(args, cwd)


def git_log(cwd: str, count: int = 10, oneline: bool = False,
            file_path: str = "") -> str:
    """Show commit history.

    Args:
        count: Number of commits to show (default 10).
        oneline: Use compact one-line format.
        file_path: Show log for a specific file only.
    """
    if not is_git_repo(cwd):
        return _NOT_GIT

    args = ["log", f"-{count}"]
    if oneline:
        args.append("--oneline")
    else:
        args.append("--format=%h %ad %an%n  %s%n")
        args.append("--date=short")
    if file_path:
        args.extend(["--", file_path])

    return _run_git(args, cwd)


def git_branch(cwd: str, action: str = "list", name: str = "") -> str:
    """List, create, switch, or delete branches.

    Args:
        action: One of "list", "create", "switch", "delete".
        name: Branch name (required for create/switch/delete).
    """
    if not is_git_repo(cwd):
        return _NOT_GIT

    action = action.lower().strip()

    if action == "list":
        return _run_git(["branch", "-a"], cwd)

    if not name:
        return f"Error: branch name is required for action '{action}'."

    if action == "create":
        return _run_git(["branch", name], cwd)
    elif action == "switch":
        return _run_git(["switch", name], cwd)
    elif action == "delete":
        # Use -d (safe delete), not -D (force delete)
        return _run_git(["branch", "-d", name], cwd)
    else:
        return f"Error: unknown branch action '{action}'. Use list/create/switch/delete."


def git_commit(cwd: str, message: str, files: list[str] | None = None,
               amend: bool = False) -> str:
    """Stage files and create a commit.

    Args:
        message: Commit message (required).
        files: Specific files to stage. If omitted, stages all modified/new files.
        amend: If True, amend the previous commit.
    """
    if not is_git_repo(cwd):
        return _NOT_GIT

    if not message and not amend:
        return "Error: commit message is required."

    # Stage files
    if files:
        stage_result = _run_git(["add", "--"] + files, cwd)
    else:
        stage_result = _run_git(["add", "-A"], cwd)

    if stage_result.startswith("Error:"):
        return f"Staging failed: {stage_result}"

    # Commit
    args = ["commit", "-m", message]
    if amend:
        args.append("--amend")

    result = _run_git(args, cwd)

    # If staging produced output worth showing, prepend it
    if stage_result and stage_result != "(no output)":
        return f"[stage] {stage_result}\n[commit] {result}"
    return result


def git_stash(cwd: str, action: str = "push", message: str = "") -> str:
    """Manage the stash.

    Args:
        action: One of "push", "pop", "list", "drop".
        message: Optional message for push.
    """
    if not is_git_repo(cwd):
        return _NOT_GIT

    action = action.lower().strip()

    if action == "push":
        args = ["stash", "push"]
        if message:
            args.extend(["-m", message])
        return _run_git(args, cwd)
    elif action == "pop":
        return _run_git(["stash", "pop"], cwd)
    elif action == "list":
        return _run_git(["stash", "list"], cwd)
    elif action == "drop":
        return _run_git(["stash", "drop"], cwd)
    else:
        return f"Error: unknown stash action '{action}'. Use push/pop/list/drop."


def git_blame(cwd: str, file_path: str,
              line_start: int = 0, line_end: int = 0) -> str:
    """Show per-line blame annotation for a file.

    Args:
        file_path: Path to the file (required).
        line_start: First line to blame (1-based, optional).
        line_end: Last line to blame (inclusive, optional).
    """
    if not is_git_repo(cwd):
        return _NOT_GIT

    if not file_path:
        return "Error: file_path is required for git_blame."

    args = ["blame"]
    if line_start > 0 and line_end > 0:
        args.extend(["-L", f"{line_start},{line_end}"])
    elif line_start > 0:
        args.extend(["-L", f"{line_start},"])
    args.append("--")
    args.append(file_path)

    return _run_git(args, cwd)


def git_show(cwd: str, ref: str = "HEAD") -> str:
    """Show the details of a commit.

    Args:
        ref: Commit reference (hash, tag, branch). Default: HEAD.
    """
    if not is_git_repo(cwd):
        return _NOT_GIT

    return _run_git(["show", "--stat", "--format=fuller", ref], cwd)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_git_tools(registry, cwd: str):
    """Register all git tools into the ToolRegistry.

    Args:
        registry: A ToolRegistry instance.
        cwd: The working directory for all git commands.
    """

    registry.register(
        "git_status",
        lambda: git_status(cwd),
        "Show the working tree status: modified, staged, and untracked files.",
        {
            "type": "object",
            "properties": {},
        },
    )

    registry.register(
        "git_diff",
        lambda staged=False, file_path="", context_lines=3: git_diff(
            cwd, staged=staged, file_path=file_path,
            context_lines=context_lines),
        "Show file changes. By default shows unstaged changes. "
        "Use staged=true to see what will be committed. "
        "Optionally restrict to a single file.",
        {
            "type": "object",
            "properties": {
                "staged": {
                    "type": "boolean",
                    "description": "Show staged (--cached) changes instead of unstaged",
                    "default": False,
                },
                "file_path": {
                    "type": "string",
                    "description": "Diff only this file",
                },
                "context_lines": {
                    "type": "integer",
                    "description": "Lines of context around each change (default 3)",
                    "default": 3,
                },
            },
        },
    )

    registry.register(
        "git_log",
        lambda count=10, oneline=False, file_path="": git_log(
            cwd, count=count, oneline=oneline, file_path=file_path),
        "Show commit history. Returns recent commits with hash, date, "
        "author, and message. Use oneline=true for a compact view.",
        {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "Number of commits to show",
                    "default": 10,
                },
                "oneline": {
                    "type": "boolean",
                    "description": "Compact one-line format",
                    "default": False,
                },
                "file_path": {
                    "type": "string",
                    "description": "Show log for this file only",
                },
            },
        },
    )

    registry.register(
        "git_branch",
        lambda action="list", name="": git_branch(cwd, action=action, name=name),
        "Manage branches. Actions: 'list' (show all branches), "
        "'create' (new branch), 'switch' (checkout branch), "
        "'delete' (safe delete).",
        {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Branch action: list, create, switch, or delete",
                    "enum": ["list", "create", "switch", "delete"],
                    "default": "list",
                },
                "name": {
                    "type": "string",
                    "description": "Branch name (required for create/switch/delete)",
                },
            },
        },
    )

    registry.register(
        "git_commit",
        lambda message, files=None, amend=False: git_commit(
            cwd, message=message, files=files, amend=amend),
        "Stage files and create a git commit. If no files are specified, "
        "stages all modified and new files. Use amend=true to amend the "
        "last commit.",
        {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Commit message",
                },
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific files to stage (default: all modified)",
                },
                "amend": {
                    "type": "boolean",
                    "description": "Amend the previous commit",
                    "default": False,
                },
            },
            "required": ["message"],
        },
    )

    registry.register(
        "git_stash",
        lambda action="push", message="": git_stash(
            cwd, action=action, message=message),
        "Manage the git stash. Actions: 'push' (save changes), "
        "'pop' (restore last stash), 'list' (show all stashes), "
        "'drop' (discard last stash).",
        {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Stash action: push, pop, list, or drop",
                    "enum": ["push", "pop", "list", "drop"],
                    "default": "push",
                },
                "message": {
                    "type": "string",
                    "description": "Stash message (only for push)",
                },
            },
        },
    )

    registry.register(
        "git_blame",
        lambda file_path, line_start=0, line_end=0: git_blame(
            cwd, file_path=file_path, line_start=line_start,
            line_end=line_end),
        "Show per-line blame annotation for a file, revealing who last "
        "modified each line and when. Optionally restrict to a line range.",
        {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to blame",
                },
                "line_start": {
                    "type": "integer",
                    "description": "First line to show (1-based)",
                },
                "line_end": {
                    "type": "integer",
                    "description": "Last line to show (inclusive)",
                },
            },
            "required": ["file_path"],
        },
    )

    registry.register(
        "git_show",
        lambda ref="HEAD": git_show(cwd, ref=ref),
        "Show details of a specific commit: author, date, message, and "
        "a summary of changed files. Defaults to HEAD.",
        {
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "Commit reference (hash, tag, or branch name)",
                    "default": "HEAD",
                },
            },
        },
    )
