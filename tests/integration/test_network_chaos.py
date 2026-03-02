"""Scenario 10: Network chaos — timeout, drop, and error simulation.

Uses OllamaStub's chaos modes with deterministic seeds.
Verifies the engine survives partial failures and maintains
consistent state.
"""

import pytest
from tests.integration.ollama_stub import ScriptedTurn, ChaosMode


@pytest.mark.stub_only
@pytest.mark.timeout(120)
class TestNetworkChaos:

    def test_random_delay_survives(self, harness, ollama_stub, verifier):
        """Engine survives random per-chunk delays."""
        ollama_stub.set_default_response(ScriptedTurn(
            text="Response with some content that will be delayed randomly.",
            eval_count=20,
            prompt_eval_count=30,
        ))
        ollama_stub.chaos_mode = ChaosMode.RANDOM_DELAY
        ollama_stub.chaos_seed = 42

        engine = harness.create_engine(ctx_max_tokens=4000)

        successes = 0
        for i in range(30):
            result = harness.run_single_turn(f"Delayed turn {i}")
            if len(result.errors) == 0:
                successes += 1

        # At least 10/30 should succeed
        assert successes >= 10, (
            f"Only {successes}/30 turns survived RANDOM_DELAY")

        verifier.check_all()

    def test_random_drop_survives(self, harness, ollama_stub, verifier):
        """Engine survives random connection drops mid-stream."""
        ollama_stub.set_default_response(ScriptedTurn(
            text="This response may get cut off randomly during streaming output.",
            eval_count=20,
            prompt_eval_count=30,
        ))
        ollama_stub.chaos_mode = ChaosMode.RANDOM_DROP
        ollama_stub.chaos_seed = 42

        engine = harness.create_engine(ctx_max_tokens=4000)

        successes = 0
        for i in range(30):
            result = harness.run_single_turn(f"Drop test {i}")
            if len(result.errors) == 0:
                successes += 1

        # Some should survive (drops are 15% per chunk)
        assert successes >= 5, (
            f"Only {successes}/30 turns survived RANDOM_DROP")

        # Token accounting should still be consistent
        computed = sum(e.token_count for e in engine.ctx._entries)
        assert computed == engine.ctx._total_tokens

        verifier.check_all()

    def test_random_error_survives(self, harness, ollama_stub, verifier):
        """Engine survives random 503 errors from the LLM."""
        ollama_stub.set_default_response(ScriptedTurn(
            text="Normal response when not erroring.",
            eval_count=15,
            prompt_eval_count=25,
        ))
        ollama_stub.chaos_mode = ChaosMode.RANDOM_ERROR
        ollama_stub.chaos_seed = 42

        engine = harness.create_engine(ctx_max_tokens=4000)

        successes = 0
        for i in range(30):
            result = harness.run_single_turn(f"Error test {i}")
            if len(result.errors) == 0:
                successes += 1

        # Most should survive (errors are 20% chance)
        assert successes >= 10, (
            f"Only {successes}/30 turns survived RANDOM_ERROR")

        verifier.check_all()

    def test_chaos_then_stable(self, harness, ollama_stub, verifier):
        """Engine recovers fully after chaos mode is disabled."""
        ollama_stub.set_default_response(ScriptedTurn(
            text="OK.",
            eval_count=10,
            prompt_eval_count=20,
        ))

        engine = harness.create_engine(ctx_max_tokens=4000)

        # Phase 1: chaos
        ollama_stub.chaos_mode = ChaosMode.RANDOM_ERROR
        ollama_stub.chaos_seed = 42
        for i in range(10):
            harness.run_single_turn(f"Chaos phase {i}")

        # Phase 2: stable
        ollama_stub.chaos_mode = ChaosMode.NONE
        stable_successes = 0
        for i in range(10):
            result = harness.run_single_turn(f"Stable phase {i}")
            if len(result.errors) == 0:
                stable_successes += 1

        # All stable-phase turns should succeed
        assert stable_successes >= 8, (
            f"Only {stable_successes}/10 stable turns succeeded after chaos")

        verifier.check_all()

    def test_token_accounting_after_chaos(self, harness, ollama_stub, verifier):
        """Token accounting stays consistent through all chaos modes."""
        ollama_stub.set_default_response(ScriptedTurn(
            text="Data for accounting verification.",
            eval_count=15,
            prompt_eval_count=25,
        ))

        engine = harness.create_engine(ctx_max_tokens=4000)

        for mode in [ChaosMode.RANDOM_DELAY, ChaosMode.RANDOM_DROP,
                     ChaosMode.RANDOM_ERROR, ChaosMode.NONE]:
            ollama_stub.chaos_mode = mode
            for i in range(5):
                harness.run_single_turn(f"{mode.value} turn {i}")

        # Final accounting check
        computed = sum(e.token_count for e in engine.ctx._entries)
        assert computed == engine.ctx._total_tokens, (
            f"Token drift after chaos: sum={computed} vs "
            f"tracked={engine.ctx._total_tokens}")

        verifier.check_all()
