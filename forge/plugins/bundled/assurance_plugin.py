"""Assurance event bridge — bundled internal subscriber.

Subscribes to ``session.end`` on the ForgeEventBus.  If ``auto_assurance``
is enabled in config, runs a minimal 3-scenario assurance check and logs
a warning if any scenario fails.  This is the background-passive variant;
the full interactive ``/assure`` command is handled by commands.py.

Not a ForgePlugin subclass — wired directly by the engine during init
via ``register_assurance_handlers()`` because it needs ``engine.llm``,
``engine.config``, and ``engine.config_dir``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from forge.event_bus import ForgeEvent, ForgeEventBus

log = logging.getLogger(__name__)

# Minimal 3-scenario suite for background auto-assurance.
# Deliberately lightweight — completes in seconds, non-blocking.
_AUTO_ASSURANCE_CATEGORIES = ["reliability", "adversarial"]


def register_assurance_handlers(
    bus: "ForgeEventBus",
    engine: Any,
) -> None:
    """Subscribe auto-assurance handler to *bus*.

    The handler fires on ``session.end`` and runs a minimal assurance
    check if ``auto_assurance: true`` is set in config.  Results are
    logged but never block the session exit.

    Args:
        bus:    The engine's ForgeEventBus instance.
        engine: The ForgeEngine instance (provides llm, config, config_dir).
    """

    def on_session_end(event: "ForgeEvent") -> None:
        if not engine.config.get("auto_assurance", False):
            return

        try:
            from forge.assurance import AssuranceRunner
            from pathlib import Path

            config_dir = Path(getattr(engine, "config_dir",
                                      Path.home() / ".forge"))
            machine_id  = getattr(engine, "_machine_id", "") or ""
            bpos = getattr(engine, "bpos", None)
            passport_id = ""
            if bpos and hasattr(bpos, "_passport") and bpos._passport:
                passport_id = bpos._passport.passport_id or ""

            runner = AssuranceRunner(
                config_dir=config_dir,
                machine_id=machine_id,
                passport_id=passport_id,
            )
            tier = bpos.tier if bpos else "community"
            run = runner.run(
                engine.llm, engine.llm.model,
                categories=_AUTO_ASSURANCE_CATEGORIES,
                self_rate=engine.config.get("assurance_self_rate", False),
                tier=tier,
            )
            failures = [r for r in run.results if not r.passed]
            if failures:
                log.warning(
                    "Auto-assurance: %d/%d scenario(s) failed for '%s': %s",
                    len(failures), len(run.results), engine.llm.model,
                    [r.scenario_id for r in failures],
                )
            else:
                log.info(
                    "Auto-assurance: all %d scenarios passed for '%s'.",
                    len(run.results), engine.llm.model,
                )
        except Exception:
            log.debug("Auto-assurance check failed", exc_info=True)

    bus.subscribe("session.end", on_session_end, priority=90)
    log.debug("Assurance event bridge registered.")
