"""Scenario 6: Malicious repo — poisoned file ingestion.

Feeds static poisoned files through Crucible's content scanner.
Verifies all threats are detected and no false positives on clean files.
"""

import pytest
from pathlib import Path

from forge.crucible import Crucible, ThreatLevel


POISONED_DIR = Path(__file__).parent / "poisoned_files"


@pytest.mark.timeout(30)
class TestMaliciousRepo:

    def test_inject_readme_detected(self):
        """inject_readme.md should trigger prompt_injection detection."""
        c = Crucible(enabled=True)
        content = (POISONED_DIR / "inject_readme.md").read_text(encoding="utf-8")
        threats = c.scan_content("inject_readme.md", content)

        assert len(threats) > 0, "No threats detected in inject_readme.md"
        assert any(t.category == "prompt_injection" for t in threats), (
            f"Expected prompt_injection, got categories: "
            f"{[t.category for t in threats]}")
        assert any(t.level >= ThreatLevel.WARNING for t in threats)

    def test_hidden_payload_detected(self):
        """hidden_payload.py should trigger injection detection."""
        c = Crucible(enabled=True)
        content = (POISONED_DIR / "hidden_payload.py").read_text(encoding="utf-8")
        threats = c.scan_content("hidden_payload.py", content)

        assert len(threats) > 0, "No threats detected in hidden_payload.py"
        assert any(t.category == "prompt_injection" for t in threats)

    def test_unicode_trap_detected(self):
        """unicode_trap.js should trigger hidden_content detection."""
        c = Crucible(enabled=True)
        content = (POISONED_DIR / "unicode_trap.js").read_text(encoding="utf-8")
        threats = c.scan_content("unicode_trap.js", content)

        assert len(threats) > 0, "No threats detected in unicode_trap.js"
        categories = {t.category for t in threats}
        assert "hidden_content" in categories or "data_exfil" in categories, (
            f"Expected hidden_content or data_exfil, got: {categories}")

    def test_nested_base64_detected(self):
        """nested_base64.toml should trigger exfil/injection detection."""
        c = Crucible(enabled=True)
        content = (POISONED_DIR / "nested_base64.toml").read_text(encoding="utf-8")
        threats = c.scan_content("nested_base64.toml", content)

        assert len(threats) > 0, "No threats detected in nested_base64.toml"

    def test_clean_file_no_false_positive(self):
        """A normal Python file should not trigger any threats."""
        c = Crucible(enabled=True)
        clean_content = '''
import os
import sys
from pathlib import Path

def main():
    """Entry point for the application."""
    config = load_config()
    app = Application(config)
    app.run()

if __name__ == "__main__":
    main()
'''
        threats = c.scan_content("main.py", clean_content)
        assert threats == [], (
            f"False positive on clean file: {[t.category for t in threats]}")

    def test_all_poisoned_files_detected(self):
        """Every file in poisoned_files/ should trigger at least one threat."""
        c = Crucible(enabled=True)
        poisoned_files = list(POISONED_DIR.glob("*"))
        assert len(poisoned_files) >= 4, (
            f"Expected at least 4 poisoned files, got {len(poisoned_files)}")

        for filepath in poisoned_files:
            if filepath.is_file():
                content = filepath.read_text(encoding="utf-8")
                threats = c.scan_content(filepath.name, content)
                assert len(threats) > 0, (
                    f"No threats detected in {filepath.name}")

    def test_crucible_scan_count_tracking(self):
        """Total scans counter should increment for each file."""
        c = Crucible(enabled=True)
        for i in range(5):
            c.scan_content(f"file{i}.txt", "clean content")
        assert c.total_scans == 5
