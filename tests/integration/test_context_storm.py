"""Scenario 3: Context swap storm — rapid swaps.

Forces many context swaps in quick succession with a small context window
and long responses. Verifies swap summaries are capped and continuity
grade remains valid throughout.

Stub mode: 60 turns (fast, scripted long responses)
Live mode: 20 turns (real inference, smaller context forces fast swaps)
"""

import pytest
from tests.integration.ollama_stub import ScriptedTurn


@pytest.mark.timeout(600)  # 10min ceiling for live mode
class TestContextStorm:

    def test_rapid_swaps_capped(self, harness, ollama_stub, verifier, is_live, nightly_params):
        """Turns with small context and long responses force many swaps."""
        long_text = " ".join(["word"] * 200)
        ollama_stub.set_default_response(ScriptedTurn(
            text=long_text,
            eval_count=200,
            prompt_eval_count=300,
        ))

        ctx_tokens = 1200
        if nightly_params and nightly_params.get("ctx_tokens"):
            ctx_tokens = nightly_params["ctx_tokens"]
        engine = harness.create_engine(ctx_max_tokens=ctx_tokens)
        turn_count = 20 if is_live else 60
        if nightly_params and nightly_params.get("turns"):
            turn_count = nightly_params["turns"]

        for i in range(turn_count):
            harness.run_single_turn(
                f"Please write a detailed analysis of module {i}.")

        # Swap summaries should be capped
        swap_summaries = [e for e in engine.ctx._entries
                          if e.tag == "swap_summary"]
        assert len(swap_summaries) <= engine.ctx._max_swap_summaries, (
            f"Swap summaries {len(swap_summaries)} exceeds cap "
            f"{engine.ctx._max_swap_summaries}")

        # At least some swaps should have occurred
        assert len(swap_summaries) >= 1, (
            f"Expected at least 1 swap summary, got {len(swap_summaries)}. "
            f"Context: {engine.ctx.total_tokens}/{engine.ctx.max_tokens} "
            f"({engine.ctx.usage_pct:.1f}%)")

        verifier.check_all()

    def test_continuity_grade_stays_valid(
            self, harness, ollama_stub, verifier, is_live, nightly_params):
        """Grade should be a valid letter (A-F) throughout heavy swapping."""
        long_text = " ".join(["analysis"] * 150)
        ollama_stub.set_default_response(ScriptedTurn(
            text=long_text,
            eval_count=150,
            prompt_eval_count=200,
        ))

        ctx_tokens = 1200
        if nightly_params and nightly_params.get("ctx_tokens"):
            ctx_tokens = nightly_params["ctx_tokens"]
        engine = harness.create_engine(ctx_max_tokens=ctx_tokens)
        from forge.continuity import score_to_grade

        turn_count = 15 if is_live else 40
        if nightly_params and nightly_params.get("turns"):
            turn_count = nightly_params["turns"]

        for i in range(turn_count):
            harness.run_single_turn(f"Analyze component {i} in detail.")

            # Check continuity grade
            if engine.continuity.enabled:
                task_state = engine.memory.get_task_state()
                snapshot = engine.continuity.score(
                    engine.ctx._entries, task_state)
                grade = score_to_grade(snapshot.score)
                assert grade in ("A", "B", "C", "D", "F"), (
                    f"Invalid grade '{grade}' at turn {i}")
                assert 0 <= snapshot.score <= 100, (
                    f"Score out of range: {snapshot.score}")

        verifier.check_all()

    def test_eviction_log_capped(self, harness, ollama_stub, verifier, is_live, nightly_params):
        """Eviction log should not grow unbounded under heavy swapping."""
        long_text = " ".join(["detailed"] * 180)
        ollama_stub.set_default_response(ScriptedTurn(
            text=long_text,
            eval_count=180,
            prompt_eval_count=250,
        ))

        ctx_tokens = 1200
        if nightly_params and nightly_params.get("ctx_tokens"):
            ctx_tokens = nightly_params["ctx_tokens"]
        engine = harness.create_engine(ctx_max_tokens=ctx_tokens)
        turn_count = 15 if is_live else 50
        if nightly_params and nightly_params.get("turns"):
            turn_count = nightly_params["turns"]

        for i in range(turn_count):
            harness.run_single_turn(f"Write report section {i}.")

        # Eviction log must be capped
        assert len(engine.ctx._eviction_log) <= engine.ctx._max_eviction_log, (
            f"Eviction log {len(engine.ctx._eviction_log)} "
            f"exceeds cap {engine.ctx._max_eviction_log}")

        verifier.check_all()
