"""Episodic memory system for Forge.

Provides persistent journaling of every turn's key information,
captures evicted context entries before they are lost, generates
deterministic swap summaries for context refreshes, and tracks
task state across sessions.
"""

import json
import logging
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional
from uuid import uuid4

from forge.ui.terminal import (
    BOLD, CYAN, DIM, GRAY, GREEN, MAGENTA, RESET, WHITE, YELLOW,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class JournalEntry:
    """A single recorded turn in the session journal."""
    session_id: str            # UUID for the session
    turn_number: int           # Which turn in the session
    timestamp: float           # Unix timestamp
    user_intent: str           # What the user asked (first 500 chars)
    actions_taken: list[str]   # List of tool calls made (e.g. "read_file: foo.py")
    files_touched: list[str]   # Files read/written/edited
    key_decisions: str         # Brief summary of decisions/outcomes
    assistant_response: str    # Summary of response (first 500 chars)
    tokens_used: int           # Tokens consumed this turn
    evicted_content: list[dict] = field(default_factory=list)
    # Each evicted entry: {role, tag, tokens, preview}


@dataclass
class TaskState:
    """Tracks the current high-level objective and progress."""
    objective: str             # Current high-level objective
    subtasks: list[dict]       # [{description, status, files}]
    files_modified: list[str]  # All files touched this session
    decisions: list[str]       # Key decisions made
    context_swaps: int         # How many times context was swapped
    last_updated: float        # Timestamp


# ---------------------------------------------------------------------------
# EpisodicMemory
# ---------------------------------------------------------------------------

class EpisodicMemory:
    """Persistent journal that records every turn, captures evictions,
    and generates deterministic swap summaries."""

    def __init__(self, persist_dir: Path):
        """
        Args:
            persist_dir: Directory for journal JSONL files
                         (typically ``~/.forge/journal/``).
        """
        self._persist_dir = Path(persist_dir)
        try:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            log.warning("Could not create journal directory %s: %s",
                        self._persist_dir, exc)

        self._session_id: str = uuid4().hex[:12]
        self._turn_count: int = 0
        self._eviction_buffer: list[dict] = []
        self._journal_file: Path = self._persist_dir / f"{self._session_id}.jsonl"
        self._task_state: Optional[TaskState] = self._load_task_state()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_turn(
        self,
        user_message: str,
        assistant_response: str,
        tool_calls: list[dict],
        files_touched: list[str],
        tokens_used: int,
    ) -> JournalEntry:
        """Record a single conversation turn to the journal.

        Consumes the current eviction buffer and flushes it into the
        new ``JournalEntry``.
        """
        self._turn_count += 1

        actions = []
        for tc in tool_calls:
            name = tc.get("name", tc.get("tool", "unknown"))
            # Build a short human-readable label
            args = tc.get("args", tc.get("arguments", {}))
            if isinstance(args, dict):
                first_val = next(iter(args.values()), "") if args else ""
                label = f"{name}: {str(first_val)[:80]}"
            else:
                label = str(name)
            actions.append(label)

        # Summarise decisions from tool calls (keep it terse)
        decision_parts = []
        for tc in tool_calls:
            name = tc.get("name", tc.get("tool", ""))
            if name in ("write_file", "edit_file", "create_file"):
                args = tc.get("args", tc.get("arguments", {}))
                fpath = args.get("path", args.get("file_path", ""))
                decision_parts.append(f"wrote {Path(fpath).name}" if fpath else f"wrote file")
        key_decisions = "; ".join(decision_parts) if decision_parts else ""

        entry = JournalEntry(
            session_id=self._session_id,
            turn_number=self._turn_count,
            timestamp=time.time(),
            user_intent=user_message[:500],
            actions_taken=actions,
            files_touched=list(files_touched),
            key_decisions=key_decisions,
            assistant_response=assistant_response[:500],
            tokens_used=tokens_used,
            evicted_content=list(self._eviction_buffer),
        )

        self._append_to_journal(entry)
        self._eviction_buffer.clear()

        # Keep task state in sync
        if self._task_state is not None:
            for fp in files_touched:
                if fp not in self._task_state.files_modified:
                    self._task_state.files_modified.append(fp)
            self._task_state.last_updated = time.time()
            self._save_task_state()

        return entry

    # Maximum entries to keep in the eviction buffer
    _MAX_EVICTION_BUFFER = 100

    def record_eviction(self, entries: list) -> None:
        """Capture context entries *before* they are discarded.

        ``entries`` are ``ContextEntry`` objects (duck-typed -- we only
        access ``.role``, ``.tag``, ``.token_count``, and ``.content``).
        Buffer is capped at _MAX_EVICTION_BUFFER entries to prevent
        unbounded memory growth.
        """
        for entry in entries:
            if len(self._eviction_buffer) >= self._MAX_EVICTION_BUFFER:
                break
            try:
                self._eviction_buffer.append({
                    "role": getattr(entry, "role", "unknown"),
                    "tag": getattr(entry, "tag", ""),
                    "tokens": getattr(entry, "token_count", 0),
                    "preview": str(getattr(entry, "content", ""))[:2000],
                })
            except Exception as exc:
                log.debug("Failed to capture eviction entry: %s", exc)

    def generate_swap_summary(self, context_entries: list) -> str:
        """Build a deterministic (no LLM) summary for context refresh.

        Targets 400-600 tokens of useful recap.
        """
        lines: list[str] = ["## Session Context (auto-generated)\n"]

        # --- Task state ---
        ts = self._task_state
        if ts is not None:
            lines.append(f"**Objective:** {ts.objective}\n")
            done = sum(1 for s in ts.subtasks if s.get("status") == "done")
            total = len(ts.subtasks)
            lines.append(f"**Progress:** {done}/{total} subtasks\n")
            if ts.files_modified:
                lines.append(f"**Files in play:** {', '.join(ts.files_modified)}\n")
        else:
            lines.append("**Objective:** (not set)\n")

        # --- Recent journal entries ---
        recent = self.get_recent_entries(count=10)
        if recent:
            lines.append("**Recent actions:**\n")
            for entry in recent:
                actions_str = ", ".join(entry.actions_taken[:3]) if entry.actions_taken else "conversation"
                intent_preview = entry.user_intent.split("\n")[0][:80]
                lines.append(
                    f"- Turn {entry.turn_number}: "
                    f"user asked \"{intent_preview}\" -> {actions_str}\n"
                )

        # --- Key decisions ---
        if ts is not None and ts.decisions:
            lines.append("**Key decisions:**\n")
            for d in ts.decisions[-10:]:
                lines.append(f"- {d}\n")

        lines.append(
            "\n**Note:** Context was swapped. Use /recall for details.\n"
        )

        return "".join(lines)

    def update_task(
        self,
        objective: str = None,
        subtask: dict = None,
        file_modified: str = None,
        decision: str = None,
    ) -> None:
        """Update task state fields (only non-None params are applied)."""
        if self._task_state is None:
            self._task_state = TaskState(
                objective=objective or "",
                subtasks=[],
                files_modified=[],
                decisions=[],
                context_swaps=0,
                last_updated=time.time(),
            )

        if objective is not None:
            self._task_state.objective = objective
        if subtask is not None:
            self._task_state.subtasks.append(subtask)
        if file_modified is not None:
            if file_modified not in self._task_state.files_modified:
                self._task_state.files_modified.append(file_modified)
        if decision is not None:
            self._task_state.decisions.append(decision)

        self._task_state.last_updated = time.time()
        self._save_task_state()

    def get_task_state(self) -> Optional[TaskState]:
        """Return the current task state, or ``None`` if unset."""
        return self._task_state

    def get_recent_entries(self, count: int = 10) -> list[JournalEntry]:
        """Return the last *count* journal entries across sessions.

        Reads from the current session first; if fewer than *count*
        entries exist, walks backwards through prior session files
        until enough entries are collected.
        """
        entries = self.get_session_entries()
        if len(entries) >= count:
            return entries[-count:]

        # Supplement from prior sessions (most recent first)
        try:
            session_files = sorted(
                self._persist_dir.glob("*.jsonl"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for sf in session_files:
                if sf.name == self._journal_file.name:
                    continue
                needed = count - len(entries)
                if needed <= 0:
                    break
                prior = self._read_journal_file(sf)
                entries = prior[-needed:] + entries
        except OSError as exc:
            log.debug("Could not read prior session files: %s", exc)

        return entries[-count:]

    def get_session_entries(self, session_id: str = None) -> list[JournalEntry]:
        """Return all entries for a session (defaults to current)."""
        if session_id is None:
            return self._read_journal_file(self._journal_file)

        target = self._persist_dir / f"{session_id}.jsonl"
        return self._read_journal_file(target)

    def to_audit_dict(self) -> dict:
        """Return a JSON-serializable audit snapshot.

        Stable API contract for the audit exporter.
        """
        entries = self.get_session_entries()
        return {
            "schema_version": 1,
            "session_id": self._session_id,
            "entries": [asdict(e) for e in entries],
        }

    def format_journal_display(self, entries: list[JournalEntry]) -> str:
        """Format journal entries for terminal display with ANSI colors."""
        if not entries:
            return f"{DIM}(no journal entries){RESET}"

        lines: list[str] = []
        lines.append(
            f"\n{BOLD}{'#':>4}  {'Time':19}  "
            f"{'User Intent':40}  {'Actions':30}  Files{RESET}"
        )
        lines.append(f"{DIM}{'--' * 60}{RESET}")

        for e in entries:
            ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(e.timestamp))
            intent = e.user_intent.split("\n")[0][:38]
            actions = ", ".join(e.actions_taken[:2]) if e.actions_taken else "-"
            if len(actions) > 28:
                actions = actions[:25] + "..."
            files = ", ".join(Path(f).name for f in e.files_touched[:3])
            if len(e.files_touched) > 3:
                files += f" +{len(e.files_touched) - 3}"

            evict_marker = ""
            if e.evicted_content:
                evict_marker = f" {YELLOW}[{len(e.evicted_content)} evicted]{RESET}"

            lines.append(
                f"{GREEN}{e.turn_number:>4}{RESET}  "
                f"{DIM}{ts_str}{RESET}  "
                f"{WHITE}{intent:40}{RESET}  "
                f"{CYAN}{actions:30}{RESET}  "
                f"{MAGENTA}{files}{RESET}"
                f"{evict_marker}"
            )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _save_task_state(self) -> None:
        """Persist task state to ``tasks.json`` atomically.

        Writes to a temp file first, then renames. This prevents
        corruption if the process is interrupted mid-write.
        """
        if self._task_state is None:
            return
        path = self._persist_dir.parent / "tasks.json"
        try:
            data = asdict(self._task_state)
            content = json.dumps(data, indent=2)
            # Atomic write: temp file in same directory, then rename
            fd, tmp_path = tempfile.mkstemp(
                dir=str(path.parent), suffix=".tmp", prefix="tasks_")
            closed = False
            try:
                os.write(fd, content.encode("utf-8"))
                os.close(fd)
                closed = True
                # On Windows, need to remove target first
                if path.exists():
                    path.unlink()
                os.rename(tmp_path, str(path))
            except Exception:
                if not closed:
                    os.close(fd)
                Path(tmp_path).unlink(missing_ok=True)
                raise
        except OSError as exc:
            log.warning("Failed to save task state to %s: %s", path, exc)

    def _load_task_state(self) -> Optional[TaskState]:
        """Load task state from ``tasks.json``, if it exists."""
        path = self._persist_dir.parent / "tasks.json"
        try:
            if not path.exists():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            return TaskState(
                objective=data.get("objective", ""),
                subtasks=data.get("subtasks", []),
                files_modified=data.get("files_modified", []),
                decisions=data.get("decisions", []),
                context_swaps=data.get("context_swaps", 0),
                last_updated=data.get("last_updated", 0.0),
            )
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            log.warning("Failed to load task state from %s: %s", path, exc)
            return None

    def _append_to_journal(self, entry: JournalEntry) -> None:
        """Append a single ``JournalEntry`` as one JSON line to the JSONL file."""
        try:
            with open(self._journal_file, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        except OSError as exc:
            log.warning("Failed to append journal entry to %s: %s",
                        self._journal_file, exc)

    def _read_journal_file(self, path: Path) -> list[JournalEntry]:
        """Read all entries from a JSONL journal file."""
        entries: list[JournalEntry] = []
        try:
            if not path.exists():
                return entries
            with open(path, "r", encoding="utf-8") as fh:
                for line_number, line in enumerate(fh, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entries.append(JournalEntry(
                            session_id=data["session_id"],
                            turn_number=data["turn_number"],
                            timestamp=data["timestamp"],
                            user_intent=data["user_intent"],
                            actions_taken=data.get("actions_taken", []),
                            files_touched=data.get("files_touched", []),
                            key_decisions=data.get("key_decisions", ""),
                            assistant_response=data.get("assistant_response", ""),
                            tokens_used=data.get("tokens_used", 0),
                            evicted_content=data.get("evicted_content", []),
                        ))
                    except (json.JSONDecodeError, KeyError) as exc:
                        log.debug("Skipping malformed journal line %d in %s: %s",
                                  line_number, path, exc)
        except OSError as exc:
            log.warning("Failed to read journal file %s: %s", path, exc)
        return entries
