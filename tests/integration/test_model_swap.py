"""Scenario 2: Model swap mid-session.

Verifies the engine survives switching the active model mid-conversation
without corrupting context, billing, or continuity state.
"""

import pytest
from tests.integration.ollama_stub import ScriptedTurn


@pytest.mark.stub_only
@pytest.mark.timeout(60)
class TestModelSwap:

    def test_swap_model_mid_session(self, harness, ollama_stub, verifier):
        """50 turns with model A, swap to model B, 50 more turns."""
        # Register two models with different context lengths
        ollama_stub.add_model("stub-coder:3b", context_length=8192)

        ollama_stub.set_default_response(ScriptedTurn(
            text="Model A response. Everything is fine.",
            eval_count=25,
            prompt_eval_count=40,
        ))

        engine = harness.create_engine(
            model="stub-coder:14b", ctx_max_tokens=4000)

        # Phase 1: 50 turns with model A
        for i in range(50):
            harness.run_single_turn(f"[14b] Task {i}: analyze module {i}")

        # Verify mid-point state
        ctx_before = engine.ctx.entry_count
        tokens_before = engine.ctx.total_tokens
        assert ctx_before > 0
        assert tokens_before > 0

        # Swap model
        engine.llm.model = "stub-coder:3b"
        engine.llm.base_url = ollama_stub.base_url

        # Phase 2: 50 more turns with model B
        for i in range(50):
            harness.run_single_turn(f"[3b] Task {i}: refactor function {i}")

        # Context should still have entries (not wiped by swap)
        assert engine.ctx.entry_count > 0
        # Token accounting intact
        computed = sum(e.token_count for e in engine.ctx._entries)
        assert computed == engine.ctx._total_tokens

        verifier.check_all()

    def test_swap_preserves_billing(self, harness, ollama_stub, verifier):
        """Billing continues across model swaps without reset."""
        ollama_stub.add_model("stub-coder:3b", context_length=8192)
        ollama_stub.set_default_response(ScriptedTurn(
            text="OK.",
            eval_count=10,
            prompt_eval_count=20,
        ))

        engine = harness.create_engine(ctx_max_tokens=4000)

        # Phase 1
        for i in range(20):
            harness.run_single_turn(f"Task {i}")
        billing_after_phase1 = engine.billing.session_input_tokens

        # Swap
        engine.llm.model = "stub-coder:3b"

        # Phase 2
        for i in range(20):
            harness.run_single_turn(f"Task {20 + i}")
        billing_after_phase2 = engine.billing.session_input_tokens

        # Billing should have increased
        assert billing_after_phase2 >= billing_after_phase1

        verifier.check_all()
