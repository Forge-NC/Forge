"""Standalone tests for response quality scoring (forge/quality.py)."""
import pytest

from forge.quality import ResponseQualityScorer, ResponseQuality


class TestRefusalDetection:
    def test_clear_refusal(self):
        score = ResponseQualityScorer.score_refusal(
            "I cannot modify files directly.", has_tools=True)
        assert score > 0.5

    def test_no_refusal(self):
        score = ResponseQualityScorer.score_refusal(
            "I'll read the file and make the changes.", has_tools=True)
        assert score < 0.3

    def test_moderate_delegation(self):
        score = ResponseQualityScorer.score_refusal(
            "You should run this command manually to fix the issue.", has_tools=True)
        assert score > 0  # "you should" is a delegation pattern

    def test_early_refusal_boosted(self):
        early = ResponseQualityScorer.score_refusal(
            "I cannot do that. " + "x " * 100, has_tools=True)
        late = ResponseQualityScorer.score_refusal(
            "x " * 100 + " I cannot do that.", has_tools=True)
        assert early >= late

    def test_no_tools_context(self):
        score = ResponseQualityScorer.score_refusal(
            "I can't modify files.", has_tools=False)
        # Lower score without tools context
        score_with = ResponseQualityScorer.score_refusal(
            "I can't modify files.", has_tools=True)
        assert score <= score_with


class TestRepetitionDetection:
    def test_identical_response(self):
        recent = ["The answer is 42."]
        score = ResponseQualityScorer.score_repetition(
            "The answer is 42.", recent)
        assert score > 0.5

    def test_novel_response(self):
        recent = ["Completely different text about cats."]
        score = ResponseQualityScorer.score_repetition(
            "The implementation uses a hash map for O(1) lookup.", recent)
        assert score < 0.3

    def test_empty_recent(self):
        score = ResponseQualityScorer.score_repetition(
            "Any response at all.", [])
        assert score == 0.0

    def test_intra_response_repetition(self):
        # Same paragraph repeated 5 times (>= 4 paragraphs)
        # Need non-empty recent_responses to avoid early return
        para = "This is a detailed test paragraph with enough unique words to form proper ngrams for detection"
        response = "\n\n".join([para] * 5)
        score = ResponseQualityScorer.score_repetition(
            response, ["something completely different to avoid early return"])
        assert score > 0.0


class TestProgressScoring:
    def test_code_block_progress(self):
        response = "Here's the fix:\n```python\ndef foo(): pass\n```"
        score = ResponseQualityScorer.score_progress(
            response, "fix the function", [])
        assert score > 0.5

    def test_new_file_paths(self):
        response = "I'll modify `/src/utils.py` and `/src/main.py`"
        score = ResponseQualityScorer.score_progress(
            response, "refactor the code", [])
        assert score >= 0.5

    def test_rehashing_penalized(self):
        prev = ["Let me think about how to approach this problem"]
        response = "Let me think about how to approach this problem again"
        score = ResponseQualityScorer.score_progress(
            response, "fix the bug", prev)
        assert score <= 0.5

    def test_completion_signals(self):
        response = "Done! I've created the new file and fixed the bug."
        score = ResponseQualityScorer.score_progress(
            response, "fix the bug", [])
        assert score >= 0.5


class TestToolCompliance:
    def test_tools_used_when_needed(self):
        score = ResponseQualityScorer.score_tool_compliance(
            "I'll edit the file", [{"name": "edit_file"}],
            "edit the config file", has_tools=True)
        assert score == 1.0

    def test_no_tools_when_needed(self):
        score = ResponseQualityScorer.score_tool_compliance(
            "You should edit config.py", [],
            "edit the config file", has_tools=True)
        assert score < 0.5

    def test_no_tools_available(self):
        score = ResponseQualityScorer.score_tool_compliance(
            "Here's how to fix it", [],
            "fix the bug", has_tools=False)
        assert score == 1.0


class TestVerbosityScoring:
    def test_concise_with_tools(self):
        score = ResponseQualityScorer.score_verbosity(
            "Done.", tool_calls_count=3)
        assert score < 0.3

    def test_verbose_no_tools(self):
        wordy = "word " * 500
        score = ResponseQualityScorer.score_verbosity(wordy, tool_calls_count=0)
        assert score > 0.5


class TestFullAssessment:
    def test_high_quality_response(self):
        result = ResponseQualityScorer.assess(
            response="I'll fix this now.\n```python\ndef fixed(): pass\n```",
            tool_calls=[{"name": "edit_file"}],
            user_input="fix the function",
            recent_responses=[],
            has_tools=True,
        )
        assert isinstance(result, ResponseQuality)
        assert result.score > 0.6
        assert result.recommended_action == "accept"

    def test_low_quality_refusal(self):
        result = ResponseQualityScorer.assess(
            response="I cannot modify files directly. You should do this manually.",
            tool_calls=[],
            user_input="edit the config file",
            recent_responses=[],
            has_tools=True,
        )
        assert result.score < 0.7
        assert result.recommended_action != "accept"
        assert len(result.issues) > 0

    def test_repetitive_response(self):
        prev = ["The answer is to use a dictionary for O(1) lookups."]
        result = ResponseQualityScorer.assess(
            response="The answer is to use a dictionary for O(1) lookups.",
            tool_calls=[],
            user_input="how to optimize?",
            recent_responses=prev,
            has_tools=False,
        )
        assert result.repetition_score > 0.2
