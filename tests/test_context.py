"""Tests for forge.context — ContextWindow management."""

import json
import time
import pytest
from forge.context import ContextWindow, ContextEntry, ContextFullError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fixed_tokenizer(text: str) -> int:
    """Deterministic tokenizer: 1 token per word."""
    return max(1, len(text.split()))


def _make_ctx(max_tokens=100):
    """Create a small ContextWindow with a deterministic tokenizer."""
    return ContextWindow(max_tokens=max_tokens, tokenizer_fn=_fixed_tokenizer)


# ---------------------------------------------------------------------------
# test_add_entry
# ---------------------------------------------------------------------------

class TestAddEntry:
    def test_basic_add(self):
        ctx = _make_ctx()
        entry = ctx.add("user", "hello world")
        assert isinstance(entry, ContextEntry)
        assert entry.role == "user"
        assert entry.content == "hello world"
        assert entry.token_count == 2  # "hello" + "world"
        assert ctx.entry_count == 1

    def test_tag_and_pinned(self):
        ctx = _make_ctx()
        entry = ctx.add("assistant", "some code", tag="tool:read_file", pinned=True)
        assert entry.tag == "tool:read_file"
        assert entry.pinned is True

    def test_multiple_entries(self):
        ctx = _make_ctx()
        ctx.add("user", "first")
        ctx.add("assistant", "second")
        ctx.add("user", "third")
        assert ctx.entry_count == 3


# ---------------------------------------------------------------------------
# test_token_counting
# ---------------------------------------------------------------------------

class TestTokenCounting:
    def test_total_tokens(self):
        ctx = _make_ctx()
        ctx.add("user", "one two three")  # 3 tokens
        ctx.add("user", "four five")      # 2 tokens
        assert ctx.total_tokens == 5

    def test_remaining_tokens(self):
        ctx = _make_ctx(max_tokens=50)
        ctx.add("user", "a b c d e f g h i j")  # 10 tokens
        assert ctx.remaining_tokens == 40

    def test_approx_tokenizer_default(self):
        ctx = ContextWindow(max_tokens=10000)
        entry = ctx.add("user", "x" * 400)
        # Default tokenizer: len(text) // 4 = 100
        assert entry.token_count == 100

    def test_custom_tokenizer(self):
        ctx = ContextWindow(max_tokens=1000, tokenizer_fn=lambda t: 42)
        entry = ctx.add("user", "anything")
        assert entry.token_count == 42


# ---------------------------------------------------------------------------
# test_usage_tracking
# ---------------------------------------------------------------------------

class TestUsageTracking:
    def test_usage_pct(self):
        ctx = _make_ctx(max_tokens=100)
        ctx.add("user", " ".join(["w"] * 25))  # 25 tokens
        assert ctx.usage_pct == 25.0

    def test_usage_pct_zero_max(self):
        ctx = ContextWindow(max_tokens=0)
        assert ctx.usage_pct == 100.0

    def test_status_dict(self):
        ctx = _make_ctx(max_tokens=200)
        ctx.add("user", "hello world", tag="general")
        ctx.add("assistant", "ok", tag="response")
        status = ctx.status()
        assert status["total_tokens"] == ctx.total_tokens
        assert status["max_tokens"] == 200
        assert status["entry_count"] == 2
        assert "general" in status["by_tag"]
        assert "user" in status["by_role"]


# ---------------------------------------------------------------------------
# test_file_dedup
# ---------------------------------------------------------------------------

class TestFileDedup:
    def test_rereading_same_file_replaces(self):
        ctx = _make_ctx(max_tokens=200)
        ctx.add("tool", "old content of foo", tag="file_read", file_path="/foo.py")
        assert ctx.entry_count == 1
        old_tokens = ctx.total_tokens

        ctx.add("tool", "new content of foo with more words",
                tag="file_read", file_path="/foo.py")
        assert ctx.entry_count == 1  # replaced, not duplicated
        assert ctx.total_tokens != old_tokens  # recounted

    def test_different_files_not_deduped(self):
        ctx = _make_ctx(max_tokens=500)
        ctx.add("tool", "content a", tag="file_read", file_path="/a.py")
        ctx.add("tool", "content b", tag="file_read", file_path="/b.py")
        assert ctx.entry_count == 2

    def test_dedup_tag_tool_read_file(self):
        ctx = _make_ctx(max_tokens=200)
        ctx.add("tool", "v1", tag="tool:read_file", file_path="/x.py")
        ctx.add("tool", "v2", tag="tool:read_file", file_path="/x.py")
        assert ctx.entry_count == 1
        msgs = ctx.get_messages()
        assert msgs[0]["content"] == "v2"


# ---------------------------------------------------------------------------
# test_eviction_order
# ---------------------------------------------------------------------------

class TestEvictionOrder:
    def test_quarantine_evicted_first(self):
        ctx = _make_ctx(max_tokens=30)
        ctx.add("user", "a b c d e", partition="working")       # 5
        ctx.add("user", "f g h i j", partition="recall")        # 5
        ctx.add("user", "k l m n o", partition="reference")     # 5
        ctx.add("user", "p q r s t", partition="quarantine")    # 5
        # total=20, adding 15 more needs to evict 5
        ctx.add("user", " ".join(["z"] * 15))                   # 15
        remaining_partitions = [e.partition for e in ctx._entries]
        assert "quarantine" not in remaining_partitions

    def test_recall_evicted_before_reference(self):
        ctx = _make_ctx(max_tokens=25)
        ctx.add("user", "a b c d e", partition="working")       # 5
        ctx.add("user", "f g h i j", partition="recall")        # 5
        ctx.add("user", "k l m n o", partition="reference")     # 5
        # total=15, adding 15 needs to free 5; quarantine is empty, so recall goes
        ctx.add("user", " ".join(["z"] * 15))                   # 15
        remaining_partitions = [e.partition for e in ctx._entries]
        assert "recall" not in remaining_partitions
        assert "reference" in remaining_partitions

    def test_reference_evicted_before_working(self):
        ctx = _make_ctx(max_tokens=20)
        ctx.add("user", "a b c d e", partition="working")       # 5
        ctx.add("user", "f g h i j", partition="reference")     # 5
        # total=10, adding 15 needs to free 5
        ctx.add("user", " ".join(["z"] * 15))                   # 15
        remaining_partitions = [e.partition for e in ctx._entries]
        assert "reference" not in remaining_partitions
        assert "working" in remaining_partitions


# ---------------------------------------------------------------------------
# test_pinned_survive_eviction
# ---------------------------------------------------------------------------

class TestPinnedSurviveEviction:
    def test_pinned_entry_not_evicted(self):
        ctx = _make_ctx(max_tokens=20)
        pinned = ctx.add("user", "a b c d e", pinned=True, partition="recall")  # 5
        ctx.add("user", "f g h i j", partition="recall")        # 5
        # total=10, adding 15 needs to free 5; only the unpinned recall can go
        ctx.add("user", " ".join(["z"] * 15))                   # 15
        assert pinned in ctx._entries

    def test_pin_unpin(self):
        ctx = _make_ctx()
        ctx.add("user", "hello")
        assert ctx.pin(0) is True
        assert ctx._entries[0].pinned is True
        assert ctx.unpin(0) is True
        assert ctx._entries[0].pinned is False

    def test_pin_invalid_index(self):
        ctx = _make_ctx()
        assert ctx.pin(99) is False
        assert ctx.unpin(-1) is False


# ---------------------------------------------------------------------------
# test_context_full_error
# ---------------------------------------------------------------------------

class TestContextFullError:
    def test_raises_when_no_eviction_candidates(self):
        ctx = _make_ctx(max_tokens=10)
        ctx.add("system", "a b c d e", pinned=True, partition="core")  # 5 pinned/core
        with pytest.raises(ContextFullError, match="Context full"):
            ctx.add("user", " ".join(["w"] * 20))  # 20 tokens, only 5 remain, nothing evictable

    def test_no_error_when_eviction_succeeds(self):
        ctx = _make_ctx(max_tokens=15)
        ctx.add("user", "a b c d e", partition="recall")  # 5
        ctx.add("user", "f g h i j", partition="recall")  # 5
        # total=10, need 10 more — can evict both recall (10 tokens)
        entry = ctx.add("user", " ".join(["z"] * 10))     # 10
        assert entry is not None
        assert ctx.total_tokens <= 15


# ---------------------------------------------------------------------------
# test_partitions
# ---------------------------------------------------------------------------

class TestPartitions:
    def test_auto_partition_system(self):
        ctx = _make_ctx()
        e = ctx.add("system", "you are helpful")
        assert e.partition == "core"

    def test_auto_partition_pinned(self):
        ctx = _make_ctx()
        e = ctx.add("user", "keep this", pinned=True)
        assert e.partition == "core"

    def test_auto_partition_tool_tag(self):
        ctx = _make_ctx()
        e = ctx.add("tool", "result", tag="tool:search")
        assert e.partition == "reference"

    def test_auto_partition_recall(self):
        ctx = _make_ctx()
        e = ctx.add("user", "some recall", tag="recall")
        assert e.partition == "recall"

    def test_auto_partition_working(self):
        ctx = _make_ctx()
        e = ctx.add("user", "normal message")
        assert e.partition == "working"

    def test_explicit_partition_overrides(self):
        ctx = _make_ctx()
        e = ctx.add("user", "hi", partition="quarantine")
        assert e.partition == "quarantine"

    def test_partition_stats(self):
        ctx = _make_ctx(max_tokens=500)
        ctx.add("system", "sys")                              # core
        ctx.add("user", "hello world", partition="working")   # working
        ctx.add("tool", "data", tag="tool:x")                 # reference
        stats = ctx.get_partition_stats()
        assert "core" in stats
        assert "working" in stats
        assert "reference" in stats


# ---------------------------------------------------------------------------
# test_quarantine_add
# ---------------------------------------------------------------------------

class TestQuarantineAdd:
    def test_add_quarantine(self):
        ctx = _make_ctx(max_tokens=500)
        entry = ctx.add_quarantine("suspicious stuff", file_path="/bad.md")
        assert entry is not None
        assert entry.partition == "quarantine"
        assert "QUARANTINED" in entry.content

    def test_quarantine_returns_none_when_full(self):
        ctx = _make_ctx(max_tokens=10)
        ctx.add("system", "a b c d e f g h i j", pinned=True, partition="core")
        result = ctx.add_quarantine("extra content that does not fit")
        assert result is None


# ---------------------------------------------------------------------------
# test_save_load_session
# ---------------------------------------------------------------------------

class TestSaveLoadSession:
    def test_save_and_load(self, tmp_path):
        ctx = _make_ctx(max_tokens=500)
        ctx.add("user", "hello world")
        ctx.add("assistant", "hi there", tag="response")
        ctx.add("tool", "file content", tag="file_read",
                file_path="/foo.py", pinned=True)

        save_path = tmp_path / "session.json"
        ctx.save_session(save_path)

        # Load into a fresh context
        ctx2 = _make_ctx(max_tokens=500)
        count = ctx2.load_session(save_path)
        assert count == 3
        assert ctx2.entry_count == 3
        assert ctx2.total_tokens == ctx.total_tokens
        assert ctx2._entries[2].pinned is True
        assert ctx2._entries[2].file_path == "/foo.py"

    def test_saved_file_is_valid_json(self, tmp_path):
        ctx = _make_ctx()
        ctx.add("user", "test")
        path = tmp_path / "s.json"
        ctx.save_session(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert len(data["entries"]) == 1


# ---------------------------------------------------------------------------
# test_clear_keeps_pinned
# ---------------------------------------------------------------------------

class TestClearKeepsPinned:
    def test_clear(self):
        ctx = _make_ctx(max_tokens=500)
        ctx.add("user", "ephemeral")
        ctx.add("system", "keep me", pinned=True)
        ctx.add("user", "also ephemeral")
        cleared = ctx.clear()
        assert cleared == 2
        assert ctx.entry_count == 1
        assert ctx._entries[0].pinned is True


# ---------------------------------------------------------------------------
# test_drop_entry
# ---------------------------------------------------------------------------

class TestDropEntry:
    def test_drop_valid_index(self):
        ctx = _make_ctx()
        ctx.add("user", "aaa")
        ctx.add("user", "bbb")
        dropped = ctx.drop(0)
        assert dropped is not None
        assert dropped.content == "aaa"
        assert ctx.entry_count == 1

    def test_drop_invalid_index(self):
        ctx = _make_ctx()
        ctx.add("user", "x")
        assert ctx.drop(5) is None
        assert ctx.drop(-1) is None

    def test_drop_updates_tokens(self):
        ctx = _make_ctx()
        ctx.add("user", "one two three")  # 3 tokens
        tokens_before = ctx.total_tokens
        ctx.drop(0)
        assert ctx.total_tokens == tokens_before - 3


# ---------------------------------------------------------------------------
# test_inject_recall
# ---------------------------------------------------------------------------

class TestInjectRecall:
    def test_inject_recall_basic(self):
        ctx = _make_ctx(max_tokens=500)
        entry = ctx.inject_recall("recalled memory", source="/mem.json")
        assert entry is not None
        assert entry.partition == "recall"
        assert entry.tag == "recall"
        assert entry.file_path == "/mem.json"

    def test_inject_recall_evicts_old_recalls(self):
        ctx = _make_ctx(max_tokens=20)
        ctx.inject_recall("a b c d e")      # 5 tokens
        ctx.inject_recall("f g h i j")      # 5 tokens
        # total=10, adding 15 needs 5 freed → evicts first recall only
        entry = ctx.inject_recall(" ".join(["z"] * 15))  # 15
        assert entry is not None
        recalls = [e for e in ctx._entries if e.partition == "recall"]
        # Only first recall evicted (freed 5), second stays (5+15=20)
        assert len(recalls) == 2
        assert recalls[-1] is entry

    def test_inject_recall_returns_none_when_impossible(self):
        ctx = _make_ctx(max_tokens=10)
        ctx.add("system", "a b c d e f g h i j", pinned=True, partition="core")
        result = ctx.inject_recall("big recall content that exceeds limit")
        assert result is None


# ---------------------------------------------------------------------------
# Additional edge-case tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_get_messages(self):
        ctx = _make_ctx()
        ctx.add("user", "hello")
        ctx.add("assistant", "world")
        msgs = ctx.get_messages()
        assert len(msgs) == 2
        assert msgs[0] == {"role": "user", "content": "hello"}
        assert msgs[1] == {"role": "assistant", "content": "world"}

    def test_list_entries(self):
        ctx = _make_ctx()
        ctx.add("user", "test entry", tag="general")
        entries = ctx.list_entries()
        assert len(entries) == 1
        assert entries[0]["role"] == "user"
        assert entries[0]["tag"] == "general"
        assert "preview" in entries[0]

    def test_get_working_memory(self):
        ctx = _make_ctx(max_tokens=1000)
        ctx.add("user", "q1")
        ctx.add("assistant", "a1")
        ctx.add("user", "q2")
        ctx.add("assistant", "a2")
        ctx.add("user", "q3")
        ctx.add("assistant", "a3")
        pairs = ctx.get_working_memory(count=2)
        assert len(pairs) <= 4
        assert all(p.role in ("user", "assistant") for p in pairs)

    def test_truncate_to(self):
        ctx = _make_ctx(max_tokens=500)
        ctx.add("user", "one")
        ctx.add("user", "two")
        ctx.add("user", "three")
        removed = ctx.truncate_to(1)
        assert len(removed) == 2
        assert ctx.entry_count == 1

    def test_context_entry_hash(self):
        e1 = ContextEntry(role="user", content="same content")
        e2 = ContextEntry(role="user", content="same content")
        assert e1._hash == e2._hash

    def test_context_entry_different_hash(self):
        e1 = ContextEntry(role="user", content="content a")
        e2 = ContextEntry(role="user", content="content b")
        assert e1._hash != e2._hash

    def test_eviction_callback(self):
        evicted = []

        def cb(entries):
            evicted.extend(entries)

        ctx = _make_ctx(max_tokens=15)
        ctx.add("user", "a b c d e", partition="recall")  # 5
        ctx.add("user", "f g h i j", partition="recall")  # 5
        # Force eviction by adding 10 tokens (total would be 20 > 15)
        ctx.add("user", " ".join(["z"] * 10), eviction_callback=cb)
        assert len(evicted) > 0
