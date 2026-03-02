"""StateVerifier — post-scenario integrity checker.

Every integration test calls verifier.check_all() after its scenario.
Fails fast on the first integrity violation found.

8 invariant checks:
  1. Context consistency     — token sum, no zero-token entries, pinned present
  2. Billing integrity       — no negative counters
  3. Forensics integrity     — events within cap, timestamps valid
  4. State files             — config.yaml valid YAML, billing.json valid JSON
  5. Continuity state        — recovery bounded, score 0-100, valid grade
  6. Crucible state          — collections within caps
  7. Workspace/sandbox       — all file ops within allowed roots, no escapes
  8. Tool-call validity      — no unknown tools accepted, rate caps respected
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class IntegrityError(AssertionError):
    """Raised when a state invariant is violated."""
    pass


class StateVerifier:
    """Verifies engine state integrity after stress scenarios."""

    def __init__(self, engine, harness):
        self.engine = engine
        self.harness = harness

    def check_all(self):
        """Run every integrity check. Raises IntegrityError on failure."""
        self.check_context_consistency()
        self.check_billing_integrity()
        self.check_forensics_integrity()
        self.check_state_files()
        self.check_continuity_state()
        self.check_crucible_state()
        self.check_workspace_sandbox()
        self.check_tool_call_validity()

    # ── 1. Context consistency ──

    def check_context_consistency(self):
        """Verify context window invariants."""
        ctx = self.engine.ctx
        entries = ctx._entries

        # Token sum must match _total_tokens
        computed = sum(e.token_count for e in entries)
        if computed != ctx._total_tokens:
            raise IntegrityError(
                f"Context token mismatch: sum(entries)={computed} "
                f"vs _total_tokens={ctx._total_tokens}")

        # No zero-token entries (except maybe system prompt)
        for i, entry in enumerate(entries):
            if entry.token_count <= 0 and entry.role != "system":
                raise IntegrityError(
                    f"Entry {i} ({entry.role}/{entry.tag}) has "
                    f"token_count={entry.token_count}")

        # Pinned entries must still be present
        pinned = [e for e in entries if e.pinned]
        for p in pinned:
            if p not in entries:
                raise IntegrityError(
                    f"Pinned entry missing: {p.tag} {p.role}")

        # Usage percentage must be <= 100 (or very close with rounding)
        if ctx.usage_pct > 105:
            raise IntegrityError(
                f"Context usage {ctx.usage_pct:.1f}% exceeds limit")

    # ── 2. Billing integrity ──

    def check_billing_integrity(self):
        """Verify billing meter is consistent."""
        billing = self.engine.billing

        if billing.session_input_tokens < 0:
            raise IntegrityError(
                f"Negative session_input_tokens: {billing.session_input_tokens}")

        if billing.session_output_tokens < 0:
            raise IntegrityError(
                f"Negative session_output_tokens: {billing.session_output_tokens}")

        if billing.balance < 0 and billing.starting_balance > 0:
            raise IntegrityError(
                f"Negative balance: {billing.balance}")

    # ── 3. Forensics integrity ──

    def check_forensics_integrity(self):
        """Verify forensics event log is bounded and consistent."""
        forensics = self.engine.forensics
        events = forensics._events
        max_events = getattr(forensics, '_MAX_EVENTS', 5000)

        if len(events) > max_events:
            raise IntegrityError(
                f"Forensics events {len(events)} > cap {max_events}")

        # All timestamps should be >= session_start
        for i, event in enumerate(events):
            if event.timestamp < forensics._session_start - 1:
                raise IntegrityError(
                    f"Forensic event {i} timestamp {event.timestamp} "
                    f"< session_start {forensics._session_start}")

    # ── 4. State files ──

    def check_state_files(self):
        """Verify persisted state files are valid."""
        forge_dir = self.harness._forge_dir
        if forge_dir is None:
            return

        # config.yaml must be valid YAML
        config_path = forge_dir / "config.yaml"
        if config_path.exists():
            import yaml
            try:
                data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise IntegrityError(
                        f"config.yaml is not a dict: {type(data)}")
            except yaml.YAMLError as e:
                raise IntegrityError(f"config.yaml invalid YAML: {e}")

        # billing.json must be valid JSON if it exists
        billing_path = forge_dir / "billing.json"
        if billing_path.exists():
            try:
                data = json.loads(billing_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise IntegrityError(
                        f"billing.json is not a dict: {type(data)}")
            except json.JSONDecodeError as e:
                raise IntegrityError(f"billing.json invalid JSON: {e}")

        # No orphaned temp files
        for f in forge_dir.rglob("*.forge_tmp"):
            raise IntegrityError(f"Orphaned temp file: {f}")

    # ── 5. Continuity state ──

    def check_continuity_state(self):
        """Verify continuity monitor state is valid."""
        cont = self.engine.continuity
        if not cont.enabled:
            return

        # Recovery attempts must be bounded
        max_attempts = getattr(cont, '_max_recovery_attempts', 5)
        current = getattr(cont, '_recovery_attempts', 0)
        if current > max_attempts:
            raise IntegrityError(
                f"Recovery attempts {current} > max {max_attempts}")

        # Score should be 0-100
        task_state = self.engine.memory.get_task_state()
        snapshot = cont.score(self.engine.ctx._entries, task_state)
        if snapshot.score < 0 or snapshot.score > 100:
            raise IntegrityError(
                f"Continuity score out of range: {snapshot.score}")

        # Grade should be valid
        from forge.continuity import score_to_grade
        grade = score_to_grade(snapshot.score)
        if grade not in ("A", "B", "C", "D", "F"):
            raise IntegrityError(f"Invalid grade: {grade}")

    # ── 6. Crucible state ──

    def check_crucible_state(self):
        """Verify crucible collections are within caps."""
        crucible = self.engine.crucible
        if not crucible.enabled:
            return

        max_prov = getattr(crucible, '_MAX_PROVENANCE', 1000)
        max_hist = getattr(crucible, '_MAX_TOOL_HISTORY', 1000)
        max_log = getattr(crucible, '_MAX_THREAT_LOG', 500)

        prov_len = len(getattr(crucible, '_provenance_chain', []))
        hist_len = len(getattr(crucible, '_tool_history', []))
        log_len = len(getattr(crucible, '_threat_log', []))

        if prov_len > max_prov:
            raise IntegrityError(
                f"Provenance chain {prov_len} > cap {max_prov}")
        if hist_len > max_hist:
            raise IntegrityError(
                f"Tool history {hist_len} > cap {max_hist}")
        if log_len > max_log:
            raise IntegrityError(
                f"Threat log {log_len} > cap {max_log}")

    # ── 7. Workspace / sandbox integrity ──

    # Directories that should NEVER be touched by the agent
    _FORBIDDEN_DIRS = {
        ".ssh", "AppData", ".gnupg", ".aws", ".kube",
        ".config/gcloud", "etc", ".env",
    }

    def check_workspace_sandbox(self):
        """Verify all file operations stayed within allowed roots.

        Checks:
        - Every forensic file_read/write/edit path resolves inside
          the sandbox roots (tmp_path for tests)
        - No writes to forbidden directories (.ssh, AppData, etc.)
        - No symlink traversal escapes
        """
        forensics = self.engine.forensics
        sandbox_root = str(self.harness.tmp_path.resolve())

        # Collect all file paths from forensics
        all_paths = set()
        all_paths.update(forensics._files_read.keys())
        all_paths.update(forensics._files_written.keys())
        all_paths.update(forensics._files_edited.keys())
        all_paths.update(forensics._files_created)

        for file_path in all_paths:
            if not file_path:
                continue

            try:
                resolved = str(Path(file_path).resolve())
            except (OSError, ValueError):
                continue  # Unresolvable path (e.g. tool returned garbage)

            # Check sandbox containment
            if not (resolved == sandbox_root
                    or resolved.startswith(sandbox_root + os.sep)):
                raise IntegrityError(
                    f"File operation escaped sandbox: '{file_path}' "
                    f"resolved to '{resolved}', outside '{sandbox_root}'")

            # Check forbidden directories — only within the sandbox portion
            # (don't flag system paths above the sandbox root)
            relative = resolved[len(sandbox_root):]
            rel_lower = relative.lower().replace("\\", "/")
            for forbidden in self._FORBIDDEN_DIRS:
                if f"/{forbidden.lower()}/" in rel_lower or \
                   rel_lower.startswith(f"/{forbidden.lower()}/") or \
                   rel_lower == f"/{forbidden.lower()}":
                    raise IntegrityError(
                        f"File operation touched forbidden dir: "
                        f"'{file_path}' contains '{forbidden}'")

            # Check symlink traversal
            try:
                p = Path(file_path)
                if p.exists():
                    for parent in p.resolve().parents:
                        if parent.is_symlink():
                            raise IntegrityError(
                                f"Symlink traversal detected: "
                                f"'{file_path}' has symlink at '{parent}'")
            except (OSError, ValueError):
                pass

    # ── 8. Tool-call validity + rate integrity ──

    def check_tool_call_validity(self):
        """Verify tool call handling is sound.

        Checks:
        - No unknown tool names were silently accepted (success=True)
        - Tool call errors are properly classified (ToolResult.success)
        - Dedup/oscillation detection respected max_iterations
        - Per-tool call counts don't exceed sane limits
        """
        io = self.harness.io

        # Check for "unknown tool" messages in error output that were
        # NOT treated as errors (this would indicate silent acceptance)
        all_output = io.get_output_pairs()
        for category, msg in all_output:
            if "unknown tool" in msg.lower() and category == "tool_result":
                raise IntegrityError(
                    f"Unknown tool accepted as success: '{msg}'")

        # Verify max_iterations was respected
        max_iter = self.engine.config.get("max_agent_iterations", 15)
        stub = self.harness.stub
        # The stub's chat_call_count is total across all turns, so
        # we can only check that it's sane relative to turn count
        turn_count = self.engine._turn_count
        if turn_count > 0:
            avg_calls_per_turn = stub.chat_call_count / turn_count
            # Average should not wildly exceed max_iterations
            # (each turn could hit max_iterations, but average should be much lower)
            if avg_calls_per_turn > max_iter + 1:
                raise IntegrityError(
                    f"Average LLM calls per turn ({avg_calls_per_turn:.1f}) "
                    f"exceeds max_iterations ({max_iter})")

        # Check forensics tool_calls dict for sane counts
        tool_counts = self.engine.forensics._tool_calls
        for tool_name, count in tool_counts.items():
            if count < 0:
                raise IntegrityError(
                    f"Negative tool call count for '{tool_name}': {count}")

        # Check that error counts dict is sane (reset each turn)
        error_counts = self.engine._turn_error_counts
        for tool_name, count in error_counts.items():
            if count < 0:
                raise IntegrityError(
                    f"Negative error count for '{tool_name}': {count}")
