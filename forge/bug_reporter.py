"""Autonomous Bug Reporter — self-healing development loop.

Captures crashes and silent failures ("ghosts") at runtime, deduplicates
them via semantic fingerprinting, and files GitHub Issues automatically.
The existing issue_fixer.py picks them up → auto-fix → auto-push → /update.

Owner-only by default (bug_reporter_enabled: false). Requires `gh` CLI
authenticated for issue filing.
"""

import hashlib
import json
import linecache
import logging
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import traceback as tb_module
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

FORGE_VERSION = "0.1.0"

# Exceptions that are transient / infrastructure — not worth filing
_TRANSIENT_EXCEPTIONS = frozenset({
    "ConnectionError", "ConnectionRefusedError", "ConnectionResetError",
    "TimeoutError", "Timeout", "ReadTimeout", "ConnectTimeout",
    "BrokenPipeError", "ConnectionAbortedError",
})

# Ghost detection thresholds
_GHOST_EMBED_FAILURES = 3
_GHOST_TOOL_RATE_THRESHOLD = 0.70
_GHOST_TOOL_MIN_CALLS = 10
_GHOST_CONTEXT_FULL = 3
_GHOST_LLM_ERRORS = 3
_GHOST_RELIABILITY_SCORE = 50
_GHOST_RELIABILITY_SESSIONS = 3


@dataclass
class CrashFingerprint:
    """Semantic crash identity for deduplication.

    Two crashes with the same fingerprint hash are "the same bug"
    regardless of line numbers, timestamps, or variable values.
    """
    exc_type: str           # e.g. "KeyError"
    forge_frame: str        # deepest forge/ file, e.g. "engine.py"
    function: str           # function name at that frame
    normalized_msg: str     # paths→<PATH>, numbers→<N>

    @property
    def hash(self) -> str:
        """SHA-512 of the 4 identity fields, first 16 hex chars."""
        data = f"{self.exc_type}|{self.forge_frame}|{self.function}|{self.normalized_msg}"
        return hashlib.sha512(data.encode()).hexdigest()[:16]

    @staticmethod
    def normalize_message(msg: str) -> str:
        """Strip variable noise from exception messages."""
        # Paths → <PATH>
        msg = re.sub(r'[A-Z]:\\[\w\\/.~-]+', '<PATH>', msg)
        msg = re.sub(r'/[\w/.~-]{3,}', '<PATH>', msg)
        # Numbers → <N>
        msg = re.sub(r'\b\d{2,}\b', '<N>', msg)
        # Hex addresses → <ADDR>
        msg = re.sub(r'0x[0-9a-fA-F]+', '<ADDR>', msg)
        return msg.strip()

    @staticmethod
    def from_exception(exc: BaseException,
                       tb: Optional[object] = None) -> "CrashFingerprint":
        """Build a fingerprint from an exception + traceback."""
        exc_type = type(exc).__name__

        # Walk the traceback to find the deepest forge/ frame
        forge_frame = "unknown"
        function = "unknown"
        if tb is None:
            tb = exc.__traceback__
        if tb:
            frames = tb_module.extract_tb(tb)
            for frame in reversed(frames):
                fname = frame.filename.replace("\\", "/")
                if "/forge/" in fname:
                    forge_frame = fname.split("/forge/")[-1]
                    function = frame.name
                    break

        normalized_msg = CrashFingerprint.normalize_message(str(exc))
        return CrashFingerprint(
            exc_type=exc_type,
            forge_frame=forge_frame,
            function=function,
            normalized_msg=normalized_msg,
        )


@dataclass
class BugReport:
    """A captured bug ready for filing."""
    fingerprint: CrashFingerprint
    severity: str           # "crash", "error", "degradation"
    category: str           # "exception", "ghost_embed", "ghost_tool", etc.
    traceback_text: str
    source_snippet: str     # 5 lines around crash via linecache
    breadcrumbs: list       # last 15 forensic events
    environment: dict       # hardware, model, versions
    timestamp: float = 0.0
    session_id: str = ""
    ghost_details: dict = field(default_factory=dict)
    user_description: str = ""


class BugReporter:
    """Captures crashes and ghost errors, files GitHub Issues on exit."""

    def __init__(self, config, forensics=None):
        self._config = config
        self._forensics = forensics
        self._pending: list[BugReport] = []
        self._session_filed = 0
        self._session_ghosts: dict[str, int] = {}  # category → count
        self._session_id = ""

        if forensics:
            self._session_id = getattr(forensics, '_session_id', '')

        # Dedup persistence
        self._store_dir = Path.home() / ".forge" / "bug_reporter"
        self._reported_path = self._store_dir / "reported.json"
        self._reported: dict[str, dict] = {}  # hash → {timestamp, issue_url}
        self._load_reported()

    @property
    def enabled(self) -> bool:
        return self._config.get("bug_reporter_enabled", False)

    def _load_reported(self):
        """Load dedup history from disk."""
        try:
            if self._reported_path.exists():
                data = json.loads(self._reported_path.read_text("utf-8"))
                # Prune entries older than 90 days
                cutoff = time.time() - (90 * 86400)
                self._reported = {
                    k: v for k, v in data.items()
                    if v.get("timestamp", 0) > cutoff
                }
        except Exception as e:
            log.debug("Failed to load bug reporter history: %s", e)
            self._reported = {}

    def _save_reported(self):
        """Persist dedup history (atomic write)."""
        try:
            self._store_dir.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(
                dir=str(self._store_dir), suffix=".tmp")
            try:
                os.write(fd, json.dumps(
                    self._reported, indent=2).encode("utf-8"))
                os.close(fd)
                fd = -1
                os.replace(tmp, str(self._reported_path))
            except BaseException:
                if fd >= 0:
                    os.close(fd)
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
        except Exception as e:
            log.debug("Failed to save bug reporter history: %s", e)

    def _should_report(self, fingerprint: CrashFingerprint,
                       is_manual: bool = False) -> bool:
        """Quality gate — decide whether this bug is worth filing."""
        if not self.enabled and not is_manual:
            return False

        # Manual reports always pass
        if is_manual:
            return True

        # Session cap
        max_session = self._config.get("bug_reporter_max_session", 3)
        if self._session_filed >= max_session:
            log.debug("Bug reporter: session cap reached (%d)", max_session)
            return False

        # Daily cap
        max_daily = self._config.get("bug_reporter_max_daily", 10)
        today = time.strftime("%Y-%m-%d")
        today_count = sum(
            1 for v in self._reported.values()
            if time.strftime("%Y-%m-%d",
                             time.localtime(v.get("timestamp", 0))) == today
        )
        if today_count >= max_daily:
            log.debug("Bug reporter: daily cap reached (%d)", max_daily)
            return False

        # Cooldown per fingerprint
        cooldown_h = self._config.get("bug_reporter_cooldown_hours", 24)
        prev = self._reported.get(fingerprint.hash)
        if prev:
            elapsed_h = (time.time() - prev.get("timestamp", 0)) / 3600
            if elapsed_h < cooldown_h:
                log.debug("Bug reporter: cooldown active for %s (%.1fh < %dh)",
                          fingerprint.hash, elapsed_h, cooldown_h)
                return False

        # Transient exceptions — skip
        if fingerprint.exc_type in _TRANSIENT_EXCEPTIONS:
            log.debug("Bug reporter: skipping transient %s",
                      fingerprint.exc_type)
            return False

        # Must have a forge/ frame (not third-party-only)
        if fingerprint.forge_frame == "unknown":
            log.debug("Bug reporter: no forge/ frame, skipping")
            return False

        return True

    def _get_source_snippet(self, tb) -> str:
        """Extract 5 lines of source around the crash site."""
        if not tb:
            return ""
        frames = tb_module.extract_tb(tb)
        # Find deepest forge/ frame
        target = None
        for frame in reversed(frames):
            fname = frame.filename.replace("\\", "/")
            if "/forge/" in fname:
                target = frame
                break
        if not target:
            target = frames[-1] if frames else None
        if not target:
            return ""

        lines = []
        start = max(1, target.lineno - 2)
        end = target.lineno + 2
        for i in range(start, end + 1):
            line = linecache.getline(target.filename, i)
            if line:
                marker = ">>>" if i == target.lineno else "   "
                lines.append(f"{marker} {i:4d} | {line.rstrip()}")
        header = target.filename.replace("\\", "/")
        if "/forge/" in header:
            header = "forge/" + header.split("/forge/")[-1]
        return f"# {header}, around line {target.lineno}\n" + "\n".join(lines)

    def _get_breadcrumbs(self, limit: int = 15) -> list[dict]:
        """Get the last N forensic events as breadcrumbs."""
        if not self._forensics:
            return []
        try:
            events = self._forensics._events[-limit:]
            crumbs = []
            now = time.time()
            for ev in events:
                elapsed = now - ev.timestamp
                crumbs.append({
                    "time": f"-{elapsed:.0f}s",
                    "category": ev.category,
                    "action": ev.action[:80],
                })
            return crumbs
        except Exception:
            return []

    def _get_environment(self) -> dict:
        """Collect environment metadata for the bug report."""
        env = {
            "forge_version": FORGE_VERSION,
            "platform": platform.platform(),
            "python": platform.python_version(),
        }
        try:
            from forge.hardware import get_hardware_summary
            hw = get_hardware_summary()
            gpu = hw.get("gpu") or {}
            env["gpu"] = gpu.get("name", "unknown")
            env["vram_mb"] = gpu.get("vram_total_mb", 0)
        except Exception:
            pass
        try:
            env["model"] = self._config.get("default_model", "unknown")
        except Exception:
            pass
        return env

    def _format_issue_body(self, report: BugReport) -> str:
        """Format a Crucible-safe GitHub Issue body.

        Uses passive voice, no directive patterns, all code in fences.
        """
        fp = report.fingerprint
        lines = [
            "## Auto-detected bug report",
            "",
            f"**Severity:** {report.severity} | "
            f"**Category:** {report.category}",
            f"**Module:** `{fp.forge_frame}` | "
            f"**Function:** `{fp.function}()`",
            f"**Fingerprint:** `{fp.hash}`",
            "",
        ]

        # Exception
        if report.traceback_text:
            exc_line = report.traceback_text.strip().splitlines()[-1] \
                if report.traceback_text.strip() else ""
            lines.extend([
                "### Exception",
                "```python",
                exc_line,
                "```",
                "",
            ])

        # Traceback
        if report.traceback_text:
            # Truncate very long tracebacks
            tb_text = report.traceback_text
            if len(tb_text) > 3000:
                tb_lines = tb_text.splitlines()
                tb_text = "\n".join(tb_lines[:15] + ["...(truncated)..."] +
                                    tb_lines[-10:])
            lines.extend([
                "### Traceback",
                "```python",
                tb_text,
                "```",
                "",
            ])

        # Source context
        if report.source_snippet:
            lines.extend([
                "### Source Context",
                "```python",
                report.source_snippet,
                "```",
                "",
            ])

        # Breadcrumbs
        if report.breadcrumbs:
            lines.extend([
                "### Breadcrumb Trail",
                "| Time | Category | Action |",
                "|------|----------|--------|",
            ])
            for crumb in report.breadcrumbs:
                lines.append(
                    f"| {crumb['time']} | {crumb['category']} | "
                    f"{crumb['action']} |"
                )
            lines.append("")

        # Ghost details
        if report.ghost_details:
            lines.extend([
                "### Ghost Detection Details",
                "```json",
                json.dumps(report.ghost_details, indent=2),
                "```",
                "",
            ])

        # User description (manual /report)
        if report.user_description:
            lines.extend([
                "### User Description",
                report.user_description,
                "",
            ])

        # Environment
        env = report.environment
        env_parts = [
            f"Forge: {env.get('forge_version', '?')}",
            f"Platform: {env.get('platform', '?')}",
            f"Python: {env.get('python', '?')}",
        ]
        if env.get("gpu"):
            env_parts.append(
                f"GPU: {env['gpu']} ({env.get('vram_mb', '?')}MB)")
        if env.get("model"):
            env_parts.append(f"Model: {env['model']}")
        lines.extend([
            "### Environment",
            "- " + " | ".join(env_parts),
            "",
            "---",
            f"*Filed by Forge Bug Reporter. Session: {report.session_id}*",
        ])

        body = "\n".join(lines)
        # Hard limit — GitHub truncates at ~65535 but keep it reasonable
        if len(body) > 8000:
            body = body[:7900] + "\n\n...(truncated)..."
        return body

    def capture(self, exc: BaseException,
                tb=None,
                context: dict = None) -> Optional[BugReport]:
        """Capture a crash for potential filing.

        Called at crash sites (engine error handler, tool exception, etc).
        Returns the BugReport if queued, None if filtered out.
        """
        if not self.enabled:
            return None

        if tb is None:
            tb = exc.__traceback__

        fp = CrashFingerprint.from_exception(exc, tb)
        if not self._should_report(fp):
            return None

        report = BugReport(
            fingerprint=fp,
            severity="crash",
            category="exception",
            traceback_text=tb_module.format_exception(
                type(exc), exc, tb).__str__()
                if not isinstance(tb_module.format_exception(
                    type(exc), exc, tb), str)
                else tb_module.format_exception(type(exc), exc, tb),
            source_snippet=self._get_source_snippet(tb),
            breadcrumbs=self._get_breadcrumbs(),
            environment=self._get_environment(),
            timestamp=time.time(),
            session_id=self._session_id,
        )

        # format_exception returns a list — join it
        if isinstance(report.traceback_text, list):
            report.traceback_text = "".join(report.traceback_text)
        elif not isinstance(report.traceback_text, str):
            report.traceback_text = str(report.traceback_text)

        if context:
            report.ghost_details = context

        self._pending.append(report)
        log.info("Bug reporter: captured %s in %s (fingerprint: %s)",
                 fp.exc_type, fp.forge_frame, fp.hash)
        return report

    def capture_ghost(self, category: str, message: str,
                      details: dict = None) -> None:
        """Record a silent failure ("ghost error").

        Called when something goes wrong silently — embed failures,
        tool degradation, context thrashing, LLM instability.
        These accumulate and are evaluated at session end.
        """
        if not self.enabled:
            return
        if not self._config.get("bug_reporter_ghost_detection", True):
            return

        self._session_ghosts.setdefault(category, 0)
        self._session_ghosts[category] += 1
        log.debug("Bug reporter ghost: %s (%d) — %s",
                  category, self._session_ghosts[category], message)

    def check_session_ghosts(self) -> list[BugReport]:
        """End-of-session anomaly scan. Creates BugReports for ghost patterns.

        Returns list of new reports added to pending queue.
        """
        if not self.enabled:
            return []
        if not self._config.get("bug_reporter_ghost_detection", True):
            return []

        new_reports = []

        # Ghost: embed failures
        embed_fails = self._session_ghosts.get("embed", 0)
        if embed_fails >= _GHOST_EMBED_FAILURES:
            report = self._create_ghost_report(
                category="ghost_embed",
                severity="degradation",
                message=f"Embedding failures: {embed_fails} in session",
                details={"embed_failures": embed_fails},
            )
            if report:
                new_reports.append(report)

        # Ghost: tool degradation
        tool_fails = self._session_ghosts.get("tool_fail", 0)
        tool_success = self._session_ghosts.get("tool_success", 0)
        total_tool = tool_fails + tool_success
        if total_tool >= _GHOST_TOOL_MIN_CALLS:
            rate = tool_success / total_tool
            if rate < _GHOST_TOOL_RATE_THRESHOLD:
                report = self._create_ghost_report(
                    category="ghost_tool",
                    severity="degradation",
                    message=f"Tool success rate: {rate:.0%} "
                            f"({tool_success}/{total_tool})",
                    details={
                        "success_rate": round(rate, 3),
                        "total_calls": total_tool,
                        "failures": tool_fails,
                    },
                )
                if report:
                    new_reports.append(report)

        # Ghost: context thrashing
        ctx_full = self._session_ghosts.get("context_full", 0)
        if ctx_full >= _GHOST_CONTEXT_FULL:
            report = self._create_ghost_report(
                category="ghost_context",
                severity="error",
                message=f"ContextFullError: {ctx_full} in session",
                details={"context_full_errors": ctx_full},
            )
            if report:
                new_reports.append(report)

        # Ghost: LLM instability
        llm_errors = self._session_ghosts.get("llm_error", 0)
        if llm_errors >= _GHOST_LLM_ERRORS:
            report = self._create_ghost_report(
                category="ghost_llm",
                severity="error",
                message=f"LLM errors: {llm_errors} in session",
                details={"llm_errors": llm_errors},
            )
            if report:
                new_reports.append(report)

        return new_reports

    def _create_ghost_report(self, category: str, severity: str,
                             message: str,
                             details: dict = None) -> Optional[BugReport]:
        """Create a BugReport for a ghost error pattern."""
        # Build a synthetic fingerprint for dedup
        fp = CrashFingerprint(
            exc_type="GhostError",
            forge_frame=category,
            function="check_session_ghosts",
            normalized_msg=CrashFingerprint.normalize_message(message),
        )

        if not self._should_report(fp):
            return None

        report = BugReport(
            fingerprint=fp,
            severity=severity,
            category=category,
            traceback_text="",
            source_snippet="",
            breadcrumbs=self._get_breadcrumbs(),
            environment=self._get_environment(),
            timestamp=time.time(),
            session_id=self._session_id,
            ghost_details=details or {},
        )
        self._pending.append(report)
        return report

    def file_manual_report(self, description: str) -> Optional[str]:
        """File a manual /report from the user. Bypasses quality gate.

        Returns the issue URL on success, None on failure.
        """
        fp = CrashFingerprint(
            exc_type="ManualReport",
            forge_frame="user",
            function="file_manual_report",
            normalized_msg=CrashFingerprint.normalize_message(description),
        )

        report = BugReport(
            fingerprint=fp,
            severity="error",
            category="manual",
            traceback_text="",
            source_snippet="",
            breadcrumbs=self._get_breadcrumbs(),
            environment=self._get_environment(),
            timestamp=time.time(),
            session_id=self._session_id,
            user_description=description,
        )

        return self._file_issue(report, is_manual=True)

    def flush(self) -> list[str]:
        """File all pending reports as GitHub Issues.

        Called on session exit. Returns list of issue URLs.
        """
        if not self._pending:
            return []

        urls = []
        for report in self._pending:
            url = self._file_issue(report)
            if url:
                urls.append(url)

        self._pending.clear()
        self._save_reported()
        return urls

    def _file_issue(self, report: BugReport,
                    is_manual: bool = False) -> Optional[str]:
        """File a single issue via `gh issue create`."""
        if not self._should_report(report.fingerprint, is_manual=is_manual):
            return None

        # Check gh is available
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                log.warning("Bug reporter: gh not authenticated")
                return None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            log.warning("Bug reporter: gh CLI not available")
            return None

        labels = self._config.get("bug_reporter_labels", "bug,auto-reported")
        title_prefix = "[Auto] " if report.category != "manual" else "[Report] "
        title = (f"{title_prefix}{report.fingerprint.exc_type} in "
                 f"{report.fingerprint.forge_frame}:"
                 f"{report.fingerprint.function}")
        if len(title) > 120:
            title = title[:117] + "..."

        body = self._format_issue_body(report)

        try:
            result = subprocess.run(
                ["gh", "issue", "create",
                 "--title", title,
                 "--body", body,
                 "--label", labels],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                url = result.stdout.strip()
                # Record in dedup history
                self._reported[report.fingerprint.hash] = {
                    "timestamp": time.time(),
                    "issue_url": url,
                    "exc_type": report.fingerprint.exc_type,
                    "forge_frame": report.fingerprint.forge_frame,
                }
                self._session_filed += 1
                log.info("Bug reporter: filed issue %s", url)
                return url
            else:
                log.warning("Bug reporter: gh issue create failed: %s",
                            result.stderr[:200])
                return None
        except Exception as e:
            log.warning("Bug reporter: failed to file issue: %s", e)
            return None

    def to_audit_dict(self) -> dict:
        """Stable API for audit/telemetry."""
        return {
            "enabled": self.enabled,
            "session_filed": self._session_filed,
            "pending": len(self._pending),
            "ghosts_detected": dict(self._session_ghosts),
            "total_reported": len(self._reported),
        }

    def stats(self) -> dict:
        """Stats for dashboard card."""
        return {
            "enabled": self.enabled,
            "session_filed": self._session_filed,
            "pending": len(self._pending),
            "ghost_categories": dict(self._session_ghosts),
            "lifetime_reported": len(self._reported),
        }


# ── Module-level convenience API ──
# Safe no-ops when reporter is not initialized (e.g., tests, imports).

_reporter: Optional[BugReporter] = None


def init_reporter(config, forensics=None) -> BugReporter:
    """Initialize the global bug reporter."""
    global _reporter
    _reporter = BugReporter(config, forensics)
    return _reporter


def get_reporter() -> Optional[BugReporter]:
    """Get the global reporter instance (may be None)."""
    return _reporter


def capture_crash(exc: BaseException, tb=None,
                  context: dict = None) -> None:
    """Module-level crash capture — safe no-op if reporter not initialized."""
    if _reporter:
        try:
            _reporter.capture(exc, tb=tb, context=context)
        except Exception:
            pass  # Never crash the crash reporter


def capture_ghost(category: str, message: str,
                  details: dict = None) -> None:
    """Module-level ghost capture — safe no-op if reporter not initialized."""
    if _reporter:
        try:
            _reporter.capture_ghost(category, message, details)
        except Exception:
            pass
