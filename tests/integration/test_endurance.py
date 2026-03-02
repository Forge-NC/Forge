"""Scenario 1: Endurance — multi-turn session.

Verifies the engine survives a long-running session without state
corruption, memory leaks, or token accounting drift.

Stub mode: 220 turns (fast, scripted responses)
Live mode: 50 turns (real inference, stochastic output — the real test)
"""

import pytest
from tests.integration.ollama_stub import ScriptedTurn


@pytest.mark.timeout(1800)  # 30min ceiling (live 50 turns can be slow)
class TestEndurance:

    def test_endurance_no_corruption(self, harness, ollama_stub, verifier, is_live, nightly_params):
        """Run many turns and verify state integrity throughout."""
        ollama_stub.set_default_response(ScriptedTurn(
            text="Understood. I have reviewed the code and everything looks correct.",
            eval_count=30,
            prompt_eval_count=50,
        ))

        ctx_tokens = 4000
        if nightly_params and nightly_params.get("ctx_tokens"):
            ctx_tokens = nightly_params["ctx_tokens"]
        engine = harness.create_engine(ctx_max_tokens=ctx_tokens)

        # Live mode: 50 turns (real inference ~5-10s each)
        # Stub mode: 220 turns (scripted, <0.2s each)
        turn_count = 50 if is_live else 220
        if nightly_params and nightly_params.get("turns"):
            turn_count = nightly_params["turns"]
        check_interval = 10 if is_live else 50

        swap_count_checkpoints = []
        for i in range(turn_count):
            user_msg = f"Turn {i}: Please review the function on line {i * 10}."
            result = harness.run_single_turn(user_msg)

            # Check token accounting periodically
            if (i + 1) % check_interval == 0:
                ctx = engine.ctx
                computed = sum(e.token_count for e in ctx._entries)
                assert computed == ctx._total_tokens, (
                    f"Token drift at turn {i+1}: "
                    f"sum={computed} vs tracked={ctx._total_tokens}")
                swap_count_checkpoints.append(harness.get_swap_count())

        # At least 1 context swap should have occurred
        total_swaps = harness.get_swap_count()
        assert total_swaps >= 1, (
            f"Expected at least 1 context swap, got {total_swaps}")

        # Full integrity check
        verifier.check_all()

    def test_token_accounting_never_drifts(
            self, harness, ollama_stub, verifier, is_live, nightly_params):
        """Verify token sum == _total_tokens after every single turn."""
        ollama_stub.set_default_response(ScriptedTurn(
            text="Done. The change has been applied successfully.",
            eval_count=20,
            prompt_eval_count=40,
        ))

        ctx_tokens = 2000
        if nightly_params and nightly_params.get("ctx_tokens"):
            ctx_tokens = nightly_params["ctx_tokens"]
        engine = harness.create_engine(ctx_max_tokens=ctx_tokens)
        turn_count = 25 if is_live else 100
        if nightly_params and nightly_params.get("turns"):
            turn_count = nightly_params["turns"]

        for i in range(turn_count):
            harness.run_single_turn(f"Quick task {i}")
            ctx = engine.ctx
            computed = sum(e.token_count for e in ctx._entries)
            assert computed == ctx._total_tokens, (
                f"Token drift at turn {i}: "
                f"sum={computed} vs tracked={ctx._total_tokens}")

        verifier.check_all()

    def test_billing_accumulates(self, harness, ollama_stub, verifier, is_live, nightly_params):
        """Verify billing tokens increase monotonically."""
        ollama_stub.set_default_response(ScriptedTurn(
            text="Processing complete.",
            eval_count=15,
            prompt_eval_count=30,
        ))

        ctx_tokens = 4000
        if nightly_params and nightly_params.get("ctx_tokens"):
            ctx_tokens = nightly_params["ctx_tokens"]
        engine = harness.create_engine(ctx_max_tokens=ctx_tokens)
        prev_input = 0
        prev_output = 0
        turn_count = 25 if is_live else 100
        if nightly_params and nightly_params.get("turns"):
            turn_count = nightly_params["turns"]

        for i in range(turn_count):
            harness.run_single_turn(f"Do task {i}")
            bill = engine.billing
            # Billing should never decrease
            assert bill.session_input_tokens >= prev_input, (
                f"Input tokens decreased at turn {i}")
            assert bill.session_output_tokens >= prev_output, (
                f"Output tokens decreased at turn {i}")
            prev_input = bill.session_input_tokens
            prev_output = bill.session_output_tokens

        verifier.check_all()
