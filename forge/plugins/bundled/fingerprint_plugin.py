"""Behavioral Fingerprint event bridge — bundled internal subscriber.

Subscribes to ``session.start`` on the ForgeEventBus.  Runs the 30-probe
behavioral fingerprint suite in a background thread (never blocks the
session).  Compares results to the stored baseline and emits
``fingerprint.drift`` events for any dimension that has shifted beyond
the configured threshold.

Not a ForgePlugin subclass — wired directly by the engine during init
via ``register_fingerprint_handlers()`` because it needs access to
``engine.llm``, ``engine.config``, and ``engine.config_dir``.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from forge.event_bus import ForgeEvent, ForgeEventBus

log = logging.getLogger(__name__)


def register_fingerprint_handlers(
    bus: "ForgeEventBus",
    engine: Any,
) -> None:
    """Subscribe behavioral fingerprint handler to *bus*.

    The handler fires on ``session.start`` and launches a daemon thread to
    run the probe suite so the session is never blocked.  Drift events are
    emitted back onto the bus if any dimension shifts by more than the
    configured threshold.

    Args:
        bus:    The engine's ForgeEventBus instance.
        engine: The ForgeEngine instance (provides llm, config, config_dir).
    """

    def _run_fingerprint(model: str) -> None:
        """Background worker — probe the model and emit drift events."""
        try:
            from forge.behavioral_fingerprint import (
                BehavioralFingerprint,
                DRIFT_ALERT_DELTA,
            )

            config_dir = Path(getattr(engine, "config_dir",
                                      Path.home() / ".forge"))
            fp = BehavioralFingerprint(config_dir=config_dir)

            log.info("Behavioral fingerprint: probing '%s' ...", model)
            scores = fp.run_probes(engine.llm, model)
            log.info(
                "Fingerprint complete for '%s': %s",
                model,
                {k: round(v, 2) for k, v in scores.items()},
            )

            baseline  = fp.load_baseline(model)
            is_first  = baseline is None
            fp.save_fingerprint(model, scores, is_baseline=is_first)

            if is_first:
                log.info("First behavioral fingerprint recorded for '%s' "
                         "(baseline set).", model)
                return

            drift       = fp.compute_drift(baseline, scores)
            significant = fp.significant_drifts(drift)

            for dim, delta in significant.items():
                bus.emit("fingerprint.drift", {
                    "model":     model,
                    "dimension": dim,
                    "delta":     delta,
                    "baseline":  baseline.get(dim, 0.0),
                    "current":   scores.get(dim, 0.0),
                })
                level = "ALERT" if abs(delta) >= DRIFT_ALERT_DELTA else "WARN"
                log.warning(
                    "Behavioral drift [%s] model='%s' dim='%s' delta=%.3f",
                    level, model, dim, delta,
                )

            if not significant:
                log.info("No significant behavioral drift detected for '%s'.",
                         model)

        except Exception:
            log.debug("Behavioral fingerprinting failed", exc_info=True)

    def on_session_start(event: "ForgeEvent") -> None:
        if not engine.config.get("behavioral_fingerprint", True):
            return
        model = event.data.get("model", "")
        if not model:
            return
        t = threading.Thread(
            target=_run_fingerprint,
            args=(model,),
            daemon=True,
            name="forge-fingerprint",
        )
        t.start()

    bus.subscribe("session.start", on_session_start, priority=70)
    log.debug("Behavioral fingerprint bridge registered.")
