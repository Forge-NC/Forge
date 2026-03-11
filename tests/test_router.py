"""Tests for forge.router — ModelRouter multi-model routing."""

import pytest
from forge.router import ModelRouter, estimate_complexity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BIG = "qwen2.5-coder:14b"
SMALL = "qwen2.5-coder:7b"


def _router(enabled=True):
    return ModelRouter(big_model=BIG, small_model=SMALL, enabled=enabled)


# ---------------------------------------------------------------------------
# test_simple_input_routes_small
# ---------------------------------------------------------------------------

class TestSimpleInputRoutesSmall:
    """Verifies the router correctly sends simple, low-complexity inputs to the small model.

    Short acknowledgments ('yes', 'ok', 'thanks'), single-file typo fixes, 'what does X do'
    questions, format/comment requests all route to SMALL. estimate_complexity('done') → level='simple'
    with score < 0 (negative score = small model territory).
    """

    def test_yes(self):
        r = _router()
        model = r.route("yes")
        assert model == SMALL

    def test_ok(self):
        r = _router()
        model = r.route("ok")
        assert model == SMALL

    def test_thanks(self):
        r = _router()
        model = r.route("thanks")
        assert model == SMALL

    def test_fix_typo(self):
        r = _router()
        model = r.route("fix the typo in main.py")
        assert model == SMALL

    def test_what_does(self):
        r = _router()
        model = r.route("what does this function do")
        assert model == SMALL

    def test_format_code(self):
        r = _router()
        model = r.route("format this code")
        assert model == SMALL

    def test_add_comment(self):
        r = _router()
        model = r.route("add a comment above this function")
        assert model == SMALL

    def test_short_input_bias(self):
        """Very short inputs should lean toward small model."""
        est = estimate_complexity("done")
        assert est["level"] == "simple"
        assert est["score"] < 0


# ---------------------------------------------------------------------------
# test_complex_input_routes_big
# ---------------------------------------------------------------------------

class TestComplexInputRoutesBig:
    """Verifies the router sends complex, high-reasoning inputs to the big model.

    Refactoring requests, multi-file edits, 'think hard'/'investigate' language, inputs
    with 250+ words, multiple question marks in one request, optimize/debug/multi-step tasks
    all route to BIG.
    """

    def test_refactor(self):
        r = _router()
        model = r.route("refactor the authentication module to use JWT")
        assert model == BIG

    def test_multi_file(self):
        r = _router()
        model = r.route(
            "update main.py, config.py, and utils.py to use the new API. "
            "Also add tests in test_main.py")
        assert model == BIG

    def test_think_hard(self):
        r = _router()
        model = r.route("think hard about the best architecture for this system")
        assert model == BIG

    def test_long_input(self):
        r = _router()
        long_text = " ".join(["word"] * 250)
        model = r.route(long_text)
        assert model == BIG

    def test_multiple_questions(self):
        r = _router()
        model = r.route(
            "What is the best pattern? How should I structure it? "
            "What are the trade-offs? Should I use async?")
        assert model == BIG

    def test_optimize(self):
        r = _router()
        model = r.route("optimize the database query performance")
        assert model == BIG

    def test_debug_investigate(self):
        r = _router()
        model = r.route("investigate and debug the root cause of the crash")
        assert model == BIG

    def test_multi_step(self):
        r = _router()
        model = r.route("implement a multi-step migration pipeline")
        assert model == BIG


# ---------------------------------------------------------------------------
# test_disabled_always_big
# ---------------------------------------------------------------------------

class TestDisabledAlwaysBig:
    """Verifies disabled router always returns BIG model and records no routing stats.

    enabled=False routes every input to BIG regardless of complexity.
    big_routes and small_routes both stay 0 (routing stats not recorded when disabled).
    """

    def test_disabled_routes_big(self):
        r = _router(enabled=False)
        model = r.route("yes")
        assert model == BIG

    def test_disabled_complex_still_big(self):
        r = _router(enabled=False)
        model = r.route("refactor everything")
        assert model == BIG

    def test_disabled_no_stats(self):
        r = _router(enabled=False)
        r.route("something")
        assert r.big_routes == 0
        assert r.small_routes == 0


# ---------------------------------------------------------------------------
# test_no_small_model_always_big
# ---------------------------------------------------------------------------

class TestNoSmallModelAlwaysBig:
    """Verifies that when small_model is empty, the router always falls back to BIG.

    An empty string small_model means there's no secondary model to route to —
    all inputs regardless of complexity get routed to BIG.
    """

    def test_no_small_model(self):
        r = ModelRouter(big_model=BIG, small_model="", enabled=True)
        model = r.route("yes")
        assert model == BIG

    def test_no_small_model_complex(self):
        r = ModelRouter(big_model=BIG, small_model="", enabled=True)
        model = r.route("refactor the entire codebase")
        assert model == BIG


# ---------------------------------------------------------------------------
# test_complexity_scoring
# ---------------------------------------------------------------------------

class TestComplexityScoring:
    """Verifies estimate_complexity() assigns correct levels and scores, and explains its reasoning.

    'ok' → level='simple', score < 0. 'refactor the entire multi-file authentication system' →
    level='complex', score > 0. 250-word input adds score with 'long input' in reason.
    Multiple .py file references boost score. Multiple question marks boost score with 'questions'
    in reason. Higher context_entries or active_files both increase score. reason is always a string.
    """

    def test_simple_classification(self):
        est = estimate_complexity("ok")
        assert est["level"] == "simple"
        assert est["score"] < 0

    def test_complex_classification(self):
        est = estimate_complexity("refactor the entire multi-file authentication system")
        assert est["level"] == "complex"
        assert est["score"] > 0

    def test_moderate_classification(self):
        est = estimate_complexity("can you help me with this function")
        assert est["level"] in ("simple", "moderate")

    def test_word_count_signal_long(self):
        est = estimate_complexity(" ".join(["word"] * 250))
        assert est["score"] > 0
        assert "long input" in est["reason"]

    def test_word_count_signal_short(self):
        est = estimate_complexity("hi")
        assert est["score"] < 0

    def test_file_references_boost(self):
        est = estimate_complexity(
            "update main.py, config.py, and utils.py to match test.py")
        assert est["score"] > 0

    def test_question_count_boost(self):
        # Multiple questions boost complexity, but short input still
        # pulls score down. Verify that questions DO add score vs baseline.
        est_no_q = estimate_complexity("why how what when")
        est_with_q = estimate_complexity("why? how? what? when?")
        assert est_with_q["score"] > est_no_q["score"]
        assert "questions" in est_with_q["reason"]

    def test_context_entries_boost(self):
        est_low = estimate_complexity("do something", context_entries=5)
        est_high = estimate_complexity("do something", context_entries=50)
        assert est_high["score"] >= est_low["score"]

    def test_active_files_boost(self):
        est = estimate_complexity("do something", active_files=10)
        assert est["score"] > estimate_complexity("do something")["score"]

    def test_reason_string(self):
        est = estimate_complexity("refactor the entire authentication module")
        assert isinstance(est["reason"], str)
        assert len(est["reason"]) > 0

    def test_balanced_signals(self):
        est = estimate_complexity("hello there friend")
        assert isinstance(est["reason"], str)


# ---------------------------------------------------------------------------
# test_route_logging
# ---------------------------------------------------------------------------

class TestRouteLogging:
    """Verifies _route_log accumulates routing decisions with full metadata, capped at 100 entries.

    After routing 2 inputs, _route_log has 2 entries. Each entry has input_preview, score, level,
    model, and reason. After 120 routes, len(_route_log) <= 100 (oldest evicted).
    small_routes and big_routes counters track the split correctly.
    Entry model fields match the actual model selected ('yes' → SMALL, long refactor text → BIG).
    """

    def test_route_log_populated(self):
        r = _router()
        r.route("yes")
        r.route("refactor everything multi-step multi-file")
        assert len(r._route_log) == 2

    def test_route_log_entry_structure(self):
        r = _router()
        r.route("hello")
        entry = r._route_log[0]
        assert "input_preview" in entry
        assert "score" in entry
        assert "level" in entry
        assert "model" in entry
        assert "reason" in entry

    def test_route_log_bounded(self):
        r = _router()
        for i in range(120):
            r.route(f"message number {i}")
        assert len(r._route_log) <= 100

    def test_stats_tracking(self):
        r = _router()
        r.route("yes")    # simple -> small
        r.route("ok")     # simple -> small
        r.route("refactor the entire multi-file architecture")  # complex -> big
        assert r.small_routes == 2
        assert r.big_routes == 1

    def test_route_log_model_field(self):
        r = _router()
        r.route("yes")
        assert r._route_log[0]["model"] == SMALL

        r.route("refactor the entire multi-file architecture")
        assert r._route_log[1]["model"] == BIG
