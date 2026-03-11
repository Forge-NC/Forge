"""Tests for forge.tools.filesystem — syntax validation on edit/write."""

import pytest
from pathlib import Path

from forge.tools.filesystem import edit_file, write_file


class TestEditFileSyntaxValidation:
    """Verifies edit_file() validates Python syntax before committing changes to disk.

    If the edit would produce invalid Python (SyntaxError, IndentationError), the result
    string must contain 'Error', 'SyntaxError', and 'File unchanged', and the file on disk
    must be byte-for-byte identical to the original. Valid edits apply and report 'Replaced'.
    Non-Python files (.txt, .js) skip syntax checking entirely.
    Error message must include the line number of the syntax error.
    """

    def test_rejects_broken_python(self, tmp_path):
        """edit_file that produces invalid Python syntax → error, file unchanged."""
        py = tmp_path / "example.py"
        py.write_text("x = 1\ny = 2\n", encoding="utf-8")

        result = edit_file(str(py), "x = 1", "x = ")  # SyntaxError
        assert "Error" in result
        assert "SyntaxError" in result
        assert "File unchanged" in result
        # Original file untouched
        assert py.read_text(encoding="utf-8") == "x = 1\ny = 2\n"

    def test_accepts_valid_python(self, tmp_path):
        py = tmp_path / "example.py"
        py.write_text("x = 1\ny = 2\n", encoding="utf-8")

        result = edit_file(str(py), "x = 1", "x = 42")
        assert "Replaced" in result
        assert py.read_text(encoding="utf-8") == "x = 42\ny = 2\n"

    def test_non_python_skips_validation(self, tmp_path):
        """Non-Python files are not syntax-checked."""
        txt = tmp_path / "notes.txt"
        txt.write_text("hello world", encoding="utf-8")

        result = edit_file(str(txt), "hello", "def (broken")
        assert "Replaced" in result
        assert txt.read_text(encoding="utf-8") == "def (broken world"

    def test_rejects_indentation_error(self, tmp_path):
        """Catches indentation errors (the exact bug qwen3 caused)."""
        py = tmp_path / "example.py"
        original = "def foo():\n    return 1\n"
        py.write_text(original, encoding="utf-8")

        # Break indentation
        result = edit_file(str(py), "    return 1", "return 1")
        assert "Error" in result
        assert "SyntaxError" in result
        assert py.read_text(encoding="utf-8") == original

    def test_reports_line_number(self, tmp_path):
        """Error message includes the line number of the syntax error."""
        py = tmp_path / "example.py"
        py.write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")

        result = edit_file(str(py), "c = 3", "c = )")
        assert "line 3" in result


class TestWriteFileSyntaxValidation:
    """Verifies write_file() validates Python syntax before creating a new file.

    Writing invalid Python → 'Error', 'SyntaxError', 'not written' in result, file does not exist.
    Writing valid Python → 'Wrote' in result, file exists with correct content.
    Non-Python files skip validation and always write.
    """

    def test_rejects_broken_python(self, tmp_path):
        py = tmp_path / "new.py"

        result = write_file(str(py), "def broken(\n")
        assert "Error" in result
        assert "SyntaxError" in result
        assert "not written" in result
        assert not py.exists()

    def test_accepts_valid_python(self, tmp_path):
        py = tmp_path / "new.py"

        result = write_file(str(py), "x = 42\n")
        assert "Wrote" in result
        assert py.read_text(encoding="utf-8") == "x = 42\n"

    def test_non_python_skips_validation(self, tmp_path):
        js = tmp_path / "app.js"

        result = write_file(str(js), "function {{{ broken")
        assert "Wrote" in result
        assert js.exists()
