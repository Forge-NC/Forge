"""Filesystem tools — read, write, edit, search.

Cross-platform (Windows + Linux). All paths are resolved to
absolute paths before any operation.
"""

import ast
import os
import re
import fnmatch
import subprocess
import logging
import tempfile
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def _check_path_safety(file_path: str) -> Optional[str]:
    """Check a file path for null bytes and other injection attempts.

    Returns an error string if unsafe, None if safe.
    """
    if "\x00" in file_path:
        return "Error: file path contains null byte."
    return None


def _validate_python(content: str, file_path: str) -> Optional[str]:
    """Return error message if Python syntax is invalid, None if OK."""
    try:
        ast.parse(content, filename=file_path)
        return None
    except SyntaxError as e:
        return f"SyntaxError at line {e.lineno}: {e.msg}"


def _validate_syntax(file_path: str, content: str) -> Optional[str]:
    """Validate syntax of content based on file extension.

    Returns error string if invalid, None if valid or not a validated type.
    """
    ext = Path(file_path).suffix.lower()
    if ext == ".py":
        return _validate_python(content, file_path)
    return None


def read_file(file_path: str, offset: int = 0, limit: int = 0) -> str:
    """Read a file and return its contents with line numbers.

    Args:
        file_path: Absolute or relative path to the file.
        offset: Start reading from this line (1-based). 0 = beginning.
        limit: Maximum number of lines to read. 0 = all.
    """
    err = _check_path_safety(file_path)
    if err:
        return err
    p = Path(file_path).resolve()
    if not p.exists():
        return f"Error: file not found: {p}"
    if not p.is_file():
        return f"Error: not a file: {p}"

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error reading {p}: {e}"

    lines = text.splitlines()
    total = len(lines)

    start = max(0, offset - 1) if offset > 0 else 0
    end = (start + limit) if limit > 0 else total
    end = min(end, total)

    result_lines = []
    for i in range(start, end):
        result_lines.append(f"{i + 1:>6}\t{lines[i]}")

    header = f"[{p}] ({total} lines"
    if offset or limit:
        header += f", showing {start + 1}-{end}"
    header += ")"

    return header + "\n" + "\n".join(result_lines)


def write_file(file_path: str, content: str) -> str:
    """Write content to a file (creates or overwrites).

    Args:
        file_path: Absolute or relative path.
        content: The full file content to write.
    """
    err = _check_path_safety(file_path)
    if err:
        return err
    p = Path(file_path).resolve()
    # Block writes through symlinks (prevents redirect attacks)
    if p.exists() and p.is_symlink():
        return f"Error: refusing to write through symlink: {p}"
    p.parent.mkdir(parents=True, exist_ok=True)

    # Syntax validation — reject writes that produce broken files
    err = _validate_syntax(str(p), content)
    if err:
        return f"Error: content has invalid syntax for {p}. {err}. File not written."

    try:
        # Atomic write: temp file in same dir then os.replace()
        # Prevents corruption if process is killed mid-write
        fd, tmp_path = tempfile.mkstemp(
            dir=str(p.parent), suffix=".forge_tmp", prefix=".~")
        try:
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
            fd = -1
            os.replace(tmp_path, str(p))
        except BaseException:
            if fd >= 0:
                os.close(fd)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        lines = content.count("\n") + 1
        return f"Wrote {lines} lines to {p}"
    except Exception as e:
        return f"Error writing {p}: {e}"


def edit_file(file_path: str, old_string: str, new_string: str,
              replace_all: bool = False) -> str:
    """Replace a string in a file.

    Args:
        file_path: Path to the file.
        old_string: The exact text to find and replace.
        new_string: The replacement text.
        replace_all: If True, replace all occurrences. Default: first only.
    """
    err = _check_path_safety(file_path)
    if err:
        return err
    p = Path(file_path).resolve()
    if not p.exists():
        return f"Error: file not found: {p}"
    if not p.is_file():
        return f"Error: not a regular file: {p}"
    if p.is_symlink():
        return f"Error: refusing to edit through symlink: {p}"

    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return f"Error reading {p}: {e}"

    count = text.count(old_string)
    if count == 0:
        return f"Error: old_string not found in {p}"
    if count > 1 and not replace_all:
        return (f"Error: old_string found {count} times in {p}. "
                f"Use replace_all=True or provide more context to be unique.")

    if replace_all:
        new_text = text.replace(old_string, new_string)
        replaced = count
    else:
        new_text = text.replace(old_string, new_string, 1)
        replaced = 1

    # Syntax validation — reject edits that break the file
    err = _validate_syntax(str(p), new_text)
    if err:
        return f"Error: edit would break syntax in {p}. {err}. File unchanged."

    # Atomic write: temp file in same dir then os.replace()
    fd, tmp_path = tempfile.mkstemp(
        dir=str(p.parent), suffix=".forge_tmp", prefix=".~")
    try:
        os.write(fd, new_text.encode("utf-8"))
        os.close(fd)
        fd = -1
        os.replace(tmp_path, str(p))
    except BaseException:
        if fd >= 0:
            os.close(fd)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return f"Replaced {replaced} occurrence(s) in {p}"


def glob_files(pattern: str, path: str = ".") -> str:
    """Find files matching a glob pattern.

    Args:
        pattern: Glob pattern (e.g. "**/*.py", "src/*.ts").
        path: Directory to search in. Default: current directory.
    """
    base = Path(path).resolve()
    if not base.exists():
        return f"Error: directory not found: {base}"

    matches = sorted(base.glob(pattern))
    # Limit output to prevent flooding context
    if len(matches) > 100:
        result = [str(m) for m in matches[:100]]
        result.append(f"... and {len(matches) - 100} more files")
    else:
        result = [str(m) for m in matches]

    if not result:
        return f"No files matching '{pattern}' in {base}"

    return f"Found {len(matches)} file(s):\n" + "\n".join(result)


def grep_files(pattern: str, path: str = ".",
               glob_filter: str = "", max_results: int = 50) -> str:
    """Search file contents using regex.

    Args:
        pattern: Regex pattern to search for.
        path: Directory to search in.
        glob_filter: Optional glob to filter files (e.g. "*.py").
        max_results: Maximum number of matches to return.
    """
    base = Path(path).resolve()
    if not base.exists():
        return f"Error: directory not found: {base}"

    try:
        regex = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        return f"Invalid regex '{pattern}': {e}"

    results = []
    files_searched = 0
    files_matched = 0

    # Collect files to search
    if glob_filter:
        files = list(base.rglob(glob_filter))
    else:
        files = list(base.rglob("*"))

    for fp in files:
        if not fp.is_file():
            continue
        # Skip binary files and hidden dirs
        if any(part.startswith(".") for part in fp.parts):
            continue
        if fp.suffix in (".pyc", ".pyd", ".so", ".dll", ".exe",
                         ".png", ".jpg", ".gif", ".ico", ".woff",
                         ".woff2", ".ttf", ".zip", ".tar", ".gz"):
            continue

        files_searched += 1
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        for i, line in enumerate(text.splitlines(), 1):
            if regex.search(line):
                if not any(r["file"] == str(fp) for r in results):
                    files_matched += 1
                results.append({
                    "file": str(fp),
                    "line": i,
                    "text": line.strip()[:120],
                })
                if len(results) >= max_results:
                    break
        if len(results) >= max_results:
            break

    if not results:
        return (f"No matches for /{pattern}/ in {base} "
                f"({files_searched} files searched)")

    lines = [f"Found {len(results)} match(es) in {files_matched} file(s):"]
    for r in results:
        lines.append(f"  {r['file']}:{r['line']}: {r['text']}")
    if len(results) >= max_results:
        lines.append(f"  (truncated at {max_results} results)")

    return "\n".join(lines)


def list_directory(path: str = ".") -> str:
    """List contents of a directory.

    Args:
        path: Directory to list.
    """
    p = Path(path).resolve()
    if not p.exists():
        return f"Error: not found: {p}"
    if not p.is_dir():
        return f"Error: not a directory: {p}"

    entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    lines = [f"[{p}]"]
    for e in entries[:200]:
        if e.is_dir():
            lines.append(f"  {e.name}/")
        else:
            size = e.stat().st_size
            if size < 1024:
                sz = f"{size}B"
            elif size < 1024 * 1024:
                sz = f"{size // 1024}K"
            else:
                sz = f"{size // (1024 * 1024)}M"
            lines.append(f"  {e.name}  ({sz})")

    if len(entries) > 200:
        lines.append(f"  ... and {len(entries) - 200} more")

    return "\n".join(lines)


def run_shell(command: str, timeout: int = 30,
              cwd: str = None) -> str:
    """Execute a shell command and return its output.

    Args:
        command: The command to execute.
        timeout: Maximum seconds to wait. Default: 30.
        cwd: Working directory. Default: current directory.
    """
    shell = True
    shell_cmd = command

    try:
        # On Windows, prevent subprocess from flashing console windows
        extra = {}
        if os.name == "nt":
            extra["creationflags"] = subprocess.CREATE_NO_WINDOW

        result = subprocess.run(
            shell_cmd,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd or os.getcwd(),
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            **extra,
        )
        output_parts = []
        if result.stdout:
            output_parts.append(result.stdout)
        if result.stderr:
            output_parts.append(f"[stderr]\n{result.stderr}")
        if result.returncode != 0:
            output_parts.append(f"[exit code: {result.returncode}]")

        output = "\n".join(output_parts) if output_parts else "(no output)"

        # Truncate long output to prevent flooding context
        if len(output) > 10000:
            output = output[:10000] + f"\n... (truncated, {len(output)} chars total)"

        return output

    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s: {command}"
    except Exception as e:
        return f"Error running command: {e}"
