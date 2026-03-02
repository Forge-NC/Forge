"""Tests for the cross-session reliability tracker."""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from forge.reliability import ReliabilityTracker, SessionHealth, WEIGHTS


def _mock_subsystems(*, verify_results=None, cont_history=None,
                      events=None, output_tokens=500):
    """Create mock subsystems with to_audit_dict() returns."""
    forensics = MagicMock()
    forensics.to_audit_dict.return_value = {
        "session_id": "test_session",
        "events": events or [
            {"category": "tool", "risk_level": 0},
            {"category": "tool", "risk_level": 0},
            {"category": "file_read", "risk_level": 0},
        ],
    }

    continuity = MagicMock()
    continuity.to_audit_dict.return_value = {
        "history": cont_history or [{"score": 90}],
    }

    plan_verifier = MagicMock()
    plan_verifier.to_audit_dict.return_value = {
        "mode": "report",
        "results": verify_results or [],
    }

    billing = MagicMock()
    billing.to_audit_dict.return_value = {
        "session_tokens": output_tokens * 2,
        "session_output": output_tokens,
    }

    return {
        "forensics": forensics,
        "continuity": continuity,
        "plan_verifier": plan_verifier,
        "billing": billing,
    }


class TestEmptyHistory:
    def test_score_is_100(self, tmp_path):
        rt = ReliabilityTracker(persist_path=tmp_path / "rel.json")
        assert rt.get_reliability_score() == 100.0

    def test_trend_insufficient(self, tmp_path):
        rt = ReliabilityTracker(persist_path=tmp_path / "rel.json")
        assert rt.get_trend()["direction"] == "insufficient data"

    def test_metrics_defaults(self, tmp_path):
        rt = ReliabilityTracker(persist_path=tmp_path / "rel.json")
        m = rt.get_underlying_metrics()
        assert m["sessions_in_window"] == 0
        assert m["verification_pass_rate"] == 1.0


class TestRecordSession:
    def test_records_successfully(self, tmp_path):
        rt = ReliabilityTracker(persist_path=tmp_path / "rel.json")
        subs = _mock_subsystems()
        health = rt.record_session(
            **subs, session_start=time.time() - 60,
            turn_count=5, model="test")
        assert isinstance(health, SessionHealth)
        assert health.total_turns == 5
        assert health.model == "test"

    def test_verify_rate_computed(self, tmp_path):
        rt = ReliabilityTracker(persist_path=tmp_path / "rel.json")
        results = [
            {"passed": True, "checks": [{"name": "tests"}]},
            {"passed": False, "checks": [{"name": "tests"}]},
        ]
        subs = _mock_subsystems(verify_results=results)
        health = rt.record_session(
            **subs, session_start=time.time() - 60,
            turn_count=5, model="test")
        assert health.verification_pass_rate == 0.5

    def test_continuity_avg_computed(self, tmp_path):
        rt = ReliabilityTracker(persist_path=tmp_path / "rel.json")
        history = [{"score": 80}, {"score": 60}]
        subs = _mock_subsystems(cont_history=history)
        health = rt.record_session(
            **subs, session_start=time.time() - 60,
            turn_count=5, model="test")
        assert health.continuity_grade_avg == 70.0

    def test_tool_success_rate(self, tmp_path):
        rt = ReliabilityTracker(persist_path=tmp_path / "rel.json")
        events = [
            {"category": "tool", "risk_level": 0},
            {"category": "tool", "risk_level": 2},
            {"category": "tool", "risk_level": 0},
        ]
        subs = _mock_subsystems(events=events)
        health = rt.record_session(
            **subs, session_start=time.time() - 60,
            turn_count=5, model="test")
        # 2 ok out of 3 tool events
        assert abs(health.tool_success_rate - 0.6667) < 0.01


class TestCompositeScore:
    def test_perfect_sessions(self, tmp_path):
        rt = ReliabilityTracker(persist_path=tmp_path / "rel.json")
        subs = _mock_subsystems(output_tokens=200)
        for _ in range(5):
            rt.record_session(
                **subs, session_start=time.time() - 300,
                turn_count=5, model="test")
        score = rt.get_reliability_score()
        assert score > 80

    def test_degraded_sessions(self, tmp_path):
        rt = ReliabilityTracker(persist_path=tmp_path / "rel.json")
        events = [{"category": "tool", "risk_level": 3}] * 10
        subs = _mock_subsystems(
            verify_results=[{"passed": False, "checks": []}],
            cont_history=[{"score": 20}],
            events=events,
            output_tokens=10)
        for _ in range(5):
            rt.record_session(
                **subs, session_start=time.time() - 300,
                turn_count=5, model="test")
        score = rt.get_reliability_score()
        assert score < 50


class TestRollingWindow:
    def test_window_cap(self, tmp_path):
        rt = ReliabilityTracker(persist_path=tmp_path / "rel.json")
        subs = _mock_subsystems()
        for _ in range(40):
            rt.record_session(
                **subs, session_start=time.time() - 60,
                turn_count=1, model="test")
        assert len(rt._sessions) == rt.WINDOW_SIZE


class TestTrend:
    def test_improving(self, tmp_path):
        rt = ReliabilityTracker(persist_path=tmp_path / "rel.json")
        # Add sessions with improving tool success
        for i in range(10):
            events = [{"category": "tool", "risk_level": 0}] * (i + 1)
            events += [{"category": "tool", "risk_level": 2}] * max(0, 5 - i)
            subs = _mock_subsystems(events=events, output_tokens=200)
            rt.record_session(
                **subs, session_start=time.time() - 300,
                turn_count=5, model="test")
        trend = rt.get_trend()
        assert trend["direction"] in ("improving", "stable")

    def test_stable(self, tmp_path):
        rt = ReliabilityTracker(persist_path=tmp_path / "rel.json")
        subs = _mock_subsystems(output_tokens=200)
        for _ in range(10):
            rt.record_session(
                **subs, session_start=time.time() - 300,
                turn_count=5, model="test")
        trend = rt.get_trend()
        assert trend["direction"] == "stable"


class TestPersistence:
    def test_save_and_load(self, tmp_path):
        path = tmp_path / "rel.json"
        rt = ReliabilityTracker(persist_path=path)
        subs = _mock_subsystems()
        rt.record_session(
            **subs, session_start=time.time() - 60,
            turn_count=5, model="test")
        assert path.exists()

        # Load into a new tracker
        rt2 = ReliabilityTracker(persist_path=path)
        assert len(rt2._sessions) == 1
        assert rt2._sessions[0].model == "test"

    def test_window_pruning_on_save(self, tmp_path):
        path = tmp_path / "rel.json"
        rt = ReliabilityTracker(persist_path=path)
        subs = _mock_subsystems()
        for _ in range(40):
            rt.record_session(
                **subs, session_start=time.time() - 60,
                turn_count=1, model="test")

        rt2 = ReliabilityTracker(persist_path=path)
        assert len(rt2._sessions) == rt.WINDOW_SIZE


class TestFormatTerminal:
    def test_contains_score(self, tmp_path):
        rt = ReliabilityTracker(persist_path=tmp_path / "rel.json")
        subs = _mock_subsystems()
        rt.record_session(
            **subs, session_start=time.time() - 60,
            turn_count=5, model="test")
        output = rt.format_terminal()
        assert "Reliability Score" in output
        assert "/100" in output

    def test_contains_autonomy_metrics(self, tmp_path):
        rt = ReliabilityTracker(persist_path=tmp_path / "rel.json")
        subs = _mock_subsystems()
        rt.record_session(
            **subs, session_start=time.time() - 60,
            turn_count=5, model="test")
        output = rt.format_terminal()
        assert "Rollbacks" in output
        assert "Auto-repairs" in output


class TestRollbackTracking:
    def test_rollback_counted(self, tmp_path):
        rt = ReliabilityTracker(persist_path=tmp_path / "rel.json")
        results = [
            {"passed": False, "rolled_back": True,
             "checks": [{"name": "tests"}]},
        ]
        subs = _mock_subsystems(verify_results=results)
        health = rt.record_session(
            **subs, session_start=time.time() - 60,
            turn_count=5, model="test")
        assert health.rollback_count == 1

    def test_repair_counted(self, tmp_path):
        rt = ReliabilityTracker(persist_path=tmp_path / "rel.json")
        results = [
            {"passed": True, "auto_fixed": True,
             "checks": [{"name": "tests"}]},
        ]
        subs = _mock_subsystems(verify_results=results)
        health = rt.record_session(
            **subs, session_start=time.time() - 60,
            turn_count=5, model="test")
        assert health.repair_success_count == 1
