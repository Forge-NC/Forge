"""Forge Event Schema Registry — canonical event schemas and version tracking.

Every event emitted on the ForgeEventBus has a ``schema`` field populated
from this registry.  The schema string is the stable data contract between
the engine and all consumers (plugins, telemetry, fleet analytics, assurance).

Schema string format:  ``forge.{event_type}.v{N}``
Example:               ``forge.turn.end.v1``

Rules
-----
1.  Never silently rename or remove a field from an existing schema.
2.  To add a new field, add it as optional (``required: False``) — existing
    consumers that don't know the field simply ignore it.  No version bump
    needed.
3.  To change a field's type, meaning, or remove it → bump the version:
    ``forge.turn.end.v2``.  Old consumers on v1 continue to work; they
    declare which schema version they consume.
4.  New event types start at v1 and are added here before the first emit.

Canonical field names (no drift allowed)
-----------------------------------------
*token counts*:  ``tokens_prompt`` (in), ``tokens_generated`` (out)
*file paths*:    ``path`` (never ``file_path`` or ``filename``)
*percentages*:   floats 0.0–1.0 (never 0–100 integers in event payloads)
*latencies*:     ``latency_ms`` (int, milliseconds)
*timestamps*:    ``timestamp`` on the event itself; ``ts`` in sub-dicts

Changelog
---------
v1  2026-03-05  Initial schema definitions for all Phase 1-4 events.
"""

from __future__ import annotations

import re

# ── Schema definitions ────────────────────────────────────────────────────────
# Each entry:
#   version   — current integer version (bump when breaking changes required)
#   schema    — the canonical schema string stamped onto ForgeEvent.schema
#   fields    — {name: {type, required, description}}  (documentation only)
#   changelog — list of (version, date, summary) tuples

_REGISTRY: dict[str, dict] = {

    # ── Session lifecycle ─────────────────────────────────────────────────
    "session.start": {
        "version": 1,
        "schema":  "forge.session.start.v1",
        "fields": {
            "session_id":     {"type": "str",  "required": True,  "desc": "Unique session UUID"},
            "model":          {"type": "str",  "required": True,  "desc": "Primary model name"},
            "cwd":            {"type": "str",  "required": False, "desc": "Working directory"},
            "config_summary": {"type": "dict", "required": False, "desc": "Non-sensitive config snapshot"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    "session.end": {
        "version": 1,
        "schema":  "forge.session.end.v1",
        "fields": {
            "session_id":        {"type": "str",   "required": True,  "desc": "Session UUID"},
            "turns":             {"type": "int",   "required": False, "desc": "Total turns completed"},
            "tokens_prompt":     {"type": "int",   "required": False, "desc": "Total prompt tokens"},
            "tokens_generated":  {"type": "int",   "required": False, "desc": "Total generated tokens"},
            "duration_s":        {"type": "float", "required": False, "desc": "Session wall-clock seconds"},
            "tool_calls":        {"type": "int",   "required": False, "desc": "Total tool calls this session"},
            "files_modified":    {"type": "int",   "required": False, "desc": "Number of distinct files written"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    # ── Turn lifecycle ────────────────────────────────────────────────────
    "turn.start": {
        "version": 1,
        "schema":  "forge.turn.start.v1",
        "fields": {
            "turn_id":            {"type": "int",   "required": True,  "desc": "1-based turn counter"},
            "user_input_preview": {"type": "str",   "required": False, "desc": "First 100 chars of input"},
            "context_pct":        {"type": "float", "required": False, "desc": "Context usage 0.0–1.0"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    "turn.end": {
        "version": 1,
        "schema":  "forge.turn.end.v1",
        "fields": {
            "turn_id":           {"type": "int",   "required": True,  "desc": "1-based turn counter"},
            "tokens_prompt":     {"type": "int",   "required": False, "desc": "Prompt tokens this turn"},
            "tokens_generated":  {"type": "int",   "required": False, "desc": "Generated tokens this turn"},
            "duration_ms":       {"type": "int",   "required": False, "desc": "Turn wall-clock milliseconds"},
            "tool_calls_count":  {"type": "int",   "required": False, "desc": "Tool calls this turn"},
            "had_errors":        {"type": "bool",  "required": False, "desc": "Any errors during turn"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    # ── Model events ──────────────────────────────────────────────────────
    "model.request": {
        "version": 1,
        "schema":  "forge.model.request.v1",
        "fields": {
            "model":        {"type": "str",   "required": True,  "desc": "Model being called"},
            "tokens_prompt": {"type": "int",  "required": False, "desc": "Prompt tokens"},
            "context_pct":  {"type": "float", "required": False, "desc": "Context usage 0.0–1.0"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    "model.response": {
        "version": 1,
        "schema":  "forge.model.response.v1",
        "fields": {
            "model":             {"type": "str",  "required": True,  "desc": "Model that responded"},
            "tokens_generated":  {"type": "int",  "required": False, "desc": "Generated tokens"},
            "latency_ms":        {"type": "int",  "required": False, "desc": "Time to first token + full gen"},
            "had_tool_calls":    {"type": "bool", "required": False, "desc": "Response contained tool calls"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    "model.switch": {
        "version": 1,
        "schema":  "forge.model.switch.v1",
        "fields": {
            "from_model": {"type": "str", "required": True,  "desc": "Model before switch"},
            "to_model":   {"type": "str", "required": True,  "desc": "Model after switch"},
            "reason":     {"type": "str", "required": False, "desc": "Why the switch occurred"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    # ── Tool events ───────────────────────────────────────────────────────
    "tool.call": {
        "version": 1,
        "schema":  "forge.tool.call.v1",
        "fields": {
            "tool_name":    {"type": "str",  "required": True,  "desc": "Registered tool name"},
            "args_summary": {"type": "str",  "required": False, "desc": "Short args preview"},
            "turn_id":      {"type": "int",  "required": False, "desc": "Turn in which call was made"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    "tool.result": {
        "version": 1,
        "schema":  "forge.tool.result.v1",
        "fields": {
            "tool_name":   {"type": "str",  "required": True,  "desc": "Registered tool name"},
            "success":     {"type": "bool", "required": True,  "desc": "Did tool complete without error"},
            "latency_ms":  {"type": "int",  "required": False, "desc": "Tool execution time"},
            "output_size": {"type": "int",  "required": False, "desc": "Length of result string"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    "tool.error": {
        "version": 1,
        "schema":  "forge.tool.error.v1",
        "fields": {
            "tool_name":  {"type": "str", "required": True,  "desc": "Registered tool name"},
            "error_type": {"type": "str", "required": False, "desc": "Exception class name"},
            "error_msg":  {"type": "str", "required": False, "desc": "Error message (sanitised)"},
            "turn_id":    {"type": "int", "required": False, "desc": "Turn in which error occurred"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    # ── File events ───────────────────────────────────────────────────────
    "file.read": {
        "version": 1,
        "schema":  "forge.file.read.v1",
        "fields": {
            "path":   {"type": "str",  "required": True,  "desc": "Absolute file path"},
            "tokens": {"type": "int",  "required": False, "desc": "Estimated token count"},
            "cached": {"type": "bool", "required": False, "desc": "Served from file cache"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    "file.write": {
        "version": 1,
        "schema":  "forge.file.write.v1",
        "fields": {
            "path":    {"type": "str",  "required": True,  "desc": "Absolute file path"},
            "created": {"type": "bool", "required": False, "desc": "True if new file, False if overwrite"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    # ── Security events ───────────────────────────────────────────────────
    "threat.detected": {
        "version": 1,
        "schema":  "forge.threat.detected.v1",
        "fields": {
            "source":   {"type": "str", "required": True,  "desc": "Origin (file path or '<llm_output>')"},
            "rule":     {"type": "str", "required": False, "desc": "Crucible rule / pattern name"},
            "level":    {"type": "str", "required": False, "desc": "Severity: SUSPICIOUS|WARNING|CRITICAL"},
            "category": {"type": "str", "required": False, "desc": "Threat category"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    "safety.prompt": {
        "version": 1,
        "schema":  "forge.safety.prompt.v1",
        "fields": {
            "action":      {"type": "str", "required": True,  "desc": "What was prompted (run_shell, write_file, etc.)"},
            "path_or_cmd": {"type": "str", "required": False, "desc": "Target path or command (sanitised)"},
            "level":       {"type": "int", "required": False, "desc": "Safety level that triggered prompt"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    "safety.decision": {
        "version": 1,
        "schema":  "forge.safety.decision.v1",
        "fields": {
            "action":  {"type": "str",  "required": True,  "desc": "Action that was decided on"},
            "allowed": {"type": "bool", "required": True,  "desc": "Was the action allowed"},
            "by_user": {"type": "bool", "required": False, "desc": "Decision came from user prompt"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    # ── Context events ────────────────────────────────────────────────────
    "context.pressure": {
        "version": 1,
        "schema":  "forge.context.pressure.v1",
        "fields": {
            "used_pct":  {"type": "float", "required": True,  "desc": "Context usage 0.0–1.0"},
            "threshold": {"type": "float", "required": False, "desc": "Swap threshold percentage (integer)"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    "context.swap": {
        "version": 1,
        "schema":  "forge.context.swap.v1",
        "fields": {
            "freed_tokens":  {"type": "int", "required": False, "desc": "Tokens freed by the swap"},
            "pre_entries":   {"type": "int", "required": False, "desc": "Context entries before swap"},
            "post_entries":  {"type": "int", "required": False, "desc": "Context entries after swap"},
            "swaps_total":   {"type": "int", "required": False, "desc": "Cumulative swaps this session"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    # ── Plan events ───────────────────────────────────────────────────────
    "plan.created": {
        "version": 1,
        "schema":  "forge.plan.created.v1",
        "fields": {
            "step_count":  {"type": "int", "required": False, "desc": "Number of plan steps"},
            "model_used":  {"type": "str", "required": False, "desc": "Model that generated the plan"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    "plan.approved": {
        "version": 1,
        "schema":  "forge.plan.approved.v1",
        "fields": {
            "method": {"type": "str", "required": False, "desc": "'auto' or 'user'"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    "plan.complete": {
        "version": 1,
        "schema":  "forge.plan.complete.v1",
        "fields": {
            "steps":      {"type": "int",   "required": False, "desc": "Total steps executed"},
            "duration_s": {"type": "float", "required": False, "desc": "Wall-clock seconds"},
            "all_passed": {"type": "bool",  "required": False, "desc": "All steps passed verification"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    # ── Infrastructure events (Phase 2-4) ─────────────────────────────────
    "fingerprint.drift": {
        "version": 1,
        "schema":  "forge.fingerprint.drift.v1",
        "fields": {
            "model":     {"type": "str",   "required": True,  "desc": "Model being fingerprinted"},
            "dimension": {"type": "str",   "required": True,  "desc": "Behavioral dimension name"},
            "delta":     {"type": "float", "required": True,  "desc": "Score change (current - baseline)"},
            "baseline":  {"type": "float", "required": False, "desc": "Baseline score"},
            "current":   {"type": "float", "required": False, "desc": "Current score"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    "challenge.received": {
        "version": 1,
        "schema":  "forge.challenge.received.v1",
        "fields": {
            "challenge_id":      {"type": "str",   "required": True,  "desc": "Server-issued challenge ID"},
            "probe_prompt":      {"type": "str",   "required": True,  "desc": "Prompt to run through LLM"},
            "expected_category": {"type": "str",   "required": True,  "desc": "Expected response category"},
            "nonce":             {"type": "str",   "required": True,  "desc": "Anti-replay nonce"},
            "expires_at":        {"type": "float", "required": True,  "desc": "Unix timestamp expiry"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    "challenge.complete": {
        "version": 1,
        "schema":  "forge.challenge.complete.v1",
        "fields": {
            "challenge_id":      {"type": "str",  "required": True,  "desc": "Challenge ID"},
            "success":           {"type": "bool", "required": True,  "desc": "Proof was generated and submitted"},
            "latency_ms":        {"type": "int",  "required": False, "desc": "Inference latency"},
            "tokens_generated":  {"type": "int",  "required": False, "desc": "Tokens in response"},
            "response_category": {"type": "str",  "required": False, "desc": "Classified response category"},
            "server_accepted":   {"type": "bool", "required": False, "desc": "Server accepted the proof"},
        },
        "changelog": [(1, "2026-03-05", "Initial definition")],
    },

    # ── Break/Assurance progress ─────────────────────────────────────────
    "break.progress": {
        "version": 1,
        "schema":  "forge.break.progress.v1",
        "fields": {
            "current":     {"type": "int",  "required": True,  "desc": "Completed scenario count"},
            "total":       {"type": "int",  "required": True,  "desc": "Total scenarios in run"},
            "scenario_id": {"type": "str",  "required": True,  "desc": "Scenario that just completed"},
            "passed":      {"type": "bool", "required": True,  "desc": "Did the scenario pass"},
            "pct":         {"type": "int",  "required": False, "desc": "Completion percentage 0-100"},
        },
        "changelog": [(1, "2026-03-12", "Initial definition — break progress tracking")],
    },

    # ── XP events ─────────────────────────────────────────────────────
    "xp.awarded": {
        "version": 1,
        "schema":  "forge.xp.awarded.v1",
        "fields": {
            "action":    {"type": "str", "required": True,  "desc": "XP action key (break_complete, etc.)"},
            "xp":        {"type": "int", "required": True,  "desc": "XP amount awarded"},
            "total_xp":  {"type": "int", "required": False, "desc": "New total XP"},
            "level":     {"type": "int", "required": False, "desc": "Current level after award"},
        },
        "changelog": [(1, "2026-03-11", "Initial definition — XP gamification")],
    },

    "xp.level_up": {
        "version": 1,
        "schema":  "forge.xp.level_up.v1",
        "fields": {
            "old_level": {"type": "int", "required": True,  "desc": "Previous level"},
            "new_level": {"type": "int", "required": True,  "desc": "New level"},
            "title":     {"type": "str", "required": False, "desc": "Title unlocked (if any)"},
        },
        "changelog": [(1, "2026-03-11", "Initial definition — XP gamification")],
    },

    "xp.achievement": {
        "version": 1,
        "schema":  "forge.xp.achievement.v1",
        "fields": {
            "achievement_id": {"type": "str", "required": True,  "desc": "Achievement ID"},
            "name":           {"type": "str", "required": True,  "desc": "Achievement display name"},
            "bonus_xp":       {"type": "int", "required": True,  "desc": "Bonus XP awarded"},
        },
        "changelog": [(1, "2026-03-11", "Initial definition — XP gamification")],
    },

    # ── CommonSenseGuard events ──────────────────────────────────────
    "common_sense.warning": {
        "version": 1,
        "schema":  "forge.common_sense.warning.v1",
        "fields": {
            "category":  {"type": "str",  "required": True,  "desc": "Warning category (e.g. scope_creep, stuck_loop)"},
            "message":   {"type": "str",  "required": True,  "desc": "Human-readable warning message"},
            "severity":  {"type": "str",  "required": True,  "desc": "info|warning|error"},
            "turn":      {"type": "int",  "required": False, "desc": "Turn number when warning was raised"},
            "files":     {"type": "list", "required": False, "desc": "Affected file paths (if any)"},
            "tool":      {"type": "str",  "required": False, "desc": "Tool name involved (if any)"},
        },
        "changelog": [(1, "2026-03-10", "Initial definition — CommonSenseGuard plugin")],
    },
}


# ── SchemaRegistry ────────────────────────────────────────────────────────────

class SchemaRegistry:
    """Canonical event schema registry — single source of truth.

    Usage::

        schema = SchemaRegistry.schema_for("turn.end")
        # → "forge.turn.end.v1"

        fields = SchemaRegistry.fields_for("turn.end")
        # → {"turn_id": {"type": "int", ...}, ...}

        # Check for unknown event types during development
        if not SchemaRegistry.knows("my.custom.event"):
            log.warning("Unregistered event type")
    """

    @staticmethod
    def schema_for(event_type: str) -> str:
        """Return the canonical schema string for *event_type*.

        Unknown event types return ``"forge.unknown.v0"`` — they are accepted
        but flagged in debug logs so you can register them.
        """
        entry = _REGISTRY.get(event_type)
        if entry is None:
            return f"forge.unknown.v0"
        return entry["schema"]

    @staticmethod
    def version_for(event_type: str) -> int:
        """Return the current integer version for *event_type*, or 0 if unknown."""
        entry = _REGISTRY.get(event_type)
        return entry["version"] if entry else 0

    @staticmethod
    def fields_for(event_type: str) -> dict:
        """Return the field definitions dict for *event_type*, or empty dict."""
        entry = _REGISTRY.get(event_type)
        return dict(entry["fields"]) if entry else {}

    @staticmethod
    def knows(event_type: str) -> bool:
        """Return True if *event_type* is registered."""
        return event_type in _REGISTRY

    @staticmethod
    def all_event_types() -> list[str]:
        """Return all registered event type strings, sorted."""
        return sorted(_REGISTRY.keys())

    @staticmethod
    def changelog_for(event_type: str) -> list[tuple]:
        """Return the changelog list for *event_type*, newest first."""
        entry = _REGISTRY.get(event_type)
        if not entry:
            return []
        return list(reversed(entry.get("changelog", [])))


# Module-level convenience
def schema_for(event_type: str) -> str:
    """Convenience alias for ``SchemaRegistry.schema_for()``."""
    return SchemaRegistry.schema_for(event_type)
