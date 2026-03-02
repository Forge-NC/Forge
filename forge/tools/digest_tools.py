"""Digest tools — structural codebase analysis for the AI.

Provides 5 tools that give the AI x-ray vision of any codebase:
  scan_codebase  — full structural map (Layer 0)
  digest_file    — single file's symbols (Layer 1)
  read_symbols   — specific function/class source (Layer 2)
  write_notes    — persist architectural observations
  read_notes     — recall previous observations

Progressive detail pyramid — Jerry exhausts layers 0-2 before
ever touching read_file (Layer 3).
"""

import sys
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def _scan_codebase(digester, path: str = ".", force: bool = False) -> str:
    """Scan a codebase and return the structural summary."""
    from forge.ui.terminal import DIM, RESET, CYAN, GREEN

    root = Path(path).resolve()
    if not root.is_dir():
        return f"Error: '{path}' is not a directory."

    # Check if we have a recent cached digest for this root
    existing = digester.get_digest()
    if (not force and existing and existing.root == str(root)
            and existing.scan_time > 0 and existing.total_files > 0):
        # Use cached digest — just regenerate summary
        return digester.generate_summary()

    # Progress callback — print to terminal
    total_ref = [0]
    last_pct = [0]

    def progress(file_path, num, total):
        total_ref[0] = total
        pct = int(num / max(1, total) * 100)
        if pct >= last_pct[0] + 5 or num == total:
            last_pct[0] = pct
            fname = Path(file_path).name
            sys.stdout.write(
                f"\r{DIM}[Scanning: {num}/{total} files ({pct}%) "
                f"— {fname[:30]}]{RESET}  ")
            sys.stdout.flush()

    try:
        digest = digester.scan(str(root), callback=progress, force=force)
        # Clear progress line
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()

        print(f"{GREEN}Scan complete:{RESET} {DIM}{digest.total_files} files, "
              f"{digest.total_lines:,} lines, {digest.total_symbols} symbols "
              f"in {digest.scan_time:.1f}s{RESET}")

        return digester.generate_summary()
    except Exception as e:
        return f"Error scanning codebase: {e}"


def _digest_file(digester, path: str) -> str:
    """Return detailed structural digest of a single file."""
    fd = digester.get_file(path)
    if not fd:
        return (f"Error: No digest found for '{path}'. "
                f"Run scan_codebase first to index the project.")

    parts = [
        f"=== {fd.path} ===",
        f"Language: {fd.language} | {fd.lines} lines | {fd.size_bytes:,} bytes",
        f"Summary: {fd.summary_line}",
    ]

    if fd.imports:
        parts.append(f"\nImports ({len(fd.imports)}):")
        for imp in fd.imports[:30]:
            parts.append(f"  {imp}")
        if len(fd.imports) > 30:
            parts.append(f"  ... and {len(fd.imports) - 30} more")

    if fd.symbols:
        parts.append(f"\nSymbols ({len(fd.symbols)}):")
        for s in fd.symbols:
            if isinstance(s, dict):
                kind = s.get("kind", "?")
                name = s.get("name", "?")
                line = s.get("line", "?")
                end_line = s.get("end_line", "?")
                sig = s.get("signature", "")
                doc = s.get("docstring", "")
                parent = s.get("parent", "")
            else:
                kind, name, line, end_line = s.kind, s.name, s.line, s.end_line
                sig, doc, parent = s.signature, s.docstring, s.parent

            indent = "    " if parent else "  "
            prefix = f"[{parent}] " if parent else ""
            line_range = f"L{line}-{end_line}" if end_line != line else f"L{line}"
            doc_str = f" — {doc}" if doc else ""
            parts.append(f"{indent}{prefix}{kind} {name} ({line_range}): {sig}{doc_str}")

    return "\n".join(parts)


def _read_symbols(digester, path: str, symbols: list = None) -> str:
    """Read only the source code of specific symbols from a file.

    10-15x cheaper than reading the full file. Use this to inspect
    specific functions or classes without polluting context.
    """
    if not symbols:
        return "Error: Provide a list of symbol names to read."

    return digester.read_symbol_source(path, symbols)


def _write_notes(digester, topic: str, content: str) -> str:
    """Write analysis notes that persist across sessions."""
    digest = digester.get_digest()
    if not digest:
        return "Error: No codebase scanned. Run scan_codebase first."

    digest.notes[topic] = content
    digester._save_cache()  # Persist immediately
    return f"Note saved: [{topic}] ({len(content)} chars)"


def _read_notes(digester, topic: str = "") -> str:
    """Read saved analysis notes."""
    digest = digester.get_digest()
    if not digest:
        return "Error: No codebase scanned. Run scan_codebase first."

    if not digest.notes:
        return "No notes saved yet. Use write_notes to record observations."

    if topic:
        content = digest.notes.get(topic)
        if content:
            return f"[{topic}]\n{content}"
        return (f"Note '{topic}' not found. "
                f"Available: {', '.join(digest.notes.keys())}")

    # List all notes
    parts = [f"Saved notes ({len(digest.notes)}):"]
    for t, c in digest.notes.items():
        preview = c[:100].replace("\n", " ")
        parts.append(f"  [{t}] {preview}...")
    return "\n".join(parts)


def register_all(registry, digester):
    """Register all digest tools with the given ToolRegistry."""

    registry.register(
        "scan_codebase",
        lambda path=".", force=False: _scan_codebase(digester, path, force),
        "Scan a codebase and return a structural map of every file, class, "
        "function, route, and database table. Use this FIRST when analyzing "
        "any project. Returns a compact summary (4-8K tokens) regardless of "
        "codebase size. Supports incremental updates — re-scans only changed files.",
        {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the project root directory",
                    "default": ".",
                },
                "force": {
                    "type": "boolean",
                    "description": "Force full re-scan even if cached",
                    "default": False,
                },
            },
        },
    )

    registry.register(
        "digest_file",
        lambda path: _digest_file(digester, path),
        "Get the detailed structural digest of a single file: all symbols "
        "with signatures, line numbers, imports. Use this to investigate a "
        "file's structure BEFORE reading the full file. ~50 tokens vs full file cost.",
        {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path (relative to project root or absolute)",
                },
            },
            "required": ["path"],
        },
    )

    registry.register(
        "read_symbols",
        lambda path, symbols=None: _read_symbols(digester, path, symbols),
        "Read ONLY the source code of specific functions or classes from a file. "
        "10-15x cheaper than reading the full file. Provide symbol names and get "
        "just those code sections with line numbers.",
        {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path",
                },
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of symbol names to read (function/class names)",
                },
            },
            "required": ["path", "symbols"],
        },
    )

    registry.register(
        "write_notes",
        lambda topic, content: _write_notes(digester, topic, content),
        "Save analysis notes that persist across sessions. Use this to record "
        "architectural observations, patterns, and findings during codebase analysis.",
        {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Note topic/key (e.g. 'architecture', 'auth_flow')",
                },
                "content": {
                    "type": "string",
                    "description": "Note content",
                },
            },
            "required": ["topic", "content"],
        },
    )

    registry.register(
        "read_notes",
        lambda topic="": _read_notes(digester, topic),
        "Read saved analysis notes from previous sessions. Call with no topic "
        "to list all notes, or with a topic to read a specific note.",
        {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Topic to read (empty = list all)",
                    "default": "",
                },
            },
        },
    )
