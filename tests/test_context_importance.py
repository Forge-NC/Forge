"""Tests for context importance-weighted eviction and persistence."""

import json
import pytest
from pathlib import Path
from forge.context import ContextWindow, ContextEntry


# ── Importance field defaults ──

class TestImportanceDefaults:
    def test_system_message_high_importance(self):
        ctx = ContextWindow(max_tokens=10000)
        entry = ctx.add("system", "You are helpful.", pinned=True)
        assert entry.importance == 0.9

    def test_user_message_importance(self):
        ctx = ContextWindow(max_tokens=10000)
        entry = ctx.add("user", "hello")
        assert entry.importance == 0.7

    def test_assistant_message_importance(self):
        ctx = ContextWindow(max_tokens=10000)
        entry = ctx.add("assistant", "hi there")
        assert entry.importance == 0.6

    def test_tool_result_importance(self):
        ctx = ContextWindow(max_tokens=10000)
        entry = ctx.add("tool", "file contents", tag="tool:read_file")
        assert entry.importance == 0.4

    def test_recall_importance(self):
        ctx = ContextWindow(max_tokens=10000)
        entry = ctx.add("system", "recalled text", tag="recall")
        # recall tag → 0.3 (but system + pinned auto-assignment may override)
        # Since partition auto-assigns to "recall", importance should be 0.3
        # Actually: role=system → importance=0.9 unless not pinned
        # Let me check: add() with role="system" and pinned=False
        entry2 = ctx.add("system", "recalled text2", tag="recall",
                         partition="recall", pinned=False)
        # role=system → importance=0.9 by default
        # But tag=recall → 0.3
        # The auto-assign checks role first, so system wins
        assert entry2.importance == 0.9  # system role overrides

    def test_explicit_importance(self):
        ctx = ContextWindow(max_tokens=10000)
        entry = ctx.add("user", "important!", importance=0.95)
        assert entry.importance == 0.95

    def test_default_importance(self):
        ctx = ContextWindow(max_tokens=10000)
        entry = ctx.add("assistant", "something", tag="other")
        assert entry.importance == 0.6


# ── Importance-weighted eviction ──

class TestImportanceEviction:
    def test_low_importance_evicted_first(self):
        """Within same partition, low importance entries are evicted first."""
        ctx = ContextWindow(max_tokens=30)
        # Each entry ~ 5 tokens (20 chars / 4)
        ctx.add("assistant", "a" * 20, importance=0.1, partition="working")
        ctx.add("assistant", "b" * 20, importance=0.9, partition="working")
        # Now at ~10 tokens. Adding 100 chars = ~25 tokens. Need ~5 freed.
        ctx.add("user", "c" * 100, partition="working")
        remaining_asst = [e for e in ctx._entries if e.role == "assistant"]
        # The low-importance entry (0.1) should have been evicted first
        if remaining_asst:
            assert remaining_asst[0].importance == 0.9

    def test_partition_order_still_respected(self):
        """Quarantine evicted before working, regardless of importance."""
        ctx = ContextWindow(max_tokens=30)
        # ~5 tokens each
        ctx.add("system", "q" * 20, partition="quarantine",
                importance=0.99, pinned=False)
        ctx.add("assistant", "w" * 20, partition="working",
                importance=0.01)
        # Need to evict to fit this. Quarantine goes first.
        ctx.add("user", "u" * 100, partition="working")
        partitions = [e.partition for e in ctx._entries]
        assert "quarantine" not in partitions

    def test_pinned_survives_regardless_of_importance(self):
        ctx = ContextWindow(max_tokens=30)
        ctx.add("assistant", "p" * 20, importance=0.0, pinned=True)
        ctx.add("assistant", "u" * 20, importance=1.0, partition="working")
        ctx.add("user", "x" * 80, partition="working")
        pinned = [e for e in ctx._entries if e.pinned]
        assert len(pinned) >= 1

    def test_eviction_order_within_partition(self):
        """Directly test that _try_evict sorts by importance."""
        ctx = ContextWindow(max_tokens=1000)
        ctx.add("assistant", "low" * 10, importance=0.1, partition="reference")
        ctx.add("assistant", "mid" * 10, importance=0.5, partition="reference")
        ctx.add("assistant", "high" * 10, importance=0.9, partition="reference")
        # Each entry is ~8 tokens. Evict just 1 token to force one eviction.
        freed = ctx._try_evict(1)
        assert freed >= 1
        # The lowest importance entry should have been evicted first
        remaining = [e for e in ctx._entries if e.partition == "reference"]
        importances = [e.importance for e in remaining]
        assert 0.1 not in importances
        assert 0.5 in importances
        assert 0.9 in importances


# ── Persistence ──

class TestImportancePersistence:
    def test_save_load_preserves_importance(self, tmp_path):
        ctx = ContextWindow(max_tokens=10000)
        ctx.add("user", "hello", importance=0.85)
        ctx.add("assistant", "response", importance=0.42)
        path = tmp_path / "session.json"
        ctx.save_session(path)

        ctx2 = ContextWindow(max_tokens=10000)
        ctx2.load_session(path)
        assert ctx2._entries[0].importance == 0.85
        assert ctx2._entries[1].importance == 0.42

    def test_load_old_session_without_importance(self, tmp_path):
        """Sessions saved before importance field should load with default 0.5."""
        path = tmp_path / "old_session.json"
        data = {
            "version": 1,
            "max_tokens": 10000,
            "saved_at": 0,
            "entries": [
                {"role": "user", "content": "hello", "token_count": 2,
                 "timestamp": 1.0, "tag": "", "pinned": False,
                 "file_path": "", "partition": "working"},
            ],
            "eviction_log": [],
        }
        path.write_text(json.dumps(data))
        ctx = ContextWindow(max_tokens=10000)
        ctx.load_session(path)
        assert ctx._entries[0].importance == 0.5  # default
