"""Scenario 9: Embedding loss mid-run.

Starts with embeddings enabled, runs 50 turns, then disables the
embedding endpoint and runs 70 more turns. Verifies the engine
degrades gracefully without crashing.
"""

import pytest
from tests.integration.ollama_stub import ScriptedTurn


@pytest.mark.stub_only
@pytest.mark.timeout(90)
class TestEmbeddingLoss:

    def test_embedding_disable_graceful(self, harness, ollama_stub, verifier):
        """Engine survives when embedding endpoint goes 503 mid-session."""
        ollama_stub.set_default_response(ScriptedTurn(
            text="Analysis complete. The code looks good.",
            eval_count=25,
            prompt_eval_count=40,
        ))

        engine = harness.create_engine(ctx_max_tokens=4000)

        # Phase 1: 50 turns with embeddings enabled
        assert ollama_stub.embed_enabled is True
        for i in range(50):
            result = harness.run_single_turn(f"Analyze module {i}")

        # Phase 2: Disable embeddings (simulate model unload/crash)
        ollama_stub.embed_enabled = False

        # 70 more turns — should degrade gracefully
        for i in range(70):
            result = harness.run_single_turn(f"Continue analysis {50 + i}")

        # Engine should still be functional
        assert engine.ctx.entry_count > 0
        assert engine.ctx.total_tokens > 0

        # Token accounting intact
        computed = sum(e.token_count for e in engine.ctx._entries)
        assert computed == engine.ctx._total_tokens

        verifier.check_all()

    def test_continuity_survives_embedding_loss(
            self, harness, ollama_stub, verifier):
        """Continuity scoring should work even without embeddings."""
        ollama_stub.set_default_response(ScriptedTurn(
            text="Processed.",
            eval_count=15,
            prompt_eval_count=25,
        ))

        engine = harness.create_engine(ctx_max_tokens=2000)

        # Start with embeddings
        for i in range(20):
            harness.run_single_turn(f"Task {i}")

        # Disable embeddings
        ollama_stub.embed_enabled = False

        # Continue — continuity should still score
        for i in range(30):
            harness.run_single_turn(f"Task {20 + i}")
            if engine.continuity.enabled:
                task_state = engine.memory.get_task_state()
                snapshot = engine.continuity.score(
                    engine.ctx._entries, task_state)
                assert 0 <= snapshot.score <= 100, (
                    f"Score out of range at turn {20+i}: {snapshot.score}")

        verifier.check_all()

    def test_embedding_re_enable(self, harness, ollama_stub, verifier):
        """Engine should recover when embeddings come back online."""
        ollama_stub.set_default_response(ScriptedTurn(
            text="OK.",
            eval_count=10,
            prompt_eval_count=20,
        ))

        engine = harness.create_engine(ctx_max_tokens=4000)

        # Phase 1: working
        for i in range(10):
            harness.run_single_turn(f"Phase 1 turn {i}")

        # Phase 2: broken
        ollama_stub.embed_enabled = False
        for i in range(10):
            harness.run_single_turn(f"Phase 2 turn {i}")

        # Phase 3: restored
        ollama_stub.embed_enabled = True
        for i in range(10):
            harness.run_single_turn(f"Phase 3 turn {i}")

        # Engine should be healthy
        verifier.check_all()
