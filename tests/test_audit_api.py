"""Tests for the to_audit_dict() API contract on every subsystem.

Verifies that each subsystem returns a JSON-serializable dict with
a schema_version key and expected top-level structure.
"""

import json
import time
from pathlib import Path

import pytest


# ── Forensics ──

class TestForensicsAuditDict:
    """Verifies SessionForensics.to_audit_dict() structure, content, and JSON-serializability.

    Empty session → schema_version=1, events=[], summary.context_swaps=0.
    With events: 4 recorded events → 4 in audit list; summary correctly aggregates
    files_read (dict), tool_calls (dict), context_swaps count, and threats list.
    All audit dicts must pass json.dumps() without error.
    """

    def test_empty_session(self, tmp_path):
        from forge.forensics import SessionForensics
        f = SessionForensics(persist_dir=tmp_path)
        d = f.to_audit_dict()
        assert d["schema_version"] == 1
        assert d["events"] == []
        assert d["summary"]["context_swaps"] == 0
        # Must be JSON-serializable
        json.dumps(d)

    def test_with_events(self, tmp_path):
        from forge.forensics import SessionForensics
        f = SessionForensics(persist_dir=tmp_path)
        f.record("file_read", "Read main.py", {"path": "main.py"})
        f.record("tool", "Called edit_file", {"name": "edit_file"}, risk_level=0)
        f.record("threat", "Injection found", {"level": "WARNING"}, risk_level=2)
        f.record("context_swap", "Swapped context")
        d = f.to_audit_dict()
        assert len(d["events"]) == 4
        assert d["summary"]["files_read"] == {"main.py": 1}
        assert d["summary"]["tool_calls"] == {"edit_file": 1}
        assert d["summary"]["context_swaps"] == 1
        assert len(d["summary"]["threats"]) == 1
        json.dumps(d)


# ── Memory ──

class TestMemoryAuditDict:
    """Verifies EpisodicMemory.to_audit_dict() structure and entry content.

    Empty memory → schema_version=1, entries=[]. After record_turn(), the audit
    entries list contains one entry with the correct user_intent string.
    """

    def test_empty_session(self, tmp_path):
        from forge.memory import EpisodicMemory
        m = EpisodicMemory(persist_dir=tmp_path)
        d = m.to_audit_dict()
        assert d["schema_version"] == 1
        assert d["entries"] == []
        json.dumps(d)

    def test_with_entries(self, tmp_path):
        from forge.memory import EpisodicMemory
        m = EpisodicMemory(persist_dir=tmp_path)
        m.record_turn("fix bug", "I'll read the file", [{"name": "read_file"}],
                       ["main.py"], 500)
        d = m.to_audit_dict()
        assert len(d["entries"]) == 1
        assert d["entries"][0]["user_intent"] == "fix bug"
        json.dumps(d)


# ── Billing ──

class TestBillingAuditDict:
    """Verifies BillingMeter.to_audit_dict() structure and usage aggregation.

    Empty meter → schema_version=1, session_tokens=0, 'comparisons' key present.
    After record_turn(1000, 500, cache_hit_tokens=200): session_tokens=1500,
    session_input=1000, session_output=500, and 'Claude Opus (with re-reads)' appears
    in comparisons. All output must be JSON-serializable.
    """

    def test_empty_session(self, tmp_path):
        from forge.billing import BillingMeter
        b = BillingMeter(persist_path=tmp_path / "billing.json")
        d = b.to_audit_dict()
        assert d["schema_version"] == 1
        assert d["session_tokens"] == 0
        assert "comparisons" in d
        json.dumps(d)

    def test_with_usage(self, tmp_path):
        from forge.billing import BillingMeter
        b = BillingMeter(persist_path=tmp_path / "billing.json")
        b.record_turn(1000, 500, cache_hit_tokens=200)
        d = b.to_audit_dict()
        assert d["session_tokens"] == 1500
        assert d["session_input"] == 1000
        assert d["session_output"] == 500
        assert "Claude Opus (with re-reads)" in d["comparisons"]
        json.dumps(d)


# ── Crucible ──

class TestCrucibleAuditDict:
    """Verifies Crucible.to_audit_dict() structure and threat log serialization.

    Empty crucible → schema_version=1, total_scans=0, threat_log=[], canary_leaked=False.
    After one scan of clean code → total_scans=1, threats_found=0.
    Manually added threat → threat_log[0] has level_name='WARNING', category='test',
    and context_before/after are excluded (they're not needed in audit packages).
    All output must be JSON-serializable.
    """

    def test_empty_session(self):
        from forge.crucible import Crucible
        c = Crucible(enabled=True)
        d = c.to_audit_dict()
        assert d["schema_version"] == 1
        assert d["total_scans"] == 0
        assert d["threat_log"] == []
        assert d["canary_leaked"] is False
        json.dumps(d)

    def test_with_scan(self):
        from forge.crucible import Crucible
        c = Crucible(enabled=True)
        c.scan_content("test.py", "def hello(): pass")
        d = c.to_audit_dict()
        assert d["total_scans"] == 1
        assert d["threats_found"] == 0
        json.dumps(d)

    def test_threat_log_serializable(self):
        from forge.crucible import Crucible, Threat
        c = Crucible(enabled=True)
        # Manually add a threat to the log
        c._threat_log.append(Threat(
            level=2, category="test", description="test threat",
            file_path="evil.py", matched_text="bad stuff"))
        c.threats_found = 1
        d = c.to_audit_dict()
        assert len(d["threat_log"]) == 1
        assert d["threat_log"][0]["level_name"] == "WARNING"
        assert d["threat_log"][0]["category"] == "test"
        # context_before/after excluded (not needed in audit)
        assert "context_before" not in d["threat_log"][0]
        json.dumps(d)


# ── Continuity ──

class TestContinuityAuditDict:
    """Verifies ContinuityMonitor.to_audit_dict() defaults and snapshot history.

    Empty monitor → schema_version=1, current_grade='A', current_score=100.0, history=[].
    After appending a ContinuitySnapshot(score=85.0, grade='B'): current_grade='B',
    history contains one entry with score=85.0.
    """

    def test_empty_state(self):
        from forge.continuity import ContinuityMonitor
        c = ContinuityMonitor(enabled=True)
        d = c.to_audit_dict()
        assert d["schema_version"] == 1
        assert d["current_grade"] == "A"
        assert d["current_score"] == 100.0
        assert d["history"] == []
        json.dumps(d)

    def test_with_history(self):
        from forge.continuity import ContinuityMonitor, ContinuitySnapshot
        c = ContinuityMonitor(enabled=True)
        c._history.append(ContinuitySnapshot(
            timestamp=time.time(), score=85.0, grade="B",
            objective_alignment=0.9, file_coverage=0.8,
            decision_retention=0.7, swap_freshness=0.6,
            recall_quality=0.5, working_memory_depth=0.4,
            swaps_total=1))
        c._current = c._history[-1]
        d = c.to_audit_dict()
        assert d["current_grade"] == "B"
        assert len(d["history"]) == 1
        assert d["history"][0]["score"] == 85.0
        json.dumps(d)


# ── PlanVerifier ──

class TestPlanVerifierAuditDict:
    """Verifies PlanVerifier.to_audit_dict() structure and result list.

    mode='off' with no results → schema_version=1, mode='off', results=[].
    With two VerificationResult entries (one passed, one failed) → mode='report',
    results list has 2 entries with correct passed flags.
    """

    def test_empty_state(self):
        from forge.plan_verifier import PlanVerifier
        pv = PlanVerifier(mode="off")
        d = pv.to_audit_dict()
        assert d["schema_version"] == 1
        assert d["mode"] == "off"
        assert d["results"] == []
        json.dumps(d)

    def test_with_results(self):
        from forge.plan_verifier import PlanVerifier, VerificationResult, VerificationCheck
        pv = PlanVerifier(mode="report")
        pv._results.append(VerificationResult(
            step_number=1, passed=True,
            checks=[VerificationCheck(name="tests", passed=True, duration_ms=100)]))
        pv._results.append(VerificationResult(
            step_number=2, passed=False,
            checks=[VerificationCheck(name="tests", passed=False, output="FAILED")],
            error_summary="tests: FAILED"))
        d = pv.to_audit_dict()
        assert d["mode"] == "report"
        assert len(d["results"]) == 2
        assert d["results"][0]["passed"] is True
        assert d["results"][1]["passed"] is False
        json.dumps(d)


# ── Stats ──

class TestStatsAuditDict:
    """Verifies StatsCollector.to_audit_dict() structure and tool analytics.

    Empty collector → schema_version=1, perf_samples=[], tool_analytics.total_calls=0.
    After record_llm_call + 3 tool calls (2x read_file, 1x edit_file):
    perf_samples has 1 entry, total_calls=3, by_tool['read_file']=2.
    """

    def test_empty_state(self, tmp_path):
        from forge.stats import StatsCollector
        s = StatsCollector(persist_dir=tmp_path)
        d = s.to_audit_dict()
        assert d["schema_version"] == 1
        assert d["perf_samples"] == []
        assert d["tool_analytics"]["total_calls"] == 0
        json.dumps(d)

    def test_with_data(self, tmp_path):
        from forge.stats import StatsCollector
        s = StatsCollector(persist_dir=tmp_path)
        s.record_llm_call(1000, 200, 500_000_000, iteration=1, model="test")
        s.record_tool_call("read_file")
        s.record_tool_call("edit_file")
        s.record_tool_call("read_file")
        d = s.to_audit_dict()
        assert len(d["perf_samples"]) == 1
        assert d["tool_analytics"]["total_calls"] == 3
        assert d["tool_analytics"]["by_tool"]["read_file"] == 2
        json.dumps(d)
