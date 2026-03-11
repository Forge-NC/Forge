"""Tests for deepened BPoS genome tracking."""
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from forge.passport import BPoS, GenomeSnapshot, TIERS


@pytest.fixture
def bpos(tmp_path):
    return BPoS(data_dir=tmp_path, machine_id="test123456ab")


def _activate_pro(bpos):
    """Helper: activate pro tier."""
    data = {
        "account_id": "acct_test", "tier": "pro",
        "issued_at": time.time(), "expires_at": 0,
        "activations": [], "max_activations": 3,
    }
    data["signature"] = bpos._sign_passport(data)
    bpos.activate(data)


# ── Quality trend tracking ──

class TestQualityTrend:
    """Verifies BPoS genome quality_trend list is populated and capped correctly.

    update_genome() with quality_trend=[0.8, 0.85, 0.9] → appends one averaged value
    in [0.8, 0.9]. With ami_average_quality=0.75 → appends exactly 0.75.
    After 60 updates → list capped at 50 entries. No quality data → list stays empty.
    """

    def test_trend_appended_from_quality_scores(self, bpos):
        _activate_pro(bpos)
        snapshot = GenomeSnapshot(
            total_turns=10,
            quality_trend=[0.8, 0.85, 0.9],
        )
        bpos.update_genome(snapshot)
        assert len(bpos._genome.quality_trend) == 1
        assert 0.8 <= bpos._genome.quality_trend[0] <= 0.9

    def test_trend_from_ami_average(self, bpos):
        _activate_pro(bpos)
        snapshot = GenomeSnapshot(
            total_turns=5,
            ami_average_quality=0.75,
        )
        bpos.update_genome(snapshot)
        assert len(bpos._genome.quality_trend) == 1
        assert bpos._genome.quality_trend[0] == 0.75

    def test_trend_capped_at_50(self, bpos):
        _activate_pro(bpos)
        for i in range(60):
            snapshot = GenomeSnapshot(
                total_turns=1,
                ami_average_quality=0.5 + i * 0.005,
            )
            bpos.update_genome(snapshot)
        assert len(bpos._genome.quality_trend) == 50

    def test_trend_empty_without_quality(self, bpos):
        _activate_pro(bpos)
        snapshot = GenomeSnapshot(total_turns=3)
        bpos.update_genome(snapshot)
        assert len(bpos._genome.quality_trend) == 0


# ── Per-model quality tracking ──

class TestPerModelQuality:
    """Verifies per-model quality tracking uses EMA smoothing across update calls.

    Single model update populates per_model_quality dict. Multiple distinct models
    accumulate independently. Two updates for same model with values 0.9 then 0.3 →
    EMA result is between 0.3 and 0.9 (smoothed, not replaced).
    """

    def test_single_model(self, bpos):
        _activate_pro(bpos)
        snapshot = GenomeSnapshot(
            total_turns=5,
            per_model_quality={"qwen3:14b": 0.88},
        )
        bpos.update_genome(snapshot)
        assert "qwen3:14b" in bpos._genome.per_model_quality
        assert bpos._genome.per_model_quality["qwen3:14b"] > 0

    def test_multiple_models_accumulated(self, bpos):
        _activate_pro(bpos)
        bpos.update_genome(GenomeSnapshot(
            total_turns=5, per_model_quality={"model_a": 0.9}))
        bpos.update_genome(GenomeSnapshot(
            total_turns=5, per_model_quality={"model_b": 0.7}))
        assert "model_a" in bpos._genome.per_model_quality
        assert "model_b" in bpos._genome.per_model_quality

    def test_ema_smoothing(self, bpos):
        _activate_pro(bpos)
        bpos.update_genome(GenomeSnapshot(
            total_turns=5, per_model_quality={"m": 0.9}))
        bpos.update_genome(GenomeSnapshot(
            total_turns=5, per_model_quality={"m": 0.3}))
        # EMA with alpha=0.3: not just 0.3, should be smoothed
        q = bpos._genome.per_model_quality["m"]
        assert 0.3 < q < 0.9


# ── AMI routing accuracy ──

class TestAMIRoutingAccuracy:
    """Verifies ami_routing_accuracy uses EMA with alpha=0.3.

    First update from 0: 0.3*1.0 + 0.7*0 = 0.3 (approx). Second update toward 0.5:
    smoothed between first and new input (0.3 < result < 0.5).
    """

    def test_routing_accuracy_tracked(self, bpos):
        _activate_pro(bpos)
        bpos.update_genome(GenomeSnapshot(
            total_turns=10, ami_routing_accuracy=0.85))
        assert bpos._genome.ami_routing_accuracy > 0

    def test_routing_accuracy_ema(self, bpos):
        _activate_pro(bpos)
        # First update from genome=0: 0.3*1.0 + 0.7*0 = 0.3
        bpos.update_genome(GenomeSnapshot(
            total_turns=10, ami_routing_accuracy=1.0))
        first = bpos._genome.ami_routing_accuracy
        assert first == pytest.approx(0.3, abs=0.01)
        # Second: 0.3*0.5 + 0.7*0.3 = 0.36 (EMA smooths toward 0.5)
        bpos.update_genome(GenomeSnapshot(
            total_turns=10, ami_routing_accuracy=0.5))
        second = bpos._genome.ami_routing_accuracy
        assert 0.3 < second < 0.5  # Smoothed between first and new input


# ── Threat pattern distribution ──

class TestThreatPatternDistribution:
    """Verifies threat_pattern_distribution accumulates counts across genome updates.

    Single category update → exact count stored. Two updates for same category
    (2 then 3) → total 5. New category in second update → added independently.
    """

    def test_single_category(self, bpos):
        _activate_pro(bpos)
        bpos.update_genome(GenomeSnapshot(
            total_turns=5,
            threat_pattern_distribution={"prompt_injection": 3},
        ))
        assert bpos._genome.threat_pattern_distribution["prompt_injection"] == 3

    def test_accumulates_across_sessions(self, bpos):
        _activate_pro(bpos)
        bpos.update_genome(GenomeSnapshot(
            total_turns=5,
            threat_pattern_distribution={"data_exfil": 2},
        ))
        bpos.update_genome(GenomeSnapshot(
            total_turns=5,
            threat_pattern_distribution={"data_exfil": 3, "prompt_injection": 1},
        ))
        assert bpos._genome.threat_pattern_distribution["data_exfil"] == 5
        assert bpos._genome.threat_pattern_distribution["prompt_injection"] == 1


# ── Models tested tracking ──

class TestModelsTested:
    """Verifies models_tested list is populated and deduplicated across updates.

    Two model names added → both in list. Same model added twice → count remains 1.
    Second update with new model → both original and new model in list.
    """

    def test_models_tracked(self, bpos):
        _activate_pro(bpos)
        bpos.update_genome(GenomeSnapshot(
            total_turns=5, models_tested=["qwen3:14b", "phi3:mini"]))
        assert "qwen3:14b" in bpos._genome.models_tested
        assert "phi3:mini" in bpos._genome.models_tested

    def test_deduplication(self, bpos):
        _activate_pro(bpos)
        bpos.update_genome(GenomeSnapshot(
            total_turns=5, models_tested=["qwen3:14b"]))
        bpos.update_genome(GenomeSnapshot(
            total_turns=5, models_tested=["qwen3:14b", "llama3:8b"]))
        assert bpos._genome.models_tested.count("qwen3:14b") == 1
        assert "llama3:8b" in bpos._genome.models_tested


# ── Tool success rate ──

class TestToolSuccessRate:
    """Verifies tool_success_rate EMA tracking. Two updates (1.0 then 0.5) → second > first (converging up)."""

    def test_tracked(self, bpos):
        _activate_pro(bpos)
        bpos.update_genome(GenomeSnapshot(
            total_turns=10, tool_success_rate=0.95))
        assert bpos._genome.tool_success_rate > 0

    def test_ema(self, bpos):
        _activate_pro(bpos)
        bpos.update_genome(GenomeSnapshot(
            total_turns=10, tool_success_rate=1.0))
        first = bpos._genome.tool_success_rate
        bpos.update_genome(GenomeSnapshot(
            total_turns=10, tool_success_rate=0.5))
        second = bpos._genome.tool_success_rate
        # EMA from 0: 0.3*1.0=0.3, then 0.3*0.5+0.7*0.3=0.36
        assert second > first  # Converging toward higher inputs


# ── Continuity recovery rate ──

class TestContinuityRecoveryRate:
    """Verifies continuity_recovery_rate is tracked and non-zero after an update."""

    def test_tracked(self, bpos):
        _activate_pro(bpos)
        bpos.update_genome(GenomeSnapshot(
            total_turns=10, continuity_recovery_rate=0.8))
        assert bpos._genome.continuity_recovery_rate > 0


# ── Persistence roundtrip with deep fields ──

class TestDeepGenomePersistence:
    """Verifies all deep genome fields survive a BPoS save/load roundtrip.

    After update_genome() with all fields set, a new BPoS from same data_dir restores:
    session_count, quality_trend, per_model_quality, ami_routing_accuracy,
    threat_pattern_distribution, models_tested, and tool_success_rate.
    """

    def test_roundtrip(self, tmp_path):
        bpos1 = BPoS(data_dir=tmp_path, machine_id="m1")
        _activate_pro(bpos1)
        bpos1.update_genome(GenomeSnapshot(
            total_turns=10,
            ami_average_quality=0.85,
            per_model_quality={"qwen3:14b": 0.9},
            ami_routing_accuracy=0.75,
            threat_pattern_distribution={"injection": 5},
            models_tested=["qwen3:14b"],
            quality_trend=[0.8, 0.85, 0.9],
            tool_success_rate=0.95,
        ))

        bpos2 = BPoS(data_dir=tmp_path, machine_id="m1")
        assert bpos2._genome.session_count == 1
        assert len(bpos2._genome.quality_trend) > 0
        assert "qwen3:14b" in bpos2._genome.per_model_quality
        assert bpos2._genome.ami_routing_accuracy > 0
        assert bpos2._genome.threat_pattern_distribution.get("injection", 0) > 0
        assert "qwen3:14b" in bpos2._genome.models_tested
        assert bpos2._genome.tool_success_rate > 0


# ── Collect genome from mock engine ──

class TestCollectGenomeDeep:
    """Verifies collect_genome() correctly extracts all deep fields from a mock engine.

    ami_routing_accuracy = retries_succeeded/retries_triggered (8/10 = 0.8).
    quality_trend extracted from turn_history quality_score values.
    per_model_quality populated from model_capabilities avg_tool_compliance.
    threat_pattern_distribution extracted from threat_intel by_category.
    tool_success_rate and models_tested both populated.
    """

    def test_collects_routing_accuracy(self, bpos):
        engine = MagicMock()
        engine.ami.to_audit_dict.return_value = {
            "failure_catalog": {"a": 1},
            "model_capabilities": {"qwen3:14b": {"avg_tool_compliance": 0.9}},
            "average_quality": 0.88,
            "stats": {"retries_triggered": 10, "retries_succeeded": 8},
            "turn_history": [
                {"quality_score": 0.7}, {"quality_score": 0.9},
            ],
        }
        engine.continuity.to_audit_dict.return_value = {
            "current_score": 85.0,
            "recovery_attempts": 3,
            "history": [
                {"recovery_triggered": True, "score": 50},
                {"recovery_triggered": False, "score": 80},
            ],
        }
        engine.crucible.to_audit_dict.return_value = {
            "total_scans": 100, "threats_found": 3,
        }
        engine.threat_intel.get_detection_stats.return_value = {
            "by_category": {"prompt_injection": 2, "data_exfil": 1},
        }
        engine.reliability.to_audit_dict.return_value = {
            "composite_score": 92.5,
        }
        engine.stats.to_audit_dict.return_value = {
            "session_turns": 15,
            "tool_analytics": {"read_file": 10, "write_file": 5},
        }
        engine.forensics.to_audit_dict.return_value = {
            "error_count": 1,
        }

        snapshot = bpos.collect_genome(engine)
        assert snapshot.ami_routing_accuracy == 0.8
        assert len(snapshot.quality_trend) == 2
        assert "qwen3:14b" in snapshot.per_model_quality
        assert snapshot.threat_pattern_distribution["prompt_injection"] == 2
        assert snapshot.tool_success_rate > 0
        assert "qwen3:14b" in snapshot.models_tested
