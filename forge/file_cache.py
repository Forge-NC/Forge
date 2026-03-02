"""File content cache — never re-analyze unchanged files.

Maintains a SHA-256 hash of every file that has been read.
When the AI requests a file read, the cache checks if the
file has changed since the last read. If not, it returns a
short "unchanged" stub instead of the full file content,
saving potentially thousands of tokens.

This is the single biggest token-waste fix over Claude Code.
Claude re-reads the same file every time it needs to reference
it, charging full price every time. Forge reads it once and
remembers.
"""

import hashlib
import json
import time
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class FileCache:
    """Content-addressed file cache.

    Tracks SHA-256 hashes of files that have been read into context.
    Returns cache hits when the file hasn't changed.
    """

    def __init__(self, persist_path: Optional[Path] = None):
        # file_path (str) -> {hash, token_count, line_count, last_read}
        self._cache: dict[str, dict] = {}
        self._persist_path = persist_path
        self._hits = 0
        self._misses = 0
        self._tokens_saved = 0
        # Track files read THIS session — cache hits only fire for files
        # that are actually in the current context window.
        self._session_reads: set[str] = set()

        if persist_path and persist_path.exists():
            self._load()

    @staticmethod
    def _hash_file(path: Path) -> Optional[str]:
        """Compute SHA-256 of a file's contents."""
        try:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return None

    def check(self, file_path: str) -> Optional[dict]:
        """Check if a file is cached and unchanged.

        Returns:
            dict with {cached: True, tokens_saved, line_count, ...}
            if the file was read this session AND is unchanged.
            None if the file needs to be re-read.
        """
        p = Path(file_path).resolve()
        key = str(p)

        if key not in self._cache:
            self._misses += 1
            return None

        # Only return a cache hit if file was read THIS session.
        # Persisted hashes from previous sessions don't mean the
        # content is in the current context window.
        if key not in self._session_reads:
            self._misses += 1
            return None

        current_hash = self._hash_file(p)
        if current_hash is None:
            self._misses += 1
            return None

        cached = self._cache[key]
        if cached["hash"] == current_hash:
            self._hits += 1
            self._tokens_saved += cached["token_count"]
            return {
                "cached": True,
                "hash": current_hash,
                "tokens_saved": cached["token_count"],
                "line_count": cached["line_count"],
                "last_read": cached["last_read"],
                "read_count": cached.get("read_count", 1),
            }

        # File changed — cache miss
        self._misses += 1
        return None

    def store(self, file_path: str, content: str, token_count: int):
        """Store a file's hash after reading it."""
        p = Path(file_path).resolve()
        key = str(p)
        file_hash = self._hash_file(p)
        if file_hash is None:
            return

        prev = self._cache.get(key, {})
        self._cache[key] = {
            "hash": file_hash,
            "token_count": token_count,
            "line_count": content.count("\n") + 1,
            "last_read": time.time(),
            "read_count": prev.get("read_count", 0) + 1,
        }
        # Mark as read this session so future checks return hits
        self._session_reads.add(key)

        if self._persist_path:
            self._save()

    def check_integrity(self, file_path: str) -> Optional[dict]:
        """Check if a file was modified externally since our last read.

        Used to detect TOCTOU (time-of-check-time-of-use) conditions
        where a file changes between when the AI reads it and when it
        tries to edit it. Also catches concurrent editor modifications.

        Returns:
            None if file is unchanged or not cached.
            dict with {changed: True, expected_hash, actual_hash}
            if the file was modified externally.
        """
        p = Path(file_path).resolve()
        key = str(p)

        if key not in self._cache:
            return None  # Never read — can't check integrity

        if key not in self._session_reads:
            return None  # Not read this session

        cached = self._cache[key]
        current_hash = self._hash_file(p)

        if current_hash is None:
            return None  # File doesn't exist anymore

        if cached["hash"] != current_hash:
            return {
                "changed": True,
                "file_path": file_path,
                "expected_hash": cached["hash"][:12],
                "actual_hash": current_hash[:12],
                "last_read_ago": round(time.time() - cached["last_read"]),
            }

        return None  # Unchanged — integrity intact

    def invalidate(self, file_path: str):
        """Invalidate cache for a file (e.g., after writing/editing it)."""
        p = Path(file_path).resolve()
        key = str(p)
        self._session_reads.discard(key)
        if key in self._cache:
            del self._cache[key]
            if self._persist_path:
                self._save()

    def invalidate_all(self):
        """Clear the entire cache."""
        self._cache.clear()
        self._session_reads.clear()
        if self._persist_path:
            self._save()

    def stats(self) -> dict:
        """Return cache statistics."""
        return {
            "cached_files": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": (self._hits / max(1, self._hits + self._misses)) * 100,
            "tokens_saved": self._tokens_saved,
            "total_cached_tokens": sum(
                c["token_count"] for c in self._cache.values()),
        }

    def cached_files_list(self) -> list[dict]:
        """List all cached files with metadata."""
        result = []
        for path, info in sorted(self._cache.items()):
            result.append({
                "path": path,
                "tokens": info["token_count"],
                "lines": info["line_count"],
                "reads": info.get("read_count", 1),
                "hash": info["hash"][:12],
                "age_s": round(time.time() - info["last_read"]),
            })
        return result

    def _save(self):
        """Persist cache to disk."""
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": 1,
                "cache": self._cache,
                "stats": {
                    "hits": self._hits,
                    "misses": self._misses,
                    "tokens_saved": self._tokens_saved,
                },
            }
            self._persist_path.write_text(
                json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:
            log.debug("Cache save failed: %s", e)

    def _load(self):
        """Load cache from disk."""
        try:
            data = json.loads(
                self._persist_path.read_text(encoding="utf-8"))
            self._cache = data.get("cache", {})
            stats = data.get("stats", {})
            self._hits = stats.get("hits", 0)
            self._misses = stats.get("misses", 0)
            self._tokens_saved = stats.get("tokens_saved", 0)
        except Exception as e:
            log.debug("Cache load failed: %s", e)
