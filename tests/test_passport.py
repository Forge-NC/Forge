"""Tests for BPoS (Behavioral Proof of Stake) licensing system."""
import json
import math
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from forge.passport import BPoS, Passport, GenomeSnapshot, BehavioralFingerprint, TIERS


@pytest.fixture
def bpos(tmp_path):
    return BPoS(data_dir=tmp_path, machine_id="test123456ab")


# ── Tier system ──

class TestTierSystem:
    """Verifies the three BPoS tiers (community/pro/power) have correct feature gates.

    Default tier is 'community'. Community: label='Community', genome_persistence=False,
    seats=1, auto_commit=False, shipwright=False. All three tiers must be in TIERS dict.
    Pro: genome_persistence=True, seats=3, auto_commit=True, shipwright=True.
    Power: enterprise_mode=True, fleet_analytics=True, seats=10.
    Community allows benchmark_suite but not genome_persistence or enterprise_mode.
    Community is always considered activated (no license required).
    """

    def test_default_tier_is_community(self, bpos):
        assert bpos.tier == "community"

    def test_community_tier_config(self, bpos):
        cfg = bpos.tier_config
        assert cfg["label"] == "Community"
        assert cfg["genome_persistence"] is False
        assert cfg["seats"] == 1
        assert cfg["auto_commit"] is False
        assert cfg["shipwright"] is False

    def test_all_tiers_defined(self):
        assert "community" in TIERS
        assert "pro" in TIERS
        assert "power" in TIERS

    def test_pro_tier_features(self):
        cfg = TIERS["pro"]
        assert cfg["genome_persistence"] is True
        assert cfg["seats"] == 3
        assert cfg["auto_commit"] is True
        assert cfg["shipwright"] is True

    def test_power_tier_features(self):
        cfg = TIERS["power"]
        assert cfg["enterprise_mode"] is True
        assert cfg["fleet_analytics"] is True
        assert cfg["seats"] == 10

    def test_feature_check_community(self, bpos):
        assert bpos.is_feature_allowed("benchmark_suite") is True
        assert bpos.is_feature_allowed("genome_persistence") is False
        assert bpos.is_feature_allowed("enterprise_mode") is False

    def test_is_activated_community(self, bpos):
        assert bpos.is_activated() is True  # Community always active


# ── Passport management ──

class TestPassportManagement:
    """Verifies passport activation, signature verification, seat limits, and deactivation.

    A valid signed passport activates successfully, upgrades tier to 'pro', and adds
    the machine_id to passport.activations. Invalid signature ('not_a_valid_ed25519_signature')
    fails with 'signature' in the message. A passport with max_activations=1 and already 1
    activation fails with 'limit' in the message. deactivate() removes the machine_id
    from activations. deactivate() with no active passport returns ok=False.
    """

    def _make_passport_data(self, bpos, tier="pro"):
        data = {
            "account_id": "acct_test_12345678",
            "tier": tier,
            "issued_at": time.time(),
            "expires_at": 0,  # Never expires
            "activations": [],
            "max_activations": 3,
        }
        data["signature"] = bpos._sign_passport(data)
        return data

    def test_activate_valid_passport(self, bpos):
        data = self._make_passport_data(bpos)
        ok, msg = bpos.activate(data)
        assert ok is True
        assert bpos.tier == "pro"
        assert bpos.is_activated()

    def test_activate_adds_machine(self, bpos):
        data = self._make_passport_data(bpos)
        bpos.activate(data)
        assert "test123456ab" in bpos._passport.activations

    def test_activate_invalid_signature(self, bpos):
        data = self._make_passport_data(bpos)
        data["origin_signature"] = "not_a_valid_ed25519_signature"
        ok, msg = bpos.activate(data)
        assert ok is False
        assert "signature" in msg.lower()

    def test_activation_limit(self, bpos):
        data = self._make_passport_data(bpos)
        data["max_activations"] = 1
        data["activations"] = ["other_machine"]
        data["signature"] = bpos._sign_passport(data)
        ok, msg = bpos.activate(data)
        assert ok is False
        assert "limit" in msg.lower()

    def test_deactivate(self, bpos):
        data = self._make_passport_data(bpos)
        bpos.activate(data)
        ok, msg = bpos.deactivate()
        assert ok is True
        assert "test123456ab" not in bpos._passport.activations

    def test_deactivate_no_passport(self, bpos):
        ok, msg = bpos.deactivate()
        assert ok is False


# ── Genome ──

class TestGenome:
    """Verifies the genome (persistent behavioral identity) tracks sessions and matures over time.

    Fresh genome: session_count==0, ami_failure_catalog_size==0.
    get_genome_maturity(): 0 sessions → < 0.2, 50 sessions → 0.4–0.6, 200 sessions → > 0.9.
    update_genome() with pro tier increments session_count and stores catalog size.
    Community tier does NOT persist genome (session_count stays 0 after update).
    collect_genome() reads from engine's subsystem audit dicts to build a GenomeSnapshot.
    """

    def test_initial_genome_empty(self, bpos):
        assert bpos._genome.session_count == 0
        assert bpos._genome.ami_failure_catalog_size == 0

    def test_genome_maturity_fresh(self, bpos):
        maturity = bpos.get_genome_maturity()
        assert maturity < 0.2  # Fresh install = low maturity

    def test_genome_maturity_mature(self, bpos):
        bpos._genome.session_count = 200
        maturity = bpos.get_genome_maturity()
        assert maturity > 0.9  # 200 sessions = high maturity

    def test_genome_maturity_midpoint(self, bpos):
        bpos._genome.session_count = 50
        maturity = bpos.get_genome_maturity()
        assert 0.4 < maturity < 0.6  # ~50% at 50 sessions

    def test_update_genome_increments_sessions(self, bpos, tmp_path):
        # Activate pro tier to allow genome persistence
        data = {
            "account_id": "acct_test", "tier": "pro",
            "issued_at": time.time(), "expires_at": 0,
            "activations": [], "max_activations": 3,
        }
        data["signature"] = bpos._sign_passport(data)
        bpos.activate(data)

        snapshot = GenomeSnapshot(
            total_turns=10, ami_failure_catalog_size=5,
            ami_model_profiles=2, ami_average_quality=0.85,
        )
        bpos.update_genome(snapshot)
        assert bpos._genome.session_count == 1
        assert bpos._genome.ami_failure_catalog_size == 5

    def test_community_genome_does_not_persist(self, bpos):
        snapshot = GenomeSnapshot(total_turns=10)
        bpos.update_genome(snapshot)
        assert bpos._genome.session_count == 0  # Community = no persistence

    def test_collect_genome_from_mock_engine(self, bpos):
        engine = MagicMock()
        engine.ami.to_audit_dict.return_value = {
            "failure_catalog": {"a": 1, "b": 2},
            "model_capabilities": {"model1": {}},
            "average_quality": 0.88,
        }
        engine.continuity.to_audit_dict.return_value = {"current_score": 85.0}
        engine.crucible.to_audit_dict.return_value = {
            "total_scans": 100, "threats_found": 3,
        }
        engine.reliability.to_audit_dict.return_value = {"composite_score": 92.5}
        engine.stats.to_audit_dict.return_value = {"session_turns": 15}

        snapshot = bpos.collect_genome(engine)
        assert snapshot.ami_failure_catalog_size == 2
        assert snapshot.ami_model_profiles == 1
        assert snapshot.ami_average_quality == 0.88
        assert snapshot.continuity_baseline_grade == 85.0
        assert snapshot.threat_scans_total == 100
        assert snapshot.reliability_score == 92.5


# ── Behavioral fingerprinting ──

class TestBehavioralFingerprint:
    """Verifies behavioral fingerprinting tracks tool/command frequency and computes similarity.

    record_tool_call() increments _fingerprint.tool_frequency[name].
    record_command() increments _fingerprint.command_frequency[name].
    compute_fingerprint_similarity() scores high (> 0.8) when top tools, model, safety level,
    theme, and session duration all match. It scores low (< 0.5) when all differ.
    Empty comparison dict returns 1.0 (no evidence of mismatch = maximum similarity).
    """

    def test_record_tool_calls(self, bpos):
        bpos.record_tool_call("read_file")
        bpos.record_tool_call("read_file")
        bpos.record_tool_call("write_file")
        assert bpos._fingerprint.tool_frequency["read_file"] == 2
        assert bpos._fingerprint.tool_frequency["write_file"] == 1

    def test_record_commands(self, bpos):
        bpos.record_command("/help")
        bpos.record_command("/help")
        bpos.record_command("/model")
        assert bpos._fingerprint.command_frequency["/help"] == 2

    def test_fingerprint_similarity_identical(self, bpos):
        bpos.record_tool_call("read_file")
        bpos._fingerprint.primary_model = "qwen3:14b"
        bpos._fingerprint.typical_safety_level = 1
        bpos._fingerprint.theme_preference = "midnight"
        bpos._fingerprint.avg_session_duration = 300.0

        other = {
            "top_tools": ["read_file"],
            "primary_model": "qwen3:14b",
            "safety_level": 1,
            "theme": "midnight",
            "avg_session_duration": 300.0,
        }
        sim = bpos.compute_fingerprint_similarity(other)
        assert sim > 0.8

    def test_fingerprint_similarity_different(self, bpos):
        bpos.record_tool_call("read_file")
        bpos._fingerprint.primary_model = "qwen3:14b"
        bpos._fingerprint.typical_safety_level = 1
        bpos._fingerprint.theme_preference = "midnight"
        bpos._fingerprint.avg_session_duration = 300.0

        other = {
            "top_tools": ["run_shell", "web_search"],
            "primary_model": "llama3:70b",
            "safety_level": 3,
            "theme": "matrix",
            "avg_session_duration": 3000.0,
        }
        sim = bpos.compute_fingerprint_similarity(other)
        assert sim < 0.5

    def test_fingerprint_similarity_empty(self, bpos):
        assert bpos.compute_fingerprint_similarity({}) == 1.0


# ── Persistence ──

class TestPersistence:
    """Verifies genome and passport data survive process restarts via disk persistence.

    After activating pro and recording a genome snapshot, a new BPoS from the same
    data_dir must reload the same session_count and ami_failure_catalog_size.
    """

    def test_genome_save_load_roundtrip(self, tmp_path):
        bpos1 = BPoS(data_dir=tmp_path, machine_id="machine1")
        # Activate pro tier
        data = {
            "account_id": "acct_1", "tier": "pro",
            "issued_at": time.time(), "expires_at": 0,
            "activations": [], "max_activations": 3,
        }
        data["signature"] = bpos1._sign_passport(data)
        bpos1.activate(data)

        snapshot = GenomeSnapshot(
            total_turns=10, ami_failure_catalog_size=5,
        )
        bpos1.update_genome(snapshot)

        bpos2 = BPoS(data_dir=tmp_path, machine_id="machine1")
        assert bpos2._genome.session_count == 1
        assert bpos2._genome.ami_failure_catalog_size == 5

    def test_passport_save_load_roundtrip(self, tmp_path):
        bpos1 = BPoS(data_dir=tmp_path, machine_id="machine1")
        data = {
            "account_id": "acct_2", "tier": "power",
            "issued_at": time.time(), "expires_at": 0,
            "activations": [], "max_activations": 10,
        }
        data["signature"] = bpos1._sign_passport(data)
        bpos1.activate(data)

        bpos2 = BPoS(data_dir=tmp_path, machine_id="machine1")
        assert bpos2.tier == "power"
        assert bpos2.is_activated()

    def test_genome_encrypted_roundtrip(self, tmp_path):
        """Genome is encrypted when passport has origin_signature."""
        bpos1 = BPoS(data_dir=tmp_path, machine_id="machine1")
        data = {
            "account_id": "acct_enc", "tier": "pro",
            "issued_at": time.time(), "expires_at": 0,
            "activations": [], "max_activations": 3,
            "origin_signature": "server_signed_abc123",
        }
        data["signature"] = bpos1._sign_passport(data)
        bpos1.activate(data)

        snapshot = GenomeSnapshot(
            total_turns=42, ami_failure_catalog_size=7,
            session_count=0,
        )
        bpos1.update_genome(snapshot)

        # Verify genome file is NOT plaintext JSON
        genome_path = tmp_path / "genome.json"
        raw = genome_path.read_bytes()
        try:
            json.loads(raw)
            is_plaintext = True
        except (json.JSONDecodeError, UnicodeDecodeError):
            is_plaintext = False
        assert not is_plaintext, "Genome should be encrypted, not plaintext"

        # Verify same machine + passport can decrypt
        bpos2 = BPoS(data_dir=tmp_path, machine_id="machine1")
        assert bpos2._genome.session_count == 1
        assert bpos2._genome.ami_failure_catalog_size == 7

    def test_genome_wrong_key_cannot_decrypt(self, tmp_path):
        """Forged passport with different origin_signature can't read genome."""
        bpos1 = BPoS(data_dir=tmp_path, machine_id="machine1")
        data = {
            "account_id": "acct_real", "tier": "pro",
            "issued_at": time.time(), "expires_at": 0,
            "activations": [], "max_activations": 3,
            "origin_signature": "real_server_signature",
        }
        data["signature"] = bpos1._sign_passport(data)
        bpos1.activate(data)

        snapshot = GenomeSnapshot(total_turns=100, session_count=0)
        bpos1.update_genome(snapshot)

        # Now forge a passport with different origin_signature
        forged = {
            "account_id": "acct_real", "tier": "power",
            "issued_at": time.time(), "expires_at": 0,
            "activations": ["machine1"], "max_activations": 999,
            "origin_signature": "forged_signature",
        }
        forged["signature"] = bpos1._sign_passport(forged)
        # Write forged passport directly
        (tmp_path / "passport.json").write_text(
            json.dumps(forged), encoding="utf-8")

        bpos2 = BPoS(data_dir=tmp_path, machine_id="machine1")
        # Genome should be empty — can't decrypt with wrong key
        assert bpos2._genome.session_count == 0
        assert bpos2._genome.total_turns == 0


# ── Display ──

class TestDisplay:
    """Verifies format_status() and to_audit_dict() expose tier, genome maturity, and required keys.

    format_status() for community tier must include 'Community' and 'Genome maturity'.
    to_audit_dict() must have schema_version==1, tier=='community', and contain 'genome'
    and 'genome_maturity' keys.
    """

    def test_format_status_community(self, bpos):
        status = bpos.format_status()
        assert "Community" in status
        assert "Genome maturity" in status

    def test_audit_dict(self, bpos):
        audit = bpos.to_audit_dict()
        assert audit["schema_version"] == 1
        assert audit["tier"] == "community"
        assert "genome" in audit
        assert "genome_maturity" in audit
