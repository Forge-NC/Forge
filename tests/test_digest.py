"""Tests for codebase digester (forge/digest.py)."""
import json
from pathlib import Path

import pytest

from forge.digest import CodebaseDigester, FileDigest, SymbolInfo, ProjectDigest


@pytest.fixture
def digester(tmp_path):
    persist_dir = tmp_path / "digest"
    persist_dir.mkdir()
    return CodebaseDigester(persist_dir=persist_dir)


@pytest.fixture
def sample_project(tmp_path):
    """Create a small sample project for scanning."""
    proj = tmp_path / "project"
    proj.mkdir()
    # Python file with class and functions
    (proj / "main.py").write_text(
        '"""Main module."""\n'
        'import os\n'
        'import sys\n\n'
        'class App:\n'
        '    """Main application class."""\n'
        '    def __init__(self, name: str):\n'
        '        self.name = name\n\n'
        '    def run(self) -> None:\n'
        '        """Run the app."""\n'
        '        print(f"Running {self.name}")\n\n'
        'def helper(x: int) -> int:\n'
        '    """Helper function."""\n'
        '    return x * 2\n',
        encoding="utf-8",
    )
    # JavaScript file
    (proj / "utils.js").write_text(
        'function formatDate(date) {\n'
        '    return date.toISOString();\n'
        '}\n\n'
        'class Logger {\n'
        '    constructor(name) {\n'
        '        this.name = name;\n'
        '    }\n'
        '    log(msg) {\n'
        '        console.log(`[${this.name}] ${msg}`);\n'
        '    }\n'
        '}\n',
        encoding="utf-8",
    )
    # Subdirectory
    sub = proj / "src"
    sub.mkdir()
    (sub / "config.py").write_text(
        'DEFAULTS = {"debug": False, "port": 8080}\n\n'
        'def load_config(path: str) -> dict:\n'
        '    """Load config from file."""\n'
        '    return DEFAULTS.copy()\n',
        encoding="utf-8",
    )
    # File that should be skipped
    skip = proj / "node_modules"
    skip.mkdir()
    (skip / "junk.js").write_text("// skip me", encoding="utf-8")
    return proj


# ── Initialization ──

class TestInit:
    """Verifies CodebaseDigester creates its persist dir and starts with no digest."""

    def test_creates_persist_dir(self, tmp_path):
        d = tmp_path / "new_digest"
        CodebaseDigester(persist_dir=d)
        assert d.exists()

    def test_no_digest_initially(self, digester):
        assert digester.get_digest() is None


# ── Scanning ──

class TestScan:
    """Verifies scan() traverses the project, extracts symbols, skips excluded dirs, and calls callbacks.

    A project with main.py + utils.js + src/config.py must yield >= 3 files and > 0 symbols.
    node_modules/ directory must be excluded. Python language detected. Symbol extraction
    finds at least App, run, helper. Non-existent root raises ValueError. callback(path, n, total)
    is called at least once. force=True rescans with same file count.
    """

    def test_scans_project(self, digester, sample_project):
        result = digester.scan(str(sample_project))
        assert isinstance(result, ProjectDigest)
        assert result.total_files >= 3  # main.py, utils.js, config.py
        assert result.total_lines > 0
        assert result.total_symbols > 0

    def test_skips_excluded_dirs(self, digester, sample_project):
        result = digester.scan(str(sample_project))
        # node_modules should be skipped
        for path in result.files:
            assert "node_modules" not in path

    def test_language_detection(self, digester, sample_project):
        result = digester.scan(str(sample_project))
        assert "python" in result.by_language or "py" in result.by_language

    def test_symbol_extraction(self, digester, sample_project):
        result = digester.scan(str(sample_project))
        assert result.total_symbols >= 3  # App, run, helper at minimum

    def test_invalid_root_raises(self, digester):
        with pytest.raises(ValueError):
            digester.scan("/nonexistent/path/xyz")

    def test_callback_called(self, digester, sample_project):
        calls = []
        def cb(path, num, total):
            calls.append((path, num, total))
        digester.scan(str(sample_project), callback=cb)
        assert len(calls) > 0

    def test_force_rescan(self, digester, sample_project):
        d1 = digester.scan(str(sample_project))
        d2 = digester.scan(str(sample_project), force=True)
        assert d2.total_files == d1.total_files


# ── Get file ──

class TestGetFile:
    """Verifies get_file() finds FileDigest by basename for scanned files and returns None for unknowns."""

    def test_get_existing_file(self, digester, sample_project):
        digester.scan(str(sample_project))
        fd = digester.get_file("main.py")
        assert fd is not None
        assert isinstance(fd, FileDigest)
        assert fd.lines > 0

    def test_get_nonexistent_file(self, digester, sample_project):
        digester.scan(str(sample_project))
        assert digester.get_file("nonexistent.py") is None

    def test_get_nested_file(self, digester, sample_project):
        digester.scan(str(sample_project))
        fd = digester.get_file("config.py")
        assert fd is not None


# ── Symbol search ──

class TestSearchSymbols:
    """Verifies search_symbols() finds symbols by name, supports partial match, kind filter, and limit.

    Exact 'App' match → result with name=='App'. Partial 'help' → finds 'helper'.
    kind='class' filter → all results have kind=='class'. 'zzzznonexistent' → [].
    limit=2 → len(results) <= 2. Results have a 'name' key in their dict.
    """

    def test_exact_match(self, digester, sample_project):
        digester.scan(str(sample_project))
        results = digester.search_symbols("App")
        assert len(results) > 0
        assert any(r["name"] == "App" for r in results)

    def test_partial_match(self, digester, sample_project):
        digester.scan(str(sample_project))
        results = digester.search_symbols("help")
        assert len(results) > 0

    def test_kind_filter(self, digester, sample_project):
        digester.scan(str(sample_project))
        results = digester.search_symbols("", kind="class")
        for r in results:
            assert r["kind"] == "class"

    def test_no_match(self, digester, sample_project):
        digester.scan(str(sample_project))
        results = digester.search_symbols("zzzznonexistent")
        assert len(results) == 0

    def test_limit(self, digester, sample_project):
        digester.scan(str(sample_project))
        results = digester.search_symbols("", limit=2)
        assert len(results) <= 2

    def test_result_structure(self, digester, sample_project):
        digester.scan(str(sample_project))
        results = digester.search_symbols("App")
        if results:
            r = results[0]
            assert "name" in r
            assert "kind" in r
            assert "file" in r
            assert "line" in r
            assert "score" in r


# ── Read symbol source ──

class TestReadSymbolSource:
    """Verifies read_symbol_source() returns source text for known symbols and an error/empty for unknowns.

    A known symbol like 'App' in main.py must return text containing 'App'. An unknown file path
    must return an error message or empty string (not raise). Multiple symbols returns non-empty text.
    """

    def test_reads_known_symbol(self, digester, sample_project):
        digester.scan(str(sample_project))
        source = digester.read_symbol_source("main.py", ["App"])
        assert "class App" in source or "App" in source

    def test_unknown_file_returns_error(self, digester, sample_project):
        digester.scan(str(sample_project))
        result = digester.read_symbol_source("nonexistent.py", ["Foo"])
        assert "error" in result.lower() or "not found" in result.lower() or result == ""

    def test_multiple_symbols(self, digester, sample_project):
        digester.scan(str(sample_project))
        source = digester.read_symbol_source("main.py", ["App", "helper"])
        assert len(source) > 0


# ── Generate summary ──

class TestGenerateSummary:
    """Verifies generate_summary() returns a non-empty string bounded by max_tokens, and '' when no digest.

    A scanned project produces a non-empty string. max_tokens=100 produces a shorter or equal string
    than max_tokens=10000. When no scan has been performed, returns '' or a 'no digest' message.
    """

    def test_generates_text(self, digester, sample_project):
        digester.scan(str(sample_project))
        summary = digester.generate_summary()
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_max_tokens_respected(self, digester, sample_project):
        digester.scan(str(sample_project))
        short = digester.generate_summary(max_tokens=100)
        long = digester.generate_summary(max_tokens=10000)
        assert len(short) <= len(long)

    def test_no_digest_returns_empty(self, digester):
        summary = digester.generate_summary()
        assert summary == "" or "no" in summary.lower()


# ── Cache persistence ──

class TestCachePersistence:
    """Verifies scan results are written to digest.json and reloaded by a new CodebaseDigester instance.

    After scanning, persist_dir/digest.json must exist. A second CodebaseDigester with the same
    persist_dir must load the cached digest with the same total_files count.
    """

    def test_cache_written(self, digester, sample_project):
        digester.scan(str(sample_project))
        cache_file = digester._persist_dir / "digest.json"
        assert cache_file.exists()

    def test_cache_loaded_on_init(self, tmp_path, sample_project):
        persist_dir = tmp_path / "digest_cache"
        persist_dir.mkdir()
        d1 = CodebaseDigester(persist_dir=persist_dir)
        d1.scan(str(sample_project))
        files1 = d1.get_digest().total_files

        d2 = CodebaseDigester(persist_dir=persist_dir)
        digest = d2.get_digest()
        assert digest is not None
        assert digest.total_files == files1


# ── Directory structure ──

class TestDirectoryStructure:
    """Verifies the ProjectDigest tracks directories and per-file SHA-256 hashes.

    result.directories must be non-empty after scanning a project with subdirectories.
    Every FileDigest in result.files must have a 64-char sha256 hex string (SHA-256 output).
    """

    def test_directories_tracked(self, digester, sample_project):
        result = digester.scan(str(sample_project))
        assert len(result.directories) > 0

    def test_file_hashes(self, digester, sample_project):
        result = digester.scan(str(sample_project))
        for path, fd in result.files.items():
            assert fd.sha256 is not None
            assert len(fd.sha256) == 64  # SHA-256 hex length
