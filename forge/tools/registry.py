"""Tool registry — all tools the AI can use.

Each tool is a callable with a schema. The registry converts them
to Ollama's tool format and dispatches calls.
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Structured result from a tool call."""
    success: bool
    output: str

    def __str__(self) -> str:
        return self.output


class ToolRegistry:
    """Registry of tools available to the LLM."""

    def __init__(self):
        self._tools: dict[str, dict] = {}  # name -> {fn, schema}
        self._stats: dict[str, dict] = {}  # name -> {calls, successes, failures, total_ms}

    def register(self, name: str, fn: Callable,
                 description: str, parameters: dict):
        """Register a tool.

        Args:
            name: Tool name (e.g. "read_file")
            fn: The function to call. Should return a string result.
            description: What the tool does.
            parameters: JSON Schema for the parameters.
        """
        self._tools[name] = {
            "fn": fn,
            "schema": {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            },
        }

    def get_ollama_tools(self) -> list[dict]:
        """Return tool schemas in Ollama's format."""
        return [t["schema"] for t in self._tools.values()]

    def call(self, name: str, arguments: dict) -> ToolResult:
        """Execute a tool by name with the given arguments.

        Returns a ToolResult with success flag and output string.
        """
        if name not in self._tools:
            return ToolResult(success=False,
                              output=f"Error: unknown tool '{name}'")

        # Ensure stats entry exists
        if name not in self._stats:
            self._stats[name] = {"calls": 0, "successes": 0,
                                 "failures": 0, "total_ms": 0.0}
        st = self._stats[name]
        st["calls"] += 1
        t0 = time.monotonic()

        try:
            result = self._tools[name]["fn"](**arguments)
            output = str(result) if result is not None else "(no output)"
            st["successes"] += 1
            st["total_ms"] += (time.monotonic() - t0) * 1000
            return ToolResult(success=True, output=output)
        except Exception as e:
            log.exception("Tool '%s' failed", name)
            st["failures"] += 1
            st["total_ms"] += (time.monotonic() - t0) * 1000
            from forge.bug_reporter import capture_crash as _capture_crash
            _capture_crash(e, context={"tool": name, "arguments": str(arguments)[:200]})
            return ToolResult(
                success=False,
                output=f"Error in {name}: {type(e).__name__}: {e}",
            )

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_description(self, name: str) -> str:
        """Get a tool's description."""
        if name in self._tools:
            return self._tools[name]["schema"]["function"]["description"]
        return ""

    def get_tool_stats(self) -> dict:
        """Per-tool analytics: calls, successes, failures, avg latency."""
        result = {}
        for name, st in self._stats.items():
            calls = st["calls"]
            avg_ms = st["total_ms"] / max(1, calls)
            result[name] = {
                "calls": calls,
                "successes": st["successes"],
                "failures": st["failures"],
                "avg_ms": round(avg_ms, 1),
            }
        return result

    def to_audit_dict(self) -> dict:
        """Serializable snapshot for audit export."""
        return {
            "schema_version": 1,
            "tool_count": len(self._tools),
            "tool_names": list(self._tools.keys()),
            "stats": self.get_tool_stats(),
        }
