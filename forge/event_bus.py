"""Forge in-process event bus.

Lightweight publish/subscribe system for Forge lifecycle events.
Engine emits events; plugins and internal subsystems subscribe to observe them.

Usage::

    bus = ForgeEventBus()

    def on_turn(event: ForgeEvent) -> None:
        print(event.data["turn_id"])

    bus.subscribe("turn.end", on_turn)
    bus.emit("turn.end", {"turn_id": 3, "tokens_generated": 120})

    # Wildcard — receives every event
    bus.subscribe("*", lambda ev: log.debug("event: %s", ev.event_type))

    # Enable replay log (appends JSONL to path)
    bus.set_event_log(Path("~/.forge/events/session_abc.jsonl"))

Handler exceptions are caught and logged; they never propagate to the emitter.

Schema versioning
-----------------
Every event carries a ``schema`` field auto-stamped from :mod:`forge.schema_registry`.
The schema string is the stable data contract, e.g. ``"forge.turn.end.v1"``.
When schemas change in a breaking way, the version number increments and old
consumers that don't know the new version continue to work uninterrupted.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

# Type alias for clarity
EventHandler = Callable[["ForgeEvent"], None]


@dataclass
class ForgeEvent:
    """A single lifecycle event emitted by the Forge engine."""

    event_type: str
    """Dot-namespaced event name, e.g. ``"turn.end"`` or ``"threat.detected"``."""

    data: dict
    """Event-specific payload.  Keys are documented in forge/schema_registry.py."""

    timestamp: float = field(default_factory=time.time)
    """Unix timestamp when the event was created."""

    session_id: str = ""
    """Session identifier, set automatically by ``ForgeEventBus.emit()``."""

    schema: str = ""
    """Canonical schema string, e.g. ``"forge.turn.end.v1"``.
    Auto-populated from :mod:`forge.schema_registry` on emit.
    Consumers that need schema-version-aware behaviour should check this field.
    """

    def to_dict(self) -> dict:
        """Serialise to a plain dict (for JSONL replay log)."""
        return {
            "schema":     self.schema,
            "event_type": self.event_type,
            "timestamp":  self.timestamp,
            "session_id": self.session_id,
            "data":       self.data,
        }

    def __repr__(self) -> str:
        return (f"<ForgeEvent {self.event_type} "
                f"schema={self.schema} "
                f"session={self.session_id[:8] or '?'}>")


class ForgeEventBus:
    """In-process publish/subscribe event bus.

    Thread-safe.  All public methods may be called from any thread.

    Subscription model
    ------------------
    - Subscribe with an exact event type (``"turn.end"``) to receive only that event.
    - Subscribe with ``"*"`` to receive every event.
    - Multiple handlers per event type are supported, ordered by *priority*
      (lower integer = runs first, default = 50).

    Emission model
    --------------
    - ``emit()``       — synchronous; all handlers run before returning.
    - ``emit_async()`` — fire-and-forget via a thread pool; use for non-critical
      observers (telemetry shipping, dashboard updates) to avoid blocking the engine.

    Error isolation
    ---------------
    Handler exceptions are caught, logged with a WARNING, and never re-raised.
    A single bad handler cannot disrupt the engine or other subscribers.

    Schema versioning
    -----------------
    Every emitted event has its ``schema`` field auto-populated from
    :mod:`forge.schema_registry`.  Unknown event types receive the schema
    ``"forge.unknown.v0"`` and a debug-level warning.

    Event replay log
    ----------------
    Call ``set_event_log(path)`` to enable JSONL logging.  Every event is
    appended as a JSON line.  Replay with::

        for line in open("session.jsonl"):
            event_dict = json.loads(line)
            # re-emit, analyse, or debug
    """

    def __init__(self, max_async_workers: int = 2) -> None:
        # {event_type: [(priority, handler), ...]}  sorted ascending by priority
        self._handlers: dict[str, list[tuple[int, EventHandler]]] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_async_workers,
            thread_name_prefix="ForgeEventBus",
        )
        self._session_id: str = ""
        self._log_path: Path | None = None
        self._log_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Session tracking
    # ------------------------------------------------------------------

    def set_session_id(self, session_id: str) -> None:
        """Set the current session ID, stamped onto every subsequent event."""
        self._session_id = session_id

    # ------------------------------------------------------------------
    # Event replay log
    # ------------------------------------------------------------------

    def set_event_log(self, path: Path | None) -> None:
        """Enable (or disable) JSONL event logging.

        When *path* is set, every emitted event is appended as one JSON line.
        Pass ``None`` to disable.  The file is created if it doesn't exist.

        Args:
            path: Absolute path for the JSONL file, or None to disable.
        """
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_lock:
            self._log_path = path
        if path:
            log.debug("Event replay log: %s", path)

    def _write_log(self, event: ForgeEvent) -> None:
        """Append *event* to the replay log (if enabled).  Never raises."""
        with self._log_lock:
            path = self._log_path
        if path is None:
            return
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict(), default=str) + "\n")
        except Exception as exc:
            log.debug("Event log write failed: %s", exc)

    # ------------------------------------------------------------------
    # Subscription
    # ------------------------------------------------------------------

    def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
        priority: int = 50,
    ) -> None:
        """Register *handler* to be called when *event_type* is emitted.

        Args:
            event_type: Exact event name (e.g. ``"turn.end"``) or ``"*"``
                        for all events.
            handler:    Callable that accepts a single :class:`ForgeEvent`.
            priority:   Lower runs first.  Default is 50.
        """
        with self._lock:
            bucket = self._handlers.setdefault(event_type, [])
            bucket.append((priority, handler))
            bucket.sort(key=lambda x: x[0])

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Remove *handler* from *event_type*.  No-op if not found."""
        with self._lock:
            bucket = self._handlers.get(event_type, [])
            self._handlers[event_type] = [
                (p, h) for p, h in bucket if h is not handler
            ]

    # ------------------------------------------------------------------
    # Emission
    # ------------------------------------------------------------------

    def emit(self, event_type: str, data: dict, session_id: str = "") -> None:
        """Emit an event synchronously.

        The ``schema`` field is auto-populated from :mod:`forge.schema_registry`.
        All subscribers run (in priority order) before this method returns.
        """
        event = self._build_event(event_type, data, session_id)
        self._write_log(event)
        self._dispatch(event)

    def emit_async(
        self, event_type: str, data: dict, session_id: str = ""
    ) -> None:
        """Emit an event asynchronously (fire-and-forget).

        Returns immediately; handlers run in a background thread pool.
        Use for observers that don't need to block the engine (telemetry,
        dashboard, logging).
        """
        event = self._build_event(event_type, data, session_id)
        self._write_log(event)
        try:
            self._executor.submit(self._dispatch, event)
        except RuntimeError:
            # Executor shut down (process exit) — fall back to sync
            self._dispatch(event)

    def _build_event(
        self, event_type: str, data: dict, session_id: str
    ) -> ForgeEvent:
        """Construct a ForgeEvent with schema auto-stamped."""
        try:
            from forge.schema_registry import schema_for
            schema = schema_for(event_type)
            if schema == "forge.unknown.v0":
                log.debug(
                    "Unregistered event type '%s' — add to forge/schema_registry.py",
                    event_type,
                )
        except ImportError:
            schema = ""

        return ForgeEvent(
            event_type=event_type,
            data=data,
            session_id=session_id or self._session_id,
            schema=schema,
        )

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Remove all subscriptions.  Primarily for test teardown."""
        with self._lock:
            self._handlers.clear()
        self._session_id = ""

    def shutdown(self) -> None:
        """Shut down the async thread pool.  Call at process exit."""
        self._executor.shutdown(wait=False)

    # ------------------------------------------------------------------
    # Internal dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, event: ForgeEvent) -> None:
        """Run all handlers registered for *event.event_type* plus wildcard."""
        with self._lock:
            # Specific handlers + wildcard handlers, preserving priority sort
            specific  = list(self._handlers.get(event.event_type, []))
            wildcards = list(self._handlers.get("*", []))

        # Merge and re-sort by priority so wildcard handlers interleave correctly
        combined = sorted(specific + wildcards, key=lambda x: x[0])

        for priority, handler in combined:
            try:
                handler(event)
            except Exception:
                log.warning(
                    "ForgeEventBus: handler %r raised on event '%s'",
                    handler,
                    event.event_type,
                    exc_info=True,
                )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def handler_count(self, event_type: str = None) -> int:
        """Return number of registered handlers, optionally filtered by type."""
        with self._lock:
            if event_type is not None:
                return len(self._handlers.get(event_type, []))
            return sum(len(v) for v in self._handlers.values())

    def __repr__(self) -> str:
        with self._lock:
            types = len(self._handlers)
            total = sum(len(v) for v in self._handlers.values())
        log_status = str(self._log_path) if self._log_path else "off"
        return (f"<ForgeEventBus event_types={types} handlers={total} "
                f"log={log_status}>")
