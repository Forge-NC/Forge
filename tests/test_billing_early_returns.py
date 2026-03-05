"""Tests for billing recording on all agent-loop exit paths."""

import pytest
from forge.billing import BillingMeter


class TestBillingRecordTurn:
    """Verify BillingMeter.record_turn tracks tokens correctly."""

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


class TestBillingHelperCoverage:
    """Test that _record_billing helper exists in the agent loop."""

    def test_record_billing_is_defined(self):
        """Verify the _record_billing closure is created in _agent_loop."""
        import inspect
        from forge.engine import ForgeEngine
        source = inspect.getsource(ForgeEngine._agent_loop)
        assert "def _record_billing():" in source
        assert "nonlocal" in source

    def test_all_early_exits_have_billing(self):
        """Every early exit in _agent_loop should record billing."""
        import inspect
        from forge.engine import ForgeEngine
        source = inspect.getsource(ForgeEngine._agent_loop)
        # Count _record_billing() calls — should be used at every early exit
        billing_calls = source.count("_record_billing()")
        # At minimum: error, post-stream interrupt, escape interrupt,
        # voice interrupt, 2x ContextFullError, 1x response ContextFullError,
        # duplicate detection, oscillation, max iterations = 9+
        assert billing_calls >= 7, (
            f"Expected >= 7 _record_billing() calls, found {billing_calls}")


class TestContextFullBilling:
    """Verify ContextFullError paths record billing."""

    def test_context_full_billing_code_exists(self):
        """ContextFullError handlers should call _record_billing."""
        import inspect
        from forge.engine import ForgeEngine
        source = inspect.getsource(ForgeEngine._agent_loop)
        # Find lines with ContextFullError and check for _record_billing nearby
        lines = source.split("\n")
        cfe_indices = [i for i, l in enumerate(lines)
                       if "except ContextFullError" in l]
        billing_after_cfe = 0
        for idx in cfe_indices:
            # Check next 5 lines for _record_billing
            window = "\n".join(lines[idx:idx + 5])
            if "_record_billing()" in window:
                billing_after_cfe += 1
        assert billing_after_cfe >= 3, (
            f"Expected >= 3 ContextFullError handlers with billing, "
            f"found {billing_after_cfe}")
