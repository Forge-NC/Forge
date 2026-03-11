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
    """Verifies ReliabilityTracker defaults when no sessions have been recorded.

    A fresh tracker with zero sessions has a reliability score of 100.0 (optimistic
    default — unknown is treated as perfect until proven otherwise), reports
    'insufficient data' for trend direction, and shows sessions_in_window=0 with
    verification_pass_rate=1.0 in the underlying metrics.
    """

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
    """Verifies record_session() correctly extracts health metrics from subsystem audit dicts.

    Each subsystem (forensics, continuity, plan_verifier, billing) exposes a to_audit_dict()
    method. record_session() reads these dicts to compute:
    - verification_pass_rate: fraction of plan_verifier results with passed=True (0.5 for 1/2)
    - continuity_grade_avg: mean of score fields in continuity history (70.0 for [80,60])
    - tool_success_rate: fraction of tool-category events with risk_level==0 (0.667 for 2/3)
    The returned SessionHealth object carries turn_count and model from the call args.
    """

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
    """Verifies the composite reliability score responds correctly to session quality.

    Five sessions with good tool outcomes, passing verifications, and high continuity
    produce a score above 80. Five sessions with all tools at max risk (risk_level=3),
    failed verifications, low continuity grades (score=20), and minimal token output
    drive the score below 50. The weighted combination of WEIGHTS factors must produce
    meaningfully different scores for high-quality vs degraded session histories.
    """

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
    """Verifies the rolling window caps session history at WINDOW_SIZE entries.

    Recording 40 sessions into a tracker that has WINDOW_SIZE < 40 must evict
    the oldest entries so len(rt._sessions) == rt.WINDOW_SIZE. This prevents
    unbounded memory growth in long-running Forge instances and keeps the
    reliability score focused on recent behavior.
    """

    def test_window_cap(self, tmp_path):
        rt = ReliabilityTracker(persist_path=tmp_path / "rel.json")
        subs = _mock_subsystems()
        for _ in range(40):
            rt.record_session(
                **subs, session_start=time.time() - 60,
                turn_count=1, model="test")
        assert len(rt._sessions) == rt.WINDOW_SIZE


class TestTrend:
    """Verifies get_trend() correctly classifies the direction of reliability over time.

    Ten sessions where tool risk_level events shift from mostly-failing to mostly-passing
    should produce an 'improving' or 'stable' direction. Ten identical sessions with
    consistent good metrics produce 'stable'. Trend requires enough sessions to compute
    (at least the number needed to split into two halves for comparison).
    """

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
    """Verifies session history is persisted to disk and reloaded correctly.

    After recording a session, the persist_path JSON file must exist. A new
    ReliabilityTracker pointed at the same file must load exactly one session
    with the same model name. The rolling window cap must also be enforced
    on load: persisting 40 sessions and reloading should give WINDOW_SIZE
    sessions, not 40.
    """

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
    """Verifies format_terminal() produces a human-readable reliability summary.

    The output must contain 'Reliability Score' and '/100' so the user can
    see their score at a glance. It must also contain 'Rollbacks' and
    'Auto-repairs' — the two autonomy metrics that matter most for
    understanding whether the model is making and correcting mistakes.
    """

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
    """Verifies rollback and auto-repair counts are correctly extracted from plan_verifier results.

    A verify result with passed=False and rolled_back=True increments health.rollback_count.
    A verify result with passed=True and auto_fixed=True increments health.repair_success_count.
    These two counters track how often the model breaks things (rollback) vs silently fixes
    them (repair) — both are shown in the reliability terminal output and the fleet genome.
    """

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
