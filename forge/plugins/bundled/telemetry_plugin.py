"""Telemetry event bridge — bundled internal subscriber.

Listens for session.end on the ForgeEventBus and triggers the telemetry
upload if enabled.  Keeps upload logic in forge/telemetry.py; this is
just the event-driven wiring so engine.py doesn't call upload_telemetry()
directly at every exit path.

Not a ForgePlugin subclass — wired directly by the engine during init
via register_telemetry_handlers() because it needs access to engine
attributes (forensics, memory, stats, billing, etc.).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from forge.event_bus import ForgeEvent, ForgeEventBus

log = logging.getLogger(__name__)


def register_telemetry_handlers(
    bus: "ForgeEventBus",
    engine: Any,
) -> None:
    """Subscribe telemetry upload handler to *bus*.

    The handler fires on ``session.end`` and calls ``upload_telemetry()``
    if telemetry is enabled in config.  All the heavy lifting stays in
    ``forge.telemetry.upload_telemetry()``.

    Args:
        bus:    The engine's ForgeEventBus instance.
        engine: The ForgeEngine instance (provides forensics, config, etc.).
    """

    def on_session_end(event: "ForgeEvent") -> None:
        if not engine.config.get("telemetry_enabled", False):
            return

        try:
            from forge.telemetry import upload_telemetry
            upload_telemetry(
                forensics=engine.forensics,
                memory=engine.memory,
                stats=engine.stats,
                billing=engine.billing,
                crucible=engine.crucible,
                continuity=engine.continuity,
                plan_verifier=engine.plan_verifier,
                reliability=engine.reliability,
                session_start=engine._session_start,
                turn_count=engine._turn_count,
                model=engine.llm.model,
                cwd=engine.cwd,
                redact=engine.config.get("telemetry_redact", True),
                telemetry_url=engine.config.get("telemetry_url", ""),
                blocking=False,
            )
        except Exception:
            log.debug("Telemetry upload failed", exc_info=True)

    bus.subscribe("session.end", on_session_end, priority=95)
    log.debug("Telemetry event bridge registered.")
