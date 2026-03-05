"""Tests for tool call rate limiter (circuit breaker) in ForgeEngine."""

import time
import pytest
from unittest.mock import MagicMock


def _make_engine(safety_level=2, rate_limiting=True):
    """Create a minimal mock engine with rate limiter."""
    engine = MagicMock()
    engine.safety = MagicMock()
    engine.safety.level = safety_level
    engine.config = MagicMock()
    engine.config.get = lambda k, d=None: {
        "rate_limiting": rate_limiting,
    }.get(k, d)
    engine._rate_limit_window = []
    engine._turn_tool_counts = {}

    from forge.engine import ForgeEngine
    engine._check_rate_limit = ForgeEngine._check_rate_limit.__get__(engine)
    return engine


class TestRateLimiter:
    def test_safety_l0_never_blocked(self):
        engine = _make_engine(safety_level=0)
        for _ in range(100):
            result = engine._check_rate_limit("run_shell")
            assert result == ""

    def test_safety_l2_run_shell_blocked(self):
        """L2: run_shell max = max(3, 10//2) = 5."""
        engine = _make_engine(safety_level=2)
        for i in range(5):
            result = engine._check_rate_limit("run_shell")
            assert result == "", f"Blocked on call {i+1}"
        # 6th call should be blocked
        result = engine._check_rate_limit("run_shell")
        assert "Rate limit" in result
        assert "run_shell" in result

    def test_safety_l3_run_shell_blocked_early(self):
        """L3: run_shell max = max(3, 5//2) = 3."""
        engine = _make_engine(safety_level=3)
        for i in range(3):
            result = engine._check_rate_limit("run_shell")
            assert result == ""
        result = engine._check_rate_limit("run_shell")
        assert "Rate limit" in result

    def test_safety_l2_any_tool_blocked(self):
        """L2: max_tool = 10."""
        engine = _make_engine(safety_level=2)
        for i in range(10):
            result = engine._check_rate_limit("read_file")
            assert result == ""
        result = engine._check_rate_limit("read_file")
        assert "Rate limit" in result

    def test_safety_l1_generous_limits(self):
        """L1: max_tool = 20, should not block at 10."""
        engine = _make_engine(safety_level=1)
        for i in range(15):
            result = engine._check_rate_limit("read_file")
            assert result == ""

    def test_rate_limiting_disabled(self):
        engine = _make_engine(safety_level=3, rate_limiting=False)
        for _ in range(50):
            result = engine._check_rate_limit("run_shell")
            assert result == ""

    def test_turn_reset_clears_counts(self):
        engine = _make_engine(safety_level=2)
        for _ in range(5):
            engine._check_rate_limit("run_shell")
        # Simulate turn reset
        engine._turn_tool_counts = {}
        result = engine._check_rate_limit("run_shell")
        assert result == ""

    def test_different_tools_independent(self):
        """Per-tool counts are independent."""
        engine = _make_engine(safety_level=2)
        for _ in range(5):
            engine._check_rate_limit("read_file")
        # Different tool should still work
        result = engine._check_rate_limit("edit_file")
        assert result == ""
