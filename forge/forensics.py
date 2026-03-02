"""Session Forensics — compliance-ready audit trail.

Tracks every action during a Forge session:
  - File reads, writes, edits (with before/after sizes)
  - Tool calls with arguments and results
  - Crucible threat events
  - Context swaps and evictions
  - Shell commands executed
  - Timeline with timestamps

Generates a markdown forensics report on session end.
Reports are saved to ~/.forge/forensics/ with session IDs.

No other local AI coding tool provides this level of
session audit capability.
"""

import os
import time
import json
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from datetime import datetime

log = logging.getLogger(__name__)


@dataclass
class ForensicEvent:
    """A single auditable event."""
    timestamp: float
    category: str          # file_read, file_write, file_edit, shell, tool,
                           # threat, context_swap, eviction, error
    action: str            # human-readable description
    details: dict = field(default_factory=dict)
    risk_level: int = 0    # 0=normal, 1=notable, 2=warning, 3=critical


class SessionForensics:
    """Tracks and reports on all session activity."""

    def __init__(self, persist_dir: Path = None):
        self._persist_dir = persist_dir or (Path.home() / ".forge" / "forensics")
        self._persist_dir.mkdir(parents=True, exist_ok=True)

        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._session_start = time.time()
        self._events: list[ForensicEvent] = []

        # Aggregated stats
        self._files_read: dict[str, int] = {}      # path -> read count
        self._files_written: dict[str, int] = {}    # path -> write count
        self._files_edited: dict[str, int] = {}     # path -> edit count
        self._files_created: list[str] = []
        self._shell_commands: list[dict] = []
        self._tool_calls: dict[str, int] = {}       # tool_name -> count
        self._threats: list[dict] = []
        self._context_swaps: int = 0
        self._total_tokens_in: int = 0
        self._total_tokens_out: int = 0
        self._turns: int = 0

    _MAX_EVENTS = 5000
    _MAX_SHELL_COMMANDS = 500

    def record(self, category: str, action: str,
               details: dict = None, risk_level: int = 0):
        """Record a forensic event."""
        event = ForensicEvent(
            timestamp=time.time(),
            category=category,
            action=action,
            details=details or {},
            risk_level=risk_level,
        )
        self._events.append(event)
        # Cap events to prevent unbounded memory growth
        if len(self._events) > self._MAX_EVENTS:
            self._events = self._events[-self._MAX_EVENTS:]

        # Update aggregates
        path = (details or {}).get("path", "")

        if category == "file_read" and path:
            self._files_read[path] = self._files_read.get(path, 0) + 1

        elif category == "file_write" and path:
            self._files_written[path] = self._files_written.get(path, 0) + 1
            if (details or {}).get("created"):
                self._files_created.append(path)

        elif category == "file_edit" and path:
            self._files_edited[path] = self._files_edited.get(path, 0) + 1

        elif category == "shell":
            self._shell_commands.append({
                "command": (details or {}).get("command", ""),
                "exit_code": (details or {}).get("exit_code"),
                "time": event.timestamp,
            })
            if len(self._shell_commands) > self._MAX_SHELL_COMMANDS:
                self._shell_commands = self._shell_commands[-self._MAX_SHELL_COMMANDS:]

        elif category == "tool":
            name = (details or {}).get("name", "unknown")
            self._tool_calls[name] = self._tool_calls.get(name, 0) + 1

        elif category == "threat":
            self._threats.append(details or {})

        elif category == "context_swap":
            self._context_swaps += 1

    def record_turn(self, tokens_in: int, tokens_out: int):
        """Record turn-level token usage."""
        self._turns += 1
        self._total_tokens_in += tokens_in
        self._total_tokens_out += tokens_out

    def generate_report(self) -> str:
        """Generate the full forensics markdown report."""
        duration = time.time() - self._session_start
        duration_min = duration / 60

        lines = []
        lines.append(f"# Forge Session Forensics Report")
        lines.append(f"")
        lines.append(f"**Session ID:** {self._session_id}")
        lines.append(f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**Duration:** {duration_min:.1f} minutes")
        lines.append(f"**Turns:** {self._turns}")
        lines.append(f"**Tokens:** {self._total_tokens_in:,} in / "
                     f"{self._total_tokens_out:,} out")
        lines.append(f"")

        # Risk summary
        risk_events = [e for e in self._events if e.risk_level >= 2]
        if risk_events:
            lines.append(f"## Risk Events ({len(risk_events)})")
            lines.append(f"")
            for e in risk_events:
                ts = datetime.fromtimestamp(e.timestamp).strftime("%H:%M:%S")
                risk_tag = "WARNING" if e.risk_level == 2 else "CRITICAL"
                lines.append(f"- **[{risk_tag}]** {ts} — {e.action}")
            lines.append(f"")
        else:
            lines.append(f"## Risk Events")
            lines.append(f"")
            lines.append(f"No risk events detected. Session was clean.")
            lines.append(f"")

        # Crucible threats
        if self._threats:
            lines.append(f"## Crucible Threats ({len(self._threats)})")
            lines.append(f"")
            for t in self._threats:
                level = t.get("level", "UNKNOWN")
                desc = t.get("description", "")
                fpath = t.get("file", "")
                lines.append(f"- **{level}** in `{fpath}`: {desc}")
            lines.append(f"")

        # Files touched
        all_files = set(list(self._files_read.keys()) +
                       list(self._files_written.keys()) +
                       list(self._files_edited.keys()))
        if all_files:
            lines.append(f"## Files Touched ({len(all_files)})")
            lines.append(f"")
            lines.append(f"| File | Reads | Writes | Edits |")
            lines.append(f"|------|-------|--------|-------|")
            for fp in sorted(all_files):
                fname = Path(fp).name
                r = self._files_read.get(fp, 0)
                w = self._files_written.get(fp, 0)
                e = self._files_edited.get(fp, 0)
                lines.append(f"| `{fname}` | {r} | {w} | {e} |")
            lines.append(f"")

        if self._files_created:
            lines.append(f"### Files Created ({len(self._files_created)})")
            lines.append(f"")
            for fp in self._files_created:
                lines.append(f"- `{fp}`")
            lines.append(f"")

        # Shell commands
        if self._shell_commands:
            lines.append(f"## Shell Commands ({len(self._shell_commands)})")
            lines.append(f"")
            for cmd in self._shell_commands:
                ts = datetime.fromtimestamp(cmd["time"]).strftime("%H:%M:%S")
                code = cmd.get("exit_code", "?")
                command = cmd["command"]
                if len(command) > 100:
                    command = command[:97] + "..."
                lines.append(f"- `{ts}` [{code}] `{command}`")
            lines.append(f"")

        # Tool usage summary
        if self._tool_calls:
            lines.append(f"## Tool Usage")
            lines.append(f"")
            for name, count in sorted(self._tool_calls.items(),
                                       key=lambda x: -x[1]):
                lines.append(f"- **{name}**: {count} calls")
            lines.append(f"")

        # Context swaps
        if self._context_swaps:
            lines.append(f"## Context Management")
            lines.append(f"")
            lines.append(f"- Context swaps: {self._context_swaps}")
            lines.append(f"")

        # Full timeline (last 50 events)
        lines.append(f"## Event Timeline (last 50)")
        lines.append(f"")
        for e in self._events[-50:]:
            ts = datetime.fromtimestamp(e.timestamp).strftime("%H:%M:%S")
            risk = ""
            if e.risk_level >= 3:
                risk = " **[CRITICAL]**"
            elif e.risk_level >= 2:
                risk = " **[WARNING]**"
            lines.append(f"- `{ts}` [{e.category}]{risk} {e.action}")
        lines.append(f"")

        lines.append(f"---")
        lines.append(f"*Generated by Forge Session Forensics*")

        return "\n".join(lines)

    def save_report(self) -> Optional[Path]:
        """Generate and save the report to disk (atomic write)."""
        try:
            report = self.generate_report()
            path = self._persist_dir / f"session_{self._session_id}.md"
            # Atomic write: temp file then os.replace()
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._persist_dir), suffix=".forge_tmp", prefix=".~")
            try:
                os.write(fd, report.encode("utf-8"))
                os.close(fd)
                fd = -1
                os.replace(tmp_path, str(path))
            except BaseException:
                if fd >= 0:
                    os.close(fd)
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
            log.info("Forensics report saved to %s", path)
            return path
        except Exception as e:
            log.warning("Failed to save forensics report: %s", e)
            return None

    def to_audit_dict(self) -> dict:
        """Return a JSON-serializable audit snapshot.

        Stable API contract for the audit exporter — never expose
        private internals directly.
        """
        return {
            "schema_version": 1,
            "session_id": self._session_id,
            "session_start": self._session_start,
            "turns": self._turns,
            "tokens_in": self._total_tokens_in,
            "tokens_out": self._total_tokens_out,
            "events": [
                {
                    "timestamp": e.timestamp,
                    "category": e.category,
                    "action": e.action,
                    "details": e.details,
                    "risk_level": e.risk_level,
                }
                for e in self._events
            ],
            "summary": {
                "files_read": dict(self._files_read),
                "files_written": dict(self._files_written),
                "files_edited": dict(self._files_edited),
                "files_created": list(self._files_created),
                "tool_calls": dict(self._tool_calls),
                "shell_commands": list(self._shell_commands),
                "threats": list(self._threats),
                "context_swaps": self._context_swaps,
            },
        }

    def format_summary(self) -> str:
        """Short summary for terminal display."""
        from forge.ui.terminal import (
            BOLD, RESET, DIM, GREEN, YELLOW, RED, CYAN
        )
        duration = time.time() - self._session_start
        risk_count = sum(1 for e in self._events if e.risk_level >= 2)
        all_files = set(list(self._files_read.keys()) +
                       list(self._files_written.keys()) +
                       list(self._files_edited.keys()))

        lines = [
            f"\n{BOLD}Session Forensics{RESET}",
            f"  Session:  {self._session_id}",
            f"  Duration: {duration / 60:.1f} min, {self._turns} turns",
            f"  Tokens:   {self._total_tokens_in:,} in / "
            f"{self._total_tokens_out:,} out",
            f"  Files:    {len(all_files)} touched "
            f"({len(self._files_created)} created)",
            f"  Tools:    {sum(self._tool_calls.values())} calls "
            f"across {len(self._tool_calls)} tools",
            f"  Shell:    {len(self._shell_commands)} commands",
            f"  Swaps:    {self._context_swaps}",
        ]

        if self._threats:
            lines.append(f"  Threats:  {RED}{len(self._threats)}{RESET}")
        if risk_count:
            lines.append(f"  Risks:    {YELLOW}{risk_count} events{RESET}")
        else:
            lines.append(f"  Risks:    {GREEN}clean{RESET}")

        lines.append(f"\n  {DIM}Reports: {self._persist_dir}{RESET}")
        lines.append(f"  {DIM}Save now: /forensics save{RESET}")

        return "\n".join(lines)
