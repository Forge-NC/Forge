"""Tests for forge.billing — sandbox billing and cost comparison."""

import pytest
from pathlib import Path
from forge.billing import BillingMeter, DEFAULT_BALANCE, PRICING


class TestAccumulation:
    def test_initial_state(self):
        bm = BillingMeter()
        assert bm.balance == DEFAULT_BALANCE
        assert bm.session_input_tokens == 0
        assert bm.session_output_tokens == 0

    def test_record_turn_updates_counters(self):
        bm = BillingMeter()
        bm.record_turn(input_tokens=1000, output_tokens=500)
        assert bm.session_input_tokens == 1000
        assert bm.session_output_tokens == 500
        assert bm.lifetime_input_tokens == 1000
        assert bm.lifetime_output_tokens == 500

    def test_multiple_turns_accumulate(self):
        bm = BillingMeter()
        bm.record_turn(input_tokens=100, output_tokens=50)
        bm.record_turn(input_tokens=200, output_tokens=100)
        bm.record_turn(input_tokens=300, output_tokens=150)
        assert bm.session_input_tokens == 600
        assert bm.session_output_tokens == 300

    def test_balance_decreases(self):
        bm = BillingMeter()
        initial = bm.balance
        bm.record_turn(input_tokens=10000, output_tokens=5000)
        assert bm.balance < initial

    def test_cache_hits_tracked(self):
        bm = BillingMeter()
        bm.record_turn(input_tokens=1000, output_tokens=500,
                        cache_hit_tokens=300)
        assert bm.session_cache_hits == 300
        assert bm.lifetime_cache_savings == 300

    def test_turns_counted(self):
        bm = BillingMeter()
        for _ in range(5):
            bm.record_turn(input_tokens=100, output_tokens=50)
        status = bm.status()
        assert status["turns"] == 5


class TestTopup:
    def test_topup_increases_balance(self):
        bm = BillingMeter()
        bm.record_turn(input_tokens=1000000, output_tokens=500000)
        low_balance = bm.balance
        bm.topup(50.0)
        assert bm.balance == low_balance + 50.0
        assert bm.lifetime_topups == 50.0

    def test_default_topup_amount(self):
        bm = BillingMeter()
        bm.topup()
        assert bm.balance == DEFAULT_BALANCE * 2


class TestComparison:
    def test_comparison_keys(self):
        bm = BillingMeter()
        bm.record_turn(input_tokens=1000, output_tokens=500)
        comp = bm.get_comparison()
        assert "session_input_tokens" in comp
        assert "session_output_tokens" in comp
        assert "comparisons" in comp
        assert "Claude Opus (with re-reads)" in comp["comparisons"]
        assert "Forge (local)" in comp["comparisons"]

    def test_forge_always_free(self):
        bm = BillingMeter()
        bm.record_turn(input_tokens=100000, output_tokens=50000)
        comp = bm.get_comparison()
        assert comp["comparisons"]["Forge (local)"]["cost"] == 0.0

    def test_opus_more_expensive_than_sonnet(self):
        bm = BillingMeter()
        bm.record_turn(input_tokens=10000, output_tokens=5000)
        comp = bm.get_comparison()
        opus = comp["comparisons"]["Claude Opus (with re-reads)"]["cost"]
        sonnet = comp["comparisons"]["Claude Sonnet (with re-reads)"]["cost"]
        assert opus > sonnet

    def test_cache_savings_positive(self):
        bm = BillingMeter()
        bm.record_turn(input_tokens=1000, output_tokens=500,
                        cache_hit_tokens=500)
        comp = bm.get_comparison()
        assert comp["savings_from_cache"] > 0


class TestFloatPrecision:
    def test_small_token_counts_precise(self):
        """Verify float precision fix — tokens * price / 1M order."""
        bm = BillingMeter()
        cost = bm._compute_cost(1, 1, "claude_opus_input",
                                 "claude_opus_output")
        # 1 token * 15/M + 1 token * 75/M = 0.000090
        expected = (1 * 15.0 + 1 * 75.0) / 1_000_000
        assert abs(cost - expected) < 1e-12

    def test_zero_tokens_zero_cost(self):
        cost = BillingMeter._compute_cost(0, 0, "claude_opus_input",
                                           "claude_opus_output")
        assert cost == 0.0


class TestPersistence:
    def test_save_and_load(self, tmp_path):
        path = tmp_path / "billing.json"
        bm1 = BillingMeter(persist_path=path)
        bm1.record_turn(input_tokens=5000, output_tokens=2000)
        bm1.topup(25.0)

        bm2 = BillingMeter(persist_path=path)
        assert bm2.lifetime_input_tokens == 5000
        assert bm2.lifetime_output_tokens == 2000
        assert bm2.lifetime_topups == 25.0

    def test_missing_file_uses_defaults(self, tmp_path):
        path = tmp_path / "nonexistent.json"
        bm = BillingMeter(persist_path=path)
        assert bm.balance == DEFAULT_BALANCE

    def test_reset_lifetime(self):
        bm = BillingMeter()
        bm.record_turn(input_tokens=5000, output_tokens=2000)
        bm.reset_lifetime()
        assert bm.lifetime_input_tokens == 0
        assert bm.lifetime_output_tokens == 0
        assert bm.balance == DEFAULT_BALANCE


class TestStatus:
    def test_status_format(self):
        bm = BillingMeter()
        bm.record_turn(input_tokens=1000, output_tokens=500)
        s = bm.status()
        assert s["session_tokens"] == 1500
        assert s["session_input"] == 1000
        assert s["session_output"] == 500
        assert s["turns"] == 1
        assert isinstance(s["balance"], float)
