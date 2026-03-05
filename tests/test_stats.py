"""Tests for stats collector (forge/stats.py)."""
import json
import time
from pathlib import Path

import pytest

from forge.stats import StatsCollector, SessionRecord, PerfSample


@pytest.fixture
def stats(tmp_path):
    stats_dir = tmp_path / "stats"
    stats_dir.mkdir()
    return StatsCollector(persist_dir=stats_dir)


# ── LLM call recording ──

class TestRecordLLMCall:
    def test_records_perf_sample(self, stats):
        stats.record_llm_call(
            prompt_tokens=100, eval_tokens=50,
            duration_ns=1_000_000_000,  # 1 second
            iteration=1, model="qwen3:14b",
        )
        assert len(stats._perf_samples) == 1
        sample = stats._perf_samples[0]
        assert sample.prompt_tokens == 100
        assert sample.eval_tokens == 50
        assert sample.tok_per_sec == pytest.approx(50.0, abs=1.0)

    def test_appends_to_perf_log(self, stats):
        stats.record_llm_call(
            prompt_tokens=50, eval_tokens=25,
            duration_ns=500_000_000, model="test",
        )
        assert stats._perf_file.exists()
        line = stats._perf_file.read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert data["eval_tokens"] == 25

    def test_multiple_calls(self, stats):
        for i in range(10):
            stats.record_llm_call(
                prompt_tokens=100, eval_tokens=50,
                duration_ns=1_000_000_000, model="test",
            )
        assert len(stats._perf_samples) == 10


# ── Tool call recording ──

class TestRecordToolCall:
    def test_increments_count(self, stats):
        stats.record_tool_call("read_file")
        stats.record_tool_call("read_file")
        stats.record_tool_call("write_file")
        assert stats._session_tool_counts["read_file"] == 2
        assert stats._session_tool_counts["write_file"] == 1


# ── Context usage ──

class TestContextUsage:
    def test_peak_tracking(self, stats):
        stats.record_context_usage(50.0)
        stats.record_context_usage(80.0)
        stats.record_context_usage(60.0)
        assert stats._peak_context_pct == 80.0


# ── Session end recording ──

class TestRecordSessionEnd:
    def test_records_session(self, stats):
        stats.record_session_end(
            session_id="abc123", start_time=time.time() - 60,
            turns=10, input_tokens=1000, output_tokens=500,
            cache_saved=200, context_swaps=2, files_touched=5,
            journal_entries=8, model="qwen3:14b",
        )
        assert len(stats._sessions) == 1
        s = stats._sessions[0]
        assert isinstance(s, SessionRecord)
        assert s.turns == 10
        assert s.total_tokens == 1500
        assert s.context_swaps == 2

    def test_persists_to_disk(self, stats, tmp_path):
        stats.record_session_end(
            session_id="sess1", start_time=time.time() - 30,
            turns=5, input_tokens=500, output_tokens=250,
            cache_saved=100, context_swaps=0, files_touched=2,
            journal_entries=4, model="test",
        )
        # Reload from disk
        stats2 = StatsCollector(persist_dir=tmp_path / "stats")
        assert len(stats2._sessions) == 1
        assert stats2._sessions[0].session_id == "sess1"

    def test_multiple_sessions(self, stats):
        for i in range(3):
            stats.record_session_end(
                session_id=f"s{i}", start_time=time.time() - 60,
                turns=i + 1, input_tokens=100, output_tokens=50,
                cache_saved=10, context_swaps=0, files_touched=1,
                journal_entries=1, model="test",
            )
        assert len(stats._sessions) == 3


# ── Performance trends ──

class TestPerformanceTrends:
    def test_no_data(self, stats):
        trends = stats.get_performance_trends()
        assert trends["samples"] == 0

    def test_with_samples(self, stats):
        for i in range(5):
            stats.record_llm_call(
                prompt_tokens=100, eval_tokens=50,
                duration_ns=1_000_000_000, model="test",
            )
        trends = stats.get_performance_trends()
        assert trends["samples"] >= 5
        assert trends["avg_tok_s"] == pytest.approx(50.0, abs=2.0)

    def test_trend_direction(self, stats):
        # Improving: each call faster
        for i in range(10):
            duration = max(100_000_000, 2_000_000_000 - i * 150_000_000)
            stats.record_llm_call(
                prompt_tokens=100, eval_tokens=50,
                duration_ns=duration, model="test",
            )
        trends = stats.get_performance_trends()
        assert trends["trend"] in ("improving", "stable", "degrading")


# ── Tool analytics ──

class TestToolAnalytics:
    def test_empty(self, stats):
        analytics = stats.get_tool_analytics()
        assert analytics["total_calls"] == 0

    def test_with_calls(self, stats):
        stats.record_tool_call("read_file")
        stats.record_tool_call("read_file")
        stats.record_tool_call("write_file")
        analytics = stats.get_tool_analytics()
        assert analytics["total_calls"] == 3
        assert analytics["most_used"] == ("read_file", 2)
        assert analytics["by_tool"]["read_file"] == 2


# ── Context efficiency ──

class TestContextEfficiency:
    def test_no_sessions(self, stats):
        eff = stats.get_context_efficiency()
        assert eff["total_swaps"] == 0

    def test_with_sessions(self, stats):
        stats.record_session_end(
            session_id="s1", start_time=time.time() - 60,
            turns=5, input_tokens=100, output_tokens=50,
            cache_saved=10, context_swaps=3, files_touched=1,
            journal_entries=1, model="test",
        )
        eff = stats.get_context_efficiency()
        assert eff["total_swaps"] == 3
        assert eff["sessions_with_swaps"] == 1


# ── Cost analysis ──

class TestCostAnalysis:
    def test_no_sessions(self, stats):
        cost = stats.get_cost_analysis()
        assert cost["total_tokens"] == 0
        assert cost["total_sessions"] == 0

    def test_with_sessions(self, stats):
        stats.record_session_end(
            session_id="s1", start_time=time.time() - 60,
            turns=5, input_tokens=10000, output_tokens=5000,
            cache_saved=2000, context_swaps=0, files_touched=1,
            journal_entries=1, model="test",
        )
        cost = stats.get_cost_analysis()
        assert cost["total_tokens"] == 15000
        assert cost["total_saved_vs_opus"] > 0
        assert cost["forge_cost"] == 0.0


# ── Dashboard data ──

class TestDashboardData:
    def test_returns_all_sections(self, stats):
        data = stats.get_dashboard_data()
        assert "performance" in data
        assert "tools" in data
        assert "context" in data
        assert "cost" in data


# ── Session history ──

class TestSessionHistory:
    def test_returns_dicts(self, stats):
        stats.record_session_end(
            session_id="s1", start_time=time.time() - 60,
            turns=5, input_tokens=100, output_tokens=50,
            cache_saved=10, context_swaps=0, files_touched=1,
            journal_entries=1, model="test",
        )
        history = stats.get_session_history(count=5)
        assert len(history) == 1
        assert isinstance(history[0], dict)
        assert history[0]["session_id"] == "s1"


# ── Stats display ──

class TestStatsDisplay:
    def test_format_output(self, stats):
        output = stats.format_stats_display()
        assert isinstance(output, str)


# ── Audit dict ──

class TestStatsAuditDict:
    def test_structure(self, stats):
        stats.record_llm_call(
            prompt_tokens=100, eval_tokens=50,
            duration_ns=1_000_000_000, model="test",
        )
        stats.record_tool_call("read_file")
        audit = stats.to_audit_dict()
        assert audit["schema_version"] == 1
        assert "perf_samples" in audit
        assert "tool_analytics" in audit
        assert "context_efficiency" in audit

    def test_perf_samples_capped(self, stats):
        for i in range(100):
            stats.record_llm_call(
                prompt_tokens=100, eval_tokens=50,
                duration_ns=1_000_000_000, model="test",
            )
        audit = stats.to_audit_dict()
        assert len(audit["perf_samples"]) <= 50
