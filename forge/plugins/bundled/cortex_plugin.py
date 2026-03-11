"""Neural Cortex event bridge — bundled internal subscriber.

Translates ForgeEventBus events into dashboard state writes so the
Neural Cortex display stays in sync without engine.py calling
_write_dashboard_state() manually at every call site.

Not a ForgePlugin subclass — wired directly by the engine during init
via register_cortex_handlers() because it needs access to engine internals
(config_dir, _write_dashboard_state).  External plugins use ForgePlugin.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from forge.event_bus import ForgeEvent, ForgeEventBus

log = logging.getLogger(__name__)


def register_cortex_handlers(
    bus: "ForgeEventBus",
    write_state_fn: Callable[[str, dict | None], None],
) -> None:
    """Subscribe cortex state handlers to *bus*.

    Args:
        bus:            The engine's ForgeEventBus instance.
        write_state_fn: Bound reference to engine._write_dashboard_state(state, extra).
    """

    def on_session_start(event: "ForgeEvent") -> None:
        write_state_fn("boot", None)

    def on_turn_start(event: "ForgeEvent") -> None:
        write_state_fn("thinking", None)

    def on_turn_end(event: "ForgeEvent") -> None:
        data = event.data
        had_errors = data.get("had_errors", False)
        write_state_fn("error" if had_errors else "idle", None)

    def on_tool_call(event: "ForgeEvent") -> None:
        write_state_fn("tool_exec", {
            "tool": event.data.get("tool", ""),
        })

    def on_model_switch(event: "ForgeEvent") -> None:
        write_state_fn("indexing", {
            "from": event.data.get("from_model", ""),
            "to": event.data.get("to_model", ""),
        })

    def on_context_pressure(event: "ForgeEvent") -> None:
        pct = event.data.get("used_pct", 0.0)
        if pct >= 0.85:
            write_state_fn("swapping", {"context_pct": round(pct * 100, 1)})

    def on_context_swap(event: "ForgeEvent") -> None:
        import threading as _t
        write_state_fn("recovering", {"freed_tokens": event.data.get("freed_tokens", 0)})
        # Hold "recovering" for 2s then return to idle
        def _revert():
            import time as _time
            _time.sleep(2)
            write_state_fn("idle", None)
        _t.Thread(target=_revert, daemon=True, name="recovering-revert").start()

    def on_threat_detected(event: "ForgeEvent") -> None:
        write_state_fn("threat", {
            "rule": event.data.get("rule", ""),
            "level": event.data.get("level", ""),
        })

    def on_assurance_pass(event: "ForgeEvent") -> None:
        import threading as _t
        write_state_fn("pass", {"score": event.data.get("score", 0)})
        # Revert to idle after 4s so the PASS glow doesn't stick forever
        def _revert():
            import time as _time
            _time.sleep(4)
            write_state_fn("idle", None)
        _t.Thread(target=_revert, daemon=True, name="pass-revert").start()

    def on_session_end(event: "ForgeEvent") -> None:
        write_state_fn("idle", None)

    bus.subscribe("session.start",    on_session_start,    priority=80)
    bus.subscribe("turn.start",       on_turn_start,       priority=80)
    bus.subscribe("turn.end",         on_turn_end,         priority=80)
    bus.subscribe("tool.call",        on_tool_call,        priority=80)
    bus.subscribe("model.switch",     on_model_switch,     priority=80)
    bus.subscribe("context.pressure", on_context_pressure, priority=80)
    bus.subscribe("context.swap",     on_context_swap,     priority=80)
    bus.subscribe("threat.detected",  on_threat_detected,  priority=80)
    bus.subscribe("assurance.pass",   on_assurance_pass,   priority=80)
    bus.subscribe("session.end",      on_session_end,      priority=80)

    log.debug("NeuralCortex event bridge registered.")
