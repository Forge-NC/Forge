"""Tests for forge.file_cache — FileCache content-addressed caching."""

import json
import time
import pytest
from pathlib import Path
from forge.file_cache import FileCache


# ---------------------------------------------------------------------------
# test_store_and_check
# ---------------------------------------------------------------------------

class TestStoreAndCheck:
    """Verifies FileCache stores content-addressed entries and returns cache hits correctly.

    store() then check() on same file → cached=True, tokens_saved==50.
    check() on unknown file → None. Storing same file twice → read_count==2.
    """

    def test_store_then_check_returns_cached(self, tmp_path):
        f = tmp_path / "hello.py"
        f.write_text("print('hello')", encoding="utf-8")

        cache = FileCache()
        cache.store(str(f), "print('hello')", token_count=50)

        result = cache.check(str(f))
        assert result is not None
        assert result["cached"] is True
        assert result["tokens_saved"] == 50

    def test_check_unknown_file_returns_none(self, tmp_path):
        cache = FileCache()
        result = cache.check(str(tmp_path / "nonexistent.py"))
        assert result is None

    def test_store_increments_read_count(self, tmp_path):
        f = tmp_path / "counter.py"
        f.write_text("x = 1", encoding="utf-8")

        cache = FileCache()
        cache.store(str(f), "x = 1", token_count=10)
        cache.store(str(f), "x = 1", token_count=10)

        result = cache.check(str(f))
        assert result is not None
        assert result["read_count"] == 2


# ---------------------------------------------------------------------------
# test_modified_file
# ---------------------------------------------------------------------------

class TestModifiedFile:
    """Verifies FileCache invalidates entries when file content changes on disk.

    Storing 'version 1' then changing the file to 'version 2' → check() returns None (stale).
    Unmodified file → cache hit (cached=True).
    """

    def test_modified_file_returns_none(self, tmp_path):
        f = tmp_path / "changing.py"
        f.write_text("version 1", encoding="utf-8")

        cache = FileCache()
        cache.store(str(f), "version 1", token_count=20)

        # Modify the file
        f.write_text("version 2 — different content", encoding="utf-8")

        result = cache.check(str(f))
        assert result is None

    def test_unmodified_file_returns_hit(self, tmp_path):
        f = tmp_path / "stable.py"
        f.write_text("stable content", encoding="utf-8")

        cache = FileCache()
        cache.store(str(f), "stable content", token_count=15)

        result = cache.check(str(f))
        assert result is not None
        assert result["cached"] is True


# ---------------------------------------------------------------------------
# test_session_tracking
# ---------------------------------------------------------------------------

class TestSessionTracking:
    """Verifies FileCache uses session-scoped reads to prevent stale cross-session hits.

    A cache entry from a previous session (present in _cache but not _session_reads) must
    return None until the file is explicitly read again this session. store() adds the
    resolved path to _session_reads automatically.
    """

    def test_not_read_this_session_is_miss(self, tmp_path):
        """A file from a previous session (loaded from disk cache) should
        not return a hit until it is read in the current session."""
        f = tmp_path / "old.py"
        f.write_text("old content", encoding="utf-8")

        # Simulate a persisted cache entry from a previous session
        cache = FileCache()
        resolved = str(Path(str(f)).resolve())
        cache._cache[resolved] = {
            "hash": cache._hash_file(Path(str(f))),
            "token_count": 30,
            "line_count": 1,
            "last_read": time.time(),
            "read_count": 1,
        }
        # Do NOT add to _session_reads

        result = cache.check(str(f))
        assert result is None  # miss because not read this session

    def test_store_marks_session_read(self, tmp_path):
        f = tmp_path / "new.py"
        f.write_text("new", encoding="utf-8")

        cache = FileCache()
        cache.store(str(f), "new", token_count=5)

        resolved = str(Path(str(f)).resolve())
        assert resolved in cache._session_reads


# ---------------------------------------------------------------------------
# test_integrity_check
# ---------------------------------------------------------------------------

class TestIntegrityCheck:
    """Verifies check_integrity() detects unexpected file modifications between reads.

    Unchanged file → None. File modified after store() → dict with changed=True,
    expected_hash and actual_hash. Unknown file → None. Deleted file → None.
    """

    def test_unchanged_returns_none(self, tmp_path):
        f = tmp_path / "intact.py"
        f.write_text("safe", encoding="utf-8")

        cache = FileCache()
        cache.store(str(f), "safe", token_count=10)

        result = cache.check_integrity(str(f))
        assert result is None  # unchanged

    def test_changed_returns_dict(self, tmp_path):
        f = tmp_path / "tampered.py"
        f.write_text("original", encoding="utf-8")

        cache = FileCache()
        cache.store(str(f), "original", token_count=10)

        # Tamper with the file
        f.write_text("tampered!", encoding="utf-8")

        result = cache.check_integrity(str(f))
        assert result is not None
        assert result["changed"] is True
        assert "expected_hash" in result
        assert "actual_hash" in result

    def test_unknown_file_returns_none(self, tmp_path):
        cache = FileCache()
        result = cache.check_integrity(str(tmp_path / "unknown.py"))
        assert result is None

    def test_deleted_file_returns_none(self, tmp_path):
        f = tmp_path / "deleted.py"
        f.write_text("here now", encoding="utf-8")

        cache = FileCache()
        cache.store(str(f), "here now", token_count=5)
        f.unlink()

        result = cache.check_integrity(str(f))
        assert result is None


# ---------------------------------------------------------------------------
# test_invalidate
# ---------------------------------------------------------------------------

class TestInvalidate:
    """Verifies invalidate() removes the entry from both _cache and _session_reads."""

    def test_invalidate_removes_from_cache(self, tmp_path):
        f = tmp_path / "stale.py"
        f.write_text("content", encoding="utf-8")

        cache = FileCache()
        cache.store(str(f), "content", token_count=10)
        cache.invalidate(str(f))

        result = cache.check(str(f))
        assert result is None

    def test_invalidate_removes_session_read(self, tmp_path):
        f = tmp_path / "inv.py"
        f.write_text("x", encoding="utf-8")

        cache = FileCache()
        cache.store(str(f), "x", token_count=1)
        cache.invalidate(str(f))

        resolved = str(Path(str(f)).resolve())
        assert resolved not in cache._session_reads

    def test_invalidate_all(self, tmp_path):
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("a", encoding="utf-8")
        f2.write_text("b", encoding="utf-8")

        cache = FileCache()
        cache.store(str(f1), "a", token_count=1)
        cache.store(str(f2), "b", token_count=1)
        cache.invalidate_all()

        assert cache.check(str(f1)) is None
        assert cache.check(str(f2)) is None
        assert len(cache._cache) == 0
        assert len(cache._session_reads) == 0


# ---------------------------------------------------------------------------
# test_stats
# ---------------------------------------------------------------------------

class TestStats:
    """Verifies stats() and cached_files_list() accurately reflect cache state.

    Initial stats: cached_files==0, hits==0, misses==0, tokens_saved==0.
    After 1 hit + 1 miss: cached_files==1, hits==1, misses==1, tokens_saved==100, hit_rate==50.0.
    cached_files_list() returns entries with correct tokens and lines fields.
    """

    def test_initial_stats(self):
        cache = FileCache()
        s = cache.stats()
        assert s["cached_files"] == 0
        assert s["hits"] == 0
        assert s["misses"] == 0
        assert s["tokens_saved"] == 0

    def test_stats_after_hits_and_misses(self, tmp_path):
        f = tmp_path / "stat.py"
        f.write_text("data", encoding="utf-8")

        cache = FileCache()
        cache.store(str(f), "data", token_count=100)

        # One hit
        cache.check(str(f))
        # One miss (unknown file)
        cache.check(str(tmp_path / "nope.py"))

        s = cache.stats()
        assert s["cached_files"] == 1
        assert s["hits"] == 1
        assert s["misses"] == 1
        assert s["tokens_saved"] == 100
        assert s["hit_rate"] == 50.0

    def test_cached_files_list(self, tmp_path):
        f = tmp_path / "listed.py"
        f.write_text("hello\nworld\n", encoding="utf-8")

        cache = FileCache()
        cache.store(str(f), "hello\nworld\n", token_count=20)

        lst = cache.cached_files_list()
        assert len(lst) == 1
        assert lst[0]["tokens"] == 20
        assert lst[0]["lines"] == 3  # "hello\nworld\n" -> 3 lines


# ---------------------------------------------------------------------------
# test_persist_and_load
# ---------------------------------------------------------------------------

class TestPersistAndLoad:
    """Verifies FileCache persists to a JSON file and reloads cache entries (but not session reads).

    persist_path is created by store(). The JSON has version==1 and one cache entry.
    A new FileCache loading from the same path has cached_files==1 but check() returns None
    (session reads are not persisted). After re-storing the file, check() succeeds.
    """

    def test_persist_creates_file(self, tmp_path):
        persist = tmp_path / "cache.json"
        f = tmp_path / "src.py"
        f.write_text("source", encoding="utf-8")

        cache = FileCache(persist_path=persist)
        cache.store(str(f), "source", token_count=25)

        assert persist.exists()
        data = json.loads(persist.read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert len(data["cache"]) == 1

    def test_load_restores_cache(self, tmp_path):
        persist = tmp_path / "cache.json"
        f = tmp_path / "src.py"
        f.write_text("source", encoding="utf-8")

        # Create and persist
        cache1 = FileCache(persist_path=persist)
        cache1.store(str(f), "source", token_count=25)

        # Load into new cache
        cache2 = FileCache(persist_path=persist)
        assert cache2.stats()["cached_files"] == 1

        # But session reads are empty — so check returns None
        result = cache2.check(str(f))
        assert result is None  # not read this session

        # After re-storing, check succeeds
        cache2.store(str(f), "source", token_count=25)
        result = cache2.check(str(f))
        assert result is not None
        assert result["cached"] is True

    def test_persist_stats_restored(self, tmp_path):
        persist = tmp_path / "cache.json"
        f = tmp_path / "src.py"
        f.write_text("code", encoding="utf-8")

        cache1 = FileCache(persist_path=persist)
        cache1.store(str(f), "code", token_count=10)
        # Stats are only persisted by store/invalidate, not by check.
        # So persisted stats are 0/0 after store (check doesn't trigger save).

        cache2 = FileCache(persist_path=persist)
        s = cache2.stats()
        assert s["hits"] == 0
        assert s["misses"] == 0
        # Cache entries themselves are restored
        assert s["cached_files"] == 1
