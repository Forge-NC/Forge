"""Plugin loader and manager for Forge.

Discovers, loads, and dispatches hooks to ForgePlugin subclasses found
in the user's plugin directory (``~/.forge/plugins/`` by default).

Quick start
-----------
::

    from pathlib import Path
    from forge.plugins import PluginManager

    pm = PluginManager()                       # uses ~/.forge/plugins/
    pm.discover()                              # scan for .py files
    pm.load_all(engine)                        # call on_load for each
    text = pm.dispatch_user_input(user_text)   # run pipeline hooks
    pm.unload_all()                            # clean shutdown

Writing a plugin
----------------
Drop a ``.py`` file in ``~/.forge/plugins/``.  It must contain at least
one class that inherits from ``forge.plugins.base.ForgePlugin``::

    # ~/.forge/plugins/example_plugin.py
    from forge.plugins.base import ForgePlugin

    class ExamplePlugin(ForgePlugin):
        name        = "Example"
        version     = "1.0.0"
        description = "Logs every user message."
        author      = "Your Name"

        def on_user_input(self, text: str) -> str:
            print(f"[Example] user said: {text}")
            return text                    # pass-through
"""

from __future__ import annotations

import fnmatch
import importlib
import importlib.util
import inspect
import logging
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from forge.plugins.base import DEFAULT_PRIORITY, ForgePlugin

if TYPE_CHECKING:
    from forge.event_bus import ForgeEvent

log = logging.getLogger(__name__)

__all__ = ["PluginManager", "ForgePlugin"]

# Auto-disable plugins that crash more than this many times per session
_MAX_PLUGIN_ERRORS = 5


# ======================================================================
# Restricted Engine Proxy
# ======================================================================

class _RestrictedEngineProxy:
    """A sandboxed view of the engine for plugins.

    Plugins receive this instead of the raw engine instance.
    Only safe, read-only attributes are exposed. Prevents malicious
    or buggy plugins from mutating safety levels, disabling Crucible,
    or accessing internal state directly.
    """

    # Attributes/methods plugins may legitimately access.
    # queue_prompt is callable — plugins may inject prompts into the
    # engine's next input slot (e.g. from a background monitor thread).
    # event_bus is exposed so plugins can subscribe to events, but
    # emit() is intentionally not blocked — plugins may emit custom events.
    _ALLOWED = frozenset({
        "tool_registry",    # to register custom tools
        "config",           # read config values
        "cache",            # check file cache
        "queue_prompt",     # inject a prompt (callable)
        "event_bus",        # subscribe to / emit events
    })

    def __init__(self, engine):
        object.__setattr__(self, "_engine", engine)

    def __getattr__(self, name):
        if name in _RestrictedEngineProxy._ALLOWED:
            return getattr(object.__getattribute__(self, "_engine"), name)
        raise AttributeError(
            f"Plugin access denied: '{name}' is not available to plugins. "
            f"Allowed: {', '.join(sorted(_RestrictedEngineProxy._ALLOWED))}")

    def __setattr__(self, name, value):
        raise AttributeError(
            "Plugins cannot modify engine attributes directly.")


# ======================================================================
# Helpers
# ======================================================================

def _hook_priority(plugin: ForgePlugin, hook_name: str) -> int:
    """Return the priority value for a specific hook on *plugin*.

    The priority is read from an attribute set directly on the bound
    method (e.g. ``plugin.on_user_input.priority = 10``).  Falls back
    to ``DEFAULT_PRIORITY`` (50).
    """
    method = getattr(plugin, hook_name, None)
    if method is None:
        return DEFAULT_PRIORITY
    # Check the *unbound* function first (class-level attribute), then
    # the bound method itself.
    fn = getattr(method, "__func__", method)
    return getattr(fn, "priority", DEFAULT_PRIORITY)


def _overrides_hook(plugin: ForgePlugin, hook_name: str) -> bool:
    """Return True if *plugin*'s class overrides *hook_name*."""
    return getattr(type(plugin), hook_name) is not getattr(ForgePlugin, hook_name)


# ======================================================================
# PluginManager
# ======================================================================

class PluginManager:
    """Discovers, loads, and dispatches hooks to Forge plugins."""

    def __init__(self, plugin_dir: Path | None = None):
        if plugin_dir is None:
            plugin_dir = Path.home() / ".forge" / "plugins"
        self._plugin_dir: Path = plugin_dir
        self._bundled_dir: Path = Path(__file__).parent / "bundled"
        self._discovered: list[type[ForgePlugin]] = []
        self._loaded: list[ForgePlugin] = []
        self._lock = threading.RLock()
        self._engine: Any = None

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover(self) -> list[type[ForgePlugin]]:
        """Scan bundled and user plugin directories for ForgePlugin subclasses.

        Bundled plugins (``forge/plugins/bundled/``) are loaded first, then
        user plugins (``~/.forge/plugins/``).  User plugins may override bundled
        behavior by registering handlers with a higher priority.

        Returns the list of discovered plugin classes (does *not* instantiate
        or load them yet).
        """
        self._discovered.clear()

        # 1. Bundled plugins (ship with Forge, always available)
        if self._bundled_dir.is_dir():
            for py_file in sorted(self._bundled_dir.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                try:
                    classes = self._import_plugin_file(py_file)
                    self._discovered.extend(classes)
                    if classes:
                        log.debug(
                            "Bundled plugin: %s (%d class(es))",
                            py_file.name, len(classes),
                        )
                except Exception:
                    log.warning(
                        "Failed to import bundled plugin '%s' -- skipping.",
                        py_file.name,
                        exc_info=True,
                    )

        # 2. User plugins
        if not self._plugin_dir.is_dir():
            log.debug("User plugin directory does not exist: %s", self._plugin_dir)
        else:
            for py_file in sorted(self._plugin_dir.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                try:
                    classes = self._import_plugin_file(py_file)
                    self._discovered.extend(classes)
                except Exception:
                    log.warning(
                        "Failed to import plugin file '%s' -- skipping.",
                        py_file.name,
                        exc_info=True,
                    )

        log.info("Discovered %d plugin class(es) total", len(self._discovered))
        return self._discovered

    def _import_plugin_file(self, path: Path) -> list[type[ForgePlugin]]:
        """Import a single Python file and return ForgePlugin subclasses found in it."""
        module_name = f"forge_plugin_{path.stem}"

        spec = importlib.util.spec_from_file_location(module_name, str(path))
        if spec is None or spec.loader is None:
            log.warning("Cannot create import spec for '%s'", path)
            return []

        module = importlib.util.module_from_spec(spec)
        # Register in sys.modules so relative imports inside the plugin
        # file work (though discouraged).
        sys.modules[module_name] = module

        try:
            spec.loader.exec_module(module)
        except Exception:
            # Clean up the partially-loaded module.
            sys.modules.pop(module_name, None)
            raise

        classes: list[type[ForgePlugin]] = []
        for _attr_name, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, ForgePlugin)
                and obj is not ForgePlugin
                and obj.__module__ == module_name
            ):
                classes.append(obj)

        return classes

    # ------------------------------------------------------------------
    # Loading / Unloading
    # ------------------------------------------------------------------

    def load_all(self, engine: Any) -> None:
        """Instantiate and load all discovered plugins.

        Calls ``on_load(engine)`` on each, then ``register_tools(registry)``
        if the engine exposes a ``tool_registry`` attribute.

        Plugins whose class name appears in the ``disabled_plugins`` config
        list are skipped.  Plugins that raise during load are logged and skipped.
        """
        self._engine = engine

        # Read disabled list from config (if engine has config)
        disabled: set[str] = set()
        config = getattr(engine, "config", None)
        if config is not None:
            raw = config.get("disabled_plugins", [])
            if isinstance(raw, list):
                disabled = {name.strip() for name in raw if isinstance(name, str)}

        for cls in self._discovered:
            if cls.__name__ in disabled:
                log.info("Plugin '%s' is disabled — skipping.", cls.__name__)
                continue
            try:
                plugin = cls()
            except Exception:
                log.warning(
                    "Failed to instantiate plugin %s -- skipping.",
                    cls.__name__,
                    exc_info=True,
                )
                continue

            try:
                proxy = _RestrictedEngineProxy(engine)
                plugin._engine = proxy
                plugin.on_load(proxy)
                plugin._loaded = True
            except Exception:
                log.warning(
                    "Plugin '%s' raised during on_load -- skipping.",
                    plugin.name,
                    exc_info=True,
                )
                continue

            # Let the plugin register custom tools.
            registry = getattr(engine, "tool_registry", None)
            if registry is not None and _overrides_hook(plugin, "register_tools"):
                try:
                    plugin.register_tools(registry)
                except Exception:
                    log.warning(
                        "Plugin '%s' raised during register_tools.",
                        plugin.name,
                        exc_info=True,
                    )

            with self._lock:
                self._loaded.append(plugin)
            log.info("Loaded plugin: %s v%s", plugin.name, plugin.version)

    def unload_all(self) -> None:
        """Unload every loaded plugin (calls ``on_unload`` on each)."""
        with self._lock:
            plugins = list(self._loaded)
        for plugin in reversed(plugins):
            try:
                plugin.on_unload()
            except Exception:
                log.warning(
                    "Plugin '%s' raised during on_unload.",
                    plugin.name,
                    exc_info=True,
                )
            plugin._loaded = False
            plugin._engine = None

        with self._lock:
            count = len(self._loaded)
            self._loaded.clear()
        log.info("Unloaded %d plugin(s).", count)

    def get_loaded(self) -> list[ForgePlugin]:
        """Return a list of currently loaded plugin instances."""
        with self._lock:
            return list(self._loaded)

    def get_discovered(self) -> list[type[ForgePlugin]]:
        """Return all discovered plugin classes (loaded or not)."""
        return list(self._discovered)

    def get_plugin_manifest(self) -> list[dict]:
        """Return a list of dicts describing every discovered plugin.

        Each dict contains:
          class_name, name, version, description, author, source,
          loaded (bool), hooks (list[str])
        """
        loaded_classes = set()
        with self._lock:
            for p in self._loaded:
                loaded_classes.add(type(p).__name__)

        manifest: list[dict] = []
        for cls in self._discovered:
            # Instantiate temporarily to read metadata without loading
            try:
                tmp = cls()
                info = tmp.get_info()
            except Exception:
                info = {
                    "name": getattr(cls, "name", cls.__name__),
                    "version": getattr(cls, "version", "?"),
                    "description": getattr(cls, "description", ""),
                    "author": getattr(cls, "author", "Unknown"),
                    "hooks": [],
                    "event_subscriptions": [],
                    "event_patterns": [],
                }

            # Determine source (bundled vs user)
            module = getattr(cls, "__module__", "")
            source_file = ""
            mod = sys.modules.get(module)
            if mod:
                source_file = getattr(mod, "__file__", "") or ""
            is_bundled = "bundled" in source_file

            manifest.append({
                "class_name": cls.__name__,
                "name": info.get("name", cls.__name__),
                "version": info.get("version", "?"),
                "description": info.get("description", ""),
                "author": info.get("author", "Unknown"),
                "source": "bundled" if is_bundled else "user",
                "source_file": source_file,
                "loaded": cls.__name__ in loaded_classes,
                "hooks": info.get("hooks", []),
                "event_patterns": info.get("event_patterns", []),
            })

        return manifest

    # ------------------------------------------------------------------
    # Hook dispatchers
    # ------------------------------------------------------------------
    # Each dispatcher runs every loaded plugin that overrides the hook,
    # ordered by priority (lower runs first).  Pipeline-style hooks pass
    # the return value of one plugin into the next.  Boolean hooks
    # short-circuit on the first True.

    def _sorted_by_priority(self, hook_name: str) -> list[ForgePlugin]:
        """Return loaded plugins sorted by their priority for *hook_name*."""
        with self._lock:
            applicable = [
                p for p in self._loaded if _overrides_hook(p, hook_name)
            ]
        applicable.sort(key=lambda p: _hook_priority(p, hook_name))
        return applicable

    def _record_plugin_error(self, plugin: ForgePlugin, hook: str) -> None:
        """Record a plugin error and auto-disable if threshold exceeded."""
        count = getattr(plugin, "_error_count", 0) + 1
        plugin._error_count = count
        log.warning(
            "Plugin '%s' raised in %s (error %d/%d) -- skipping.",
            plugin.name, hook, count, _MAX_PLUGIN_ERRORS,
            exc_info=True,
        )
        if count >= _MAX_PLUGIN_ERRORS:
            log.error(
                "Auto-disabling plugin '%s' after %d errors.",
                plugin.name, count,
            )
            with self._lock:
                try:
                    self._loaded.remove(plugin)
                except ValueError:
                    pass  # Already removed by another thread

    # -- pipeline hooks (value flows through each plugin) ---------------

    def dispatch_user_input(self, text: str) -> str:
        """Run ``on_user_input`` across all plugins.  Returns final text."""
        for plugin in self._sorted_by_priority("on_user_input"):
            try:
                text = plugin.on_user_input(text)
            except Exception:
                self._record_plugin_error(plugin, "on_user_input")
        return text

    def dispatch_response(self, text: str) -> str:
        """Run ``on_response`` across all plugins.  Returns final text."""
        for plugin in self._sorted_by_priority("on_response"):
            try:
                text = plugin.on_response(text)
            except Exception:
                self._record_plugin_error(plugin, "on_response")
        return text

    def dispatch_tool_call(self, tool_name: str, args: dict) -> dict:
        """Run ``on_tool_call`` across all plugins.  Returns final args."""
        for plugin in self._sorted_by_priority("on_tool_call"):
            try:
                args = plugin.on_tool_call(tool_name, args)
            except Exception:
                self._record_plugin_error(plugin, "on_tool_call")
        return args

    def dispatch_tool_result(self, tool_name: str, result: str) -> str:
        """Run ``on_tool_result`` across all plugins.  Returns final result."""
        for plugin in self._sorted_by_priority("on_tool_result"):
            try:
                result = plugin.on_tool_result(tool_name, result)
            except Exception:
                self._record_plugin_error(plugin, "on_tool_result")
        return result

    def dispatch_file_read(self, path: str, content: str) -> str:
        """Run ``on_file_read`` across all plugins.  Returns final content."""
        for plugin in self._sorted_by_priority("on_file_read"):
            try:
                content = plugin.on_file_read(path, content)
            except Exception:
                self._record_plugin_error(plugin, "on_file_read")
        return content

    def dispatch_file_write(self, path: str, content: str) -> str:
        """Run ``on_file_write`` across all plugins.  Returns final content."""
        for plugin in self._sorted_by_priority("on_file_write"):
            try:
                content = plugin.on_file_write(path, content)
            except Exception:
                self._record_plugin_error(plugin, "on_file_write")
        return content

    # -- event observer dispatch ----------------------------------------

    def dispatch_event(self, event: "ForgeEvent") -> None:
        """Route a ForgeEvent to all loaded plugins that subscribed to it.

        For each plugin:
        - If the plugin declared ``event_subscriptions`` or ``event_patterns``,
          only dispatch if the event type matches (exact name, ``"*"``, or
          a glob pattern from ``event_patterns`` such as ``"tool.*"``).
          An empty declaration on both means "receive all events".
        - Call the specific handler (e.g. ``on_turn_end``) if overridden.
        - Always call ``on_event`` if overridden (catch-all observer).
        """
        with self._lock:
            plugins = list(self._loaded)

        for plugin in plugins:
            subs     = getattr(plugin, "event_subscriptions", [])
            patterns = getattr(plugin, "event_patterns", [])

            # If neither filter is declared, receive all events (no filter)
            has_filter = bool(subs) or bool(patterns)
            if has_filter:
                # Accept if exact subscription matches
                exact_match = (
                    event.event_type in subs or "*" in subs
                )
                # Accept if any glob pattern matches
                pattern_match = any(
                    fnmatch.fnmatch(event.event_type, p) for p in patterns
                )
                if not exact_match and not pattern_match:
                    continue

            # Derive the specific hook name: "turn.end" → "on_turn_end"
            specific = "on_" + event.event_type.replace(".", "_")

            # Call specific handler if overridden by this plugin's class
            if getattr(type(plugin), specific, None) is not getattr(
                ForgePlugin, specific, None
            ):
                try:
                    getattr(plugin, specific)(event.data)
                except Exception:
                    self._record_plugin_error(plugin, specific)

            # Call catch-all on_event if overridden
            if _overrides_hook(plugin, "on_event"):
                # Avoid double-calling if specific == "on_event" (shouldn't happen)
                if specific != "on_event":
                    try:
                        plugin.on_event(event)
                    except Exception:
                        self._record_plugin_error(plugin, "on_event")

    # -- boolean hook (short-circuits on True) --------------------------

    def dispatch_command(self, command: str, arg: str) -> bool:
        """Run ``on_command`` across plugins.  Returns True if any handled it."""
        for plugin in self._sorted_by_priority("on_command"):
            try:
                if plugin.on_command(command, arg):
                    return True
            except Exception:
                self._record_plugin_error(plugin, "on_command")
        return False

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def format_status(self) -> str:
        """Return a human-readable summary of loaded plugins for the terminal."""
        if not self._loaded:
            return "Plugins: (none loaded)"

        lines: list[str] = [f"Plugins ({len(self._loaded)} loaded):"]
        for plugin in self._loaded:
            info = plugin.get_info()
            hooks = ", ".join(info["hooks"]) if info["hooks"] else "(no hooks)"
            lines.append(
                f"  {info['name']} v{info['version']}"
                f"  by {info['author']}"
                f"  -- {hooks}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"<PluginManager dir={self._plugin_dir} "
            f"discovered={len(self._discovered)} "
            f"loaded={len(self._loaded)}>"
        )
