"""Tests for billing token accumulation across multiple turns.

Verifies BillingMeter correctly tracks input tokens, output tokens,
cache hits, and per-turn history through the full recording lifecycle.
"""

import pytest
from forge.billing import BillingMeter


class TestBillingRecordTurn:
    """Verifies BillingMeter.record_turn() accumulates token counts across turns.

    Two turns of (100 input + 50 output) + (200 input + 100 output) must
    produce a session total of 450 tokens with cache_hits=30.  Zero-token
    turns must not corrupt state.  Five turns of (10+5) each must total 75.
    The internal _turns list must grow by exactly one entry per call.
    """

    def test_record_turn_accumulates(self, tmp_path):
        bm = BillingMeter(persist_path=tmp_path / "billing.json")
        bm.record_turn(input_tokens=100, output_tokens=50, cache_hit_tokens=10)
        bm.record_turn(input_tokens=200, output_tokens=100, cache_hit_tokens=20)
        total = bm.session_input_tokens + bm.session_output_tokens
        assert total == 450  # 100+50+200+100
        assert bm.session_cache_hits == 30

    def test_record_turn_zero_tokens(self, tmp_path):
        bm = BillingMeter(persist_path=tmp_path / "billing.json")
        bm.record_turn(input_tokens=0, output_tokens=0, cache_hit_tokens=0)
        assert bm.session_input_tokens == 0
        assert bm.session_output_tokens == 0

    def test_multiple_turns_tracking(self, tmp_path):
        bm = BillingMeter(persist_path=tmp_path / "billing.json")
        for _ in range(5):
            bm.record_turn(input_tokens=10, output_tokens=5, cache_hit_tokens=2)
        total = bm.session_input_tokens + bm.session_output_tokens
        assert total == 75  # 5 * (10 + 5)
        assert bm.session_cache_hits == 10

    def test_turns_list_grows(self, tmp_path):
        bm = BillingMeter(persist_path=tmp_path / "billing.json")
        bm.record_turn(input_tokens=10, output_tokens=5)
        bm.record_turn(input_tokens=20, output_tokens=10)
        assert len(bm._turns) == 2
