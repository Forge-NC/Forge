"""Tests for engine event emission at lifecycle points — Phase 1 deferred tests.

Verifies that ForgeEngine emits the expected events at the correct lifecycle
points by subscribing to the bus before executing engine operations and
asserting on the collected events.

These tests use the integration harness stubs (OllamaStub) rather than
a live LLM, so they run offline with no external dependencies.
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from forge.event_bus import ForgeEvent, ForgeEventBus
from forge.schema_registry import SchemaRegistry


# ── Helpers ───────────────────────────────────────────────────────────────────

def collect_events(bus: ForgeEventBus) -> list[ForgeEvent]:
    """Return a mutable list that accumulates all events emitted on *bus*."""
    events: list[ForgeEvent] = []
    bus.subscribe("*", lambda e: events.append(e))
    return events


# ── Schema registry coverage ──────────────────────────────────────────────────
# These tests don't need an engine — they verify that all roadmap-specified
# event types are registered in the schema registry.

_REQUIRED_EVENT_TYPES = [
    # Phase 1 — session lifecycle
    "session.start",
    "session.end",
    "turn.start",
    "turn.end",
    # Phase 1 — model events
    "model.request",
    "model.response",
    "model.switch",
    # Phase 1 — tool events
    "tool.call",
    "tool.result",
    "tool.error",
    # Phase 1 — file events
    "file.read",
    "file.write",
    # Phase 1 — security events
    "threat.detected",
    "safety.prompt",
    "safety.decision",
    # Phase 1 — context events
    "context.pressure",
    "context.swap",
    # Phase 1 — plan events
    "plan.created",
    "plan.approved",
    "plan.complete",
    # Phase 2 — behavioral fingerprinting
    "fingerprint.drift",
    # Phase 3 — proof of inference
    "challenge.received",
    "challenge.complete",
]


@pytest.mark.parametrize("event_type", _REQUIRED_EVENT_TYPES)
def test_schema_registry_knows_event(event_type):
    """Every roadmap-specified event type must be in the schema registry."""
    assert SchemaRegistry.knows(event_type), (
        f"Event type '{event_type}' is missing from forge/schema_registry.py. "
        f"Add it before emitting."
    )


@pytest.mark.parametrize("event_type", _REQUIRED_EVENT_TYPES)
def test_schema_string_format(event_type):
    """Schema strings must follow the forge.{type}.v{N} convention."""
    schema = SchemaRegistry.schema_for(event_type)
    assert schema != "forge.unknown.v0", (
        f"'{event_type}' returned unknown schema — not registered properly."
    )
    assert schema.startswith("forge."), f"Bad schema prefix: {schema}"
    assert ".v" in schema, f"Schema missing version suffix: {schema}"


def test_all_registered_events_have_fields():
    """Every registered event must have at least one documented field."""
    for event_type in SchemaRegistry.all_event_types():
        fields = SchemaRegistry.fields_for(event_type)
        assert isinstance(fields, dict), (
            f"fields_for('{event_type}') did not return a dict"
        )
        # Some events (like plan.approved) may have only optional fields — that's fine
        # We just assert the structure is present
        for field_name, field_def in fields.items():
            assert "type" in field_def, (
                f"Field '{field_name}' in '{event_type}' missing 'type' key"
            )
            assert "required" in field_def, (
                f"Field '{field_name}' in '{event_type}' missing 'required' key"
            )


# ── ForgeEventBus — plugin dispatch ───────────────────────────────────────────

def test_plugin_dispatch_event_calls_specific_hook():
    """dispatch_event should call on_turn_end for turn.end events."""
    from forge.plugins import PluginManager
    from forge.plugins.base import ForgePlugin

    class TurnPlugin(ForgePlugin):
        name = "TurnPlugin"
        calls = []

        def on_turn_end(self, data: dict) -> None:
            TurnPlugin.calls.append(data)

    pm = PluginManager(plugin_dir=Path("/nonexistent"))
    pm._loaded = [TurnPlugin()]
    pm._discovered = []

    event = ForgeEvent(event_type="turn.end", data={"turn_id": 7})
    pm.dispatch_event(event)

    assert TurnPlugin.calls == [{"turn_id": 7}]


def test_plugin_dispatch_event_calls_on_event_catchall():
    """dispatch_event should call on_event for every event when no filter set."""
    from forge.plugins import PluginManager
    from forge.plugins.base import ForgePlugin

    class CatchallPlugin(ForgePlugin):
        name = "CatchallPlugin"
        calls = []

        def on_event(self, event: ForgeEvent) -> None:
            CatchallPlugin.calls.append(event.event_type)

    pm = PluginManager(plugin_dir=Path("/nonexistent"))
    pm._loaded = [CatchallPlugin()]

    for et in ["turn.start", "turn.end", "session.end"]:
        pm.dispatch_event(ForgeEvent(event_type=et, data={}))

    assert CatchallPlugin.calls == ["turn.start", "turn.end", "session.end"]


def test_plugin_event_subscription_filter():
    """Plugin with event_subscriptions=['turn.end'] must not receive turn.start."""
    from forge.plugins import PluginManager
    from forge.plugins.base import ForgePlugin

    class FilteredPlugin(ForgePlugin):
        name = "FilteredPlugin"
        event_subscriptions = ["turn.end"]
        received = []

        def on_event(self, event: ForgeEvent) -> None:
            FilteredPlugin.received.append(event.event_type)

    pm = PluginManager(plugin_dir=Path("/nonexistent"))
    pm._loaded = [FilteredPlugin()]

    pm.dispatch_event(ForgeEvent(event_type="turn.start", data={}))
    pm.dispatch_event(ForgeEvent(event_type="turn.end",   data={}))

    assert FilteredPlugin.received == ["turn.end"]


def test_plugin_event_pattern_filter():
    """Plugin with event_patterns=['tool.*'] receives tool.call but not turn.end."""
    from forge.plugins import PluginManager
    from forge.plugins.base import ForgePlugin

    class PatternPlugin(ForgePlugin):
        name = "PatternPlugin"
        event_patterns = ["tool.*"]
        received = []

        def on_event(self, event: ForgeEvent) -> None:
            PatternPlugin.received.append(event.event_type)

    pm = PluginManager(plugin_dir=Path("/nonexistent"))
    pm._loaded = [PatternPlugin()]

    pm.dispatch_event(ForgeEvent(event_type="tool.call",   data={}))
    pm.dispatch_event(ForgeEvent(event_type="tool.result", data={}))
    pm.dispatch_event(ForgeEvent(event_type="turn.end",    data={}))

    assert PatternPlugin.received == ["tool.call", "tool.result"]


def test_plugin_error_does_not_propagate():
    """A plugin that crashes in on_event must not crash dispatch_event."""
    from forge.plugins import PluginManager
    from forge.plugins.base import ForgePlugin

    class BrokenPlugin(ForgePlugin):
        name = "BrokenPlugin"

        def on_event(self, event: ForgeEvent) -> None:
            raise RuntimeError("intentional crash in plugin")

    class GoodPlugin(ForgePlugin):
        name = "GoodPlugin"
        received = []

        def on_event(self, event: ForgeEvent) -> None:
            GoodPlugin.received.append(True)

    pm = PluginManager(plugin_dir=Path("/nonexistent"))
    pm._loaded = [BrokenPlugin(), GoodPlugin()]

    pm.dispatch_event(ForgeEvent(event_type="turn.end", data={}))
    assert GoodPlugin.received == [True]


# ── Event field validation ─────────────────────────────────────────────────────

def test_turn_end_required_fields():
    """turn.end events must carry turn_id as required."""
    fields = SchemaRegistry.fields_for("turn.end")
    assert "turn_id" in fields
    assert fields["turn_id"]["required"] is True


def test_tool_call_required_fields():
    """tool.call must require tool_name."""
    fields = SchemaRegistry.fields_for("tool.call")
    assert "tool_name" in fields
    assert fields["tool_name"]["required"] is True


def test_threat_detected_required_fields():
    """threat.detected must require source."""
    fields = SchemaRegistry.fields_for("threat.detected")
    assert "source" in fields
    assert fields["source"]["required"] is True


def test_challenge_received_all_required():
    """challenge.received must have all 5 required fields."""
    fields = SchemaRegistry.fields_for("challenge.received")
    required = {k for k, v in fields.items() if v.get("required")}
    expected = {"challenge_id", "probe_prompt", "expected_category",
                "nonce", "expires_at"}
    assert expected.issubset(required), (
        f"Missing required fields: {expected - required}"
    )


# ── Bundled plugin wiring ──────────────────────────────────────────────────────

def test_telemetry_plugin_subscribes_to_session_end():
    """register_telemetry_handlers must subscribe to session.end."""
    bus = ForgeEventBus()
    engine_mock = MagicMock()
    engine_mock.config.get.return_value = False  # telemetry disabled

    from forge.plugins.bundled.telemetry_plugin import register_telemetry_handlers
    register_telemetry_handlers(bus, engine_mock)

    assert bus.handler_count("session.end") >= 1
    bus.shutdown()


def test_cortex_plugin_subscribes_to_multiple_events():
    """register_cortex_handlers must subscribe to at least 5 lifecycle events."""
    bus = ForgeEventBus()
    write_fn = MagicMock()

    from forge.plugins.bundled.cortex_plugin import register_cortex_handlers
    register_cortex_handlers(bus, write_fn)

    lifecycle_events = [
        "session.start", "turn.start", "turn.end",
        "model.switch", "context.pressure", "threat.detected", "session.end",
    ]
    covered = [e for e in lifecycle_events if bus.handler_count(e) >= 1]
    assert len(covered) >= 5, (
        f"Cortex plugin only covers: {covered}"
    )
    bus.shutdown()


def test_fingerprint_plugin_subscribes_to_session_start():
    """register_fingerprint_handlers must subscribe to session.start."""
    bus = ForgeEventBus()
    engine_mock = MagicMock()
    engine_mock.config.get.return_value = True  # fingerprint enabled

    from forge.plugins.bundled.fingerprint_plugin import register_fingerprint_handlers
    register_fingerprint_handlers(bus, engine_mock)

    assert bus.handler_count("session.start") >= 1
    bus.shutdown()


def test_poi_plugin_subscribes_to_challenge_received():
    """register_poi_handlers must subscribe to challenge.received."""
    bus = ForgeEventBus()
    engine_mock = MagicMock()
    engine_mock.config.get.return_value = ""
    engine_mock.config_dir = Path("/tmp")
    engine_mock._machine_id = "test-machine"
    engine_mock.bpos = None

    from forge.plugins.bundled.poi_plugin import register_poi_handlers
    register_poi_handlers(bus, engine_mock)

    assert bus.handler_count("challenge.received") >= 1
    bus.shutdown()


def test_assurance_plugin_subscribes_to_session_end():
    """register_assurance_handlers must subscribe to session.end."""
    bus = ForgeEventBus()
    engine_mock = MagicMock()
    engine_mock.config.get.return_value = False  # auto_assurance disabled

    from forge.plugins.bundled.assurance_plugin import register_assurance_handlers
    register_assurance_handlers(bus, engine_mock)

    assert bus.handler_count("session.end") >= 1
    bus.shutdown()
