"""Adaptive Pressure event bridge — bundled internal subscriber.

Observes file.read, file.write, turn.end, and context.swap events and
feeds them into the engine's AdaptivePressure session profile.  The
profile is then used by Crucible's scenario runner to generate workload-
specific adversarial test cases.

Not a ForgePlugin subclass — wired directly by the engine during init
via ``register_adaptive_pressure_handlers()``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from forge.event_bus import ForgeEvent, ForgeEventBus

log = logging.getLogger(__name__)


def register_adaptive_pressure_handlers(
    bus: "ForgeEventBus",
    engine: Any,
) -> None:
    """Subscribe adaptive pressure observation handlers to *bus*.

    Initialises ``engine.adaptive_pressure`` (an :class:`AdaptivePressure`
    instance) and keeps its session profile in sync with live events.

    Args:
        bus:    The engine's ForgeEventBus instance.
        engine: The ForgeEngine instance (attribute ``adaptive_pressure``
                is set here if not already present).
    """
    from forge.adaptive_pressure import AdaptivePressure

    if not hasattr(engine, "adaptive_pressure"):
        engine.adaptive_pressure = AdaptivePressure(max_scenarios=3)
        log.debug("AdaptivePressure instance created on engine.")

    ap = engine.adaptive_pressure

    def on_session_start(event: "ForgeEvent") -> None:
        ap.reset()

    def on_file_read(event: "ForgeEvent") -> None:
        path = event.data.get("path", "")
        if path:
            ap.observe_file_read(path)

    def on_file_write(event: "ForgeEvent") -> None:
        path = event.data.get("path", "")
        if path:
            ap.observe_file_write(path)

    def on_turn_end(event: "ForgeEvent") -> None:
        tc = event.data.get("tool_calls_count", 0)
        ap.observe_turn_end(tool_calls_count=tc)

    def on_context_swap(event: "ForgeEvent") -> None:
        ap.observe_context_swap()

    bus.subscribe("session.start",  on_session_start, priority=60)
    bus.subscribe("file.read",      on_file_read,     priority=60)
    bus.subscribe("file.write",     on_file_write,    priority=60)
    bus.subscribe("turn.end",       on_turn_end,      priority=60)
    bus.subscribe("context.swap",   on_context_swap,  priority=60)

    log.debug("Adaptive pressure event bridge registered.")
