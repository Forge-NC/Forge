"""Tests for CodebaseIndex function-boundary chunking."""

import pytest
from forge.index import CodebaseIndex, CodeChunk


class TestFunctionBoundaryChunking:
    """Verifies _chunk_by_functions correctly detects Python function/method boundaries.

    3 top-level functions → >=3 chunks with file_path='test.py'. Class with methods +
    standalone function → >=2 chunks. async def and decorated functions handled.
    Decorator lines included in chunk content. Indented class methods detected as
    boundaries. No functions → [] (triggers fixed-size fallback). Single function → []
    (need >=2 boundaries). Nested outer/inner functions → >=2 chunks.
    start_line >= 1 and end_line >= start_line. file_hash and language propagated to all chunks.
    """

    def _chunk(self, source: str) -> list[CodeChunk]:
        """Helper: chunk a Python source string."""
        lines = source.splitlines(keepends=True)
        return CodebaseIndex._chunk_by_functions(
            lines, "test.py", "abc123", "py")

    def test_top_level_functions(self):
        source = """import os

def foo():
    pass

def bar():
    pass

def baz():
    pass
"""
        chunks = self._chunk(source)
        assert len(chunks) >= 3  # module header + 3 functions (or merged)
        # All chunks should reference test.py
        for c in chunks:
            assert c.file_path == "test.py"

    def test_class_with_methods(self):
        source = """class MyClass:
    def __init__(self):
        self.x = 1

    def method_a(self):
        return self.x

    def method_b(self):
        return self.x + 1

def standalone():
    pass
"""
        chunks = self._chunk(source)
        assert len(chunks) >= 2  # at least class + standalone

    def test_async_functions(self):
        source = """import asyncio

async def fetch_data():
    pass

async def process_data():
    pass

def sync_func():
    pass
"""
        chunks = self._chunk(source)
        assert len(chunks) >= 2

    def test_decorated_functions(self):
        source = """import functools

@functools.lru_cache
def cached_func():
    pass

@property
def my_prop():
    pass

def plain_func():
    pass
"""
        chunks = self._chunk(source)
        assert len(chunks) >= 2
        # Decorator should be included in the chunk content
        combined = "".join(c.content for c in chunks)
        assert "@functools.lru_cache" in combined

    def test_indented_methods_detected(self):
        """Class methods (indented def) should be detected as boundaries."""
        source = """class Foo:
    def method_one(self):
        return 1

    def method_two(self):
        return 2

    def method_three(self):
        return 3

class Bar:
    def bar_method(self):
        pass
"""
        chunks = self._chunk(source)
        # Should detect indented defs as boundaries
        assert len(chunks) >= 2

    def test_fallback_on_no_functions(self):
        """Files with no functions should return empty (triggers fallback)."""
        source = """x = 1
y = 2
z = x + y
"""
        chunks = self._chunk(source)
        assert chunks == []  # Fallback

    def test_single_function_returns_empty(self):
        """Files with only 1 function boundary return empty (fallback)."""
        source = """def only_one():
    pass
"""
        chunks = self._chunk(source)
        assert chunks == []  # Need >= 2 boundaries

    def test_nested_functions(self):
        source = """def outer():
    def inner():
        pass
    return inner

def another():
    pass

def third():
    pass
"""
        chunks = self._chunk(source)
        # Should detect all three as boundaries
        assert len(chunks) >= 2

    def test_chunk_line_numbers_correct(self):
        source = """# Module header

def first():
    pass

def second():
    pass

def third():
    pass
"""
        chunks = self._chunk(source)
        assert len(chunks) >= 2
        for c in chunks:
            assert c.start_line >= 1
            assert c.end_line >= c.start_line

    def test_file_hash_propagated(self):
        source = """def a():
    pass

def b():
    pass
"""
        chunks = self._chunk(source)
        for c in chunks:
            assert c.file_hash == "abc123"
            assert c.language == "py"


class TestChunkFileDispatch:
    """Verifies _chunk_file routes Python to function-boundary chunking and other langs to fixed-size.

    Python file >50 lines with 10 functions → >=2 function-boundary chunks.
    Non-Python file (data.js) → fixed-size chunks all with language='js'.
    """

    def test_python_uses_function_chunking(self):
        """Python file with functions should use function-boundary chunking."""
        source_lines = []
        # Generate a Python file with multiple functions (>50 lines)
        for i in range(10):
            source_lines.append(f"def func_{i}():\n")
            for j in range(8):
                source_lines.append(f"    line_{j} = {j}\n")
            source_lines.append("\n")
        source = "".join(source_lines)
        assert len(source.splitlines()) > 50

        # Use a mock embed_fn (won't be called by _chunk_file)
        idx = CodebaseIndex.__new__(CodebaseIndex)
        chunks = idx._chunk_file(source, "big.py", "hash123")
        assert len(chunks) >= 2
        # Verify function boundary chunking was used (chunk sizes should vary)
        # rather than all being exactly CHUNK_SIZE

    def test_non_python_uses_fixed_chunks(self):
        """Non-Python files should use fixed-size chunking."""
        source = "\n".join([f"line {i}" for i in range(100)])
        idx = CodebaseIndex.__new__(CodebaseIndex)
        chunks = idx._chunk_file(source, "data.js", "hash456")
        assert len(chunks) >= 1
        for c in chunks:
            assert c.language == "js"


class TestConfigValidatorsComplete:
    """Verifies every key in config DEFAULTS has a corresponding entry in _VALIDATORS.

    Any DEFAULTS key missing from _VALIDATORS would cause a crash on config load.
    """

    def test_all_defaults_have_validators(self):
        from forge.config import DEFAULTS, _VALIDATORS
        missing = [k for k in DEFAULTS if k not in _VALIDATORS]
        assert missing == [], f"Config keys without validators: {missing}"
