"""Tree-sitter code navigation tools — language-aware symbol search.

Provides the AI with structural code understanding: find definitions,
references, call graphs, and file outlines across multiple languages.

Uses tree-sitter for accurate AST-based analysis when available,
falls back to regex-based parsing when tree-sitter is not installed.
All functions work in both modes.

Supported languages: Python, JavaScript, TypeScript, Go, Rust,
Java, C, C++, Ruby, PHP.
"""

import os
import re
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tree-sitter availability check
# ---------------------------------------------------------------------------

_HAS_TREESITTER = False
_ts_module = None
_ts_language_module = None

try:
    import tree_sitter as _ts_module
    _HAS_TREESITTER = True
    try:
        import tree_sitter_languages as _ts_language_module
    except ImportError:
        _ts_language_module = None
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

_EXT_TO_LANG = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".hxx": "cpp",
    ".rb": "ruby",
    ".php": "php",
}

# tree-sitter language names (may differ from our keys)
_TS_LANG_NAMES = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "go": "go",
    "rust": "rust",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "ruby": "ruby",
    "php": "php",
}

# Directories to skip when searching project-wide
_SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", ".eggs",
    "target", "vendor", ".next", ".nuxt", "coverage", ".cache",
    "egg-info", ".egg-info",
}

# Binary/non-source extensions to skip
_SKIP_EXTS = {
    ".pyc", ".pyd", ".so", ".dll", ".exe", ".o", ".obj", ".a", ".lib",
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".bmp", ".svg",
    ".woff", ".woff2", ".ttf", ".eot",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z",
    ".pdf", ".doc", ".docx",
    ".mp3", ".wav", ".mp4", ".avi",
    ".bin", ".dat", ".db", ".sqlite",
}

# Source extensions we care about for project-wide search
_SOURCE_EXTS = set(_EXT_TO_LANG.keys())


def _detect_language(file_path: str) -> Optional[str]:
    """Detect language from file extension."""
    ext = Path(file_path).suffix.lower()
    return _EXT_TO_LANG.get(ext)


def _iter_source_files(root: str, lang_filter: str = None,
                       max_files: int = 5000):
    """Iterate over source files in a project directory.

    Skips hidden dirs, build artifacts, and binary files.
    """
    root_path = Path(root).resolve()
    count = 0
    for dirpath, dirnames, filenames in os.walk(root_path):
        # Prune directories in-place
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".") and d not in _SKIP_DIRS
            and not d.endswith(".egg-info")
        ]
        for fname in filenames:
            ext = Path(fname).suffix.lower()
            if ext in _SKIP_EXTS:
                continue
            if ext not in _SOURCE_EXTS:
                continue
            if lang_filter and _EXT_TO_LANG.get(ext) != lang_filter:
                continue
            fp = os.path.join(dirpath, fname)
            yield fp
            count += 1
            if count >= max_files:
                return


# ---------------------------------------------------------------------------
# Regex fallback patterns
# ---------------------------------------------------------------------------

# Each language maps to a list of (pattern, kind_extractor) tuples.
# The pattern should have named groups: 'kind' and 'name' at minimum.
# Some patterns use a fixed kind.

_REGEX_PATTERNS = {
    "python": [
        # class definitions
        (re.compile(
            r"^(\s*)(async\s+)?(?P<kind>class)\s+(?P<name>\w+)"
            r"(?P<sig>\([^)]*\))?:"),
         None),
        # function/method definitions (sig optional for multi-line params)
        (re.compile(
            r"^(?P<indent>\s*)(async\s+)?(?P<kind>def)\s+(?P<name>\w+)"
            r"\s*(?P<sig>\([^)]*\))?"),
         None),
    ],
    "javascript": [
        # class
        (re.compile(
            r"^(\s*)(?:export\s+)?(?:default\s+)?(?P<kind>class)\s+"
            r"(?P<name>\w+)"),
         None),
        # function declaration
        (re.compile(
            r"^(\s*)(?:export\s+)?(?:default\s+)?(?:async\s+)?"
            r"(?P<kind>function)\s+(?P<name>\w+)\s*(?P<sig>\([^)]*\))"),
         None),
        # const/let/var arrow or function expression
        (re.compile(
            r"^(\s*)(?:export\s+)?(?:const|let|var)\s+(?P<name>\w+)\s*=\s*"
            r"(?:async\s+)?(?:function|\([^)]*\)\s*=>|(?P<param>\w+)\s*=>)"),
         lambda m: "function"),
        # method in class
        (re.compile(
            r"^(\s+)(?:static\s+)?(?:async\s+)?(?P<name>\w+)\s*"
            r"(?P<sig>\([^)]*\))\s*\{"),
         lambda m: "method"),
    ],
    "typescript": [
        # interface
        (re.compile(
            r"^(\s*)(?:export\s+)?(?P<kind>interface)\s+(?P<name>\w+)"),
         None),
        # type alias
        (re.compile(
            r"^(\s*)(?:export\s+)?(?P<kind>type)\s+(?P<name>\w+)\s*="),
         None),
        # class
        (re.compile(
            r"^(\s*)(?:export\s+)?(?:default\s+)?(?:abstract\s+)?"
            r"(?P<kind>class)\s+(?P<name>\w+)"),
         None),
        # function
        (re.compile(
            r"^(\s*)(?:export\s+)?(?:default\s+)?(?:async\s+)?"
            r"(?P<kind>function)\s+(?P<name>\w+)\s*(?P<sig>\([^)]*\))"),
         None),
        # const arrow
        (re.compile(
            r"^(\s*)(?:export\s+)?(?:const|let|var)\s+(?P<name>\w+)\s*"
            r"(?::\s*[^=]+)?\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>)"),
         lambda m: "function"),
        # enum
        (re.compile(
            r"^(\s*)(?:export\s+)?(?P<kind>enum)\s+(?P<name>\w+)"),
         None),
        # method
        (re.compile(
            r"^(\s+)(?:public|private|protected|static|async|readonly|\s)*"
            r"(?P<name>\w+)\s*(?P<sig>\([^)]*\))\s*[:{]"),
         lambda m: "method"),
    ],
    "go": [
        # method (receiver)
        (re.compile(
            r"^func\s+\((?P<recv>[^)]+)\)\s+(?P<name>\w+)"
            r"\s*(?P<sig>\([^)]*\))"),
         lambda m: "method"),
        # function
        (re.compile(
            r"^func\s+(?P<name>\w+)\s*(?P<sig>\([^)]*\))"),
         lambda m: "function"),
        # type struct/interface
        (re.compile(
            r"^type\s+(?P<name>\w+)\s+(?P<kind>struct|interface)\b"),
         None),
    ],
    "rust": [
        # fn
        (re.compile(
            r"^(\s*)(?:pub(?:\([\w:]+\))?\s+)?(?:async\s+)?(?:unsafe\s+)?"
            r"(?P<kind>fn)\s+(?P<name>\w+)\s*(?P<sig>\([^)]*\))"),
         None),
        # struct
        (re.compile(
            r"^(\s*)(?:pub(?:\([\w:]+\))?\s+)?(?P<kind>struct)\s+"
            r"(?P<name>\w+)"),
         None),
        # enum
        (re.compile(
            r"^(\s*)(?:pub(?:\([\w:]+\))?\s+)?(?P<kind>enum)\s+"
            r"(?P<name>\w+)"),
         None),
        # trait
        (re.compile(
            r"^(\s*)(?:pub(?:\([\w:]+\))?\s+)?(?P<kind>trait)\s+"
            r"(?P<name>\w+)"),
         None),
        # impl
        (re.compile(
            r"^(\s*)(?P<kind>impl)(?:<[^>]*>)?\s+(?P<name>\w+)"),
         None),
    ],
    "java": [
        # class/interface/enum
        (re.compile(
            r"^(\s*)(?:public|private|protected|static|abstract|final|\s)*"
            r"(?P<kind>class|interface|enum)\s+(?P<name>\w+)"),
         None),
        # method
        (re.compile(
            r"^(\s+)(?:public|private|protected|static|abstract|final|"
            r"synchronized|native|\s)*"
            r"(?:\w+(?:<[^>]*>)?(?:\[\])*)\s+(?P<name>\w+)\s*"
            r"(?P<sig>\([^)]*\))"),
         lambda m: "method"),
    ],
    "c": [
        # struct/union/enum
        (re.compile(
            r"^(?:typedef\s+)?(?P<kind>struct|union|enum)\s+(?P<name>\w+)"),
         None),
        # function definition (simplified)
        (re.compile(
            r"^(?:static\s+|inline\s+|extern\s+)*"
            r"(?:(?:unsigned|signed|const|volatile|long|short)\s+)*"
            r"(?:\w+[\s*]+)(?P<name>\w+)\s*(?P<sig>\([^)]*\))\s*\{"),
         lambda m: "function"),
    ],
    "ruby": [
        # class
        (re.compile(
            r"^(\s*)(?P<kind>class)\s+(?P<name>\w+)"),
         None),
        # module
        (re.compile(
            r"^(\s*)(?P<kind>module)\s+(?P<name>\w+)"),
         None),
        # def
        (re.compile(
            r"^(\s*)(?P<kind>def)\s+(?:self\.)?(?P<name>\w+[?!=]?)"
            r"(?P<sig>\([^)]*\))?"),
         None),
    ],
    "php": [
        # class/interface/trait
        (re.compile(
            r"^(\s*)(?:abstract\s+|final\s+)?(?P<kind>class|interface|trait)"
            r"\s+(?P<name>\w+)"),
         None),
        # function
        (re.compile(
            r"^(\s*)(?:public|private|protected|static|\s)*"
            r"(?P<kind>function)\s+(?P<name>\w+)\s*(?P<sig>\([^)]*\))"),
         None),
    ],
}

# C++ uses C patterns plus extras
_REGEX_PATTERNS["cpp"] = _REGEX_PATTERNS["c"] + [
    # class
    (re.compile(
        r"^(\s*)(?P<kind>class)\s+(?P<name>\w+)"),
     None),
    # namespace
    (re.compile(
        r"^(\s*)(?P<kind>namespace)\s+(?P<name>\w+)"),
     None),
    # template function
    (re.compile(
        r"^template\s*<[^>]*>\s*(?:static\s+|inline\s+)*"
        r"(?:\w+[\s*&]+)(?P<name>\w+)\s*(?P<sig>\([^)]*\))"),
     lambda m: "function"),
]

# Call pattern: match function/method calls  name(
_CALL_PATTERN = re.compile(r"\b(?P<callee>\w+)\s*\(")

# Word boundary pattern for reference searching
def _word_boundary_pattern(symbol: str) -> re.Pattern:
    """Build a regex that matches `symbol` as a whole word."""
    escaped = re.escape(symbol)
    return re.compile(r"\b" + escaped + r"\b")


# ---------------------------------------------------------------------------
# AST cache
# ---------------------------------------------------------------------------

class _ASTCache:
    """Cache parsed ASTs keyed by (file_path, mtime)."""

    def __init__(self, max_entries: int = 200):
        self._cache: dict[str, tuple[float, object]] = {}  # path -> (mtime, tree)
        self._max = max_entries

    def get(self, file_path: str) -> Optional[object]:
        """Return cached tree if file hasn't changed, else None."""
        if file_path not in self._cache:
            return None
        try:
            mtime = os.path.getmtime(file_path)
        except OSError:
            return None
        cached_mtime, tree = self._cache[file_path]
        if mtime == cached_mtime:
            return tree
        # Stale
        del self._cache[file_path]
        return None

    def put(self, file_path: str, tree: object):
        """Store a parsed tree."""
        try:
            mtime = os.path.getmtime(file_path)
        except OSError:
            return
        # Evict oldest if full
        if len(self._cache) >= self._max and file_path not in self._cache:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        self._cache[file_path] = (mtime, tree)

    def clear(self):
        self._cache.clear()


# ---------------------------------------------------------------------------
# CodeNavigator — the main analysis engine
# ---------------------------------------------------------------------------

class CodeNavigator:
    """Language-aware code navigation with tree-sitter or regex fallback."""

    def __init__(self, cwd: str):
        self.cwd = str(Path(cwd).resolve())
        self._ast_cache = _ASTCache()
        self._parsers: dict[str, object] = {}  # lang -> parser (lazy)
        self._use_treesitter = _HAS_TREESITTER and _ts_language_module is not None

        if self._use_treesitter:
            log.debug("CodeNavigator: tree-sitter available")
        else:
            log.debug("CodeNavigator: using regex fallback")

    # ----- Parser management -----

    def _get_parser(self, lang: str):
        """Lazy-load a tree-sitter parser for the given language."""
        if not self._use_treesitter:
            return None
        if lang in self._parsers:
            return self._parsers[lang]

        ts_name = _TS_LANG_NAMES.get(lang)
        if not ts_name:
            return None

        try:
            language = _ts_language_module.get_language(ts_name)
            parser = _ts_module.Parser()
            parser.set_language(language)
            self._parsers[lang] = parser
            return parser
        except Exception as e:
            log.debug("Failed to load tree-sitter parser for %s: %s", lang, e)
            self._parsers[lang] = None
            return None

    def _parse_file(self, file_path: str, lang: str):
        """Parse a file, using cache if available. Returns (tree, source_bytes) or (None, source_bytes)."""
        abs_path = self._resolve(file_path)
        try:
            source = Path(abs_path).read_bytes()
        except (OSError, IOError) as e:
            return None, None

        cached = self._ast_cache.get(abs_path)
        if cached is not None:
            return cached, source

        parser = self._get_parser(lang)
        if parser is None:
            return None, source

        try:
            tree = parser.parse(source)
            self._ast_cache.put(abs_path, tree)
            return tree, source
        except Exception as e:
            log.debug("tree-sitter parse failed for %s: %s", abs_path, e)
            return None, source

    def _resolve(self, file_path: str) -> str:
        """Resolve a path relative to cwd."""
        p = Path(file_path)
        if not p.is_absolute():
            p = Path(self.cwd) / p
        return str(p.resolve())

    def _read_lines(self, file_path: str) -> Optional[list[str]]:
        """Read a file and return lines, or None on error."""
        abs_path = self._resolve(file_path)
        try:
            text = Path(abs_path).read_text(encoding="utf-8", errors="replace")
            return text.splitlines()
        except (OSError, IOError):
            return None

    # ----- Tree-sitter symbol extraction -----

    def _ts_find_symbols(self, tree, source: bytes, lang: str) -> list[dict]:
        """Extract symbols from a tree-sitter AST."""
        symbols = []
        root = tree.root_node

        # Dispatch per-language
        if lang == "python":
            self._ts_python_symbols(root, source, symbols, parent=None)
        elif lang in ("javascript", "typescript"):
            self._ts_js_symbols(root, source, symbols, parent=None)
        elif lang == "go":
            self._ts_go_symbols(root, source, symbols)
        elif lang == "rust":
            self._ts_rust_symbols(root, source, symbols)
        elif lang == "java":
            self._ts_java_symbols(root, source, symbols, parent=None)
        elif lang in ("c", "cpp"):
            self._ts_c_symbols(root, source, symbols, parent=None)
        elif lang == "ruby":
            self._ts_ruby_symbols(root, source, symbols, parent=None)
        elif lang == "php":
            self._ts_php_symbols(root, source, symbols, parent=None)
        else:
            # Generic: walk all named children
            self._ts_generic_symbols(root, source, symbols)

        return symbols

    def _node_text(self, node, source: bytes) -> str:
        """Get the text of a tree-sitter node."""
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _find_child_by_type(self, node, *types):
        """Find first child matching any of the given types."""
        for child in node.children:
            if child.type in types:
                return child
        return None

    def _ts_python_symbols(self, node, source, symbols, parent=None):
        """Extract Python symbols from AST."""
        for child in node.children:
            if child.type in ("function_definition", "decorated_definition"):
                actual = child
                if child.type == "decorated_definition":
                    actual = self._find_child_by_type(
                        child, "function_definition", "class_definition")
                    if not actual:
                        continue

                if actual.type == "function_definition":
                    name_node = self._find_child_by_type(actual, "identifier")
                    params_node = self._find_child_by_type(actual, "parameters")
                    name = self._node_text(name_node, source) if name_node else "?"
                    sig = self._node_text(params_node, source) if params_node else "()"
                    kind = "method" if parent else "function"
                    symbols.append({
                        "name": name,
                        "kind": kind,
                        "line": actual.start_point[0] + 1,
                        "end_line": actual.end_point[0] + 1,
                        "signature": f"def {name}{sig}",
                        "parent": parent,
                    })
                elif actual.type == "class_definition":
                    # Decorated class — handle below
                    self._ts_python_class(actual, source, symbols, parent)

            elif child.type == "class_definition":
                self._ts_python_class(child, source, symbols, parent)

    def _ts_python_class(self, node, source, symbols, parent):
        """Extract a Python class and its methods."""
        name_node = self._find_child_by_type(node, "identifier")
        name = self._node_text(name_node, source) if name_node else "?"
        # superclass
        args_node = self._find_child_by_type(node, "argument_list")
        sup = self._node_text(args_node, source) if args_node else ""
        sig = f"class {name}{sup}" if sup else f"class {name}"
        symbols.append({
            "name": name,
            "kind": "class",
            "line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "signature": sig,
            "parent": parent,
        })
        # Recurse into class body for methods
        body = self._find_child_by_type(node, "block")
        if body:
            self._ts_python_symbols(body, source, symbols, parent=name)

    def _ts_js_symbols(self, node, source, symbols, parent=None):
        """Extract JS/TS symbols."""
        for child in node.children:
            ctype = child.type

            if ctype == "class_declaration":
                name_node = self._find_child_by_type(child, "identifier", "type_identifier")
                name = self._node_text(name_node, source) if name_node else "?"
                symbols.append({
                    "name": name,
                    "kind": "class",
                    "line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "signature": f"class {name}",
                    "parent": parent,
                })
                body = self._find_child_by_type(child, "class_body")
                if body:
                    self._ts_js_symbols(body, source, symbols, parent=name)

            elif ctype == "function_declaration":
                name_node = self._find_child_by_type(child, "identifier")
                params = self._find_child_by_type(child, "formal_parameters")
                name = self._node_text(name_node, source) if name_node else "?"
                sig = self._node_text(params, source) if params else "()"
                symbols.append({
                    "name": name,
                    "kind": "function",
                    "line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "signature": f"function {name}{sig}",
                    "parent": parent,
                })

            elif ctype in ("method_definition", "public_field_definition"):
                name_node = self._find_child_by_type(
                    child, "property_identifier", "identifier")
                params = self._find_child_by_type(child, "formal_parameters")
                name = self._node_text(name_node, source) if name_node else "?"
                sig = self._node_text(params, source) if params else ""
                symbols.append({
                    "name": name,
                    "kind": "method",
                    "line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "signature": f"{name}{sig}",
                    "parent": parent,
                })

            elif ctype in ("lexical_declaration", "variable_declaration"):
                # const foo = function/arrow
                for decl in child.children:
                    if decl.type == "variable_declarator":
                        name_node = self._find_child_by_type(decl, "identifier")
                        val = self._find_child_by_type(
                            decl, "arrow_function", "function")
                        if name_node and val:
                            name = self._node_text(name_node, source)
                            params = self._find_child_by_type(val, "formal_parameters")
                            sig = self._node_text(params, source) if params else "()"
                            symbols.append({
                                "name": name,
                                "kind": "function",
                                "line": child.start_point[0] + 1,
                                "end_line": child.end_point[0] + 1,
                                "signature": f"const {name} = {sig} =>",
                                "parent": parent,
                            })

            elif ctype == "export_statement":
                # Recurse into exported declarations
                self._ts_js_symbols(child, source, symbols, parent)

            elif ctype in ("interface_declaration", "type_alias_declaration",
                           "enum_declaration"):
                name_node = self._find_child_by_type(
                    child, "type_identifier", "identifier")
                name = self._node_text(name_node, source) if name_node else "?"
                kind_map = {
                    "interface_declaration": "interface",
                    "type_alias_declaration": "type",
                    "enum_declaration": "enum",
                }
                kind = kind_map.get(ctype, "type")
                symbols.append({
                    "name": name,
                    "kind": kind,
                    "line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "signature": f"{kind} {name}",
                    "parent": parent,
                })

    def _ts_go_symbols(self, node, source, symbols):
        """Extract Go symbols."""
        for child in node.children:
            if child.type == "function_declaration":
                name_node = self._find_child_by_type(child, "identifier")
                params = self._find_child_by_type(child, "parameter_list")
                name = self._node_text(name_node, source) if name_node else "?"
                sig = self._node_text(params, source) if params else "()"
                symbols.append({
                    "name": name,
                    "kind": "function",
                    "line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "signature": f"func {name}{sig}",
                    "parent": None,
                })
            elif child.type == "method_declaration":
                name_node = self._find_child_by_type(child, "field_identifier")
                params = self._find_child_by_type(child, "parameter_list")
                recv = self._find_child_by_type(child, "parameter_list")
                name = self._node_text(name_node, source) if name_node else "?"
                sig = self._node_text(params, source) if params else "()"
                symbols.append({
                    "name": name,
                    "kind": "method",
                    "line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "signature": f"func {name}{sig}",
                    "parent": None,
                })
            elif child.type == "type_declaration":
                for spec in child.children:
                    if spec.type == "type_spec":
                        name_node = self._find_child_by_type(
                            spec, "type_identifier")
                        type_node = self._find_child_by_type(
                            spec, "struct_type", "interface_type")
                        name = self._node_text(name_node, source) if name_node else "?"
                        kind = "struct"
                        if type_node and type_node.type == "interface_type":
                            kind = "interface"
                        symbols.append({
                            "name": name,
                            "kind": kind,
                            "line": spec.start_point[0] + 1,
                            "end_line": spec.end_point[0] + 1,
                            "signature": f"type {name} {kind}",
                            "parent": None,
                        })

    def _ts_rust_symbols(self, node, source, symbols):
        """Extract Rust symbols."""
        for child in node.children:
            ctype = child.type
            if ctype == "function_item":
                name_node = self._find_child_by_type(child, "identifier")
                params = self._find_child_by_type(child, "parameters")
                name = self._node_text(name_node, source) if name_node else "?"
                sig = self._node_text(params, source) if params else "()"
                symbols.append({
                    "name": name, "kind": "function",
                    "line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "signature": f"fn {name}{sig}", "parent": None,
                })
            elif ctype in ("struct_item", "enum_item", "trait_item"):
                name_node = self._find_child_by_type(child, "type_identifier")
                name = self._node_text(name_node, source) if name_node else "?"
                kind = ctype.replace("_item", "")
                symbols.append({
                    "name": name, "kind": kind,
                    "line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "signature": f"{kind} {name}", "parent": None,
                })
            elif ctype == "impl_item":
                name_node = self._find_child_by_type(child, "type_identifier")
                name = self._node_text(name_node, source) if name_node else "?"
                symbols.append({
                    "name": name, "kind": "impl",
                    "line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "signature": f"impl {name}", "parent": None,
                })
                # Methods inside impl
                body = self._find_child_by_type(child, "declaration_list")
                if body:
                    for item in body.children:
                        if item.type == "function_item":
                            mname_node = self._find_child_by_type(
                                item, "identifier")
                            mparams = self._find_child_by_type(
                                item, "parameters")
                            mname = (self._node_text(mname_node, source)
                                     if mname_node else "?")
                            msig = (self._node_text(mparams, source)
                                    if mparams else "()")
                            symbols.append({
                                "name": mname, "kind": "method",
                                "line": item.start_point[0] + 1,
                                "end_line": item.end_point[0] + 1,
                                "signature": f"fn {mname}{msig}",
                                "parent": name,
                            })

    def _ts_java_symbols(self, node, source, symbols, parent=None):
        """Extract Java symbols."""
        for child in node.children:
            ctype = child.type
            if ctype in ("class_declaration", "interface_declaration",
                         "enum_declaration"):
                name_node = self._find_child_by_type(child, "identifier")
                name = self._node_text(name_node, source) if name_node else "?"
                kind = ctype.replace("_declaration", "")
                symbols.append({
                    "name": name, "kind": kind,
                    "line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "signature": f"{kind} {name}", "parent": parent,
                })
                body = self._find_child_by_type(child, "class_body",
                                                "interface_body", "enum_body")
                if body:
                    self._ts_java_symbols(body, source, symbols, parent=name)
            elif ctype == "method_declaration":
                name_node = self._find_child_by_type(child, "identifier")
                params = self._find_child_by_type(child, "formal_parameters")
                name = self._node_text(name_node, source) if name_node else "?"
                sig = self._node_text(params, source) if params else "()"
                symbols.append({
                    "name": name, "kind": "method",
                    "line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "signature": f"{name}{sig}", "parent": parent,
                })
            elif ctype == "constructor_declaration":
                name_node = self._find_child_by_type(child, "identifier")
                params = self._find_child_by_type(child, "formal_parameters")
                name = self._node_text(name_node, source) if name_node else "?"
                sig = self._node_text(params, source) if params else "()"
                symbols.append({
                    "name": name, "kind": "constructor",
                    "line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "signature": f"{name}{sig}", "parent": parent,
                })

    def _ts_c_symbols(self, node, source, symbols, parent=None):
        """Extract C/C++ symbols."""
        for child in node.children:
            ctype = child.type
            if ctype == "function_definition":
                declarator = self._find_child_by_type(child, "function_declarator")
                if declarator:
                    name_node = self._find_child_by_type(
                        declarator, "identifier", "field_identifier",
                        "qualified_identifier")
                    params = self._find_child_by_type(
                        declarator, "parameter_list")
                    name = self._node_text(name_node, source) if name_node else "?"
                    sig = self._node_text(params, source) if params else "()"
                    symbols.append({
                        "name": name, "kind": "function",
                        "line": child.start_point[0] + 1,
                        "end_line": child.end_point[0] + 1,
                        "signature": f"{name}{sig}", "parent": parent,
                    })
            elif ctype in ("struct_specifier", "union_specifier",
                           "enum_specifier"):
                name_node = self._find_child_by_type(child, "type_identifier")
                if name_node:
                    name = self._node_text(name_node, source)
                    kind = ctype.replace("_specifier", "")
                    symbols.append({
                        "name": name, "kind": kind,
                        "line": child.start_point[0] + 1,
                        "end_line": child.end_point[0] + 1,
                        "signature": f"{kind} {name}", "parent": parent,
                    })
            elif ctype == "class_specifier":
                name_node = self._find_child_by_type(child, "type_identifier")
                name = self._node_text(name_node, source) if name_node else "?"
                symbols.append({
                    "name": name, "kind": "class",
                    "line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "signature": f"class {name}", "parent": parent,
                })
                body = self._find_child_by_type(child, "field_declaration_list")
                if body:
                    self._ts_c_symbols(body, source, symbols, parent=name)
            elif ctype == "namespace_definition":
                name_node = self._find_child_by_type(child, "identifier")
                name = self._node_text(name_node, source) if name_node else "?"
                symbols.append({
                    "name": name, "kind": "namespace",
                    "line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "signature": f"namespace {name}", "parent": parent,
                })
                body = self._find_child_by_type(child, "declaration_list")
                if body:
                    self._ts_c_symbols(body, source, symbols, parent=name)

    def _ts_ruby_symbols(self, node, source, symbols, parent=None):
        """Extract Ruby symbols."""
        for child in node.children:
            ctype = child.type
            if ctype == "class":
                name_node = self._find_child_by_type(
                    child, "constant", "scope_resolution")
                name = self._node_text(name_node, source) if name_node else "?"
                symbols.append({
                    "name": name, "kind": "class",
                    "line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "signature": f"class {name}", "parent": parent,
                })
                body = self._find_child_by_type(child, "body_statement")
                if body:
                    self._ts_ruby_symbols(body, source, symbols, parent=name)
            elif ctype == "module":
                name_node = self._find_child_by_type(
                    child, "constant", "scope_resolution")
                name = self._node_text(name_node, source) if name_node else "?"
                symbols.append({
                    "name": name, "kind": "module",
                    "line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "signature": f"module {name}", "parent": parent,
                })
                body = self._find_child_by_type(child, "body_statement")
                if body:
                    self._ts_ruby_symbols(body, source, symbols, parent=name)
            elif ctype == "method":
                name_node = self._find_child_by_type(child, "identifier")
                params = self._find_child_by_type(child, "method_parameters")
                name = self._node_text(name_node, source) if name_node else "?"
                sig = self._node_text(params, source) if params else ""
                symbols.append({
                    "name": name, "kind": "method" if parent else "function",
                    "line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "signature": f"def {name}{sig}", "parent": parent,
                })

    def _ts_php_symbols(self, node, source, symbols, parent=None):
        """Extract PHP symbols."""
        for child in node.children:
            ctype = child.type
            if ctype in ("class_declaration", "interface_declaration",
                         "trait_declaration"):
                name_node = self._find_child_by_type(child, "name")
                name = self._node_text(name_node, source) if name_node else "?"
                kind = ctype.replace("_declaration", "")
                symbols.append({
                    "name": name, "kind": kind,
                    "line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "signature": f"{kind} {name}", "parent": parent,
                })
                body = self._find_child_by_type(child, "declaration_list")
                if body:
                    self._ts_php_symbols(body, source, symbols, parent=name)
            elif ctype in ("function_definition", "method_declaration"):
                name_node = self._find_child_by_type(child, "name")
                params = self._find_child_by_type(child, "formal_parameters")
                name = self._node_text(name_node, source) if name_node else "?"
                sig = self._node_text(params, source) if params else "()"
                kind = "method" if parent else "function"
                symbols.append({
                    "name": name, "kind": kind,
                    "line": child.start_point[0] + 1,
                    "end_line": child.end_point[0] + 1,
                    "signature": f"function {name}{sig}", "parent": parent,
                })
            elif ctype == "program":
                # PHP wraps everything in a program node
                self._ts_php_symbols(child, source, symbols, parent)

    def _ts_generic_symbols(self, node, source, symbols):
        """Fallback: walk tree and grab function/class-like nodes."""
        for child in node.children:
            ctype = child.type
            if "function" in ctype or "method" in ctype:
                name_node = self._find_child_by_type(child, "identifier",
                                                     "name")
                if name_node:
                    symbols.append({
                        "name": self._node_text(name_node, source),
                        "kind": "function",
                        "line": child.start_point[0] + 1,
                        "end_line": child.end_point[0] + 1,
                        "signature": "",
                        "parent": None,
                    })
            elif "class" in ctype:
                name_node = self._find_child_by_type(child, "identifier",
                                                     "name",
                                                     "type_identifier")
                if name_node:
                    symbols.append({
                        "name": self._node_text(name_node, source),
                        "kind": "class",
                        "line": child.start_point[0] + 1,
                        "end_line": child.end_point[0] + 1,
                        "signature": "",
                        "parent": None,
                    })
            # Recurse into top-level containers
            if child.child_count > 0:
                self._ts_generic_symbols(child, source, symbols)

    # ----- Regex symbol extraction -----

    def _regex_find_symbols(self, lines: list[str],
                            lang: str) -> list[dict]:
        """Extract symbols using regex patterns."""
        patterns = _REGEX_PATTERNS.get(lang, [])
        if not patterns:
            return []

        symbols = []
        # Track class/struct scope by indentation (for Python, Ruby, etc.)
        class_stack: list[tuple[str, int]] = []  # (name, indent_level)

        for lineno, line in enumerate(lines, 1):
            for regex, kind_fn in patterns:
                m = regex.match(line)
                if not m:
                    continue

                # Determine kind
                groups = m.groupdict()
                if kind_fn:
                    kind = kind_fn(m)
                else:
                    kind = groups.get("kind", "function")
                    # Normalize
                    if kind == "def":
                        kind = "function"
                    elif kind == "async def":
                        kind = "function"

                name = groups.get("name", "?")
                sig = groups.get("sig", "")

                # If sig is empty but line has '(' without ')',
                # collect multi-line signature
                if not sig and "(" in line and ")" not in line:
                    sig_parts = [line[line.index("("):]]
                    for j in range(lineno, min(lineno + 10, len(lines))):
                        sig_parts.append(lines[j].strip())
                        if ")" in lines[j]:
                            break
                    sig = " ".join(sig_parts)
                    # Clean up whitespace
                    sig = re.sub(r"\s+", " ", sig).strip()
                    # Truncate very long signatures
                    if len(sig) > 120:
                        sig = sig[:117] + "..."

                # Determine indentation for parent detection
                indent = len(line) - len(line.lstrip())

                # Pop classes that are at same or deeper indent
                while class_stack and class_stack[-1][1] >= indent:
                    class_stack.pop()

                parent = class_stack[-1][0] if class_stack else None

                # If this is inside a class, it is a method
                if parent and kind == "function":
                    kind = "method"

                # Build signature string
                if sig:
                    signature = f"{kind} {name}{sig}"
                else:
                    signature = f"{kind} {name}"

                symbols.append({
                    "name": name,
                    "kind": kind,
                    "line": lineno,
                    "end_line": lineno,  # regex can't determine end
                    "signature": signature,
                    "parent": parent,
                })

                # Track classes for scope
                if kind in ("class", "struct", "interface", "module",
                            "trait", "impl", "namespace", "enum"):
                    class_stack.append((name, indent))

                break  # Only first matching pattern per line

        # Attempt to compute end_line for regex results (Python/Ruby style)
        self._infer_end_lines(symbols, lines, lang)

        return symbols

    def _infer_end_lines(self, symbols: list[dict], lines: list[str],
                         lang: str):
        """Try to infer end_line for regex-found symbols using indentation.

        Works well for Python and Ruby where indentation is significant.
        For brace languages, looks for matching brace depth.
        """
        if lang in ("python", "ruby"):
            # Indentation-based
            for i, sym in enumerate(symbols):
                start = sym["line"] - 1  # 0-based
                if start >= len(lines):
                    continue
                base_indent = len(lines[start]) - len(lines[start].lstrip())
                end = start
                for j in range(start + 1, len(lines)):
                    stripped = lines[j].strip()
                    if not stripped:
                        continue  # Skip blank lines
                    cur_indent = len(lines[j]) - len(lines[j].lstrip())
                    if cur_indent <= base_indent:
                        break
                    end = j
                sym["end_line"] = end + 1  # back to 1-based

    # ----- Public API: find_symbols -----

    def find_symbols(self, file_path: str) -> str:
        """Find all symbols (functions, classes, methods) in a file.

        Returns a formatted list of symbols with name, type, line number,
        and signature.
        """
        abs_path = self._resolve(file_path)
        if not Path(abs_path).exists():
            return f"Error: file not found: {abs_path}"

        lang = _detect_language(abs_path)
        if not lang:
            return f"Error: unsupported file type: {Path(abs_path).suffix}"

        # Try tree-sitter first
        tree, source = self._parse_file(abs_path, lang)
        if tree is not None:
            symbols = self._ts_find_symbols(tree, source, lang)
        else:
            # Regex fallback
            lines = self._read_lines(abs_path)
            if lines is None:
                return f"Error: cannot read file: {abs_path}"
            symbols = self._regex_find_symbols(lines, lang)

        if not symbols:
            return f"No symbols found in {abs_path}"

        parts = [f"Symbols in {abs_path} ({len(symbols)} found):"]
        for s in symbols:
            indent = "    " if s.get("parent") else "  "
            parent_prefix = f"[{s['parent']}] " if s.get("parent") else ""
            line_info = f"L{s['line']}"
            if s.get("end_line") and s["end_line"] != s["line"]:
                line_info = f"L{s['line']}-{s['end_line']}"
            parts.append(
                f"{indent}{parent_prefix}{s['kind']} {s['name']} "
                f"({line_info}): {s.get('signature', '')}"
            )

        mode = "tree-sitter" if (tree is not None) else "regex"
        parts.append(f"\n[parsed with {mode}]")
        return "\n".join(parts)

    # ----- Public API: find_definition -----

    def find_definition(self, symbol: str, scope: str = "project",
                        file_path: str = None) -> str:
        """Find where a symbol is defined.

        Args:
            symbol: Symbol name to find.
            scope: "file" to search one file, "project" to search all.
            file_path: Required when scope is "file".

        Returns file path, line number, and full definition line.
        """
        if scope == "file":
            if not file_path:
                return "Error: file_path required when scope is 'file'"
            return self._find_def_in_file(symbol, file_path)

        # Project scope — search source files
        results = []
        for fp in _iter_source_files(self.cwd):
            hit = self._find_def_in_file(symbol, fp, quiet=True)
            if hit:
                results.append(hit)
            if len(results) >= 20:
                break

        if not results:
            return f"No definition found for '{symbol}' in project"

        parts = [f"Definitions of '{symbol}' ({len(results)} found):"]
        parts.extend(results)
        return "\n".join(parts)

    def _find_def_in_file(self, symbol: str, file_path: str,
                          quiet: bool = False) -> Optional[str]:
        """Search a single file for a symbol definition."""
        abs_path = self._resolve(file_path)
        if not Path(abs_path).exists():
            if quiet:
                return None
            return f"Error: file not found: {abs_path}"

        lang = _detect_language(abs_path)
        if not lang:
            if quiet:
                return None
            return f"Error: unsupported file type: {Path(abs_path).suffix}"

        # Get symbols
        tree, source = self._parse_file(abs_path, lang)
        if tree is not None:
            symbols = self._ts_find_symbols(tree, source, lang)
        else:
            lines = self._read_lines(abs_path)
            if lines is None:
                return None
            symbols = self._regex_find_symbols(lines, lang)

        # Find matching symbol
        for s in symbols:
            if s["name"] == symbol:
                # Read the definition line from file
                lines = self._read_lines(abs_path)
                if lines and 0 < s["line"] <= len(lines):
                    def_line = lines[s["line"] - 1].strip()
                else:
                    def_line = s.get("signature", "")

                if quiet:
                    return (f"  {abs_path}:{s['line']} "
                            f"({s['kind']}): {def_line}")
                else:
                    return (f"Found '{symbol}' in {abs_path}:\n"
                            f"  Line {s['line']} ({s['kind']}): {def_line}")

        if quiet:
            return None
        return f"Symbol '{symbol}' not found in {abs_path}"

    # ----- Public API: find_references -----

    def find_references(self, symbol: str,
                        file_path: str = None) -> str:
        """Find all references to a symbol.

        Args:
            symbol: Symbol name to search for.
            file_path: If set, search only this file. Otherwise search project.

        Returns list of {file, line, context_line}.
        """
        pattern = _word_boundary_pattern(symbol)
        results = []
        max_results = 50

        if file_path:
            files = [self._resolve(file_path)]
        else:
            files = list(_iter_source_files(self.cwd))

        for fp in files:
            abs_fp = self._resolve(fp) if not Path(fp).is_absolute() else fp
            lines = self._read_lines(abs_fp)
            if lines is None:
                continue

            for lineno, line in enumerate(lines, 1):
                if pattern.search(line):
                    results.append({
                        "file": abs_fp,
                        "line": lineno,
                        "context": line.strip()[:150],
                    })
                    if len(results) >= max_results:
                        break
            if len(results) >= max_results:
                break

        if not results:
            scope = file_path or "project"
            return f"No references to '{symbol}' found in {scope}"

        # Group by file
        by_file: dict[str, list] = {}
        for r in results:
            by_file.setdefault(r["file"], []).append(r)

        parts = [f"References to '{symbol}' ({len(results)} found "
                 f"in {len(by_file)} file(s)):"]
        for fp, refs in by_file.items():
            parts.append(f"\n  {fp}:")
            for r in refs:
                parts.append(f"    L{r['line']}: {r['context']}")

        if len(results) >= max_results:
            parts.append(f"\n  (truncated at {max_results} results)")

        return "\n".join(parts)

    # ----- Public API: get_outline -----

    def get_outline(self, file_path: str) -> str:
        """Get a hierarchical structural outline of a file.

        Returns a text tree showing classes with their methods,
        top-level functions, and imports.
        """
        abs_path = self._resolve(file_path)
        if not Path(abs_path).exists():
            return f"Error: file not found: {abs_path}"

        lang = _detect_language(abs_path)
        if not lang:
            return f"Error: unsupported file type: {Path(abs_path).suffix}"

        lines = self._read_lines(abs_path)
        if lines is None:
            return f"Error: cannot read file: {abs_path}"

        # Get symbols
        tree, source = self._parse_file(abs_path, lang)
        if tree is not None:
            symbols = self._ts_find_symbols(tree, source, lang)
        else:
            symbols = self._regex_find_symbols(lines, lang)

        # Extract imports
        imports = self._extract_imports(lines, lang)

        # Build outline
        parts = [f"Outline of {abs_path} ({len(lines)} lines):"]

        if imports:
            parts.append("")
            parts.append("  Imports:")
            for imp in imports[:20]:
                parts.append(f"    {imp}")
            if len(imports) > 20:
                parts.append(f"    ... and {len(imports) - 20} more")

        # Group symbols: top-level vs children
        top_level = [s for s in symbols if not s.get("parent")]
        children: dict[str, list] = {}
        for s in symbols:
            if s.get("parent"):
                children.setdefault(s["parent"], []).append(s)

        if top_level:
            parts.append("")
            parts.append("  Structure:")
            for s in top_level:
                line_info = f"L{s['line']}"
                if s.get("end_line") and s["end_line"] != s["line"]:
                    line_info = f"L{s['line']}-{s['end_line']}"

                icon = self._kind_icon(s["kind"])
                parts.append(f"    {icon} {s['name']} ({line_info})")

                # Show children
                child_list = children.get(s["name"], [])
                for c in child_list:
                    c_line = f"L{c['line']}"
                    c_icon = self._kind_icon(c["kind"])
                    parts.append(f"      {c_icon} {c['name']} ({c_line})")

        if not top_level and not imports:
            parts.append("  (no symbols found)")

        mode = "tree-sitter" if (tree is not None) else "regex"
        parts.append(f"\n[parsed with {mode}]")
        return "\n".join(parts)

    def _kind_icon(self, kind: str) -> str:
        """Return a text marker for a symbol kind."""
        markers = {
            "class": "[C]",
            "interface": "[I]",
            "struct": "[S]",
            "enum": "[E]",
            "trait": "[T]",
            "module": "[M]",
            "namespace": "[N]",
            "impl": "[impl]",
            "function": "[f]",
            "method": "[m]",
            "constructor": "[m]",
            "type": "[T]",
        }
        return markers.get(kind, f"[{kind}]")

    def _extract_imports(self, lines: list[str], lang: str) -> list[str]:
        """Extract import/require/use statements."""
        imports = []
        patterns = {
            "python": re.compile(
                r"^\s*(import\s+\S+|from\s+\S+\s+import\s+.+)"),
            "javascript": re.compile(
                r"^\s*(import\s+.+|const\s+.+\s*=\s*require\(.+\))"),
            "typescript": re.compile(
                r"^\s*(import\s+.+|const\s+.+\s*=\s*require\(.+\))"),
            "go": re.compile(r'^\s*"[^"]+"|^\s*\w+\s+"[^"]+"'),
            "rust": re.compile(r"^\s*(use\s+.+|extern\s+crate\s+.+)"),
            "java": re.compile(r"^\s*import\s+.+"),
            "c": re.compile(r'^\s*#include\s+[<"].+[>"]'),
            "cpp": re.compile(r'^\s*#include\s+[<"].+[>"]'),
            "ruby": re.compile(r"^\s*(require\s+.+|require_relative\s+.+)"),
            "php": re.compile(
                r"^\s*(use\s+.+|require\s+.+|include\s+.+|require_once\s+.+)"),
        }

        pat = patterns.get(lang)
        if not pat:
            return imports

        # Go has multi-line import blocks
        in_go_import = False
        for line in lines:
            stripped = line.strip()
            if lang == "go":
                if stripped == "import (":
                    in_go_import = True
                    continue
                if in_go_import:
                    if stripped == ")":
                        in_go_import = False
                        continue
                    if stripped and not stripped.startswith("//"):
                        imports.append(stripped.strip('"'))
                    continue
                if stripped.startswith("import "):
                    # Single import
                    m = re.match(r'import\s+"([^"]+)"', stripped)
                    if m:
                        imports.append(m.group(1))
                    continue

            m = pat.match(line)
            if m:
                imports.append(stripped)

        return imports

    # ----- Public API: get_call_graph -----

    def get_call_graph(self, file_path: str,
                       function_name: str = None) -> str:
        """Show caller -> callee relationships in a file.

        Args:
            file_path: Path to the source file.
            function_name: If set, show only calls from/to this function.

        Returns caller -> callee relationships.
        """
        abs_path = self._resolve(file_path)
        if not Path(abs_path).exists():
            return f"Error: file not found: {abs_path}"

        lang = _detect_language(abs_path)
        if not lang:
            return f"Error: unsupported file type: {Path(abs_path).suffix}"

        lines = self._read_lines(abs_path)
        if lines is None:
            return f"Error: cannot read file: {abs_path}"

        # Get symbols to know function boundaries
        tree, source = self._parse_file(abs_path, lang)
        if tree is not None:
            symbols = self._ts_find_symbols(tree, source, lang)
        else:
            symbols = self._regex_find_symbols(lines, lang)

        # Filter to functions/methods
        funcs = [s for s in symbols
                 if s["kind"] in ("function", "method", "constructor")]

        if not funcs:
            return f"No functions found in {abs_path}"

        # Build set of known symbol names in this file
        known_names = {s["name"] for s in symbols}

        # For each function, find calls within its body
        call_graph: dict[str, list[str]] = {}

        for func in funcs:
            start = func["line"] - 1  # 0-based
            end = func.get("end_line", func["line"])  # 1-based already
            if end <= start:
                end = min(start + 50, len(lines))  # fallback: 50 lines

            caller = func["name"]
            if func.get("parent"):
                caller = f"{func['parent']}.{func['name']}"

            callees = set()
            for i in range(start + 1, min(end, len(lines))):
                for m in _CALL_PATTERN.finditer(lines[i]):
                    callee = m.group("callee")
                    # Skip keywords and self-recursion noise
                    if callee in ("if", "for", "while", "return", "print",
                                  "len", "range", "str", "int", "float",
                                  "list", "dict", "set", "tuple", "type",
                                  "isinstance", "hasattr", "getattr",
                                  "setattr", "super", "self", "cls",
                                  "True", "False", "None", "not", "and",
                                  "or", "in", "is"):
                        continue
                    callees.add(callee)

            if callees:
                call_graph[caller] = sorted(callees)

        if function_name:
            # Filter to show only the requested function
            filtered = {}
            for caller, callees in call_graph.items():
                bare_caller = caller.split(".")[-1]
                if bare_caller == function_name or caller == function_name:
                    filtered[caller] = callees

            # Also find who calls this function
            callers_of = []
            for caller, callees in call_graph.items():
                if function_name in callees:
                    callers_of.append(caller)

            parts = [f"Call graph for '{function_name}' in {abs_path}:"]

            if callers_of:
                parts.append(f"\n  Called by:")
                for c in callers_of:
                    parts.append(f"    {c} -> {function_name}")

            if filtered:
                parts.append(f"\n  Calls:")
                for caller, callees in filtered.items():
                    for callee in callees:
                        parts.append(f"    {caller} -> {callee}")
            elif not callers_of:
                parts.append(f"  '{function_name}' not found in call graph")

            return "\n".join(parts)

        # Full call graph
        parts = [f"Call graph for {abs_path} "
                 f"({len(call_graph)} functions with calls):"]

        for caller, callees in sorted(call_graph.items()):
            parts.append(f"\n  {caller}:")
            for callee in callees:
                marker = " *" if callee in known_names else ""
                parts.append(f"    -> {callee}{marker}")

        if call_graph:
            parts.append("\n  (* = defined in this file)")

        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def register_treesitter_tools(registry, cwd: str):
    """Register all tree-sitter code navigation tools.

    Args:
        registry: ToolRegistry instance to register tools with.
        cwd: Working directory (project root).
    """
    nav = CodeNavigator(cwd)

    registry.register(
        "find_symbols",
        nav.find_symbols,
        "Find all symbols (functions, classes, methods) in a source file. "
        "Returns each symbol's name, kind, line number, and signature. "
        "Supports Python, JS/TS, Go, Rust, Java, C/C++, Ruby, PHP.",
        {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the source file to analyze",
                },
            },
            "required": ["file_path"],
        },
    )

    registry.register(
        "find_definition",
        lambda symbol, scope="project", file_path=None: (
            nav.find_definition(symbol, scope, file_path)),
        "Find where a symbol (function, class, method) is defined. "
        "Searches the entire project by default, or a single file. "
        "Returns the file path, line number, and definition line.",
        {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Symbol name to find the definition of",
                },
                "scope": {
                    "type": "string",
                    "description": "'project' to search all files, 'file' to search one file",
                    "default": "project",
                    "enum": ["project", "file"],
                },
                "file_path": {
                    "type": "string",
                    "description": "File to search (required when scope is 'file')",
                },
            },
            "required": ["symbol"],
        },
    )

    registry.register(
        "find_references",
        lambda symbol, file_path=None: nav.find_references(symbol, file_path),
        "Find all references to a symbol across the project or within a file. "
        "Returns each occurrence with file path, line number, and context. "
        "Uses word-boundary matching to avoid partial matches.",
        {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Symbol name to search for",
                },
                "file_path": {
                    "type": "string",
                    "description": "Limit search to this file (optional)",
                },
            },
            "required": ["symbol"],
        },
    )

    registry.register(
        "get_outline",
        nav.get_outline,
        "Get a hierarchical structural outline of a source file. "
        "Shows classes with their methods, top-level functions, and imports "
        "in an indented tree format. Use this to understand file structure "
        "before reading the full source.",
        {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the source file",
                },
            },
            "required": ["file_path"],
        },
    )

    registry.register(
        "get_call_graph",
        lambda file_path, function_name=None: (
            nav.get_call_graph(file_path, function_name)),
        "Show function call relationships in a source file. "
        "Maps which functions call which other functions. "
        "Optionally focus on a single function to see what it calls "
        "and what calls it.",
        {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the source file",
                },
                "function_name": {
                    "type": "string",
                    "description": "Focus on this function (optional)",
                },
            },
            "required": ["file_path"],
        },
    )

    mode = "tree-sitter" if nav._use_treesitter else "regex-fallback"
    log.info("Registered tree-sitter tools (mode: %s)", mode)
