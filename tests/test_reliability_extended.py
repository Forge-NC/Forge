"""Extended tests for ReliabilityTracker — to_audit_dict, get_score_history."""

import time
import pytest
from forge.reliability import ReliabilityTracker, SessionHealth


def _make_health(**overrides) -> SessionHealth:
    """Create a SessionHealth with sensible defaults."""
    defaults = dict(
        session_id="test-session",
        timestamp=time.time(),
        verification_pass_rate=0.9,
        continuity_grade_avg=85.0,
        tool_success_rate=0.95,
        duration_s=300,
        token_efficiency=50.0,
        total_turns=10,
        total_tokens=5000,
        model="test-model",
    )
    defaults.update(overrides)
    return SessionHealth(**defaults)


@pytest.fixture
def tracker(tmp_path):
    return ReliabilityTracker(persist_path=tmp_path / "reliability.json")


def _add_sessions(tracker, count, **overrides):
    """Directly populate tracker sessions for testing."""
    for _ in range(count):
        tracker._sessions.append(_make_health(**overrides))


class TestToAuditDict:
    """Verifies ReliabilityTracker.to_audit_dict() structure, content, and empty defaults.

    Audit dict has schema_version=1, score, trend, metrics, score_history, sessions_count keys.
    With 5 sessions: sessions_count=5, len(score_history)==5, score>0.
    Empty tracker: sessions_count=0, score_history=[], score=100.0 (optimistic default).
    """

    def test_audit_dict_structure(self, tracker):
        audit = tracker.to_audit_dict()
        assert audit["schema_version"] == 1
        assert "score" in audit
        assert "trend" in audit
        assert "metrics" in audit
        assert "score_history" in audit
        assert "sessions_count" in audit

    def test_audit_dict_with_sessions(self, tracker):
        for i in range(5):
            tracker._sessions.append(_make_health(
                verification_pass_rate=0.8 + i * 0.02,
                continuity_grade_avg=80.0 + i,
            ))
        audit = tracker.to_audit_dict()
        assert audit["sessions_count"] == 5
        assert len(audit["score_history"]) == 5
        assert audit["score"] > 0

    def test_audit_dict_empty(self, tracker):
        audit = tracker.to_audit_dict()
        assert audit["sessions_count"] == 0
        assert audit["score_history"] == []
        assert audit["score"] == 100.0  # benefit of the doubt


class TestGetScoreHistory:
    """Verifies get_score_history() returns recent composite scores capped at 20 entries.

    Empty tracker → []. 3 sessions → list of 3 floats > 0. 30 sessions → list of <= 20.
    Perfect-health session (pass_rate=1.0, grade=100, tool_success=1.0) → score >= 50.
    """

    def test_empty_history(self, tracker):
        assert tracker.get_score_history() == []

    def test_history_matches_sessions(self, tracker):
        _add_sessions(tracker, 3)
        history = tracker.get_score_history()
        assert len(history) == 3
        for s in history:
            assert isinstance(s, float)
            assert s > 0

    def test_history_capped_at_20(self, tracker):
        _add_sessions(tracker, 30)
        history = tracker.get_score_history()
        assert len(history) <= 20

    def test_history_values_are_composites(self, tracker):
        tracker._sessions.append(_make_health(
            verification_pass_rate=1.0,
            continuity_grade_avg=100.0,
            tool_success_rate=1.0,
            duration_s=600,
            total_turns=20,
        ))
        history = tracker.get_score_history()
        assert len(history) == 1
        assert history[0] >= 50  # reasonable score
