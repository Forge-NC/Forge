"""XP event bridge — bundled internal subscriber.

Listens for session.end, challenge.complete, and other events on the
ForgeEventBus to automatically award XP.  The heavy lifting lives in
forge/xp.py; this is just the event-driven wiring.

Not a ForgePlugin subclass — wired directly by the engine during init
via register_xp_handlers() because it needs access to engine attributes.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from forge.event_bus import ForgeEvent, ForgeEventBus

log = logging.getLogger(__name__)


def register_xp_handlers(
    bus: "ForgeEventBus",
    engine: Any,
) -> None:
    """Subscribe XP award handlers to *bus*.

    Args:
        bus:    The engine's ForgeEventBus instance.
        engine: The ForgeEngine instance (provides xp_engine, config, etc.).
    """

    def on_session_end(event: "ForgeEvent") -> None:
        xp = getattr(engine, 'xp_engine', None)
        if not xp:
            return
        if not engine.config.get("xp_enabled", False):
            return

        duration_s = event.data.get("duration_s", 0)
        turns = event.data.get("turns", 0)

        try:
            xp.record_session_end(duration_s, turns)
        except Exception:
            log.debug("XP session_end award failed", exc_info=True)

    def on_challenge_complete(event: "ForgeEvent") -> None:
        xp = getattr(engine, 'xp_engine', None)
        if not xp:
            return
        if not engine.config.get("xp_enabled", False):
            return

        if event.data.get("success"):
            try:
                xp.record_poi()
            except Exception:
                log.debug("XP poi award failed", exc_info=True)

    def on_telemetry_uploaded(event: "ForgeEvent") -> None:
        """Award XP when telemetry is successfully uploaded."""
        xp = getattr(engine, 'xp_engine', None)
        if not xp:
            return
        if not engine.config.get("xp_enabled", False):
            return

        try:
            xp.record_telemetry()
        except Exception:
            log.debug("XP telemetry award failed", exc_info=True)

    bus.subscribe("session.end", on_session_end, priority=85)
    bus.subscribe("challenge.complete", on_challenge_complete, priority=85)
    # Telemetry uploads are handled by the telemetry plugin; we piggyback
    # on session.end and check if telemetry is enabled to award that XP.
    # (The telemetry_plugin fires on session.end at priority=95, so we
    # fire after it at priority=96.)
    def on_session_end_telemetry(event: "ForgeEvent") -> None:
        xp = getattr(engine, 'xp_engine', None)
        if not xp:
            return
        if not engine.config.get("xp_enabled", False):
            return
        if engine.config.get("telemetry_enabled", False):
            try:
                xp.record_telemetry()
            except Exception:
                log.debug("XP telemetry award failed", exc_info=True)

    bus.subscribe("session.end", on_session_end_telemetry, priority=96)

    log.debug("XP event bridge registered.")
