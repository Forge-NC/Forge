"""Proof of Inference event bridge — bundled internal subscriber.

Subscribes to ``challenge.received`` on the ForgeEventBus.  Executes the
challenge proof in a background thread (never blocks the session), then
POSTs the signed response to the challenge server and emits
``challenge.complete`` when done.

Not a ForgePlugin subclass — wired directly by the engine during init
via ``register_poi_handlers()`` because it needs access to ``engine.llm``
and the BPoS passport identifiers.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from forge.event_bus import ForgeEvent, ForgeEventBus

log = logging.getLogger(__name__)


def register_poi_handlers(
    bus: "ForgeEventBus",
    engine: Any,
) -> None:
    """Subscribe Proof of Inference handlers to *bus*.

    Initialises a ``ProofOfInference`` instance on *engine* and wires
    the ``challenge.received`` handler.  Challenge execution is always
    off-thread.

    Args:
        bus:    The engine's ForgeEventBus instance.
        engine: The ForgeEngine instance (provides llm, config, bpos).
    """
    from forge.proof_of_inference import ProofOfInference
    from pathlib import Path

    config_dir = Path(getattr(engine, "config_dir", Path.home() / ".forge"))

    # Pull machine / passport IDs from BPoS if available
    bpos = getattr(engine, "bpos", None)
    machine_id  = getattr(engine, "_machine_id", "") or ""
    passport_id = ""
    if bpos and hasattr(bpos, "_passport") and bpos._passport:
        passport_id = bpos._passport.passport_id or ""

    poi = ProofOfInference(
        config_dir=config_dir,
        machine_id=machine_id,
        passport_id=passport_id,
    )
    engine.proof_of_inference = poi

    def _execute_and_report(challenge: dict) -> None:
        """Background worker — run proof, POST result, emit event."""
        try:
            proof = poi.execute_challenge(challenge, engine.llm)
            if proof is None:
                bus.emit("challenge.complete", {
                    "challenge_id": challenge.get("challenge_id", ""),
                    "success":      False,
                    "reason":       "proof generation failed",
                })
                return

            # Attempt to POST the proof to the challenge server
            challenge_url = engine.config.get("challenge_url", "")
            if challenge_url:
                try:
                    import requests
                    resp = requests.post(
                        challenge_url + "/submit",
                        json=proof,
                        timeout=15,
                    )
                    server_ok = resp.status_code == 200
                    log.info("PoI submission: HTTP %d", resp.status_code)
                except Exception as exc:
                    server_ok = False
                    log.warning("PoI server POST failed: %s", exc)
            else:
                server_ok = None   # No server configured — local only

            bus.emit("challenge.complete", {
                "challenge_id":    proof["challenge_id"],
                "success":         True,
                "latency_ms":      proof["latency_ms"],
                "tokens_generated": proof["tokens_generated"],
                "response_category": proof["response_category"],
                "server_accepted": server_ok,
            })

        except Exception:
            log.debug("PoI challenge execution failed", exc_info=True)
            bus.emit("challenge.complete", {
                "challenge_id": challenge.get("challenge_id", ""),
                "success":      False,
                "reason":       "unhandled exception",
            })

    def on_challenge_received(event: "ForgeEvent") -> None:
        challenge = event.data
        if not challenge.get("challenge_id"):
            return
        t = threading.Thread(
            target=_execute_and_report,
            args=(challenge,),
            daemon=True,
            name=f"forge-poi-{challenge['challenge_id'][:8]}",
        )
        t.start()

    bus.subscribe("challenge.received", on_challenge_received, priority=50)
    log.debug("Proof of Inference event bridge registered.")
