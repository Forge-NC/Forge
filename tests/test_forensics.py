"""Tests for forge.forensics — SessionForensics audit trail."""

import time
import pytest
from unittest.mock import patch
from forge.forensics import SessionForensics, ForensicEvent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_forensics(tmp_path):
    """Create a SessionForensics writing to a temp directory."""
    return SessionForensics(persist_dir=tmp_path)


# ---------------------------------------------------------------------------
# test_record_event
# ---------------------------------------------------------------------------

class TestRecordEvent:
    def test_basic_record(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record("file_read", "Read main.py",
                  details={"path": "/project/main.py"})
        assert len(sf._events) == 1
        assert sf._events[0].category == "file_read"
        assert sf._events[0].action == "Read main.py"

    def test_file_read_aggregation(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record("file_read", "Read main.py",
                  details={"path": "/project/main.py"})
        sf.record("file_read", "Read main.py again",
                  details={"path": "/project/main.py"})
        assert sf._files_read["/project/main.py"] == 2

    def test_file_write_aggregation(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record("file_write", "Write output.txt",
                  details={"path": "/project/output.txt", "created": True})
        assert sf._files_written["/project/output.txt"] == 1
        assert "/project/output.txt" in sf._files_created

    def test_file_edit_aggregation(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record("file_edit", "Edit config.py",
                  details={"path": "/project/config.py"})
        assert sf._files_edited["/project/config.py"] == 1

    def test_shell_command_tracking(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record("shell", "Run git status",
                  details={"command": "git status", "exit_code": 0})
        assert len(sf._shell_commands) == 1
        assert sf._shell_commands[0]["command"] == "git status"
        assert sf._shell_commands[0]["exit_code"] == 0

    def test_tool_call_tracking(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record("tool", "Called read_file",
                  details={"name": "read_file"})
        sf.record("tool", "Called read_file",
                  details={"name": "read_file"})
        sf.record("tool", "Called edit_file",
                  details={"name": "edit_file"})
        assert sf._tool_calls["read_file"] == 2
        assert sf._tool_calls["edit_file"] == 1

    def test_threat_tracking(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record("threat", "Injection detected",
                  details={"level": "CRITICAL",
                           "description": "prompt injection",
                           "file": "evil.md"},
                  risk_level=3)
        assert len(sf._threats) == 1
        assert sf._threats[0]["level"] == "CRITICAL"

    def test_context_swap_tracking(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record("context_swap", "Context swapped")
        sf.record("context_swap", "Context swapped again")
        assert sf._context_swaps == 2

    def test_risk_level_recorded(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record("error", "Something bad", risk_level=3)
        assert sf._events[0].risk_level == 3

    def test_no_details_defaults_to_empty(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record("file_read", "Read something")
        assert sf._events[0].details == {}


# ---------------------------------------------------------------------------
# test_record_turn
# ---------------------------------------------------------------------------

class TestRecordTurn:
    def test_single_turn(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record_turn(tokens_in=500, tokens_out=200)
        assert sf._turns == 1
        assert sf._total_tokens_in == 500
        assert sf._total_tokens_out == 200

    def test_multiple_turns(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record_turn(100, 50)
        sf.record_turn(200, 100)
        sf.record_turn(300, 150)
        assert sf._turns == 3
        assert sf._total_tokens_in == 600
        assert sf._total_tokens_out == 300


# ---------------------------------------------------------------------------
# test_generate_report
# ---------------------------------------------------------------------------

class TestGenerateReport:
    def test_report_is_markdown(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record_turn(100, 50)
        sf.record("file_read", "Read test.py",
                  details={"path": "/test.py"})
        sf.record("shell", "Run ls",
                  details={"command": "ls", "exit_code": 0})

        report = sf.generate_report()
        assert report.startswith("# Forge Session Forensics Report")
        assert "Session ID" in report
        assert "Duration" in report

    def test_report_includes_risk_events(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record("threat", "Injection found", risk_level=3,
                  details={"level": "CRITICAL"})
        report = sf.generate_report()
        assert "Risk Events" in report
        assert "CRITICAL" in report

    def test_report_clean_session(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record("file_read", "Read safe.py",
                  details={"path": "/safe.py"})
        report = sf.generate_report()
        assert "No risk events detected" in report

    def test_report_includes_files(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record("file_read", "Read x.py", details={"path": "/x.py"})
        sf.record("file_write", "Write y.py",
                  details={"path": "/y.py", "created": True})
        report = sf.generate_report()
        assert "Files Touched" in report
        assert "Files Created" in report

    def test_report_includes_shell(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record("shell", "Run git",
                  details={"command": "git status", "exit_code": 0})
        report = sf.generate_report()
        assert "Shell Commands" in report
        assert "git status" in report

    def test_report_includes_tools(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record("tool", "Called search",
                  details={"name": "search"})
        report = sf.generate_report()
        assert "Tool Usage" in report
        assert "search" in report

    def test_report_includes_timeline(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record("file_read", "Read foo.py",
                  details={"path": "/foo.py"})
        report = sf.generate_report()
        assert "Event Timeline" in report

    def test_report_includes_context_swaps(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record("context_swap", "Swapped context")
        report = sf.generate_report()
        assert "Context Management" in report

    def test_save_report(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record_turn(100, 50)
        path = sf.save_report()
        assert path is not None
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "Forge Session Forensics" in content


# ---------------------------------------------------------------------------
# test_format_summary
# ---------------------------------------------------------------------------

class TestFormatSummary:
    def test_summary_contains_key_info(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record_turn(1000, 500)
        sf.record("file_read", "Read a.py", details={"path": "/a.py"})
        sf.record("shell", "Run pytest",
                  details={"command": "pytest", "exit_code": 0})
        sf.record("tool", "Called edit",
                  details={"name": "edit_file"})

        try:
            summary = sf.format_summary()
        except ImportError:
            pytest.skip("forge.ui.terminal not importable")
            return

        assert sf._session_id in summary
        assert "1,000" in summary or "1000" in summary

    def test_summary_shows_clean_session(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record_turn(100, 50)
        try:
            summary = sf.format_summary()
            assert "clean" in summary.lower()
        except ImportError:
            pytest.skip("forge.ui.terminal not importable")

    def test_summary_shows_threats(self, tmp_path):
        sf = _make_forensics(tmp_path)
        sf.record("threat", "Bad stuff",
                  details={"level": "CRITICAL"})
        sf.record_turn(100, 50)
        try:
            summary = sf.format_summary()
            assert "1" in summary  # threat count
        except ImportError:
            pytest.skip("forge.ui.terminal not importable")


# ---------------------------------------------------------------------------
# test_categories
# ---------------------------------------------------------------------------

class TestCategories:
    """Ensure all expected categories are handled without errors."""

    def test_all_categories(self, tmp_path):
        sf = _make_forensics(tmp_path)
        categories = [
            ("file_read", {"path": "/a.py"}),
            ("file_write", {"path": "/b.py", "created": False}),
            ("file_write", {"path": "/c.py", "created": True}),
            ("file_edit", {"path": "/d.py"}),
            ("shell", {"command": "ls", "exit_code": 0}),
            ("tool", {"name": "read_file"}),
            ("threat", {"level": "WARNING", "description": "test"}),
            ("context_swap", {}),
            ("eviction", {"tokens": 500}),
            ("error", {"message": "timeout"}),
        ]
        for cat, details in categories:
            sf.record(cat, f"Action for {cat}", details=details)

        assert len(sf._events) == len(categories)
        # Verify specific aggregates
        assert len(sf._files_read) == 1
        assert len(sf._files_written) == 2
        assert len(sf._files_edited) == 1
        assert len(sf._shell_commands) == 1
        assert len(sf._threats) == 1
        assert sf._context_swaps == 1
        assert "/c.py" in sf._files_created


class TestForensicEventDataclass:
    def test_event_creation(self):
        event = ForensicEvent(
            timestamp=time.time(),
            category="file_read",
            action="Read main.py",
            details={"path": "/main.py"},
            risk_level=0,
        )
        assert event.category == "file_read"
        assert event.risk_level == 0

    def test_event_default_details(self):
        event = ForensicEvent(
            timestamp=time.time(),
            category="test",
            action="test action",
        )
        assert event.details == {}
        assert event.risk_level == 0
