"""Codebase Digest — enterprise-grade structural analysis engine.

Parses every file in a codebase structurally (AST for Python, regex for
PHP/JS/SQL/HTML/CSS), extracting classes, functions, methods, routes,
DB tables, and imports. Zero LLM tokens — all analysis happens in Python.

Produces a compact structural map (4-8K tokens for 2000+ files) that gives
the AI x-ray vision of the entire project. Supports incremental updates
via SHA-256 change detection and parallel I/O for speed.

Progressive detail pyramid:
  Layer 0: scan()          — full project summary (~4-8K tokens total)
  Layer 1: get_file()      — one file's symbols (~50 tokens)
  Layer 2: read_symbols()  — specific function/class source (~10-100 tokens)
  Layer 3: read_file       — full file (only when editing)
"""

import ast
import hashlib
import json
import logging
import os
import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reuse constants from index.py
# ---------------------------------------------------------------------------

CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".c", ".cpp", ".h", ".hpp",
    ".java", ".go", ".rs", ".rb", ".php", ".cs", ".swift", ".kt",
    ".scala", ".lua", ".sh", ".bash", ".ps1", ".bat",
    ".yaml", ".yml", ".toml", ".json", ".md", ".txt", ".cfg", ".ini",
    ".html", ".css", ".scss", ".sql", ".vue", ".svelte",
}

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".env", "dist", "build", ".next", ".nuxt", "target", "bin", "obj",
    ".idea", ".vscode", ".claude", "vendor", "packages",
    ".cache", ".tox", "coverage", "htmlcov", ".mypy_cache",
}

# Max file size to parse (skip huge generated/minified files)
MAX_FILE_SIZE = 512 * 1024  # 512 KB

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class SymbolInfo:
    """A single symbol extracted from a source file."""
    name: str           # "MyClass", "handle_request", "users"
    kind: str           # "class", "function", "method", "route", "table", etc.
    line: int           # Start line (1-based)
    end_line: int       # End line (for read_symbols extraction)
    signature: str      # "def handle_request(self, req: Request) -> Response"
    docstring: str      # First line of docstring (truncated)
    parent: str         # "MyClass" for methods, "" for top-level


@dataclass
class FileDigest:
    """Structural digest of a single file."""
    path: str           # Relative path from project root
    language: str       # "python", "php", "javascript", etc.
    lines: int          # Total line count
    size_bytes: int     # File size
    sha256: str         # For incremental updates
    symbols: list       # list[SymbolInfo] (stored as dicts for JSON)
    imports: list       # list[str]
    summary_line: str   # Auto-generated one-liner


@dataclass
class ProjectDigest:
    """Full structural digest of a project."""
    root: str
    total_files: int = 0
    total_lines: int = 0
    total_symbols: int = 0
    by_language: dict = field(default_factory=dict)
    by_kind: dict = field(default_factory=dict)
    files: dict = field(default_factory=dict)       # path -> FileDigest
    directories: dict = field(default_factory=dict)  # dir -> [files]
    scan_time: float = 0.0
    notes: dict = field(default_factory=dict)        # topic -> content


# ---------------------------------------------------------------------------
# Language extractors
# ---------------------------------------------------------------------------

def _extract_python(content: str, lines: list[str]) -> tuple[list[SymbolInfo], list[str]]:
    """Extract symbols from Python using AST (most reliable).

    Uses explicit tree traversal — NOT ast.walk() — so we always know
    the parent context (top-level vs inside a class vs nested function).
    """
    symbols = []
    imports = []

    try:
        tree = ast.parse(content)
    except SyntaxError:
        # Fall back to regex for files with syntax errors
        return _extract_python_regex(content, lines)

    def _visit_body(body: list, parent_class: str = ""):
        """Recursively visit a list of AST statements.

        parent_class tracks whether we're inside a class definition,
        so methods vs top-level functions are distinguished correctly.
        """
        for node in body:
            if isinstance(node, ast.ClassDef):
                doc = ast.get_docstring(node) or ""
                doc_line = doc.split("\n")[0][:80] if doc else ""
                end = node.end_lineno or node.lineno
                sig = f"class {node.name}"
                if node.bases:
                    bases = []
                    for b in node.bases:
                        if isinstance(b, ast.Name):
                            bases.append(b.id)
                        elif isinstance(b, ast.Attribute):
                            try:
                                bases.append(ast.unparse(b))
                            except Exception:
                                pass
                    if bases:
                        sig += f"({', '.join(bases)})"
                symbols.append(SymbolInfo(
                    name=node.name, kind="class", line=node.lineno,
                    end_line=end, signature=sig,
                    docstring=doc_line, parent=parent_class,
                ))
                # Recurse into the class body — children are methods
                _visit_body(node.body, parent_class=node.name)

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node) or ""
                doc_line = doc.split("\n")[0][:80] if doc else ""
                end = node.end_lineno or node.lineno
                sig = _python_func_sig(node)
                kind = "method" if parent_class else "function"
                symbols.append(SymbolInfo(
                    name=node.name, kind=kind, line=node.lineno,
                    end_line=end, signature=sig,
                    docstring=doc_line, parent=parent_class,
                ))
                # Recurse into function body for nested classes/functions
                _visit_body(node.body, parent_class="")

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    imports.append(
                        f"{module}.{alias.name}" if module else alias.name)

            # Recurse into control flow bodies (if/for/while/try/with)
            # so we catch functions defined inside conditionals
            elif isinstance(node, (ast.If, ast.For, ast.While,
                                   ast.AsyncFor, ast.With, ast.AsyncWith)):
                _visit_body(getattr(node, 'body', []), parent_class)
                _visit_body(getattr(node, 'orelse', []), parent_class)
            elif isinstance(node, ast.Try):
                _visit_body(node.body, parent_class)
                for handler in node.handlers:
                    _visit_body(handler.body, parent_class)
                _visit_body(node.orelse, parent_class)
                _visit_body(node.finalbody, parent_class)

    # Start from the module body — these are the actual top-level statements
    _visit_body(tree.body)
    return symbols, imports


def _python_func_sig(node) -> str:
    """Build a function signature string from an AST node."""
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    args_parts = []
    args = node.args

    # Regular args
    for i, arg in enumerate(args.args):
        a = arg.arg
        if arg.annotation:
            try:
                a += f": {ast.unparse(arg.annotation)}"
            except Exception:
                pass
        # Default values
        defaults_offset = len(args.args) - len(args.defaults)
        if i >= defaults_offset:
            try:
                a += f"={ast.unparse(args.defaults[i - defaults_offset])}"
            except Exception:
                pass
        args_parts.append(a)

    if args.vararg:
        args_parts.append(f"*{args.vararg.arg}")
    if args.kwonlyargs:
        if not args.vararg:
            args_parts.append("*")
        for kw in args.kwonlyargs:
            args_parts.append(kw.arg)
    if args.kwarg:
        args_parts.append(f"**{args.kwarg.arg}")

    sig = f"{prefix} {node.name}({', '.join(args_parts)})"

    if node.returns:
        try:
            sig += f" -> {ast.unparse(node.returns)}"
        except Exception:
            pass

    return sig


def _extract_python_regex(content: str, lines: list[str]) -> tuple[list[SymbolInfo], list[str]]:
    """Fallback Python extractor using regex (for files with syntax errors)."""
    symbols = []
    imports = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Classes
        m = re.match(r'^class\s+(\w+)', stripped)
        if m:
            symbols.append(SymbolInfo(
                name=m.group(1), kind="class", line=i, end_line=i,
                signature=stripped.rstrip(":"), docstring="", parent="",
            ))
        # Functions
        m = re.match(r'^(async\s+)?def\s+(\w+)\s*\(', stripped)
        if m:
            symbols.append(SymbolInfo(
                name=m.group(2), kind="function", line=i, end_line=i,
                signature=stripped.rstrip(":"), docstring="", parent="",
            ))
        # Imports
        m = re.match(r'^(?:from\s+(\S+)\s+)?import\s+(.+)', stripped)
        if m:
            module = m.group(1) or ""
            names = [n.strip().split(" as ")[0] for n in m.group(2).split(",")]
            for n in names:
                imports.append(f"{module}.{n}" if module else n)

    return symbols, imports


def _extract_php(content: str, lines: list[str]) -> tuple[list[SymbolInfo], list[str]]:
    """Extract symbols from PHP files using regex."""
    symbols = []
    imports = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Namespace
        m = re.match(r'^namespace\s+([\w\\]+)', stripped)
        if m:
            imports.append(f"namespace:{m.group(1)}")

        # Use statements
        m = re.match(r'^use\s+([\w\\]+)', stripped)
        if m:
            imports.append(m.group(1))

        # Include/require
        m = re.match(r'^(?:include|require|include_once|require_once)\s*[\(]?\s*[\'"]([^\'"]+)', stripped)
        if m:
            imports.append(f"include:{m.group(1)}")

        # Classes (with optional extends/implements)
        m = re.match(r'^(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?', stripped)
        if m:
            sig = f"class {m.group(1)}"
            if m.group(2):
                sig += f" extends {m.group(2)}"
            symbols.append(SymbolInfo(
                name=m.group(1), kind="class", line=i, end_line=i,
                signature=sig, docstring="", parent="",
            ))

        # Interfaces
        m = re.match(r'^interface\s+(\w+)', stripped)
        if m:
            symbols.append(SymbolInfo(
                name=m.group(1), kind="class", line=i, end_line=i,
                signature=f"interface {m.group(1)}", docstring="", parent="",
            ))

        # Functions (top-level and methods)
        m = re.match(r'^(?:public|protected|private|static|\s)*function\s+(\w+)\s*\(([^)]*)\)', stripped)
        if m:
            name = m.group(1)
            params = m.group(2).strip()
            sig = f"function {name}({params})"
            symbols.append(SymbolInfo(
                name=name, kind="function", line=i, end_line=i,
                signature=sig, docstring="", parent="",
            ))

        # Routes: $router->get/post/put/delete or $app->get etc.
        m = re.match(r'.*(?:\$router|\$app|Route::)\s*(?:->|::)\s*(get|post|put|delete|patch)\s*\(\s*[\'"]([^\'"]+)', stripped, re.IGNORECASE)
        if m:
            method = m.group(1).upper()
            path = m.group(2)
            symbols.append(SymbolInfo(
                name=f"{method} {path}", kind="route", line=i, end_line=i,
                signature=f"route {method} {path}", docstring="", parent="",
            ))

    # Compute end_lines for PHP symbols
    _compute_end_lines_brace(symbols, lines)
    return symbols, imports


def _extract_javascript(content: str, lines: list[str]) -> tuple[list[SymbolInfo], list[str]]:
    """Extract symbols from JavaScript/TypeScript files using regex."""
    symbols = []
    imports = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # ES6 imports
        m = re.match(r'^import\s+.*\s+from\s+[\'"]([^\'"]+)', stripped)
        if m:
            imports.append(m.group(1))

        # CommonJS require
        m = re.match(r'^(?:const|let|var)\s+\w+\s*=\s*require\s*\(\s*[\'"]([^\'"]+)', stripped)
        if m:
            imports.append(m.group(1))

        # Classes
        m = re.match(r'^(?:export\s+)?(?:default\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?', stripped)
        if m:
            sig = f"class {m.group(1)}"
            if m.group(2):
                sig += f" extends {m.group(2)}"
            symbols.append(SymbolInfo(
                name=m.group(1), kind="class", line=i, end_line=i,
                signature=sig, docstring="", parent="",
            ))

        # Named function declarations
        m = re.match(r'^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)', stripped)
        if m:
            sig = f"function {m.group(1)}({m.group(2).strip()})"
            symbols.append(SymbolInfo(
                name=m.group(1), kind="function", line=i, end_line=i,
                signature=sig, docstring="", parent="",
            ))

        # Arrow / function expression: const name = (async) (...) =>
        m = re.match(r'^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[^=])\s*=>', stripped)
        if m:
            symbols.append(SymbolInfo(
                name=m.group(1), kind="function", line=i, end_line=i,
                signature=f"const {m.group(1)} = =>", docstring="", parent="",
            ))

        # Express-style routes
        m = re.match(r'.*(?:app|router)\.(get|post|put|delete|patch|use)\s*\(\s*[\'"]([^\'"]+)', stripped, re.IGNORECASE)
        if m:
            method = m.group(1).upper()
            path = m.group(2)
            symbols.append(SymbolInfo(
                name=f"{method} {path}", kind="route", line=i, end_line=i,
                signature=f"route {method} {path}", docstring="", parent="",
            ))

    _compute_end_lines_brace(symbols, lines)
    return symbols, imports


def _extract_sql(content: str, lines: list[str]) -> tuple[list[SymbolInfo], list[str]]:
    """Extract symbols from SQL files using regex."""
    symbols = []
    imports = []

    # Multi-line patterns — search the full content
    # CREATE TABLE
    for m in re.finditer(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`"\[]?(\w+)', content, re.IGNORECASE):
        line_num = content[:m.start()].count("\n") + 1
        # Count columns
        table_block = content[m.start():]
        paren_match = re.search(r'\(([^;]*?)\)', table_block, re.DOTALL)
        col_count = 0
        if paren_match:
            cols = paren_match.group(1)
            col_count = len([l for l in cols.split("\n")
                           if re.match(r'\s*[`"\[]?\w+[`"\]]?\s+\w+', l.strip())])
        symbols.append(SymbolInfo(
            name=m.group(1), kind="table", line=line_num, end_line=line_num,
            signature=f"CREATE TABLE {m.group(1)} ({col_count} columns)",
            docstring="", parent="",
        ))

    # CREATE VIEW
    for m in re.finditer(r'CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+[`"\[]?(\w+)', content, re.IGNORECASE):
        line_num = content[:m.start()].count("\n") + 1
        symbols.append(SymbolInfo(
            name=m.group(1), kind="view", line=line_num, end_line=line_num,
            signature=f"CREATE VIEW {m.group(1)}", docstring="", parent="",
        ))

    # CREATE PROCEDURE / FUNCTION
    for m in re.finditer(r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:PROCEDURE|FUNCTION)\s+[`"\[]?(\w+)', content, re.IGNORECASE):
        line_num = content[:m.start()].count("\n") + 1
        symbols.append(SymbolInfo(
            name=m.group(1), kind="function", line=line_num, end_line=line_num,
            signature=f"CREATE {m.group(0).split()[1].upper()} {m.group(1)}",
            docstring="", parent="",
        ))

    # CREATE INDEX
    for m in re.finditer(r'CREATE\s+(?:UNIQUE\s+)?INDEX\s+[`"\[]?(\w+)\s+ON\s+[`"\[]?(\w+)', content, re.IGNORECASE):
        line_num = content[:m.start()].count("\n") + 1
        symbols.append(SymbolInfo(
            name=m.group(1), kind="index", line=line_num, end_line=line_num,
            signature=f"INDEX {m.group(1)} ON {m.group(2)}",
            docstring="", parent="",
        ))

    # ALTER TABLE (just the table name)
    for m in re.finditer(r'ALTER\s+TABLE\s+[`"\[]?(\w+)', content, re.IGNORECASE):
        line_num = content[:m.start()].count("\n") + 1
        imports.append(f"alters:{m.group(1)}")

    return symbols, imports


def _extract_html(content: str, lines: list[str]) -> tuple[list[SymbolInfo], list[str]]:
    """Extract structural info from HTML files."""
    symbols = []
    imports = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Script src
        m = re.search(r'<script[^>]+src=[\'"]([^\'"]+)', stripped, re.IGNORECASE)
        if m:
            imports.append(m.group(1))

        # Link href (stylesheets)
        m = re.search(r'<link[^>]+href=[\'"]([^\'"]+)', stripped, re.IGNORECASE)
        if m:
            imports.append(m.group(1))

        # Forms with action
        m = re.search(r'<form[^>]+action=[\'"]([^\'"]+)', stripped, re.IGNORECASE)
        if m:
            method = "POST"
            mm = re.search(r'method=[\'"](\w+)', stripped, re.IGNORECASE)
            if mm:
                method = mm.group(1).upper()
            symbols.append(SymbolInfo(
                name=f"{method} {m.group(1)}", kind="route", line=i,
                end_line=i, signature=f"form {method} {m.group(1)}",
                docstring="", parent="",
            ))

        # IDs on major elements
        m = re.search(r'<(div|section|main|nav|header|footer|aside|article)[^>]+id=[\'"]([^\'"]+)',
                       stripped, re.IGNORECASE)
        if m:
            symbols.append(SymbolInfo(
                name=m.group(2), kind="element", line=i, end_line=i,
                signature=f"<{m.group(1)} id=\"{m.group(2)}\">",
                docstring="", parent="",
            ))

    return symbols, imports


def _extract_css(content: str, lines: list[str]) -> tuple[list[SymbolInfo], list[str]]:
    """Extract structural info from CSS/SCSS files."""
    symbols = []
    imports = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # @import
        m = re.match(r'@import\s+[\'"]([^\'"]+)', stripped)
        if m:
            imports.append(m.group(1))

        # @media queries
        m = re.match(r'@media\s+(.+?)\s*\{', stripped)
        if m:
            symbols.append(SymbolInfo(
                name=f"@media {m.group(1)[:50]}", kind="media", line=i,
                end_line=i, signature=f"@media {m.group(1)[:60]}",
                docstring="", parent="",
            ))

        # Class selectors (top-level only — not nested)
        m = re.match(r'^\.([a-zA-Z][\w-]*)\s*[,{]', stripped)
        if m:
            symbols.append(SymbolInfo(
                name=f".{m.group(1)}", kind="selector", line=i,
                end_line=i, signature=f".{m.group(1)}",
                docstring="", parent="",
            ))

        # ID selectors
        m = re.match(r'^#([a-zA-Z][\w-]*)\s*[,{]', stripped)
        if m:
            symbols.append(SymbolInfo(
                name=f"#{m.group(1)}", kind="selector", line=i,
                end_line=i, signature=f"#{m.group(1)}",
                docstring="", parent="",
            ))

    return symbols, imports


def _extract_c_cpp(content: str, lines: list[str]) -> tuple[list[SymbolInfo], list[str]]:
    """Extract symbols from C/C++ files using regex."""
    symbols = []
    imports = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # #include
        m = re.match(r'#include\s+[<"]([^>"]+)', stripped)
        if m:
            imports.append(m.group(1))

        # Class/struct
        m = re.match(r'^(?:class|struct)\s+(\w+)', stripped)
        if m:
            symbols.append(SymbolInfo(
                name=m.group(1), kind="class", line=i, end_line=i,
                signature=stripped.rstrip("{").strip(),
                docstring="", parent="",
            ))

        # Function definitions (heuristic: type name(params) {)
        m = re.match(r'^(?:[\w:*&<>\s]+?)\s+(\w+)\s*\(([^)]*)\)\s*(?:const\s*)?(?:\{|$)', stripped)
        if m and m.group(1) not in ("if", "for", "while", "switch", "return", "else"):
            symbols.append(SymbolInfo(
                name=m.group(1), kind="function", line=i, end_line=i,
                signature=stripped.rstrip("{").strip()[:100],
                docstring="", parent="",
            ))

    _compute_end_lines_brace(symbols, lines)
    return symbols, imports


def _extract_java(content: str, lines: list[str]) -> tuple[list[SymbolInfo], list[str]]:
    """Extract symbols from Java/Kotlin files using regex."""
    symbols = []
    imports = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Imports
        m = re.match(r'^import\s+([\w.]+)', stripped)
        if m:
            imports.append(m.group(1))

        # Classes/interfaces
        m = re.match(r'^(?:public|private|protected|abstract|static|\s)*(?:class|interface|enum)\s+(\w+)', stripped)
        if m:
            symbols.append(SymbolInfo(
                name=m.group(1), kind="class", line=i, end_line=i,
                signature=stripped.rstrip("{").strip()[:100],
                docstring="", parent="",
            ))

        # Methods
        m = re.match(r'^(?:\s*)(?:public|private|protected|static|abstract|synchronized|\s)*(?:[\w<>\[\]]+)\s+(\w+)\s*\(', stripped)
        if m and m.group(1) not in ("if", "for", "while", "switch", "return", "new", "class"):
            symbols.append(SymbolInfo(
                name=m.group(1), kind="function", line=i, end_line=i,
                signature=stripped.rstrip("{").strip()[:100],
                docstring="", parent="",
            ))

    _compute_end_lines_brace(symbols, lines)
    return symbols, imports


def _extract_go(content: str, lines: list[str]) -> tuple[list[SymbolInfo], list[str]]:
    """Extract symbols from Go files using regex."""
    symbols = []
    imports = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Imports (single-line)
        m = re.match(r'^import\s+"([^"]+)"', stripped)
        if m:
            imports.append(m.group(1))

        # Imports (block) — just the quoted strings
        m = re.match(r'^\s*"([^"]+)"', stripped)
        if m and i > 1 and any("import" in lines[j] for j in range(max(0, i-5), i-1)):
            imports.append(m.group(1))

        # Structs
        m = re.match(r'^type\s+(\w+)\s+struct', stripped)
        if m:
            symbols.append(SymbolInfo(
                name=m.group(1), kind="class", line=i, end_line=i,
                signature=f"type {m.group(1)} struct",
                docstring="", parent="",
            ))

        # Interfaces
        m = re.match(r'^type\s+(\w+)\s+interface', stripped)
        if m:
            symbols.append(SymbolInfo(
                name=m.group(1), kind="class", line=i, end_line=i,
                signature=f"type {m.group(1)} interface",
                docstring="", parent="",
            ))

        # Functions
        m = re.match(r'^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(', stripped)
        if m:
            symbols.append(SymbolInfo(
                name=m.group(1), kind="function", line=i, end_line=i,
                signature=stripped.rstrip("{").strip()[:100],
                docstring="", parent="",
            ))

    _compute_end_lines_brace(symbols, lines)
    return symbols, imports


def _extract_rust(content: str, lines: list[str]) -> tuple[list[SymbolInfo], list[str]]:
    """Extract symbols from Rust files using regex."""
    symbols = []
    imports = []

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Use statements
        m = re.match(r'^use\s+([\w:]+)', stripped)
        if m:
            imports.append(m.group(1))

        # Structs/enums
        m = re.match(r'^(?:pub\s+)?(?:struct|enum)\s+(\w+)', stripped)
        if m:
            symbols.append(SymbolInfo(
                name=m.group(1), kind="class", line=i, end_line=i,
                signature=stripped.rstrip("{").strip()[:100],
                docstring="", parent="",
            ))

        # Traits
        m = re.match(r'^(?:pub\s+)?trait\s+(\w+)', stripped)
        if m:
            symbols.append(SymbolInfo(
                name=m.group(1), kind="class", line=i, end_line=i,
                signature=stripped.rstrip("{").strip()[:100],
                docstring="", parent="",
            ))

        # Impl blocks
        m = re.match(r'^impl(?:<[^>]*>)?\s+(?:(\w+)\s+for\s+)?(\w+)', stripped)
        if m:
            target = m.group(2)
            trait = m.group(1) or ""
            sig = f"impl {trait + ' for ' if trait else ''}{target}"
            symbols.append(SymbolInfo(
                name=f"impl {target}", kind="class", line=i, end_line=i,
                signature=sig, docstring="", parent="",
            ))

        # Functions
        m = re.match(r'^(?:pub\s+)?(?:async\s+)?fn\s+(\w+)', stripped)
        if m:
            symbols.append(SymbolInfo(
                name=m.group(1), kind="function", line=i, end_line=i,
                signature=stripped.rstrip("{").strip()[:100],
                docstring="", parent="",
            ))

    _compute_end_lines_brace(symbols, lines)
    return symbols, imports


def _extract_fallback(content: str, lines: list[str]) -> tuple[list[SymbolInfo], list[str]]:
    """Fallback extractor for unknown file types — just count lines."""
    return [], []


# ---------------------------------------------------------------------------
# Brace-matching end_line computation
# ---------------------------------------------------------------------------

def _compute_end_lines_brace(symbols: list[SymbolInfo], lines: list[str]):
    """Compute end_lines for symbols in brace-delimited languages.

    For each symbol, find the matching closing brace after its start line.
    """
    for sym in symbols:
        if sym.end_line != sym.line:
            continue  # Already computed
        depth = 0
        found_open = False
        for j in range(sym.line - 1, len(lines)):
            for ch in lines[j]:
                if ch == '{':
                    depth += 1
                    found_open = True
                elif ch == '}':
                    depth -= 1
                    if found_open and depth <= 0:
                        sym.end_line = j + 1  # 1-based
                        break
            if found_open and depth <= 0:
                break
        if sym.end_line == sym.line:
            # Couldn't find closing brace — estimate
            sym.end_line = min(sym.line + 20, len(lines))


# ---------------------------------------------------------------------------
# Language router
# ---------------------------------------------------------------------------

EXTRACTORS = {
    ".py":    _extract_python,
    ".php":   _extract_php,
    ".js":    _extract_javascript,
    ".jsx":   _extract_javascript,
    ".ts":    _extract_javascript,
    ".tsx":   _extract_javascript,
    ".vue":   _extract_javascript,
    ".svelte": _extract_javascript,
    ".sql":   _extract_sql,
    ".html":  _extract_html,
    ".htm":   _extract_html,
    ".css":   _extract_css,
    ".scss":  _extract_css,
    ".less":  _extract_css,
    ".c":     _extract_c_cpp,
    ".cpp":   _extract_c_cpp,
    ".cc":    _extract_c_cpp,
    ".h":     _extract_c_cpp,
    ".hpp":   _extract_c_cpp,
    ".java":  _extract_java,
    ".kt":    _extract_java,
    ".go":    _extract_go,
    ".rs":    _extract_rust,
}

LANG_NAMES = {
    ".py": "python", ".php": "php", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".vue": "vue", ".svelte": "svelte",
    ".sql": "sql", ".html": "html", ".htm": "html", ".css": "css",
    ".scss": "scss", ".less": "less", ".c": "c", ".cpp": "cpp", ".cc": "cpp",
    ".h": "c-header", ".hpp": "cpp-header", ".java": "java", ".kt": "kotlin",
    ".go": "go", ".rs": "rust", ".rb": "ruby", ".cs": "csharp",
    ".swift": "swift", ".scala": "scala", ".lua": "lua",
    ".sh": "shell", ".bash": "shell", ".ps1": "powershell", ".bat": "batch",
    ".yaml": "yaml", ".yml": "yaml", ".toml": "toml", ".json": "json",
    ".md": "markdown", ".txt": "text", ".cfg": "config", ".ini": "config",
}


# ---------------------------------------------------------------------------
# CodebaseDigester
# ---------------------------------------------------------------------------

class CodebaseDigester:
    """Enterprise-grade structural analysis engine.

    Parses every file in a codebase, extracts symbols, and produces
    compact summaries. Supports incremental updates and parallel I/O.
    """

    def __init__(self, persist_dir: Path):
        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._digest: Optional[ProjectDigest] = None
        self._hashes: dict[str, str] = {}  # path -> sha256
        self._load_cache()

    def scan(self, root: str, callback: Optional[Callable] = None,
             force: bool = False) -> ProjectDigest:
        """Scan a codebase and produce a full structural digest.

        Args:
            root: Path to project root directory
            callback: Optional (path, num, total) progress callback
            force: If True, re-parse all files even if unchanged
        """
        root_path = Path(root).resolve()
        if not root_path.is_dir():
            raise ValueError(f"Not a directory: {root}")

        start_time = time.time()

        # Collect all files to scan
        all_files = list(self._iter_files(root_path))
        total = len(all_files)

        if total == 0:
            self._digest = ProjectDigest(root=str(root_path))
            return self._digest

        # Determine which files need re-parsing
        if force:
            files_to_parse = all_files
        else:
            files_to_parse = []
            for fp in all_files:
                key = str(fp)
                new_hash = self._hash_file(fp)
                if new_hash and self._hashes.get(key) != new_hash:
                    files_to_parse.append(fp)
                elif new_hash is None:
                    files_to_parse.append(fp)

        log.info("Scanning %d files (%d need parsing)", total, len(files_to_parse))

        # Initialize or reuse existing digest
        if self._digest is None or force or self._digest.root != str(root_path):
            digest = ProjectDigest(root=str(root_path))
            if self._digest and self._digest.notes:
                digest.notes = dict(self._digest.notes)
        else:
            digest = self._digest
            # Remove files that no longer exist
            current_paths = {str(fp) for fp in all_files}
            removed = [p for p in list(digest.files.keys()) if p not in current_paths]
            for p in removed:
                del digest.files[p]
                self._hashes.pop(p, None)

        # Parse files in parallel
        completed = 0
        parse_results = {}

        def _parse_one(file_path: Path) -> tuple[str, Optional[FileDigest]]:
            try:
                return str(file_path), self._parse_file(file_path, root_path)
            except Exception as e:
                log.debug("Parse failed for %s: %s", file_path, e)
                return str(file_path), None

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_parse_one, fp): fp for fp in files_to_parse}
            for future in as_completed(futures):
                completed += 1
                path_str, file_digest = future.result()
                if file_digest:
                    parse_results[path_str] = file_digest
                    self._hashes[path_str] = file_digest.sha256
                if callback:
                    callback(path_str, completed, len(files_to_parse))

        # Merge results into digest
        digest.files.update(parse_results)

        # For files that didn't need re-parsing, keep existing entries
        # (they're already in digest.files from the previous scan)

        # Rebuild aggregates
        self._rebuild_aggregates(digest, root_path, all_files)

        digest.scan_time = time.time() - start_time
        self._digest = digest
        self._save_cache()

        log.info("Scan complete: %d files, %d symbols, %.1fs",
                 digest.total_files, digest.total_symbols, digest.scan_time)
        return digest

    def get_digest(self) -> Optional[ProjectDigest]:
        """Return the current digest (None if no scan done)."""
        return self._digest

    def get_file(self, path: str) -> Optional[FileDigest]:
        """Return the digest for a single file."""
        if not self._digest:
            return None

        # Normalize separators for comparison
        norm = path.replace("\\", "/")

        # Try exact key match (absolute path)
        p = str(Path(path).resolve())
        fd = self._digest.files.get(p)
        if fd:
            return fd

        # Try matching against stored relative paths
        for key, fd in self._digest.files.items():
            fd_norm = fd.path.replace("\\", "/")
            key_norm = key.replace("\\", "/")
            if (fd_norm == norm or
                    key_norm == norm or
                    key_norm.endswith("/" + norm) or
                    fd_norm.endswith("/" + norm) or
                    norm.endswith("/" + fd_norm)):
                return fd
        return None

    def read_symbol_source(self, file_path: str,
                           symbol_names: list[str]) -> str:
        """Read ONLY the source code of specific symbols from a file.

        This is the key efficiency tool — instead of reading a 500-line file
        (125 tokens), read just the 40-line function (10 tokens).
        """
        fd = self.get_file(file_path)
        if not fd:
            return f"Error: No digest found for {file_path}. Run scan_codebase first."

        # Resolve the actual file path
        actual_path = None
        if self._digest:
            for key in self._digest.files:
                if self._digest.files[key].path == fd.path:
                    actual_path = key
                    break
        if not actual_path:
            actual_path = str(Path(file_path).resolve())

        try:
            with open(actual_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except Exception as e:
            return f"Error reading {file_path}: {e}"

        # Find requested symbols
        result_parts = []
        symbols_data = fd.symbols
        if isinstance(symbols_data, list) and symbols_data and isinstance(symbols_data[0], dict):
            # Stored as dicts, convert
            symbols_list = [SymbolInfo(**s) for s in symbols_data]
        elif isinstance(symbols_data, list) and symbols_data and isinstance(symbols_data[0], SymbolInfo):
            symbols_list = symbols_data
        else:
            symbols_list = []

        found = set()
        for name in symbol_names:
            name_lower = name.lower()
            for sym in symbols_list:
                if sym.name.lower() == name_lower:
                    start = max(0, sym.line - 1)
                    end = min(len(lines), sym.end_line)
                    chunk = lines[start:end]
                    header = f"--- {sym.kind} {sym.name} ({fd.path}:{sym.line}-{sym.end_line}) ---"
                    result_parts.append(header)
                    for j, line in enumerate(chunk, sym.line):
                        result_parts.append(f"{j:>5} {line.rstrip()}")
                    result_parts.append("")
                    found.add(name_lower)
                    break

        not_found = [n for n in symbol_names if n.lower() not in found]
        if not_found:
            result_parts.append(f"Symbols not found: {', '.join(not_found)}")
            if symbols_list:
                available = [s.name for s in symbols_list[:20]]
                result_parts.append(f"Available: {', '.join(available)}")

        return "\n".join(result_parts) if result_parts else "No symbols matched."

    def search_symbols(self, query: str, kind: Optional[str] = None,
                       limit: int = 30) -> list[dict]:
        """Fuzzy search across all symbols in the digest."""
        if not self._digest:
            return []

        query_lower = query.lower()
        results = []

        for path, fd in self._digest.files.items():
            symbols = fd.symbols
            if isinstance(symbols, list):
                for s in symbols:
                    if isinstance(s, dict):
                        name = s.get("name", "")
                        s_kind = s.get("kind", "")
                        sig = s.get("signature", "")
                        line = s.get("line", 0)
                    else:
                        name = s.name
                        s_kind = s.kind
                        sig = s.signature
                        line = s.line

                    if kind and s_kind != kind:
                        continue

                    # Score: exact match > starts with > contains
                    name_lower = name.lower()
                    if name_lower == query_lower:
                        score = 100
                    elif name_lower.startswith(query_lower):
                        score = 80
                    elif query_lower in name_lower:
                        score = 60
                    elif query_lower in sig.lower():
                        score = 40
                    else:
                        continue

                    results.append({
                        "name": name,
                        "kind": s_kind,
                        "file": fd.path,
                        "line": line,
                        "signature": sig,
                        "score": score,
                    })

        results.sort(key=lambda r: -r["score"])
        return results[:limit]

    def generate_summary(self, max_tokens: int = 6000) -> str:
        """Generate a compact structural map of the codebase.

        Fits ~2000+ files into 4-8K tokens by showing:
        1. Overview stats
        2. Directory tree (top 3 levels, collapsed)
        3. Top symbols ranked by connectivity
        4. Entry points
        5. Architecture notes
        """
        d = self._digest
        if not d or not d.files:
            return "(No codebase scanned. Use scan_codebase first.)"

        parts = []

        # --- Header ---
        project_name = Path(d.root).name
        lang_str = ", ".join(f"{count} {lang}"
                            for lang, count in sorted(d.by_language.items(),
                                                      key=lambda x: -x[1])[:8])
        parts.append(f"=== CODEBASE: {project_name} ===")
        parts.append(f"{d.total_files} files | {d.total_lines:,} lines | {lang_str}")
        parts.append(f"Scanned in {d.scan_time:.1f}s\n")

        # --- Directory tree (top 3 levels, collapsed) ---
        parts.append("--- DIRECTORY STRUCTURE ---")
        dir_tree = self._build_dir_tree(d, max_depth=3)
        parts.append(dir_tree)
        parts.append("")

        # --- Top symbols by connectivity ---
        parts.append("--- KEY SYMBOLS (by importance) ---")
        top_symbols = self._rank_symbols(d, limit=100)
        for sym_info in top_symbols:
            parts.append(sym_info)
        parts.append("")

        # --- Entry points ---
        parts.append("--- ENTRY POINTS ---")
        entry_points = self._find_entry_points(d)
        if entry_points:
            parts.append(", ".join(entry_points))
        else:
            parts.append("(none detected)")
        parts.append("")

        # --- Database summary ---
        tables = []
        for fd in d.files.values():
            for s in (fd.symbols if isinstance(fd.symbols, list) else []):
                if isinstance(s, dict):
                    if s.get("kind") == "table":
                        tables.append(s)
                elif hasattr(s, 'kind') and s.kind == "table":
                    tables.append({"name": s.name, "signature": s.signature,
                                   "file": fd.path, "line": s.line})
        if tables:
            parts.append(f"--- DATABASE ({len(tables)} tables) ---")
            for t in tables[:50]:
                name = t.get("name", t.get("signature", "?"))
                sig = t.get("signature", "")
                parts.append(f"  {sig}")
            if len(tables) > 50:
                parts.append(f"  ... and {len(tables) - 50} more tables")
            parts.append("")

        # --- Routes ---
        routes = []
        for fd in d.files.values():
            for s in (fd.symbols if isinstance(fd.symbols, list) else []):
                if isinstance(s, dict):
                    if s.get("kind") == "route":
                        routes.append({**s, "file": fd.path})
                elif hasattr(s, 'kind') and s.kind == "route":
                    routes.append({"name": s.name, "signature": s.signature,
                                   "file": fd.path, "line": s.line})
        if routes:
            parts.append(f"--- ROUTES ({len(routes)} endpoints) ---")
            for r in routes[:40]:
                parts.append(f"  {r.get('name', '?')} ({r.get('file', '?')}:{r.get('line', '?')})")
            if len(routes) > 40:
                parts.append(f"  ... and {len(routes) - 40} more routes")
            parts.append("")

        # --- Architecture notes ---
        if d.notes:
            parts.append("--- ARCHITECTURE NOTES ---")
            for topic, content in d.notes.items():
                parts.append(f"[{topic}] {content[:200]}")
            parts.append("")

        summary = "\n".join(parts)

        # Truncate if over budget (rough: 1 token per 4 chars)
        max_chars = max_tokens * 4
        if len(summary) > max_chars:
            summary = summary[:max_chars] + "\n... (truncated)"

        return summary

    # -------------------------------------------------------------------
    # Private methods
    # -------------------------------------------------------------------

    def _parse_file(self, file_path: Path, root: Path) -> Optional[FileDigest]:
        """Parse a single file and return its digest."""
        try:
            stat = file_path.stat()
            if stat.st_size > MAX_FILE_SIZE:
                return FileDigest(
                    path=str(file_path.relative_to(root)).replace("\\", "/"),
                    language=LANG_NAMES.get(file_path.suffix.lower(), "unknown"),
                    lines=0, size_bytes=stat.st_size,
                    sha256=self._hash_file(file_path) or "",
                    symbols=[], imports=[],
                    summary_line=f"Large file ({stat.st_size:,} bytes), skipped parsing",
                )

            content = file_path.read_text(encoding="utf-8", errors="replace")
            lines_list = content.splitlines()
            ext = file_path.suffix.lower()

            extractor = EXTRACTORS.get(ext, _extract_fallback)
            symbols, imports = extractor(content, lines_list)

            # Convert SymbolInfo to dicts for JSON serialization
            symbols_dicts = []
            for s in symbols:
                symbols_dicts.append({
                    "name": s.name, "kind": s.kind,
                    "line": s.line, "end_line": s.end_line,
                    "signature": s.signature,
                    "docstring": s.docstring, "parent": s.parent,
                })

            # Generate summary line
            summary = self._summarize_file(symbols, ext, len(lines_list))

            return FileDigest(
                path=str(file_path.relative_to(root)).replace("\\", "/"),
                language=LANG_NAMES.get(ext, "unknown"),
                lines=len(lines_list),
                size_bytes=stat.st_size,
                sha256=self._hash_file(file_path) or "",
                symbols=symbols_dicts,
                imports=imports,
                summary_line=summary,
            )
        except Exception as e:
            log.debug("Failed to parse %s: %s", file_path, e)
            return None

    def _summarize_file(self, symbols: list[SymbolInfo], ext: str,
                        line_count: int) -> str:
        """Generate a one-line summary of a file's contents."""
        kinds = Counter(s.kind for s in symbols)
        parts = []
        if kinds.get("class", 0):
            parts.append(f"{kinds['class']} class{'es' if kinds['class'] > 1 else ''}")
        if kinds.get("function", 0):
            parts.append(f"{kinds['function']} func{'s' if kinds['function'] > 1 else ''}")
        if kinds.get("method", 0):
            parts.append(f"{kinds['method']} method{'s' if kinds['method'] > 1 else ''}")
        if kinds.get("route", 0):
            parts.append(f"{kinds['route']} route{'s' if kinds['route'] > 1 else ''}")
        if kinds.get("table", 0):
            parts.append(f"{kinds['table']} table{'s' if kinds['table'] > 1 else ''}")

        if parts:
            return ", ".join(parts)
        return f"{line_count} lines"

    def _rebuild_aggregates(self, digest: ProjectDigest, root: Path,
                            all_files: list[Path]):
        """Rebuild totals, by_language, by_kind, directories from file data."""
        digest.total_files = len(digest.files)
        digest.total_lines = sum(fd.lines for fd in digest.files.values())
        digest.total_symbols = sum(
            len(fd.symbols) for fd in digest.files.values())

        # by_language
        lang_counts = Counter()
        for fd in digest.files.values():
            lang_counts[fd.language] += 1
        digest.by_language = dict(lang_counts)

        # by_kind
        kind_counts = Counter()
        for fd in digest.files.values():
            for s in fd.symbols:
                if isinstance(s, dict):
                    kind_counts[s.get("kind", "unknown")] += 1
                else:
                    kind_counts[s.kind] += 1
        digest.by_kind = dict(kind_counts)

        # directories
        dirs = defaultdict(list)
        for fd in digest.files.values():
            parent = str(Path(fd.path).parent).replace("\\", "/")
            if parent == ".":
                parent = "/"
            dirs[parent].append(Path(fd.path).name)
        digest.directories = dict(dirs)

    def _build_dir_tree(self, digest: ProjectDigest,
                        max_depth: int = 3) -> str:
        """Build a collapsed directory tree string."""
        lines = []
        # Group files by directory
        dir_info = {}
        for fd in digest.files.values():
            parts = fd.path.replace("\\", "/").split("/")
            for depth in range(min(len(parts) - 1, max_depth)):
                dir_path = "/".join(parts[:depth + 1])
                if dir_path not in dir_info:
                    dir_info[dir_path] = {"count": 0, "symbols": []}
                dir_info[dir_path]["count"] += 1
                # Collect top symbol names for preview
                for s in (fd.symbols if isinstance(fd.symbols, list) else []):
                    name = s.get("name", s.name if hasattr(s, "name") else "")
                    kind = s.get("kind", s.kind if hasattr(s, "kind") else "")
                    if kind in ("class", "function") and name:
                        dir_info[dir_path]["symbols"].append(name)

        # Sort and format
        for dir_path in sorted(dir_info.keys()):
            info = dir_info[dir_path]
            depth = dir_path.count("/")
            indent = "  " * depth
            dir_name = dir_path.split("/")[-1]
            count = info["count"]

            # Preview top symbols (max 5)
            sym_preview = ""
            top_syms = list(dict.fromkeys(info["symbols"]))[:5]
            if top_syms:
                sym_preview = f": {', '.join(top_syms)}"
                if len(info["symbols"]) > 5:
                    sym_preview += ", ..."

            lines.append(f"{indent}{dir_name}/ ({count} files{sym_preview})")

        # Root-level files
        root_files = [fd.path for fd in digest.files.values()
                      if "/" not in fd.path.replace("\\", "/")]
        if root_files:
            lines.append(f"(root: {', '.join(root_files[:10])})")

        return "\n".join(lines) if lines else "(empty)"

    def _rank_symbols(self, digest: ProjectDigest, limit: int = 100) -> list[str]:
        """Rank symbols by importance (connectivity heuristic)."""
        # Count how many files reference each symbol name
        symbol_refs = Counter()
        all_symbol_info = {}  # name -> (kind, file, line, signature)

        for fd in digest.files.values():
            # Count imports as references
            for imp in fd.imports:
                # Extract the last part of the import path
                parts = imp.replace("\\", "/").split(".")
                for part in parts:
                    clean = part.strip()
                    if clean and not clean.startswith(("include:", "namespace:", "alters:")):
                        symbol_refs[clean] += 1

            # Register all symbols
            for s in (fd.symbols if isinstance(fd.symbols, list) else []):
                if isinstance(s, dict):
                    name = s.get("name", "")
                    kind = s.get("kind", "")
                    sig = s.get("signature", "")
                    line = s.get("line", 0)
                else:
                    name, kind, sig, line = s.name, s.kind, s.signature, s.line

                if name and kind in ("class", "function", "method", "route", "table"):
                    if name not in all_symbol_info:
                        all_symbol_info[name] = (kind, fd.path, line, sig)

        # Score: references × kind_weight
        kind_weights = {
            "class": 3.0, "route": 2.5, "table": 2.5,
            "function": 1.5, "method": 1.0,
        }

        scored = []
        for name, (kind, fpath, line, sig) in all_symbol_info.items():
            refs = symbol_refs.get(name, 0)
            weight = kind_weights.get(kind, 1.0)
            score = (refs + 1) * weight
            scored.append((score, name, kind, fpath, line, sig, refs))

        scored.sort(key=lambda x: -x[0])

        results = []
        for score, name, kind, fpath, line, sig, refs in scored[:limit]:
            ref_str = f", referenced by {refs} files" if refs > 0 else ""
            results.append(f"  {kind} {name} ({fpath}:{line}){ref_str}")

        return results

    def _find_entry_points(self, digest: ProjectDigest) -> list[str]:
        """Find likely entry point files."""
        entry_names = {
            "main.py", "__main__.py", "app.py", "server.py", "index.py",
            "index.js", "index.ts", "server.js", "app.js",
            "index.php", "index.html", "main.go", "main.rs",
            "manage.py", "wsgi.py", "asgi.py",
            "Makefile", "Dockerfile", "docker-compose.yml",
            "package.json", "pyproject.toml", "Cargo.toml", "go.mod",
        }
        found = []
        for fd in digest.files.values():
            name = Path(fd.path).name
            if name in entry_names:
                found.append(fd.path)
        return sorted(found)

    def _iter_files(self, root: Path):
        """Iterate all indexable files under root."""
        try:
            for entry in os.scandir(root):
                if entry.is_dir(follow_symlinks=False):
                    if entry.name in SKIP_DIRS or entry.name.startswith("."):
                        continue
                    yield from self._iter_files(Path(entry.path))
                elif entry.is_file():
                    ext = Path(entry.name).suffix.lower()
                    if ext in CODE_EXTENSIONS:
                        yield Path(entry.path)
        except PermissionError:
            pass

    @staticmethod
    def _hash_file(path: Path) -> Optional[str]:
        """SHA-256 hash of a file's contents."""
        try:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return None

    # -------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------

    def _save_cache(self):
        """Persist digest to disk."""
        if not self._digest:
            return
        try:
            data = {
                "version": 2,
                "root": self._digest.root,
                "hashes": self._hashes,
                "notes": self._digest.notes,
                "files": {},
            }
            for path, fd in self._digest.files.items():
                data["files"][path] = {
                    "path": fd.path,
                    "language": fd.language,
                    "lines": fd.lines,
                    "size_bytes": fd.size_bytes,
                    "sha256": fd.sha256,
                    "symbols": fd.symbols,
                    "imports": fd.imports,
                    "summary_line": fd.summary_line,
                }

            cache_file = self._persist_dir / "digest.json"
            cache_file.write_text(
                json.dumps(data, indent=1, default=str),
                encoding="utf-8",
            )
            log.debug("Digest saved to %s (%d files)", cache_file, len(data["files"]))
        except Exception as e:
            log.debug("Digest save failed: %s", e)

    def _load_cache(self):
        """Load cached digest from disk."""
        cache_file = self._persist_dir / "digest.json"
        if not cache_file.exists():
            return

        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if data.get("version") != 2:
                return

            self._hashes = data.get("hashes", {})

            # Rebuild ProjectDigest from cached data
            files = {}
            for path, fd_data in data.get("files", {}).items():
                files[path] = FileDigest(
                    path=fd_data["path"],
                    language=fd_data["language"],
                    lines=fd_data["lines"],
                    size_bytes=fd_data["size_bytes"],
                    sha256=fd_data["sha256"],
                    symbols=fd_data["symbols"],
                    imports=fd_data["imports"],
                    summary_line=fd_data["summary_line"],
                )

            self._digest = ProjectDigest(
                root=data.get("root", ""),
                files=files,
                notes=data.get("notes", {}),
            )

            # Rebuild aggregates from cached files
            if files:
                root_path = Path(data.get("root", ""))
                all_files_list = list(Path(p) for p in files.keys())
                self._rebuild_aggregates(self._digest, root_path, all_files_list)

            log.debug("Loaded cached digest: %d files", len(files))
        except Exception as e:
            log.debug("Digest load failed: %s", e)
