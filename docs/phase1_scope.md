# Phase 1 — Detailed Implementation Scope
# Event Bus + Plugin Lifecycle Events

> Status: Ready to implement
> Depends on: nothing (this is the foundation)
> Breaks existing behavior: NO — fully backward compatible
> Tests required: yes (test_event_bus.py, test_plugin_events.py)

---

## New File: forge/event_bus.py

```python
@dataclass
class ForgeEvent:
    event_type: str
    data: dict
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""

class ForgeEventBus:
    def subscribe(self, event_type: str, handler: Callable[[ForgeEvent], None],
                  priority: int = 50) -> None
    def unsubscribe(self, event_type: str, handler: Callable) -> None
    def emit(self, event_type: str, data: dict, session_id: str = "") -> None
        # Fires synchronously. Handler exceptions are caught+logged, never propagate.
        # Supports wildcard: subscribers to "*" receive all events.
    def emit_async(self, event_type: str, data: dict, session_id: str = "") -> None
        # Thread-pool fire-and-forget for non-critical observers (telemetry, dashboard).
    def clear(self) -> None  # for test teardown
```

Internals:
  - _handlers: dict[str, list[tuple[int, Callable]]]  (sorted by priority)
  - _lock: threading.RLock  (handler list is modified rarely, read frequently)
  - _executor: ThreadPoolExecutor(max_workers=2)  (for emit_async only)

---

## Modified File: forge/plugins/base.py

Add these new observer methods to ForgePlugin (all no-ops in base — override to use):

```python
# Which event types this plugin wants. Empty list = all events via on_event.
# Set this on the class to opt in to specific events (performance filter).
event_subscriptions: list[str] = []

def on_event(self, event: "ForgeEvent") -> None:
    """Catch-all event observer. Called for ALL events if event_subscriptions is empty."""

def on_session_start(self, data: dict) -> None:
    """Session began. data: {session_id, model, cwd, config_summary}"""

def on_session_end(self, data: dict) -> None:
    """Session ended. data: {session_id, turns, tokens_prompt, tokens_generated,
       duration_s, tool_calls, files_modified}"""

def on_turn_start(self, data: dict) -> None:
    """Turn began. data: {turn_id, user_input_preview, context_pct}"""

def on_turn_end(self, data: dict) -> None:
    """Turn ended. data: {turn_id, tokens_prompt, tokens_generated, duration_ms,
       tool_calls_count, had_errors}"""

def on_model_switch(self, from_model: str, to_model: str) -> None:
    """Model router switched models."""

def on_context_pressure(self, used_pct: float, data: dict) -> None:
    """Context window is filling up. data: {used_pct, tokens_used, tokens_max}"""

def on_threat_detected(self, threat: dict) -> None:
    """Crucible detected a threat. data: {level, rule, source, preview, action}"""
```

Update get_info() to include event_subscriptions in the returned dict.

---

## Modified File: forge/plugins/__init__.py

### Add to PluginManager.__init__:
```python
self._bundled_dir = Path(__file__).parent / "bundled"
```

### Update discover() to load bundled dir first:
```python
def discover(self) -> list[type[ForgePlugin]]:
    self._discovered.clear()
    # Load bundled plugins first (ship with Forge, always available)
    if self._bundled_dir.is_dir():
        for py_file in sorted(self._bundled_dir.glob("*.py")):
            if not py_file.name.startswith("_"):
                try:
                    self._discovered.extend(self._import_plugin_file(py_file))
                except Exception:
                    log.warning("Failed to import bundled plugin '%s'", py_file.name,
                                exc_info=True)
    # Then load user plugins (can override bundled behavior via priority)
    if self._plugin_dir.is_dir():
        for py_file in sorted(self._plugin_dir.glob("*.py")):
            ...  # existing logic unchanged
```

### Add dispatch_event():
```python
def dispatch_event(self, event: "ForgeEvent") -> None:
    """Route a ForgeEvent to all plugins that subscribed to it."""
    for plugin in self._loaded:
        # Skip if plugin declared specific subscriptions and this isn't one
        subs = getattr(plugin, "event_subscriptions", [])
        if subs and event.event_type not in subs and "*" not in subs:
            continue
        # Call specific handler if it exists and is overridden
        specific = f"on_{event.event_type.replace('.', '_')}"
        if _overrides_hook(plugin, specific):
            try:
                getattr(plugin, specific)(event.data)
            except Exception:
                self._record_plugin_error(plugin, specific)
        # Always call on_event if overridden
        if _overrides_hook(plugin, "on_event"):
            try:
                plugin.on_event(event)
            except Exception:
                self._record_plugin_error(plugin, "on_event")
```

### Update _RestrictedEngineProxy._ALLOWED:
```python
_ALLOWED = frozenset({
    "tool_registry",
    "config",
    "cache",
    "queue_prompt",
    "event_bus",   # ADD THIS — plugins can subscribe but not emit
})
```

---

## Modified File: forge/engine.py

### In __init__, after plugin manager setup (~line 388):
```python
# Event bus — in-process pub/sub for lifecycle events
from forge.event_bus import ForgeEventBus
self.event_bus = ForgeEventBus()
# Wire plugin manager to dispatch events from bus
self.event_bus.subscribe(
    "*",
    lambda ev: self.plugin_manager.dispatch_event(ev),
    priority=90  # plugins run after internal subscribers
)
```

### In run() — session lifecycle (~line 1014):
At session start (after model check, before main loop):
```python
self.event_bus.emit("session.start", {
    "session_id": self._session_id,
    "model": self.llm.model,
    "cwd": self.cwd,
    "config_summary": {
        "safety_level": self.safety.level,
        "plan_mode": self.planner.mode,
        "router_enabled": self.router.enabled,
    },
})
```

At session end (in finally block):
```python
self.event_bus.emit("session.end", {
    "session_id": self._session_id,
    "turns": self._turn_count,
    "tokens_prompt": self._total_prompt_tokens,   # track this
    "tokens_generated": self._total_generated,
    "duration_s": time.time() - self._session_start,
    "tool_calls": self._session_tool_count,        # track this
    "files_modified": list(self._session_files),
})
```

### In _agent_loop() — turn lifecycle (~line 1553):
At turn start:
```python
self.event_bus.emit("turn.start", {
    "turn_id": self._turn_count,
    "user_input_preview": user_input[:100] if user_input else "",
    "context_pct": round(self.ctx.usage_pct() * 100, 1),
})
```

At turn end (after billing record):
```python
self.event_bus.emit("turn.end", {
    "turn_id": self._turn_count,
    "tokens_prompt": self._turn_prompt_tokens,
    "tokens_generated": self._turn_eval_count,
    "duration_ms": int((time.time() - turn_start) * 1000),
    "tool_calls_count": len(self._current_turn_tools),
    "had_errors": bool(self._turn_error_counts),
})
```

After LLM response received:
```python
self.event_bus.emit("model.response", {
    "model": self.llm.model,
    "response_tokens": self._turn_eval_count,
    "duration_ms": llm_duration_ms,
    "had_tool_calls": bool(tool_calls),
})
```

### In _cached_read_file / _cached_write_file:
```python
# In _cached_read_file, after cache check:
self.event_bus.emit_async("file.read", {"path": file_path, "cached": is_cached})

# In _cached_write_file, before return:
self.event_bus.emit_async("file.write", {"path": file_path, "size": len(content)})
```

### In _scan_llm_output / _scan_recall_content:
```python
# When Crucible fires, emit the threat event too:
self.event_bus.emit("threat.detected", {
    "level": str(threat.level),
    "rule": threat.rule_id,
    "source": source,
    "preview": threat.snippet[:80],
    "action": action_taken,
})
```

### In _auto_context_swap:
```python
# Before swap:
self.event_bus.emit("context.pressure", {
    "used_pct": ctx_pct,
    "tokens_used": self.ctx._total_tokens,
    "tokens_max": self.ctx.max_tokens,
    "swap_imminent": ctx_pct > self.config.get("swap_threshold_pct", 90) / 100,
})
# After swap:
self.event_bus.emit("context.swap", {
    "turns_preserved": preserved_turns,
    "tokens_before": tokens_before,
    "tokens_after": self.ctx._total_tokens,
})
```

### In router model switch (wherever router.switch() is called):
```python
old_model = self.llm.model
# ... switch logic ...
self.event_bus.emit("model.switch", {
    "from_model": old_model,
    "to_model": self.llm.model,
    "reason": switch_reason,
})
```

---

## New File: forge/plugins/bundled/__init__.py
(empty — just marks it as a package)

---

## New File: forge/plugins/bundled/telemetry_plugin.py

```python
class TelemetryPlugin(ForgePlugin):
    name = "Forge Telemetry"
    version = "1.0.0"
    description = "Collects session telemetry and ships signed bundles to fleet."
    author = "Forge Team"
    event_subscriptions = ["session.end", "turn.end", "threat.detected"]

    def on_session_end(self, data: dict) -> None:
        # Format + ship telemetry bundle (wraps existing forge/telemetry.py logic)
        ...

    def on_threat_detected(self, data: dict) -> None:
        # Append to session threat log for bundle
        ...
```

This wraps the existing telemetry.py functionality. Nothing changes in behavior —
this just moves it from engine.py hardcode to an event subscriber.

---

## New File: forge/plugins/bundled/cortex_plugin.py

```python
class NeuralCortexPlugin(ForgePlugin):
    name = "Neural Cortex"
    version = "1.0.0"
    description = "Drives Neural Cortex state display."
    author = "Forge Team"
    event_subscriptions = [
        "session.start", "turn.start", "turn.end",
        "model.switch", "threat.detected", "context.pressure"
    ]

    def on_turn_start(self, data: dict) -> None:
        # Write "thinking" state to cortex
        ...

    def on_turn_end(self, data: dict) -> None:
        # Write "idle" state
        ...

    def on_threat_detected(self, data: dict) -> None:
        # Write "threat" state
        ...

    def on_context_pressure(self, data: dict) -> None:
        # Write "pressure" state, intensity based on used_pct
        ...
```

---

## New File: tests/test_event_bus.py

Tests:
- subscribe + emit — handler called with correct event
- multiple subscribers same event — all called
- priority ordering — lower priority number runs first
- wildcard subscription — receives all events
- handler exception isolation — one bad handler doesn't kill others
- emit_async — fires without blocking
- unsubscribe — handler no longer called
- clear() — all handlers removed (test isolation)

---

## New File: tests/test_plugin_events.py

Tests:
- Engine emits session.start on run()
- Engine emits session.end in finally
- Engine emits turn.start, turn.end for each turn
- Engine emits file.read on _cached_read_file
- Engine emits file.write on _cached_write_file
- Engine emits threat.detected when Crucible fires
- Plugin's on_session_start is called when session.start emitted
- Bundled plugins loaded before user plugins
- event_subscriptions filter works (plugin with ["session.end"] not called for "turn.start")

---

## Implementation Order (within Phase 1)

1. forge/event_bus.py — standalone, no dependencies
2. tests/test_event_bus.py — verify bus in isolation before wiring
3. forge/plugins/base.py — add new hooks (no behavior change, just new no-ops)
4. forge/plugins/__init__.py — add dispatch_event + bundled dir loading
5. forge/plugins/bundled/__init__.py
6. forge/engine.py — wire bus, add emits (session + turn lifecycle first)
7. forge/plugins/bundled/telemetry_plugin.py
8. forge/plugins/bundled/cortex_plugin.py
9. forge/engine.py — add remaining emits (file, threat, context, model switch)
10. tests/test_plugin_events.py
11. Run full test suite — all 1,318+ tests must pass

---

## What We Are NOT Doing in Phase 1

- NOT migrating Crucible to a plugin (it's synchronous/blocking — stays direct)
- NOT migrating Safety to a plugin (same reason)
- NOT migrating Shipwright or AutoForge to plugins (Phase 2 candidate)
- NOT changing the public plugin hook API (on_user_input, on_response, etc.)
- NOT breaking existing ~/.forge/plugins/ user plugins
- NOT restructuring engine.py method layout (just adding emits + bus init)
- NOT reducing engine.py line count significantly — that's a Phase 2+ goal

Phase 1 is additive. The bus sits alongside everything. Nothing breaks.
