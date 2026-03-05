"""Tests for episodic memory (forge/memory.py)."""
import json
import time
from pathlib import Path

import pytest

from forge.memory import EpisodicMemory, JournalEntry, TaskState


@pytest.fixture
def memory(tmp_path):
    journal_dir = tmp_path / "journal"
    journal_dir.mkdir()
    return EpisodicMemory(persist_dir=journal_dir)


# ── Session ID ──

class TestSessionId:
    def test_session_id_is_hex(self, memory):
        assert len(memory._session_id) == 12
        int(memory._session_id, 16)  # must not raise

    def test_unique_across_instances(self, tmp_path):
        d1 = tmp_path / "j1"
        d1.mkdir()
        d2 = tmp_path / "j2"
        d2.mkdir()
        m1 = EpisodicMemory(persist_dir=d1)
        m2 = EpisodicMemory(persist_dir=d2)
        assert m1._session_id != m2._session_id


# ── Record turn ──

class TestRecordTurn:
    def test_basic_recording(self, memory):
        entry = memory.record_turn(
            user_message="Fix the bug in main.py",
            assistant_response="I'll read the file and fix it.",
            tool_calls=[{"name": "read_file", "args": {"path": "main.py"}}],
            files_touched=["main.py"],
            tokens_used=150,
        )
        assert isinstance(entry, JournalEntry)
        assert entry.session_id == memory._session_id
        assert entry.turn_number == 1
        assert "fix" in entry.user_intent.lower() or "bug" in entry.user_intent.lower()
        assert "main.py" in entry.files_touched
        assert entry.tokens_used == 150

    def test_turn_count_increments(self, memory):
        for i in range(3):
            entry = memory.record_turn(
                user_message=f"Turn {i}",
                assistant_response=f"Response {i}",
                tool_calls=[], files_touched=[], tokens_used=10,
            )
        assert entry.turn_number == 3

    def test_journal_file_written(self, memory):
        memory.record_turn(
            user_message="test", assistant_response="ok",
            tool_calls=[], files_touched=[], tokens_used=5,
        )
        assert memory._journal_file.exists()
        lines = memory._journal_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["session_id"] == memory._session_id

    def test_multiple_entries_appended(self, memory):
        for i in range(5):
            memory.record_turn(
                user_message=f"msg {i}", assistant_response=f"resp {i}",
                tool_calls=[], files_touched=[], tokens_used=10,
            )
        lines = memory._journal_file.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 5


# ── Eviction buffer ──

class TestEvictionBuffer:
    def test_record_eviction(self, memory):
        class MockEntry:
            role = "user"
            tag = "test"
            token_count = 500
            content = "Some content here"
        memory.record_eviction([MockEntry()])
        assert len(memory._eviction_buffer) == 1

    def test_eviction_buffer_capped(self, memory):
        class MockEntry:
            role = "user"
            tag = "test"
            token_count = 50
            content = "x"
        for _ in range(150):
            memory.record_eviction([MockEntry()])
        assert len(memory._eviction_buffer) <= 100

    def test_eviction_drains_on_record_turn(self, memory):
        class MockEntry:
            role = "assistant"
            tag = "response"
            token_count = 200
            content = "Previous response content"
        memory.record_eviction([MockEntry()])
        entry = memory.record_turn(
            user_message="next", assistant_response="yes",
            tool_calls=[], files_touched=[], tokens_used=10,
        )
        assert len(entry.evicted_content) == 1
        assert entry.evicted_content[0]["role"] == "assistant"
        assert len(memory._eviction_buffer) == 0


# ── Recent entries ──

class TestRecentEntries:
    def test_get_recent(self, memory):
        for i in range(5):
            memory.record_turn(
                user_message=f"msg {i}", assistant_response=f"resp {i}",
                tool_calls=[], files_touched=[], tokens_used=10,
            )
        recent = memory.get_recent_entries(3)
        assert len(recent) == 3
        # Most recent first or last depends on implementation, just check count
        assert all(isinstance(e, JournalEntry) for e in recent)

    def test_get_recent_more_than_available(self, memory):
        memory.record_turn(
            user_message="only one", assistant_response="ok",
            tool_calls=[], files_touched=[], tokens_used=10,
        )
        recent = memory.get_recent_entries(100)
        assert len(recent) >= 1


# ── Session entries ──

class TestSessionEntries:
    def test_get_current_session(self, memory):
        memory.record_turn(
            user_message="test", assistant_response="ok",
            tool_calls=[], files_touched=[], tokens_used=5,
        )
        entries = memory.get_session_entries()
        assert len(entries) == 1
        assert entries[0].session_id == memory._session_id


# ── Swap summary ──

class TestSwapSummary:
    def test_generates_summary(self, memory):
        for i in range(3):
            memory.record_turn(
                user_message=f"Work on task {i}",
                assistant_response=f"Done with task {i}",
                tool_calls=[{"name": "edit_file"}],
                files_touched=[f"file_{i}.py"],
                tokens_used=100,
            )
        summary = memory.generate_swap_summary([])
        assert isinstance(summary, str)
        assert len(summary) > 0

    def test_empty_session_summary(self, memory):
        summary = memory.generate_swap_summary([])
        assert isinstance(summary, str)


# ── Task state ──

class TestTaskState:
    def test_update_objective(self, memory):
        memory.update_task(objective="Fix the login bug")
        ts = memory.get_task_state()
        assert ts is not None
        assert ts.objective == "Fix the login bug"

    def test_update_file_modified(self, memory):
        memory.update_task(objective="refactor")
        memory.update_task(file_modified="auth.py")
        memory.update_task(file_modified="config.py")
        ts = memory.get_task_state()
        assert "auth.py" in ts.files_modified
        assert "config.py" in ts.files_modified

    def test_update_decision(self, memory):
        memory.update_task(objective="build API")
        memory.update_task(decision="Use REST not GraphQL")
        ts = memory.get_task_state()
        assert "Use REST not GraphQL" in ts.decisions

    def test_update_subtask(self, memory):
        memory.update_task(objective="deploy")
        memory.update_task(subtask={"description": "write Dockerfile", "status": "done"})
        ts = memory.get_task_state()
        assert len(ts.subtasks) == 1

    def test_no_task_state_initially(self, memory):
        assert memory.get_task_state() is None

    def test_context_swaps_tracked(self, memory):
        memory.update_task(objective="test")
        ts = memory.get_task_state()
        assert ts.context_swaps == 0


# ── Journal display ──

class TestJournalDisplay:
    def test_format_with_entries(self, memory):
        entry = memory.record_turn(
            user_message="hello", assistant_response="hi there",
            tool_calls=[], files_touched=["test.py"], tokens_used=20,
        )
        output = memory.format_journal_display([entry])
        assert isinstance(output, str)
        assert len(output) > 0

    def test_format_empty(self, memory):
        output = memory.format_journal_display([])
        assert "no journal" in output.lower() or output == ""


# ── Audit dict ──

class TestMemoryAuditDict:
    def test_structure(self, memory):
        memory.record_turn(
            user_message="audit test", assistant_response="ok",
            tool_calls=[], files_touched=[], tokens_used=10,
        )
        audit = memory.to_audit_dict()
        assert audit["schema_version"] == 1
        assert audit["session_id"] == memory._session_id
        assert len(audit["entries"]) == 1

    def test_truncation(self, memory):
        long_msg = "x" * 2000
        memory.record_turn(
            user_message=long_msg, assistant_response=long_msg,
            tool_calls=[], files_touched=[], tokens_used=10,
        )
        audit = memory.to_audit_dict()
        entry = audit["entries"][0]
        assert len(entry["user_intent"]) <= 500
        assert len(entry["assistant_response"]) <= 500
