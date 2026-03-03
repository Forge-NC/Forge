"""
Semantic codebase index for Forge.

Indexes code files as vector embeddings using nomic-embed-text (via Ollama),
stores them in a numpy flat index, and provides cosine-similarity search.
"""

import hashlib
import json
import time
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, Optional

import numpy as np

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# File extensions to index
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".c", ".cpp", ".h", ".hpp",
    ".java", ".go", ".rs", ".rb", ".php", ".cs", ".swift", ".kt",
    ".scala", ".lua", ".sh", ".bash", ".ps1", ".bat",
    ".yaml", ".yml", ".toml", ".json", ".md", ".txt", ".cfg", ".ini",
    ".html", ".css", ".scss", ".sql",
}

# Directories to skip
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".env", "dist", "build", ".next", ".nuxt", "target", "bin", "obj",
    ".idea", ".vscode", ".claude", "vendor", "packages",
}

CHUNK_SIZE = 200     # Lines per chunk
CHUNK_OVERLAP = 50   # Overlap between chunks

# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass
class CodeChunk:
    file_path: str
    start_line: int
    end_line: int
    content: str
    language: str      # file extension without dot
    file_hash: str     # SHA-256 of the full file


# ---------------------------------------------------------------------------
# Codebase index
# ---------------------------------------------------------------------------


class CodebaseIndex:
    """Flat numpy vector index with cosine-similarity search."""

    def __init__(self, persist_dir: Path, embed_fn: Callable):
        """
        Parameters
        ----------
        persist_dir : Path
            Directory for persisted index files (e.g. ``~/.forge/vectors/``).
        embed_fn : Callable
            A callable that takes ``list[str]`` and returns
            ``list[list[float]]``  (from ``OllamaBackend.embed()``).
        """
        self._embed_fn: Callable = embed_fn
        self._persist_dir: Path = Path(persist_dir)
        self._dim: int = 768  # nomic-embed-text dimension

        self._vectors: Optional[np.ndarray] = None   # (N, dim) float32
        self._metadata: list[dict] = []               # CodeChunk dicts, parallel to vectors
        self._file_hashes: dict[str, str] = {}        # abs_path -> SHA-256
        self._last_indexed: float = 0.0               # epoch timestamp

        # Load persisted state if available
        self.load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index_file(self, file_path: str) -> int:
        """Index a single file.

        Returns the number of chunks added (0 if unchanged).
        """
        path = Path(file_path).resolve()
        abs_path = str(path)

        # 1. Hash
        file_hash = self._hash_file(path)
        if file_hash is None:
            log.warning("Could not hash file: %s", abs_path)
            return 0

        # 2. Skip unchanged
        if self._file_hashes.get(abs_path) == file_hash:
            return 0

        # 3. Remove stale data if re-indexing
        if abs_path in self._file_hashes:
            self.remove_file(abs_path)

        # 4. Read content
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            log.warning("Failed to read %s: %s", abs_path, exc)
            return 0

        if not content.strip():
            return 0

        # 5. Chunk
        chunks = self._chunk_file(content, abs_path, file_hash)
        if not chunks:
            return 0

        # 6. Embed (single batch call)
        texts = [c.content for c in chunks]
        try:
            raw_embeddings = self._embed_fn(texts)
        except Exception as exc:
            log.error("Embedding failed for %s: %s", abs_path, exc)
            return 0

        if not raw_embeddings:
            log.warning("Empty embedding result for %s", abs_path)
            return 0

        embeddings = np.array(raw_embeddings, dtype=np.float32)

        # Guard against wrong-shape arrays (e.g. old Ollama returning flat list)
        if embeddings.ndim == 1:
            embeddings = embeddings.reshape(1, -1)
        if embeddings.ndim != 2 or embeddings.shape[0] == 0:
            log.warning("Unexpected embedding shape %s for %s",
                        embeddings.shape, abs_path)
            return 0

        # Normalise so cosine similarity == dot product
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        embeddings = embeddings / norms

        # 7. Append to index
        if self._vectors is None:
            self._vectors = embeddings
        else:
            self._vectors = np.vstack([self._vectors, embeddings])

        for chunk in chunks:
            self._metadata.append(asdict(chunk))

        # 8. Update bookkeeping
        self._file_hashes[abs_path] = file_hash
        self._last_indexed = time.time()

        return len(chunks)

    def index_directory(
        self,
        dir_path: str,
        extensions: Optional[set] = None,
        callback: Optional[Callable] = None,
    ) -> dict:
        """Recursively index all code files under *dir_path*.

        Collects all chunks first, embeds in bulk batches, then assigns
        vectors back. This avoids loading/unloading the embed model per file.

        Parameters
        ----------
        extensions : set, optional
            File extensions to consider.  Defaults to ``CODE_EXTENSIONS``.
        callback : callable, optional
            ``callback(file_path: str, chunks_added: int)`` called per file.

        Returns
        -------
        dict
            ``{files_indexed, chunks_created, files_skipped, files_unchanged}``
        """
        exts = extensions or CODE_EXTENSIONS
        root = Path(dir_path).resolve()

        stats = {
            "files_indexed": 0,
            "chunks_created": 0,
            "files_skipped": 0,
            "files_unchanged": 0,
        }

        # Phase 1: Collect all chunks that need embedding
        pending: list[tuple[str, list[CodeChunk]]] = []  # (abs_path, chunks)
        for path in self._iter_code_files(root, exts):
            abs_path = str(path.resolve())
            try:
                file_hash = self._hash_file(path)
                if file_hash is None:
                    stats["files_skipped"] += 1
                    continue

                # Skip unchanged
                if self._file_hashes.get(abs_path) == file_hash:
                    stats["files_unchanged"] += 1
                    if callback:
                        try:
                            callback(str(path), 0)
                        except Exception:
                            pass
                    continue

                # Remove stale data if re-indexing
                if abs_path in self._file_hashes:
                    self.remove_file(abs_path)

                # Read content
                content = path.read_text(encoding="utf-8", errors="replace")
                if not content.strip():
                    stats["files_skipped"] += 1
                    continue

                chunks = self._chunk_file(content, abs_path, file_hash)
                if not chunks:
                    stats["files_skipped"] += 1
                    continue

                pending.append((abs_path, chunks))

            except Exception as exc:
                log.warning("Error reading %s: %s", path, exc)
                stats["files_skipped"] += 1

        if not pending:
            try:
                self.save()
            except Exception as exc:
                log.error("Failed to save index: %s", exc)
            return stats

        # Phase 2: Flatten all chunk texts for bulk embedding
        all_texts: list[str] = []
        chunk_ranges: list[tuple[int, int]] = []  # (start, end) indices
        for abs_path, chunks in pending:
            start = len(all_texts)
            all_texts.extend(c.content for c in chunks)
            chunk_ranges.append((start, len(all_texts)))

        # Phase 3: Embed everything in one call (embed() handles batching)
        log.info("Embedding %d chunks from %d files...",
                 len(all_texts), len(pending))
        try:
            raw_embeddings = self._embed_fn(all_texts)
        except Exception as exc:
            log.error("Bulk embedding failed: %s", exc)
            stats["files_skipped"] += len(pending)
            return stats

        if not raw_embeddings or len(raw_embeddings) != len(all_texts):
            log.warning(
                "Embedding count mismatch: expected %d, got %d",
                len(all_texts),
                len(raw_embeddings) if raw_embeddings else 0)
            stats["files_skipped"] += len(pending)
            try:
                self.save()
            except Exception:
                pass
            return stats

        all_vecs = np.array(raw_embeddings, dtype=np.float32)
        if all_vecs.ndim == 1:
            all_vecs = all_vecs.reshape(1, -1)
        if all_vecs.ndim != 2 or all_vecs.shape[0] != len(all_texts):
            log.warning("Unexpected embedding shape %s for %d texts",
                        all_vecs.shape, len(all_texts))
            stats["files_skipped"] += len(pending)
            return stats

        # Normalise so cosine similarity == dot product
        norms = np.linalg.norm(all_vecs, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        all_vecs = all_vecs / norms

        # Phase 4: Assign embeddings back to each file
        for idx, (abs_path, chunks) in enumerate(pending):
            start, end = chunk_ranges[idx]
            file_vecs = all_vecs[start:end]

            if self._vectors is None:
                self._vectors = file_vecs
            else:
                self._vectors = np.vstack([self._vectors, file_vecs])

            for chunk in chunks:
                self._metadata.append(asdict(chunk))

            file_hash = chunks[0].file_hash
            self._file_hashes[abs_path] = file_hash
            self._last_indexed = time.time()

            n = len(chunks)
            stats["files_indexed"] += 1
            stats["chunks_created"] += n

            if callback:
                try:
                    callback(abs_path, n)
                except Exception:
                    pass

        # Phase 5: Persist
        try:
            self.save()
        except Exception as exc:
            log.error("Failed to save index: %s", exc)

        return stats

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Return the *top_k* most similar chunks to *query*.

        Each result dict contains:
        ``{file_path, start_line, end_line, content, score, language}``
        """
        if self._vectors is None or len(self._metadata) == 0:
            return []

        # Embed query
        try:
            raw = self._embed_fn([query])
        except Exception as exc:
            log.error("Query embedding failed: %s", exc)
            return []

        if not raw or not raw[0]:
            log.warning("Empty query embedding result")
            return []

        q_vec = np.array(raw[0], dtype=np.float32)
        q_norm = np.linalg.norm(q_vec)
        if q_norm == 0:
            return []
        q_vec = q_vec / q_norm

        # Cosine similarity (vectors already normalised)
        scores = self._vectors @ q_vec  # (N,)

        # Top-k indices (descending)
        k = min(top_k, len(scores))
        top_indices = np.argpartition(scores, -k)[-k:]
        top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

        results = []
        for idx in top_indices:
            meta = self._metadata[idx]
            results.append({
                "file_path": meta["file_path"],
                "start_line": meta["start_line"],
                "end_line": meta["end_line"],
                "content": meta["content"],
                "score": float(scores[idx]),
                "language": meta["language"],
            })
        return results

    def remove_file(self, file_path: str):
        """Remove all chunks belonging to *file_path* from the index."""
        abs_path = str(Path(file_path).resolve())

        # Identify indices to keep
        keep = [
            i for i, m in enumerate(self._metadata)
            if m["file_path"] != abs_path
        ]

        if len(keep) == len(self._metadata):
            # Nothing to remove
            self._file_hashes.pop(abs_path, None)
            return

        if keep:
            self._vectors = self._vectors[keep]
            self._metadata = [self._metadata[i] for i in keep]
        else:
            self._vectors = None
            self._metadata = []

        self._file_hashes.pop(abs_path, None)

    def stats(self) -> dict:
        """Return summary statistics about the index."""
        total_chunks = len(self._metadata)
        unique_files = len({m["file_path"] for m in self._metadata})
        size_mb = 0.0
        if self._vectors is not None:
            size_mb = self._vectors.nbytes / (1024 * 1024)

        return {
            "total_chunks": total_chunks,
            "total_files": unique_files,
            "index_size_mb": round(size_mb, 2),
            "last_indexed": self._last_indexed,
            "embedding_model": "nomic-embed-text",
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self):
        """Persist vectors, metadata, and file hashes to disk."""
        try:
            self._persist_dir.mkdir(parents=True, exist_ok=True)

            emb_path = self._persist_dir / "embeddings.npy"
            meta_path = self._persist_dir / "metadata.json"
            hash_path = self._persist_dir / "file_hashes.json"

            if self._vectors is not None and len(self._metadata) > 0:
                np.save(str(emb_path), self._vectors)
            elif emb_path.exists():
                emb_path.unlink()

            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(self._metadata, f)

            with open(hash_path, "w", encoding="utf-8") as f:
                json.dump(self._file_hashes, f)

            log.debug(
                "Index saved: %d chunks, %d files",
                len(self._metadata),
                len(self._file_hashes),
            )
        except Exception as exc:
            log.error("Failed to save index to %s: %s", self._persist_dir, exc)

    def load(self):
        """Load vectors, metadata, and file hashes from disk.

        Silently skips missing files (fresh start).
        """
        emb_path = self._persist_dir / "embeddings.npy"
        meta_path = self._persist_dir / "metadata.json"
        hash_path = self._persist_dir / "file_hashes.json"

        # Metadata
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    self._metadata = json.load(f)
            except Exception as exc:
                log.warning("Failed to load metadata: %s", exc)
                self._metadata = []

        # Embeddings
        if emb_path.exists() and self._metadata:
            try:
                self._vectors = np.load(str(emb_path)).astype(np.float32)
                if self._vectors.shape[0] != len(self._metadata):
                    log.warning(
                        "Vectors/metadata size mismatch (%d vs %d) -- resetting",
                        self._vectors.shape[0],
                        len(self._metadata),
                    )
                    self._vectors = None
                    self._metadata = []
            except Exception as exc:
                log.warning("Failed to load embeddings: %s", exc)
                self._vectors = None
        else:
            self._vectors = None

        # File hashes
        if hash_path.exists():
            try:
                with open(hash_path, "r", encoding="utf-8") as f:
                    self._file_hashes = json.load(f)
            except Exception as exc:
                log.warning("Failed to load file hashes: %s", exc)
                self._file_hashes = {}

        log.debug(
            "Index loaded: %d chunks, %d file hashes",
            len(self._metadata),
            len(self._file_hashes),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _chunk_file(
        self, content: str, file_path: str, file_hash: str
    ) -> list[CodeChunk]:
        """Split *content* into overlapping chunks of ~CHUNK_SIZE lines."""
        ext = Path(file_path).suffix.lstrip(".")
        lines = content.splitlines(keepends=True)
        total = len(lines)

        if total == 0:
            return []

        chunks: list[CodeChunk] = []

        if total < 50:
            # Small file -- single chunk
            chunk_text = (
                f"# File: {file_path} (lines 1-{total})\n"
                + "".join(lines)
            )
            chunks.append(CodeChunk(
                file_path=file_path,
                start_line=1,
                end_line=total,
                content=chunk_text,
                language=ext,
                file_hash=file_hash,
            ))
            return chunks

        start = 0
        while start < total:
            end = min(start + CHUNK_SIZE, total)
            chunk_lines = lines[start:end]
            chunk_text = (
                f"# File: {file_path} (lines {start + 1}-{end})\n"
                + "".join(chunk_lines)
            )
            chunks.append(CodeChunk(
                file_path=file_path,
                start_line=start + 1,
                end_line=end,
                content=chunk_text,
                language=ext,
                file_hash=file_hash,
            ))

            # Advance with overlap
            if end >= total:
                break
            start = end - CHUNK_OVERLAP

        return chunks

    @staticmethod
    def _iter_code_files(root: Path, extensions: set):
        """Yield code files under *root*, respecting SKIP_DIRS and size limits."""
        try:
            entries = sorted(root.iterdir())
        except PermissionError:
            return

        for entry in entries:
            if entry.is_dir():
                if entry.name in SKIP_DIRS:
                    continue
                yield from CodebaseIndex._iter_code_files(entry, extensions)
            elif entry.is_file():
                if entry.suffix.lower() not in extensions:
                    continue
                # Skip files > 500 KB (likely binary / generated)
                try:
                    if entry.stat().st_size > 500 * 1024:
                        continue
                except OSError:
                    continue
                yield entry

    @staticmethod
    def _hash_file(path: Path) -> Optional[str]:
        """Return the SHA-256 hex digest of a file's bytes."""
        try:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for block in iter(lambda: f.read(8192), b""):
                    h.update(block)
            return h.hexdigest()
        except Exception:
            return None
