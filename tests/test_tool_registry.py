"""Tests for ToolRegistry — registration, calling, analytics, and audit."""

import time
import pytest
from forge.tools.registry import ToolRegistry, ToolResult


# ── Fixtures ──

@pytest.fixture
def registry():
    r = ToolRegistry()
    r.register("greet", lambda name: f"Hello, {name}!",
               "Greet someone", {"type": "object", "properties": {"name": {"type": "string"}}})
    r.register("add", lambda a, b: a + b,
               "Add two numbers", {"type": "object", "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}}})
    r.register("fail", lambda: (_ for _ in ()).throw(ValueError("boom")),
               "Always fails", {"type": "object", "properties": {}})
    return r


# ── Basic registration ──

class TestRegistration:
    def test_list_tools(self, registry):
        names = registry.list_tools()
        assert "greet" in names
        assert "add" in names
        assert "fail" in names

    def test_get_description(self, registry):
        assert registry.get_description("greet") == "Greet someone"
        assert registry.get_description("nonexistent") == ""

    def test_get_ollama_tools_format(self, registry):
        tools = registry.get_ollama_tools()
        assert len(tools) == 3
        for t in tools:
            assert t["type"] == "function"
            assert "name" in t["function"]
            assert "description" in t["function"]


# ── Tool calling ──

class TestToolCall:
    def test_call_success(self, registry):
        result = registry.call("greet", {"name": "World"})
        assert result.success is True
        assert result.output == "Hello, World!"

    def test_call_returns_computed(self, registry):
        result = registry.call("add", {"a": 3, "b": 7})
        assert result.success is True
        assert result.output == "10"

    def test_call_unknown_tool(self, registry):
        result = registry.call("nonexistent", {})
        assert result.success is False
        assert "unknown tool" in result.output

    def test_call_failure(self, registry):
        result = registry.call("fail", {})
        assert result.success is False
        assert "boom" in result.output

    def test_tool_result_str(self):
        tr = ToolResult(success=True, output="hello")
        assert str(tr) == "hello"


# ── Per-tool analytics ──

class TestToolAnalytics:
    def test_stats_empty_initially(self, registry):
        stats = registry.get_tool_stats()
        assert stats == {}  # No calls yet

    def test_stats_after_calls(self, registry):
        registry.call("greet", {"name": "A"})
        registry.call("greet", {"name": "B"})
        registry.call("add", {"a": 1, "b": 2})
        stats = registry.get_tool_stats()
        assert stats["greet"]["calls"] == 2
        assert stats["greet"]["successes"] == 2
        assert stats["greet"]["failures"] == 0
        assert stats["add"]["calls"] == 1

    def test_stats_track_failures(self, registry):
        registry.call("fail", {})
        registry.call("fail", {})
        stats = registry.get_tool_stats()
        assert stats["fail"]["failures"] == 2
        assert stats["fail"]["successes"] == 0

    def test_stats_avg_latency(self, registry):
        registry.call("greet", {"name": "test"})
        stats = registry.get_tool_stats()
        assert stats["greet"]["avg_ms"] >= 0  # should be non-negative

    def test_stats_mixed_success_failure(self, registry):
        registry.call("greet", {"name": "ok"})
        registry.call("fail", {})
        registry.call("greet", {"name": "ok2"})
        stats = registry.get_tool_stats()
        assert stats["greet"]["calls"] == 2
        assert stats["greet"]["successes"] == 2
        assert stats["fail"]["calls"] == 1
        assert stats["fail"]["failures"] == 1

    def test_unknown_tool_not_in_stats(self, registry):
        registry.call("nonexistent", {})
        stats = registry.get_tool_stats()
        assert "nonexistent" not in stats


# ── Audit dict ──

class TestToolRegistryAudit:
    def test_audit_dict_structure(self, registry):
        registry.call("greet", {"name": "test"})
        audit = registry.to_audit_dict()
        assert audit["schema_version"] == 1
        assert audit["tool_count"] == 3
        assert "greet" in audit["tool_names"]
        assert "greet" in audit["stats"]

    def test_audit_dict_empty(self):
        r = ToolRegistry()
        audit = r.to_audit_dict()
        assert audit["tool_count"] == 0
        assert audit["stats"] == {}
