"""Tests for forge.billing — sandbox billing and cost comparison."""

import pytest
from pathlib import Path
from forge.billing import BillingMeter, DEFAULT_BALANCE, PRICING


class TestAccumulation:
    """Verifies BillingMeter correctly accumulates token counts and decrements the balance.

    Initial state: balance==DEFAULT_BALANCE, all session/lifetime counters at 0.
    Each record_turn() call adds input_tokens and output_tokens to both session and lifetime totals.
    Multiple turns accumulate: 3 turns of (100,50), (200,100), (300,150) give session_input==600.
    Balance decreases after a turn with non-trivial token counts (cost > 0).
    cache_hit_tokens are tracked in session_cache_hits and lifetime_cache_savings.
    After 5 turns, status()['turns'] == 5.
    """

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
    """Verifies topup() adds funds to the balance and records lifetime topup total.

    topup(50.0) adds exactly 50.0 to the current balance and sets lifetime_topups to 50.0.
    topup() with no argument adds DEFAULT_BALANCE, so balance == DEFAULT_BALANCE * 2.
    """

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
    """Verifies get_comparison() produces correct cost comparisons against cloud model pricing.

    The returned dict must have session_input_tokens, session_output_tokens, a 'comparisons'
    dict with 'Claude Opus (with re-reads)' and 'Forge (local)' entries.
    Forge (local) always costs $0.00. Claude Opus costs more than Claude Sonnet for the same
    token counts. 500 cache_hit_tokens must produce savings_from_cache > 0.
    """

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
    """Verifies _compute_cost() uses the correct (tokens * price / 1M) formula without precision loss.

    1 input token at $15/M + 1 output token at $75/M = $0.000090 exactly.
    The result must match (1*15 + 1*75) / 1_000_000 within 1e-12.
    Zero tokens must produce exactly $0.00.
    """

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
    """Verifies lifetime billing stats survive process restarts via JSON persistence.

    After recording 5000 input + 2000 output tokens and topping up $25, a new BillingMeter
    loading the same file must have the same lifetime_input_tokens, lifetime_output_tokens,
    and lifetime_topups. A missing persist_path must use DEFAULT_BALANCE without crashing.
    reset_lifetime() must zero all lifetime counters and restore DEFAULT_BALANCE.
    """

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
    """Verifies status() returns a dict with correct session totals and balance.

    After 1000 input + 500 output tokens in one turn: session_tokens==1500, session_input==1000,
    session_output==500, turns==1, and balance is a float.
    """

    def test_status_format(self):
        bm = BillingMeter()
        bm.record_turn(input_tokens=1000, output_tokens=500)
        s = bm.status()
        assert s["session_tokens"] == 1500
        assert s["session_input"] == 1000
        assert s["session_output"] == 500
        assert s["turns"] == 1
        assert isinstance(s["balance"], float)
