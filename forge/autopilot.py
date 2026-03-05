"""Autonomous self-repair monitor for Forge.

Watches for error signals in ~/.forge/forge.log, injects repair prompts
into the engine's input queue, and verifies the repair succeeded.

If a repair attempt introduces new errors, the pre-repair state is
restored from a git stash automatically.

State machine:
  WATCHING  — polling log for errors
  REPAIRING — engine is processing the repair prompt
  VERIFYING — engine is idle; measuring whether errors decreased
  ROLLING_BACK — repair worsened things; restoring pre-repair state

Press F12 in the GUI terminal to toggle user control at any time.
"""

import logging
import queue
import subprocess
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

_FORGE_DIR = Path.home() / ".forge"
_LOG_FILE = _FORGE_DIR / "forge.log"

# Log lines that are routine/expected — don't trigger repair
_NOISE_PATTERNS = (
    "KV cache quantization",
    "ami_enabled",
    "checking for updates",
    "threat_auto_update",
    "voice mode",
    "AutopilotMonitor",  # Don't react to own log lines
    "BugReporter",
)

# Seconds to wait after detecting errors before triggering repair
_REPAIR_DELAY = 4.0

# Minimum seconds between successive repair sessions
_COOLDOWN = 30.0

# Seconds to wait after engine goes idle before evaluating repair outcome
_VERIFY_WAIT = 12.0

# Seconds to wait after engine startup before monitoring begins
_BOOT_GRACE = 8.0

# New errors within this window after repair count as repair-induced
_VERIFY_WINDOW = 20.0


class _State:
    WATCHING = "watching"
    REPAIRING = "repairing"
    VERIFYING = "verifying"
    ROLLING_BACK = "rolling_back"


class AutopilotMonitor:
    """Background monitor: detect errors → snapshot → repair → verify → rollback.

    Uses a queue-based injection mechanism: puts prompts onto
    gui_io._autopilot_queue, then fires _win._input_ready to wake up
    the engine thread if it's blocked on prompt_user().
    """

    def __init__(self, gui_io, win, cwd: str = None):
        self._gui_io = gui_io
        self._win = win
        self._cwd = cwd or str(Path.home())
        self._running = False
        self._thread = None

        self._user_control = False       # True while user has manually taken over
        self._last_repair = 0.0          # Timestamp of last repair session
        self._log_pos = 0                # Read cursor in forge.log

        self._state = _State.WATCHING
        self._pre_repair_stashed = False # Whether we successfully stashed
        self._pre_repair_errors = 0      # Error count before the repair
        self._repair_idle_time = 0.0     # When engine went idle after repair
        self._verify_log_pos = 0         # Log position when verification started

    # ── Lifecycle ──

    def start(self):
        """Start the monitor thread."""
        self._running = True
        self._thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="AutopilotMonitor",
        )
        self._thread.start()
        self._narrate(
            "[AUTOPILOT] Self-repair monitor active. "
            "Press F12 to take control at any time.",
            "info",
        )

    def stop(self):
        """Stop the monitor thread."""
        self._running = False

    def toggle_user_control(self):
        """F12 handler — toggle between user control and autopilot."""
        if self._user_control:
            self._user_control = False
            self._narrate(
                "\n[AUTOPILOT] Autopilot resumed — monitoring for errors.\n",
                "info",
            )
        else:
            self._user_control = True
            self._narrate(
                "\n[AUTOPILOT] Paused — you have control. "
                "Press F12 to hand back to autopilot.\n",
                "warning",
            )

    def on_user_input(self):
        """Call this whenever the user manually sends a message.

        Pauses autopilot injection — avoids the autopilot butting in
        while the user is actively working.
        """
        self._user_control = True

    def on_engine_idle(self):
        """Call this when the engine becomes idle (prompt_user called).

        Used to detect that a repair turn has completed and to drain
        any queued prompts.
        """
        if self._state == _State.REPAIRING:
            # Repair turn finished — begin verification window
            self._state = _State.VERIFYING
            self._repair_idle_time = time.time()
            self._verify_log_pos = self._log_pos
            self._narrate(
                f"[AUTOPILOT] Repair turn completed. "
                f"Verifying in {_VERIFY_WAIT:.0f}s...",
                "info",
            )

        if not self._user_control:
            self._drain_queue()

    # ── Injection ──

    def inject(self, prompt: str):
        """Queue a prompt for injection into the engine's input loop.

        If the engine is currently idle it will be woken up immediately.
        If busy, the prompt will be picked up the next time prompt_user()
        is called.
        """
        if self._win._shutting_down or self._gui_io._shutting_down:
            return
        if self._user_control:
            return

        # Show a preview in the terminal so the user can watch
        first_content = prompt.split("\n\n", 2)
        display = first_content[2][:80] if len(first_content) > 2 else prompt[:80]
        self._gui_io._safe_after(
            self._win.append_text,
            f"\n> [AUTOPILOT] {display}...\n",
            "user",
        )

        self._gui_io._autopilot_queue.put(prompt)
        self._win._input_ready.set()

    def _drain_queue(self):
        """Fire _input_ready if there are queued prompts and engine is idle."""
        if self._gui_io._autopilot_queue.empty():
            return
        if self._win._input_enabled and not self._win._shutting_down:
            self._win._input_ready.set()

    # ── Narration ──

    def _narrate(self, text: str, tag: str = "info"):
        """Print a message to the GUI terminal from the autopilot."""
        if self._gui_io._shutting_down:
            return
        self._gui_io._safe_after(
            self._win.append_text,
            text + "\n",
            tag,
        )

    # ── Monitor loop ──

    def _monitor_loop(self):
        """Background thread: watch → repair → verify → rollback."""
        time.sleep(_BOOT_GRACE)

        error_buffer: list[str] = []
        last_error_time = 0.0

        while self._running:
            try:
                now = time.time()

                if self._state == _State.WATCHING:
                    new_errors = self._poll_log_file()
                    if new_errors:
                        error_buffer.extend(new_errors)
                        last_error_time = now

                    if (error_buffer
                            and not self._user_control
                            and now - last_error_time >= _REPAIR_DELAY
                            and now - self._last_repair >= _COOLDOWN):
                        self._initiate_repair(error_buffer[:8])
                        error_buffer.clear()
                        self._last_repair = now

                    self._drain_queue()

                elif self._state == _State.REPAIRING:
                    # Just wait — on_engine_idle() transitions to VERIFYING
                    pass

                elif self._state == _State.VERIFYING:
                    # Poll for new errors since repair finished
                    new_errors = self._poll_log_file()

                    if now - self._repair_idle_time >= _VERIFY_WAIT:
                        self._evaluate_repair(new_errors)

                elif self._state == _State.ROLLING_BACK:
                    # Rollback is synchronous; state returns to WATCHING when done
                    pass

            except Exception as exc:
                log.debug("AutopilotMonitor loop error: %s", exc)

            time.sleep(1.5)

    # ── Pre-repair snapshot ──

    def _git_snapshot(self) -> bool:
        """Stash uncommitted working-tree changes before repair.

        Returns True if a stash was created (so we know to pop it on
        rollback). Returns False if the tree was clean (nothing to stash).
        """
        try:
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self._cwd,
                capture_output=True, text=True, timeout=10,
            )
            if not status.stdout.strip():
                log.debug("AutopilotMonitor: working tree clean, no stash needed")
                return False

            ts = int(time.time())
            result = subprocess.run(
                ["git", "stash", "push", "-u", "-m",
                 f"autopilot-pre-repair-{ts}"],
                cwd=self._cwd,
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0:
                log.debug("AutopilotMonitor: stashed pre-repair state")
                return True
            log.debug("AutopilotMonitor: git stash failed: %s", result.stderr)
        except Exception as exc:
            log.debug("AutopilotMonitor: snapshot error: %s", exc)
        return False

    def _git_rollback(self) -> bool:
        """Discard repair changes and restore the pre-repair stash.

        Returns True on success.
        """
        ok = True
        try:
            # Discard all working-tree changes made by the repair
            subprocess.run(
                ["git", "checkout", "--", "."],
                cwd=self._cwd,
                capture_output=True, text=True, timeout=15,
            )
            subprocess.run(
                ["git", "clean", "-fd"],
                cwd=self._cwd,
                capture_output=True, text=True, timeout=15,
            )
            log.debug("AutopilotMonitor: discarded repair changes")

            if self._pre_repair_stashed:
                result = subprocess.run(
                    ["git", "stash", "pop"],
                    cwd=self._cwd,
                    capture_output=True, text=True, timeout=15,
                )
                if result.returncode != 0:
                    log.debug("AutopilotMonitor: stash pop failed: %s",
                              result.stderr)
                    ok = False
                else:
                    log.debug("AutopilotMonitor: restored pre-repair state")
        except Exception as exc:
            log.debug("AutopilotMonitor: rollback error: %s", exc)
            ok = False
        return ok

    def _git_drop_stash(self):
        """Discard the pre-repair snapshot after a successful repair."""
        if not self._pre_repair_stashed:
            return
        try:
            subprocess.run(
                ["git", "stash", "drop"],
                cwd=self._cwd,
                capture_output=True, text=True, timeout=10,
            )
            log.debug("AutopilotMonitor: dropped pre-repair stash (repair OK)")
        except Exception:
            pass

    # ── Repair / Verify / Rollback ──

    def _initiate_repair(self, error_lines: list[str]):
        """Take a snapshot, narrate, and inject the repair prompt."""
        count = len(error_lines)
        summary = "\n".join(f"  {i+1}. {e}" for i, e in enumerate(error_lines))

        self._narrate(
            f"\n[AUTOPILOT] Detected {count} error(s) — "
            f"saving pre-repair snapshot...",
            "warning",
        )

        # Snapshot before touching anything
        self._pre_repair_stashed = self._git_snapshot()
        self._pre_repair_errors = count
        stash_msg = ("pre-repair state stashed"
                     if self._pre_repair_stashed
                     else "working tree was clean — no stash needed")
        self._narrate(f"[AUTOPILOT] Snapshot: {stash_msg}.", "info")
        self._narrate(f"[AUTOPILOT] Errors to fix:\n{summary}", "tool_body")

        forge_dir = Path(__file__).parent
        tests_dir = forge_dir.parent / "tests"
        prompt = (
            "[AUTOPILOT SELF-REPAIR]\n\n"
            f"I have detected {count} error(s) in my own operation:\n\n"
            f"{summary}\n\n"
            "Work through this autonomously in order:\n"
            "1. Read the full traceback above and identify the exact file "
            "and line number responsible.\n"
            "2. Read that file fresh — do not rely on memory.\n"
            "3. Diagnose the root cause from the actual file content.\n"
            "4. Apply the fix.\n"
            "5. Verify with a targeted test — find the test file that "
            "covers the module you changed (e.g. if you changed "
            "forge/engine.py look for tests/test_engine.py) and run only "
            f"that: run_shell 'python -m pytest {{test_file}} -x -q --tb=short' "
            f"(tests live in {tests_dir}). "
            "Only run the full suite if no targeted test exists.\n"
            "6. If tests pass, you are done. "
            "If they fail, revert your edit and try a different approach.\n"
            "Narrate each step."
        )

        self._state = _State.REPAIRING
        self.inject(prompt)

    def _evaluate_repair(self, new_errors: list[str]):
        """Decide pass/fail and either keep or rollback the repair."""
        new_count = len(new_errors)

        if new_count == 0:
            # No new errors — repair succeeded
            self._narrate(
                "\n[AUTOPILOT] Verification passed — no new errors detected. "
                "Repair successful.",
                "info",
            )
            self._git_drop_stash()
            self._state = _State.WATCHING
            return

        if new_count >= self._pre_repair_errors:
            # Repair introduced as many or more errors — roll back
            self._narrate(
                f"\n[AUTOPILOT] Verification FAILED — "
                f"{new_count} error(s) detected after repair "
                f"(was {self._pre_repair_errors}). Rolling back...",
                "error",
            )
            self._state = _State.ROLLING_BACK
            ok = self._git_rollback()
            if ok:
                self._narrate(
                    "[AUTOPILOT] Rollback complete — pre-repair state restored. "
                    "Pausing autopilot to avoid repair loop. Press F12 to re-enable.",
                    "warning",
                )
            else:
                self._narrate(
                    "[AUTOPILOT] Rollback encountered an error — "
                    "check git status manually.",
                    "error",
                )
            # Pause autopilot so we don't immediately try again and loop
            self._user_control = True
            self._state = _State.WATCHING
            return

        # Fewer errors than before — partial success, keep changes
        self._narrate(
            f"\n[AUTOPILOT] Partial success — errors reduced from "
            f"{self._pre_repair_errors} to {new_count}. "
            "Keeping changes; will attempt further repair after cooldown.",
            "warning",
        )
        self._git_drop_stash()
        self._state = _State.WATCHING

    def _poll_log_file(self) -> list[str]:
        """Read new ERROR/CRITICAL lines from forge.log.

        Filters out known-routine noise so only actionable problems
        trigger a repair session.
        """
        if not _LOG_FILE.exists():
            return []
        try:
            with open(_LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self._log_pos)
                chunk = f.read()
                self._log_pos = f.tell()
            errors = []
            for line in chunk.splitlines():
                upper = line.upper()
                if " ERROR " not in upper and " CRITICAL " not in upper:
                    continue
                if any(pat.lower() in line.lower() for pat in _NOISE_PATTERNS):
                    continue
                errors.append(line.strip())
            return errors
        except Exception:
            return []
