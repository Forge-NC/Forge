"""Tests for forge.dedup — Tool call deduplication."""

import pytest
from forge.dedup import ToolDedup


# ---------------------------------------------------------------------------
# test_unique_calls_pass
# ---------------------------------------------------------------------------

class TestUniqueCallsPass:
    def test_different_tools(self):
        d = ToolDedup(threshold=0.92)
        assert d.check("read_file", {"path": "a.py"}) is None
        assert d.check("write_file", {"path": "b.py"}) is None

    def test_different_args(self):
        d = ToolDedup(threshold=0.92)
        assert d.check("read_file", {"path": "a.py"}) is None
        assert d.check("read_file", {"path": "completely_different.py"}) is None

    def test_first_call_always_passes(self):
        d = ToolDedup(threshold=0.92)
        assert d.check("write_notes", {"content": "hello world"}) is None


# ---------------------------------------------------------------------------
# test_duplicate_detection
# ---------------------------------------------------------------------------

class TestDuplicateDetection:
    def test_identical_args(self):
        d = ToolDedup(threshold=0.92)
        d.check("write_notes", {"topic": "arch", "content": "The system is modular"})
        result = d.check("write_notes", {"topic": "arch", "content": "The system is modular"})
        assert result is not None
        assert result["duplicate"] is True
        assert result["similarity"] == 1.0

    def test_nearly_identical_args(self):
        d = ToolDedup(threshold=0.90)
        d.check("write_notes", {
            "topic": "architecture",
            "content": "The Forge codebase is structured with a modular approach "
                       "featuring distinct directories for audio handling models "
                       "and plugins"
        })
        result = d.check("write_notes", {
            "topic": "architecture",
            "content": "The Forge codebase is structured with a modular approach "
                       "featuring distinct directories for audio handling, models, "
                       "and plugins."
        })
        assert result is not None
        assert result["duplicate"] is True
        assert result["similarity"] >= 0.90

    def test_below_threshold_passes(self):
        d = ToolDedup(threshold=0.95)
        d.check("write_notes", {"content": "Short note about X"})
        result = d.check("write_notes", {"content": "Completely different note about Y"})
        assert result is None

    def test_high_threshold_strict(self):
        d = ToolDedup(threshold=0.99)
        d.check("read_file", {"path": "main.py"})
        # Very similar but not identical
        result = d.check("read_file", {"path": "main.py", "offset": 0})
        # Should NOT be caught — different args
        assert result is None


# ---------------------------------------------------------------------------
# test_configuration
# ---------------------------------------------------------------------------

class TestConfiguration:
    def test_disabled(self):
        d = ToolDedup(enabled=False)
        d.check("write_notes", {"content": "same"})
        result = d.check("write_notes", {"content": "same"})
        assert result is None  # disabled = never suppresses

    def test_threshold_clamped(self):
        d = ToolDedup(threshold=1.5)
        assert d.threshold == 1.0
        d2 = ToolDedup(threshold=-0.5)
        assert d2.threshold == 0.0

    def test_window_size(self):
        d = ToolDedup(threshold=0.92, window_size=2)
        # Fill the window
        d.check("write_notes", {"content": "first"})
        d.check("write_notes", {"content": "second"})
        d.check("write_notes", {"content": "third"})
        # "first" should have been evicted from window
        result = d.check("write_notes", {"content": "first"})
        assert result is None  # no longer in window


# ---------------------------------------------------------------------------
# test_reset_and_stats
# ---------------------------------------------------------------------------

class TestResetAndStats:
    def test_reset_clears_window(self):
        d = ToolDedup(threshold=0.92)
        d.check("write_notes", {"content": "hello"})
        d.reset()
        result = d.check("write_notes", {"content": "hello"})
        assert result is None  # window was cleared

    def test_stats(self):
        d = ToolDedup(threshold=0.92)
        d.check("a", {"x": 1})
        d.check("a", {"x": 1})  # duplicate
        d.check("b", {"y": 2})

        s = d.stats()
        assert s["total_checked"] == 3
        assert s["total_suppressed"] == 1
        assert s["suppression_rate"] > 0

    def test_initial_stats(self):
        d = ToolDedup()
        s = d.stats()
        assert s["total_checked"] == 0
        assert s["total_suppressed"] == 0
        assert s["suppression_rate"] == 0.0

    def test_format_status(self):
        d = ToolDedup(threshold=0.92)
        output = d.format_status()
        assert "92%" in output
        assert "ON" in output


# ---------------------------------------------------------------------------
# test_similarity_edge_cases
# ---------------------------------------------------------------------------

class TestSimilarityEdgeCases:
    def test_empty_args(self):
        d = ToolDedup(threshold=0.92)
        d.check("tool", {})
        result = d.check("tool", {})
        assert result is not None  # identical empty args

    def test_non_serializable_args(self):
        """Args that can't be JSON-serialized should still work."""
        d = ToolDedup(threshold=0.92)
        # This shouldn't raise
        d.check("tool", {"fn": lambda x: x})
        result = d.check("tool", {"fn": lambda x: x})
        # May or may not match depending on repr, but shouldn't crash
        assert True  # no exception = success


# ---------------------------------------------------------------------------
# test_cross_turn_dedup
# ---------------------------------------------------------------------------

class TestCrossTurnDedup:
    def test_soft_reset_preserves_previous_turn(self):
        """After soft_reset, identical calls from previous turn are caught."""
        d = ToolDedup(threshold=0.92)
        d.check("scan_codebase", {"path": "/project"})
        d.soft_reset()  # simulate new turn
        result = d.check("scan_codebase", {"path": "/project"})
        assert result is not None
        assert result["duplicate"] is True
        assert result.get("cross_turn") is True

    def test_soft_reset_allows_different_args(self):
        """Different args across turns should NOT be blocked."""
        d = ToolDedup(threshold=0.92)
        d.check("read_file", {"path": "a.py"})
        d.soft_reset()
        result = d.check("read_file", {"path": "completely_different.py"})
        assert result is None

    def test_soft_reset_only_keeps_one_turn(self):
        """Two soft_resets should clear the oldest turn's data."""
        d = ToolDedup(threshold=0.92)
        d.check("scan_codebase", {"path": "/old"})
        d.soft_reset()  # turn 1 → prev_turn
        d.check("read_file", {"path": "b.py"})
        d.soft_reset()  # turn 2 → prev_turn, turn 1 gone
        result = d.check("scan_codebase", {"path": "/old"})
        assert result is None  # too old — no longer tracked

    def test_full_reset_clears_cross_turn(self):
        """Full reset() should clear both current and previous turn."""
        d = ToolDedup(threshold=0.92)
        d.check("scan_codebase", {"path": "/project"})
        d.soft_reset()
        d.reset()  # full reset
        result = d.check("scan_codebase", {"path": "/project"})
        assert result is None  # everything cleared

    def test_cross_turn_uses_strict_threshold(self):
        """Cross-turn checks use 0.98 threshold, not 0.92."""
        d = ToolDedup(threshold=0.92)
        d.check("write_notes", {
            "content": "The system uses a modular architecture pattern"
        })
        d.soft_reset()
        # Similar but not near-identical (>0.92 but <0.98)
        result = d.check("write_notes", {
            "content": "The system uses a modular architecture design"
        })
        assert result is None  # below 0.98 cross-turn threshold
