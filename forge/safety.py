"""Safety guard — tiered shell command protection.

Four levels, configured once, never nags:
  0  unleashed     — Everything runs. No questions. Full trust.
  1  smart_guard   — Shell commands checked against a blocklist of
                     known-dangerous patterns (curl|bash, rm -rf /,
                     powershell -enc, etc). Normal dev commands fly
                     through untouched. DEFAULT.
  2  confirm_writes— File writes/edits show a 1-line summary and
                     auto-accept after 3s unless user hits 'n'.
                     Shell commands use the blocklist.
  3  locked_down   — Every tool call requires explicit approval.

Optional path sandboxing restricts file operations to the working
directory + any explicitly allowed paths.

All settings live in ~/.forge/config.yaml and can be changed at
runtime via /safety.
"""

import os
import re
import sys
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ── Safety levels ──

UNLEASHED = 0
SMART_GUARD = 1
CONFIRM_WRITES = 2
LOCKED_DOWN = 3

LEVEL_NAMES = {
    0: "unleashed",
    1: "smart_guard",
    2: "confirm_writes",
    3: "locked_down",
}

NAME_TO_LEVEL = {v: k for k, v in LEVEL_NAMES.items()}


# ── Shell blocklist — catches prompt-injection attacks ──
# These patterns match commands that have no legitimate use in a
# coding assistant context.  Normal dev commands (git, pip, python,
# npm, cargo, make, etc.) pass through freely.

SHELL_BLOCKLIST = [
    # Remote code execution / exfiltration
    r"curl\s.*\|\s*(ba)?sh",          # curl ... | bash
    r"wget\s.*\|\s*(ba)?sh",          # wget ... | bash
    r"curl\s.*\|\s*sh\b",            # curl ... | sh
    r"wget\s.*\|\s*sh\b",            # wget ... | sh
    r"curl\s.*-o\s+/",               # curl download to root
    r"wget\s.*-O\s+/",               # wget download to root
    r"curl\s.*--output\s+/",         # curl download to root
    r"\b(?:powershell|pwsh)(?:\.exe)?\b.*-enc",  # powershell -EncodedCommand
    r"\b(?:powershell|pwsh)(?:\.exe)?\b.*-ec\b", # powershell -ec (abbrev)
    r"\b(?:powershell|pwsh)(?:\.exe)?\b.*-e\s",  # powershell -e (short)
    r"\b(?:powershell|pwsh)(?:\.exe)?\b.*downloadstring", # PS download
    r"\b(?:powershell|pwsh)(?:\.exe)?\b.*webclient",     # PS webclient
    r"\biex\b.*\bnet\.webclient\b",   # IEX download cradle
    r"\bInvoke-Expression\b",         # PowerShell IEX full name
    r"\bInvoke-WebRequest\b.*\|\s*iex", # Download and execute
    r"\bpython[23]?\b\s+-c\s+.*(?:subprocess|os\.system|os\.popen)", # python -c
    r"\bperl\b\s+-e\s+.*(?:system|exec)\b",  # perl -e system()
    r"\bnode\b\s+-e\s+.*(?:child_process|exec)\b",  # node -e exec

    # Windows LOLBins (Living Off the Land Binaries)
    r"\bcertutil\b.*-urlcache",       # certutil download
    r"\bbitsadmin\b.*/transfer",      # bitsadmin download
    r"\bmshta\b\s+(?:http|vbscript)",  # mshta execution

    # Destructive filesystem operations
    r"\brm\s+-rf\s+/",               # rm -rf / (root) — no $ anchor
    r"\brm\s+-rf\s+~",               # rm -rf ~ (home dir)
    r"\brm\s+-rf\s+\$HOME",          # rm -rf $HOME
    r"\brm\s+-rf\s+%USERPROFILE%",   # rm -rf %USERPROFILE%
    r"del\s+/[sfq]\s+[A-Z]:\\",      # del /s /f C:\
    r"rd\s+/s\s+/q\s+[A-Z]:\\",      # rd /s /q C:\
    r"format\s+[A-Z]:",              # format C:

    # Registry / system modification
    r"\breg\s+(add|delete)\b.*\\HKLM\\", # registry modification
    r"\breg\s+(add|delete)\b.*\\HKEY_LOCAL_MACHINE\\",
    r"\bnet\s+user\b",               # user account manipulation
    r"\bnet\s+localgroup\b",         # group manipulation
    r"\bnetsh\b.*firewall",          # firewall manipulation
    r"\bschtasks\b.*/create",        # scheduled task creation
    r"\bcrontab\b.*-r",              # crontab removal

    # Crypto miners / reverse shells
    r"\bnc\s+-[le]",                  # netcat listener
    r"\bncat\b.*-[le]",              # ncat listener
    r"/dev/tcp/",                     # bash reverse shell
    r"\bxmrig\b",                     # crypto miner
    r"\bminerd\b",                    # crypto miner
    r"\bcoinminer\b",                # crypto miner

    # Privilege escalation
    r"\bchmod\s+[0-7]*777\s+/",     # chmod 777 on system dirs
    r"\bchmod\s+u\+s\b",            # setuid bit
    r"\bsudo\s+chmod\b.*777",        # sudo chmod 777

    # SSH / credential theft
    r"cat\s+.*\.ssh/",               # reading SSH keys
    r"cat\s+.*/etc/shadow",          # reading shadow file
    r"cat\s+.*/etc/passwd",          # reading passwd
    r"\bscp\b.*\.ssh/",              # exfiltrating SSH keys
    r"\bbase64\b.*\.ssh/",           # encoding SSH keys
]

# Compile once
_BLOCKLIST_RE = [re.compile(p, re.IGNORECASE) for p in SHELL_BLOCKLIST]


def check_shell_command(command: str) -> Optional[str]:
    """Check a shell command against the blocklist.

    Returns None if the command is safe, or a reason string if blocked.
    """
    for i, pattern in enumerate(_BLOCKLIST_RE):
        if pattern.search(command):
            return f"Blocked by safety rule: {SHELL_BLOCKLIST[i]}"
    return None


def check_path_sandbox(file_path: str, allowed_roots: list[str]) -> Optional[str]:
    """Check if a file path is within allowed directories.

    Returns None if allowed, or a reason string if blocked.
    Only active when sandbox is enabled in config.
    """
    if not allowed_roots:
        return None  # No sandbox — everything allowed

    resolved = Path(file_path).resolve()
    resolved_str = str(resolved)

    # Check for symlinks that escape the sandbox
    try:
        for parent in resolved.parents:
            if parent.is_symlink():
                return (f"Path '{file_path}' contains a symlink at {parent} "
                        f"that may escape the sandbox.")
    except (OSError, ValueError):
        pass

    for root in allowed_roots:
        root_resolved = str(Path(root).resolve())
        # Ensure path separator to prevent /project matching /project_evil
        if (resolved_str == root_resolved
                or resolved_str.startswith(root_resolved + os.sep)):
            return None

    return (f"Path '{file_path}' is outside the sandbox. "
            f"Allowed: {', '.join(allowed_roots)}")


def prompt_user_confirm(action_desc: str, timeout: float = 3.0) -> bool:
    """Show a brief confirmation prompt that auto-accepts after timeout.

    Used at CONFIRM_WRITES level for file modifications.
    Returns True to proceed, False to skip.
    """
    from forge.ui.terminal import YELLOW, DIM, RESET, BOLD

    sys.stdout.write(
        f"{YELLOW}{BOLD}[CONFIRM]{RESET} {action_desc} "
        f"{DIM}(auto-accept in {timeout:.0f}s, 'n' to skip){RESET} ")
    sys.stdout.flush()

    # Platform-specific timeout input
    if sys.platform == "win32":
        import msvcrt
        import time
        end = time.time() + timeout
        while time.time() < end:
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                print()  # newline after input
                return ch.lower() != "n"
            time.sleep(0.05)
        print()  # newline after timeout
        return True  # auto-accept
    else:
        import select
        rlist, _, _ = select.select([sys.stdin], [], [], timeout)
        if rlist:
            ch = sys.stdin.readline().strip()
            return ch.lower() != "n"
        print()
        return True


class SafetyGuard:
    """Central safety manager. Configured once, checks tool calls."""

    def __init__(self, level: int = SMART_GUARD,
                 sandbox_enabled: bool = False,
                 sandbox_roots: list[str] = None):
        self.level = max(0, min(3, level))
        self.sandbox_enabled = sandbox_enabled
        self.sandbox_roots = sandbox_roots or []

    @property
    def level_name(self) -> str:
        return LEVEL_NAMES.get(self.level, "unknown")

    def set_level(self, level) -> str:
        """Set safety level. Accepts int or string name."""
        if isinstance(level, str):
            level = NAME_TO_LEVEL.get(level.lower(), -1)
        if level not in LEVEL_NAMES:
            return (f"Unknown level. Valid: "
                    f"{', '.join(f'{v} ({k})' for k, v in LEVEL_NAMES.items())}")
        self.level = level
        return f"Safety level set to: {self.level_name} ({self.level})"

    def check_shell(self, command: str) -> tuple[bool, str]:
        """Check if a shell command should be allowed.

        Returns (allowed: bool, reason: str).
        """
        if self.level == UNLEASHED:
            return True, ""

        if self.level == LOCKED_DOWN:
            from forge.ui.terminal import YELLOW, RESET, BOLD, DIM
            sys.stdout.write(
                f"\n{YELLOW}{BOLD}[APPROVE?]{RESET} run_shell: "
                f"{DIM}{command[:120]}{RESET}\n"
                f"  {YELLOW}y/n (default: y):{RESET} ")
            sys.stdout.flush()
            try:
                answer = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                return False, "User cancelled"
            if answer == "n":
                return False, "User denied"
            return True, ""

        # SMART_GUARD or CONFIRM_WRITES — use blocklist
        reason = check_shell_command(command)
        if reason:
            from forge.ui.terminal import RED, YELLOW, RESET, BOLD, DIM
            print(f"\n{RED}{BOLD}[BLOCKED]{RESET} {RED}{reason}{RESET}")
            print(f"  {DIM}Command: {command[:200]}{RESET}")
            print(f"  {YELLOW}Override? y/n (default: n):{RESET} ", end="")
            sys.stdout.flush()
            try:
                answer = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                return False, reason
            if answer == "y":
                return True, "User override"
            return False, reason

        return True, ""

    def check_file_write(self, file_path: str, action: str = "write") -> tuple[bool, str]:
        """Check if a file write/edit should be allowed.

        Returns (allowed: bool, reason: str).
        """
        # Sandbox check applies at all levels except unleashed
        if self.sandbox_enabled and self.level > UNLEASHED:
            reason = check_path_sandbox(file_path, self.sandbox_roots)
            if reason:
                return False, reason

        if self.level <= SMART_GUARD:
            return True, ""

        if self.level == CONFIRM_WRITES:
            fname = Path(file_path).name
            allowed = prompt_user_confirm(f"{action} → {fname}")
            if not allowed:
                return False, "User skipped"
            return True, ""

        if self.level == LOCKED_DOWN:
            from forge.ui.terminal import YELLOW, RESET, BOLD, DIM
            fname = Path(file_path).name
            sys.stdout.write(
                f"\n{YELLOW}{BOLD}[APPROVE?]{RESET} {action}_file: "
                f"{DIM}{fname}{RESET}\n"
                f"  {YELLOW}y/n (default: y):{RESET} ")
            sys.stdout.flush()
            try:
                answer = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                return False, "User cancelled"
            if answer == "n":
                return False, "User denied"
            return True, ""

        return True, ""

    def check_file_read(self, file_path: str) -> tuple[bool, str]:
        """Check if a file read should be allowed.

        Only blocks in locked_down mode or if sandboxed.
        """
        if self.sandbox_enabled and self.level > UNLEASHED:
            reason = check_path_sandbox(file_path, self.sandbox_roots)
            if reason:
                return False, reason

        if self.level == LOCKED_DOWN:
            from forge.ui.terminal import YELLOW, RESET, BOLD, DIM
            fname = Path(file_path).name
            sys.stdout.write(
                f"\n{YELLOW}{BOLD}[APPROVE?]{RESET} read_file: "
                f"{DIM}{fname}{RESET}\n"
                f"  {YELLOW}y/n (default: y):{RESET} ")
            sys.stdout.flush()
            try:
                answer = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                return False, "User cancelled"
            if answer == "n":
                return False, "User denied"
            return True, ""

        return True, ""

    def format_status(self) -> str:
        """Return a formatted status string."""
        from forge.ui.terminal import (
            BOLD, RESET, DIM, GREEN, YELLOW, RED, CYAN, WHITE
        )

        level_colors = {
            0: RED,       # unleashed = red (you're flying without a net)
            1: GREEN,     # smart_guard = green (safe default)
            2: YELLOW,    # confirm_writes = yellow (some friction)
            3: RED,       # locked_down = red (max friction)
        }
        color = level_colors.get(self.level, WHITE)

        lines = [
            f"\n{BOLD}Safety Configuration{RESET}",
            f"  Level: {color}{BOLD}{self.level_name}{RESET} "
            f"{DIM}({self.level}){RESET}",
            "",
        ]

        descs = {
            0: "Everything runs freely. No checks. Full trust mode.",
            1: "Shell commands checked against blocklist. "
               "Normal dev commands pass through. File ops unrestricted.",
            2: "File writes show brief confirmation (auto-accepts in 3s). "
               "Shell commands use blocklist.",
            3: "Every tool call requires explicit approval.",
        }
        lines.append(f"  {DIM}{descs[self.level]}{RESET}")
        lines.append("")

        # Sandbox status
        if self.sandbox_enabled:
            lines.append(f"  Sandbox: {YELLOW}ON{RESET}")
            for root in self.sandbox_roots:
                lines.append(f"    {DIM}+ {root}{RESET}")
        else:
            lines.append(f"  Sandbox: {DIM}OFF (file ops can reach any path){RESET}")

        lines.append("")
        lines.append(f"  {DIM}Change level: /safety <0-3 or name>{RESET}")
        lines.append(f"  {DIM}Toggle sandbox: /safety sandbox on|off{RESET}")
        lines.append(f"  {DIM}Add sandbox root: /safety allow <path>{RESET}")

        return "\n".join(lines)
