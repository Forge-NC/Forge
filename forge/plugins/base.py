"""Base plugin class and hook definitions for Forge plugins.

Every Forge plugin is a Python class that inherits from ``ForgePlugin`` and
overrides one or more hook methods.  Hooks are entirely optional -- only
implement the ones your plugin needs.

Example -- a minimal plugin saved as ``~/.forge/plugins/hello.py``::

    from forge.plugins.base import ForgePlugin

    class HelloPlugin(ForgePlugin):
        name = "Hello"
        version = "1.0.0"
        description = "Adds a /hello command."
        author = "you"

        def on_command(self, command: str, arg: str) -> bool:
            if command == "hello":
                print(f"Hello, {arg or 'world'}!")
                return True            # handled
            return False               # not ours

Hook priority
-------------
Each hook method can carry a ``priority`` attribute (int, default 50).
Plugins whose hook has a *lower* priority value run first.  Set it on the
method itself::

    def on_user_input(self, text: str) -> str:
        return text.upper()
    on_user_input.priority = 10        # runs before default (50)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from forge.event_bus import ForgeEvent

log = logging.getLogger(__name__)

# Sentinel used internally so dispatchers can tell "hook returned None
# intentionally" from "hook is not overridden".  Plugin authors never
# need to reference this.
_UNSET = object()

# Default priority for hooks that do not declare one.
DEFAULT_PRIORITY = 50


class ForgePlugin:
    """Base class for all Forge plugins.

    Subclass this and override any hooks you need.  Class-level attributes
    ``name``, ``version``, ``description``, and ``author`` should be set on
    every plugin.
    """

    # ------------------------------------------------------------------
    # Metadata -- override these in your subclass
    # ------------------------------------------------------------------
    name: str = "Unnamed Plugin"
    version: str = "0.0.0"
    description: str = ""
    author: str = "Unknown"

    # ------------------------------------------------------------------
    # Internal state (set by the plugin manager, not by the plugin)
    # ------------------------------------------------------------------
    _engine: Any = None          # reference to the Forge engine
    _loaded: bool = False

    # ------------------------------------------------------------------
    # Event subscriptions
    # ------------------------------------------------------------------

    # Declare which event types this plugin wants to receive.
    # An empty list means "subscribe to all events via on_event()".
    # Listing specific types (e.g. ["session.end", "turn.end"]) skips
    # dispatch for unrelated high-frequency events — useful for performance.
    event_subscriptions: list[str] = []

    # Glob-style event patterns for broader subscriptions.
    # Supports "*" wildcards using fnmatch rules, e.g.:
    #   event_patterns = ["tool.*"]          # all tool events
    #   event_patterns = ["model.*"]         # all model events
    #   event_patterns = ["tool.*", "file.*"]  # tools and file events
    # Patterns are checked in addition to event_subscriptions.
    # An empty list applies no pattern filter.
    event_patterns: list[str] = []

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def on_load(self, forge_engine: Any) -> None:
        """Called when the plugin is loaded.

        *forge_engine* is the main Forge engine instance, giving you
        access to the tool registry, conversation state, config, etc.
        Store it if you need it later.
        """

    def on_unload(self) -> None:
        """Called when the plugin is unloaded (shutdown or reload).

        Clean up any resources your plugin holds (open files, threads,
        network connections, etc.).
        """

    # ------------------------------------------------------------------
    # Event observer hooks  (observe without transforming)
    # ------------------------------------------------------------------

    def on_event(self, event: "ForgeEvent") -> None:
        """Catch-all observer.  Called for every event if event_subscriptions is empty.

        Override to receive all events without filtering.  For selective
        listening, override the specific methods below or set event_subscriptions.
        """

    def on_session_start(self, data: dict) -> None:
        """Session began.

        data keys: session_id, model, cwd, config_summary
        """

    def on_session_end(self, data: dict) -> None:
        """Session ended cleanly or via /quit.

        data keys: session_id, turns, tokens_prompt, tokens_generated,
                   duration_s, tool_calls, files_modified
        """

    def on_turn_start(self, data: dict) -> None:
        """A new user turn began (input received, agent loop starting).

        data keys: turn_id, user_input_preview, context_pct
        """

    def on_turn_end(self, data: dict) -> None:
        """Turn completed (agent loop finished, response displayed).

        data keys: turn_id, tokens_prompt, tokens_generated, duration_ms,
                   tool_calls_count, had_errors
        """

    def on_model_switch(self, from_model: str, to_model: str) -> None:
        """Model router switched from one model to another.

        Args:
            from_model: Model name before switch.
            to_model:   Model name after switch.
        """

    def on_context_pressure(self, used_pct: float, data: dict) -> None:
        """Context window is filling up.

        Args:
            used_pct: Fraction used, 0.0–1.0.
        data keys: used_pct, tokens_used, tokens_max, swap_imminent
        """

    def on_threat_detected(self, threat: dict) -> None:
        """Crucible detected a security threat in model output or recall.

        threat keys: level, rule, source, preview, action
        """

    # ------------------------------------------------------------------
    # Input / output pipeline hooks
    # ------------------------------------------------------------------

    def on_user_input(self, text: str) -> str:
        """Modify user input before it is sent to the AI.

        Return the (possibly modified) text.  Return the original *text*
        unchanged if you only want to observe.
        """
        return text

    def on_response(self, text: str) -> str:
        """Modify the AI response before it is displayed to the user.

        Return the (possibly modified) text.
        """
        return text

    # ------------------------------------------------------------------
    # Tool hooks
    # ------------------------------------------------------------------

    def on_tool_call(self, tool_name: str, args: dict) -> dict:
        """Intercept a tool call before it executes.

        Return the (possibly modified) *args* dict.  You can inspect or
        alter arguments, or log them for auditing.
        """
        return args

    def on_tool_result(self, tool_name: str, result: str) -> str:
        """Intercept a tool result after execution.

        Return the (possibly modified) *result* string.
        """
        return result

    # ------------------------------------------------------------------
    # File hooks
    # ------------------------------------------------------------------

    def on_file_read(self, path: str, content: str) -> str:
        """Called after a file is read.

        Return the (possibly modified) *content* string.
        """
        return content

    def on_file_write(self, path: str, content: str) -> str:
        """Called before content is written to a file.

        Return the (possibly modified) *content* string.
        """
        return content

    # ------------------------------------------------------------------
    # Command hook
    # ------------------------------------------------------------------

    def on_command(self, command: str, arg: str) -> bool:
        """Handle a custom slash command.

        Return ``True`` if the command was handled by this plugin (no
        further dispatch), ``False`` otherwise.
        """
        return False

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def register_tools(self, registry: Any) -> None:
        """Register custom tools with the Forge tool registry.

        *registry* is a ``forge.tools.registry.ToolRegistry`` instance.
        Call ``registry.register(name, fn, description, parameters)``
        to add tools.
        """

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_info(self) -> dict:
        """Return a dict of plugin metadata and the hooks it overrides."""
        overridden: list[str] = []
        base = ForgePlugin
        for attr_name in (
            "on_load", "on_unload",
            "on_user_input", "on_response",
            "on_tool_call", "on_tool_result",
            "on_file_read", "on_file_write",
            "on_command", "register_tools",
            # event observer hooks
            "on_event", "on_session_start", "on_session_end",
            "on_turn_start", "on_turn_end", "on_model_switch",
            "on_context_pressure", "on_threat_detected",
        ):
            # A hook is "overridden" if the subclass provides its own.
            if getattr(type(self), attr_name) is not getattr(base, attr_name):
                overridden.append(attr_name)

        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "hooks": overridden,
            "event_subscriptions": list(self.event_subscriptions),
            "event_patterns": list(self.event_patterns),
        }

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"<{type(self).__name__} '{self.name}' v{self.version}>"
