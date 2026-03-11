"""Unit tests for ForgeEventBus — Phase 1 deferred tests.

Tests cover: subscribe, emit (sync + async), wildcard dispatch,
error isolation, priority ordering, session_id stamping, schema
auto-stamping, JSONL replay log, and handler_count introspection.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from forge.event_bus import ForgeEvent, ForgeEventBus


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def bus():
    b = ForgeEventBus()
    yield b
    b.shutdown()


# ── Basic subscribe / emit ─────────────────────────────────────────────────────

def test_emit_calls_subscriber(bus):
    received = []
    bus.subscribe("turn.end", lambda e: received.append(e))
    bus.emit("turn.end", {"turn_id": 1})
    assert len(received) == 1
    assert received[0].event_type == "turn.end"
    assert received[0].data["turn_id"] == 1


def test_emit_unknown_type_does_not_crash(bus):
    bus.emit("totally.unknown.event", {"foo": "bar"})


def test_no_subscribers_is_no_op(bus):
    bus.emit("session.start", {"session_id": "abc"})  # must not raise


def test_multiple_subscribers_all_called(bus):
    counts = [0, 0]
    bus.subscribe("turn.end", lambda e: counts.__setitem__(0, counts[0] + 1))
    bus.subscribe("turn.end", lambda e: counts.__setitem__(1, counts[1] + 1))
    bus.emit("turn.end", {"turn_id": 2})
    assert counts == [1, 1]


# ── Wildcard subscription ──────────────────────────────────────────────────────

def test_wildcard_receives_all_events(bus):
    received_types = []
    bus.subscribe("*", lambda e: received_types.append(e.event_type))
    bus.emit("turn.start", {})
    bus.emit("session.end", {})
    bus.emit("tool.call", {})
    assert received_types == ["turn.start", "session.end", "tool.call"]


def test_wildcard_and_specific_both_fire(bus):
    log = []
    bus.subscribe("*",       lambda e: log.append("wildcard"))
    bus.subscribe("turn.end", lambda e: log.append("specific"))
    bus.emit("turn.end", {})
    assert "wildcard" in log
    assert "specific" in log


# ── Priority ordering ─────────────────────────────────────────────────────────

def test_lower_priority_runs_first(bus):
    order = []
    bus.subscribe("turn.end", lambda e: order.append("high"),   priority=10)
    bus.subscribe("turn.end", lambda e: order.append("low"),    priority=90)
    bus.subscribe("turn.end", lambda e: order.append("default"))  # 50
    bus.emit("turn.end", {})
    assert order == ["high", "default", "low"]


# ── Error isolation ───────────────────────────────────────────────────────────

def test_handler_exception_does_not_propagate(bus):
    def bad_handler(e):
        raise RuntimeError("intentional test error")

    bus.subscribe("turn.end", bad_handler)
    # Must not raise
    bus.emit("turn.end", {})


def test_subsequent_handlers_still_run_after_exception(bus):
    called = []
    bus.subscribe("turn.end", lambda e: (_ for _ in ()).throw(ValueError("boom")))
    bus.subscribe("turn.end", lambda e: called.append(True), priority=90)
    bus.emit("turn.end", {})
    assert called == [True]


# ── Schema auto-stamping ───────────────────────────────────────────────────────

def test_known_event_gets_schema_stamped(bus):
    received = []
    bus.subscribe("turn.end", lambda e: received.append(e))
    bus.emit("turn.end", {"turn_id": 1})
    assert received[0].schema == "forge.turn.end.v1"


def test_unknown_event_gets_unknown_schema(bus):
    received = []
    bus.subscribe("custom.thing", lambda e: received.append(e))
    bus.emit("custom.thing", {})
    assert received[0].schema == "forge.unknown.v0"


# ── Session ID stamping ───────────────────────────────────────────────────────

def test_session_id_stamped_on_events(bus):
    bus.set_session_id("sess-abc-123")
    received = []
    bus.subscribe("turn.end", lambda e: received.append(e))
    bus.emit("turn.end", {})
    assert received[0].session_id == "sess-abc-123"


def test_explicit_session_id_overrides_bus_default(bus):
    bus.set_session_id("default-session")
    received = []
    bus.subscribe("turn.end", lambda e: received.append(e))
    bus.emit("turn.end", {}, session_id="override-session")
    assert received[0].session_id == "override-session"


# ── Async emission ─────────────────────────────────────────────────────────────

def test_emit_async_eventually_calls_handler(bus):
    received = []
    event_done = threading.Event()

    def handler(e):
        received.append(e)
        event_done.set()

    bus.subscribe("session.start", handler)
    bus.emit_async("session.start", {"model": "test"})
    event_done.wait(timeout=2.0)
    assert len(received) == 1


# ── Replay log ────────────────────────────────────────────────────────────────

def test_replay_log_written(tmp_path, bus):
    log_path = tmp_path / "events.jsonl"
    bus.set_event_log(log_path)
    bus.emit("turn.end", {"turn_id": 99})
    bus.emit("session.start", {"session_id": "x"})

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["event_type"] == "turn.end"
    assert first["data"]["turn_id"] == 99


def test_replay_log_disabled_by_default(tmp_path, bus):
    bus.emit("turn.end", {"turn_id": 1})
    # No log should be created
    assert not any(tmp_path.glob("*.jsonl"))


def test_replay_log_can_be_disabled(tmp_path, bus):
    log_path = tmp_path / "events.jsonl"
    bus.set_event_log(log_path)
    bus.emit("turn.end", {"turn_id": 1})
    bus.set_event_log(None)   # disable
    bus.emit("turn.end", {"turn_id": 2})

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1   # only the first event


# ── Unsubscribe ───────────────────────────────────────────────────────────────

def test_unsubscribe_stops_calls(bus):
    called = []
    handler = lambda e: called.append(True)
    bus.subscribe("turn.end", handler)
    bus.emit("turn.end", {})
    assert called == [True]
    bus.unsubscribe("turn.end", handler)
    bus.emit("turn.end", {})
    assert called == [True]  # not called again


# ── Clear ─────────────────────────────────────────────────────────────────────

def test_clear_removes_all_subscriptions(bus):
    received = []
    bus.subscribe("turn.end", lambda e: received.append(e))
    bus.subscribe("*",        lambda e: received.append(e))
    bus.clear()
    bus.emit("turn.end", {})
    assert received == []


# ── handler_count ─────────────────────────────────────────────────────────────

def test_handler_count_all(bus):
    bus.subscribe("turn.end",    lambda e: None)
    bus.subscribe("session.end", lambda e: None)
    bus.subscribe("turn.end",    lambda e: None)
    assert bus.handler_count() == 3


def test_handler_count_filtered(bus):
    bus.subscribe("turn.end",    lambda e: None)
    bus.subscribe("session.end", lambda e: None)
    bus.subscribe("turn.end",    lambda e: None)
    assert bus.handler_count("turn.end") == 2
    assert bus.handler_count("session.end") == 1


# ── ForgeEvent.to_dict ────────────────────────────────────────────────────────

def test_forge_event_to_dict_roundtrip():
    ev = ForgeEvent(
        event_type="turn.end",
        data={"turn_id": 5},
        session_id="sess-1",
        schema="forge.turn.end.v1",
    )
    d = ev.to_dict()
    assert d["event_type"] == "turn.end"
    assert d["data"]["turn_id"] == 5
    assert d["session_id"] == "sess-1"
    assert d["schema"] == "forge.turn.end.v1"
    assert json.dumps(d)  # must be JSON-serialisable


# ── Thread safety ─────────────────────────────────────────────────────────────

def test_concurrent_emits_do_not_crash(bus):
    """Rapid concurrent emits from multiple threads must not deadlock or crash."""
    errors = []

    def emit_many():
        try:
            for _ in range(50):
                bus.emit("turn.end", {"turn_id": 1})
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=emit_many) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert errors == [], f"Concurrent emit errors: {errors}"
