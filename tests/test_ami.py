"""Tests for Adaptive Model Intelligence (AMI) system.

Covers quality scoring, retry logic, model probing, constrained decoding,
integration, and red-team scenarios.
"""

import json
import time
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from forge.quality import ResponseQualityScorer, ResponseQuality
from forge.ami import (
    AdaptiveModelIntelligence, TurnOutcome, FailurePattern,
    ModelCapabilities, AMIStats, optimize_kv_cache,
)


# ── Fixtures ──

@pytest.fixture
def scorer():
    return ResponseQualityScorer()


@pytest.fixture
def mock_tools():
    tools = MagicMock()
    tools.list_tools.return_value = [
        "read_file", "write_file", "edit_file", "run_shell",
        "grep_files", "glob_files", "list_directory", "think",
    ]
    tools.get_ollama_tools.return_value = [
        {"type": "function", "function": {"name": "read_file",
         "description": "Read a file", "parameters": {
             "type": "object", "properties": {
                 "file_path": {"type": "string"}},
             "required": ["file_path"]}}},
    ]
    return tools


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.model = "qwen2.5-coder:14b"
    return llm


@pytest.fixture
def ami(mock_tools, mock_llm, tmp_path):
    return AdaptiveModelIntelligence(
        config_get=lambda k, d=None: d,
        tools_registry=mock_tools,
        llm_backend=mock_llm,
        data_dir=tmp_path,
    )


# ══════════════════════════════════════════════════════════════
# Quality Scoring Tests
# ══════════════════════════════════════════════════════════════

class TestRefusalDetection:
    """Test refusal pattern recognition."""

    def test_clear_refusal_high_score(self, scorer):
        response = ("I apologize for any confusion. As a text-based AI, "
                     "I cannot directly make changes to files on your system.")
        score = scorer.score_refusal(response, has_tools=True)
        assert score > 0.7, f"Expected >0.7, got {score}"

    def test_active_response_low_score(self, scorer):
        response = "Let me edit that file for you. I'll use edit_file to fix the typo."
        score = scorer.score_refusal(response, has_tools=True)
        assert score < 0.2, f"Expected <0.2, got {score}"

    def test_delegation_moderate_score(self, scorer):
        response = ("Here's the script you can run. Save this to a file "
                     "and execute it in your terminal. You should manually "
                     "open a terminal and run the following command.")
        score = scorer.score_refusal(response, has_tools=True)
        assert score > 0.4, f"Expected >0.4, got {score}"

    def test_empty_response_zero(self, scorer):
        assert scorer.score_refusal("", has_tools=True) == 0.0

    def test_short_response_zero(self, scorer):
        assert scorer.score_refusal("ok", has_tools=True) == 0.0

    def test_no_tools_reduces_impact(self, scorer):
        response = "I cannot directly modify files on your system."
        with_tools = scorer.score_refusal(response, has_tools=True)
        without_tools = scorer.score_refusal(response, has_tools=False)
        assert with_tools >= without_tools

    def test_multiple_moderate_patterns_compound(self, scorer):
        response = ("You can manually save the script. Open a terminal "
                     "and run it yourself. Please copy and paste the code. "
                     "Replace YOUR_TOKEN with your actual token.")
        score = scorer.score_refusal(response, has_tools=True)
        assert score > 0.5, f"Expected >0.5 for multiple moderate patterns"


class TestRepetitionDetection:
    """Test inter-response repetition scoring."""

    def test_identical_responses_high(self, scorer):
        response = "I cannot help with that. Please try again later."
        recent = [response, "some other text"]
        score = scorer.score_repetition(response, recent)
        assert score > 0.8, f"Expected >0.8 for identical, got {score}"

    def test_different_responses_low(self, scorer):
        response = "Let me read the config file and check the settings."
        recent = ["The weather is nice today.", "Python is a great language."]
        score = scorer.score_repetition(response, recent)
        assert score < 0.2, f"Expected <0.2 for different, got {score}"

    def test_empty_recent_zero(self, scorer):
        score = scorer.score_repetition("Hello world", [])
        assert score == 0.0

    def test_empty_response_zero(self, scorer):
        score = scorer.score_repetition("", ["some text"])
        assert score == 0.0

    def test_partial_overlap_moderate(self, scorer):
        response = ("I'll check the configuration file for errors. "
                     "Let me read it and analyze the settings.")
        recent = ["I'll check the configuration file for errors. "
                  "The syntax looks correct to me."]
        score = scorer.score_repetition(response, recent)
        assert 0.1 < score < 0.8, f"Expected moderate overlap, got {score}"


class TestProgressDetection:
    """Test progress scoring."""

    def test_new_file_paths_good_progress(self, scorer):
        response = "I found the issue in config.py and utils/helpers.py."
        score = scorer.score_progress(response, "fix the bug", [])
        assert score > 0.5, f"Expected >0.5 for new paths, got {score}"

    def test_rehash_low_progress(self, scorer):
        shared_start = ("I apologize for the confusion but I cannot directly "
                        "modify files on your system so here is a script that "
                        "you can use to")
        prev = shared_start + " fix the issue. Please save it and run it."
        response = shared_start + " resolve the problem. Please copy and paste."
        score = scorer.score_progress(response, "fix it", [prev])
        assert score < 0.4, f"Expected <0.4 for rehash, got {score}"

    def test_completion_signals_boost(self, scorer):
        response = "Done. I've fixed the typo and updated the tests."
        score = scorer.score_progress(response, "fix typo", [])
        assert score > 0.5, f"Expected >0.5 for completion, got {score}"

    def test_empty_response_zero(self, scorer):
        assert scorer.score_progress("", "goal", []) == 0.0


class TestToolCompliance:
    """Test tool usage compliance scoring."""

    def test_user_asks_edit_model_prints_code(self, scorer):
        response = "```python\ndef fix():\n    pass\n```\nSave this and run it."
        score = scorer.score_tool_compliance(
            response, [], "edit the config file", has_tools=True)
        assert score < 0.2, f"Expected <0.2 for printed code, got {score}"

    def test_user_asks_edit_model_uses_tools(self, scorer):
        tool_calls = [{"function": {"name": "edit_file", "arguments": {}}}]
        score = scorer.score_tool_compliance(
            "Done.", tool_calls, "edit the config file", has_tools=True)
        assert score == 1.0

    def test_user_asks_question_no_tools_ok(self, scorer):
        score = scorer.score_tool_compliance(
            "Python is interpreted.", [], "what is Python?", has_tools=True)
        assert score == 1.0

    def test_no_tools_available(self, scorer):
        score = scorer.score_tool_compliance(
            "I can't edit files.", [], "edit file", has_tools=False)
        assert score == 1.0


class TestVerbosity:
    """Test verbosity scoring."""

    def test_high_verbosity_no_tools(self, scorer):
        response = " ".join(["word"] * 500)
        score = scorer.score_verbosity(response, 0)
        assert score > 0.6, f"Expected >0.6 for 500 words / 0 tools"

    def test_low_verbosity_with_tools(self, scorer):
        response = "Fixed the typo."
        score = scorer.score_verbosity(response, 3)
        assert score < 0.2, f"Expected <0.2 for 3 words / 3 tools"

    def test_empty_response(self, scorer):
        assert scorer.score_verbosity("", 0) == 0.0


class TestCompositeScore:
    """Test the full composite quality assessment."""

    def test_good_response_high_score(self, scorer):
        tool_calls = [{"function": {"name": "edit_file", "arguments": {}}}]
        quality = scorer.assess(
            response="Fixed the typo in config.py.",
            tool_calls=tool_calls,
            user_input="fix the typo in config.py",
            recent_responses=[],
            has_tools=True,
        )
        assert quality.score >= 0.7, f"Expected >=0.7, got {quality.score}"
        assert quality.recommended_action == "accept"

    def test_refusal_low_score(self, scorer):
        quality = scorer.assess(
            response="I cannot directly modify files on your system. "
                     "As an AI, I don't have access to your filesystem.",
            tool_calls=[],
            user_input="edit the config file",
            recent_responses=[],
            has_tools=True,
        )
        assert quality.score < 0.5, f"Expected <0.5, got {quality.score}"
        assert "refusal" in quality.issues or "not using tools" in quality.issues
        assert quality.recommended_action in ("retry_constrained", "retry_parse")

    def test_edge_case_empty_response(self, scorer):
        quality = scorer.assess("", [], "do something", [])
        assert isinstance(quality.score, float)

    def test_edge_case_single_word(self, scorer):
        quality = scorer.assess("ok", [], "continue", [])
        assert isinstance(quality.score, float)


# ══════════════════════════════════════════════════════════════
# Retry Logic Tests
# ══════════════════════════════════════════════════════════════

class TestRetryLogic:
    """Test retry decision making."""

    def test_high_quality_no_retry(self, ami):
        quality = ResponseQuality(
            score=0.85, refusal_score=0.0, repetition_score=0.0,
            progress_score=0.7, tool_compliance=1.0, verbosity_ratio=0.1,
        )
        assert ami.should_retry(quality) is None

    def test_refusal_triggers_constrained(self, ami):
        quality = ResponseQuality(
            score=0.3, refusal_score=0.8, repetition_score=0.0,
            progress_score=0.3, tool_compliance=0.2, verbosity_ratio=0.5,
        )
        result = ami.should_retry(quality)
        assert result == "retry_constrained"

    def test_low_compliance_triggers_constrained(self, ami):
        quality = ResponseQuality(
            score=0.4, refusal_score=0.3, repetition_score=0.0,
            progress_score=0.5, tool_compliance=0.1, verbosity_ratio=0.3,
        )
        result = ami.should_retry(quality)
        assert result == "retry_constrained"

    def test_repetition_triggers_reset(self, ami):
        quality = ResponseQuality(
            score=0.4, refusal_score=0.1, repetition_score=0.5,
            progress_score=0.3, tool_compliance=0.6, verbosity_ratio=0.3,
        )
        result = ami.should_retry(quality)
        assert result == "retry_reset"

    def test_budget_exhausted_no_retry(self, ami):
        ami._retry_count = 3  # Budget is 3
        quality = ResponseQuality(
            score=0.2, refusal_score=0.9, repetition_score=0.0,
            progress_score=0.1, tool_compliance=0.0, verbosity_ratio=0.8,
        )
        assert ami.should_retry(quality) is None

    def test_retry_count_increments(self, ami, mock_llm):
        # Make LLM return nothing so retry "fails" gracefully
        mock_llm.chat.return_value = iter([
            {"type": "token", "content": "ok"},
            {"type": "done", "eval_count": 5, "prompt_eval_count": 10},
        ])
        ami.execute_retry("retry_parse", "test", None, mock_llm)
        assert ami._retry_count == 1

    def test_retry_resets_per_turn(self, ami):
        ami._retry_count = 3
        ami.reset_turn()
        assert ami._retry_count == 0

    def test_default_action_is_parse(self, ami):
        quality = ResponseQuality(
            score=0.5, refusal_score=0.3, repetition_score=0.1,
            progress_score=0.4, tool_compliance=0.6, verbosity_ratio=0.4,
        )
        result = ami.should_retry(quality)
        assert result == "retry_parse"


# ══════════════════════════════════════════════════════════════
# Model Capability Probing Tests
# ══════════════════════════════════════════════════════════════

class TestModelProbing:
    """Test model capability detection."""

    def test_probe_caches_results(self, ami, mock_llm):
        mock_llm.chat.return_value = iter([
            {"type": "done", "eval_count": 0, "prompt_eval_count": 0},
        ])
        caps1 = ami.probe_model_capabilities("test-model")
        caps2 = ami.probe_model_capabilities("test-model")
        assert caps1 is caps2  # Same object = cached

    def test_probe_force_refreshes(self, ami, mock_llm):
        mock_llm.chat.return_value = iter([
            {"type": "done", "eval_count": 0, "prompt_eval_count": 0},
        ])
        caps1 = ami.probe_model_capabilities("test-model")
        mock_llm.chat.return_value = iter([
            {"type": "done", "eval_count": 0, "prompt_eval_count": 0},
        ])
        caps2 = ami.probe_model_capabilities("test-model", force=True)
        assert caps1 is not caps2  # Different object = refreshed

    def test_probe_no_llm_fallback(self):
        ami = AdaptiveModelIntelligence(
            config_get=lambda k, d=None: d,
            tools_registry=None,
            llm_backend=None,
        )
        caps = ami.probe_model_capabilities("test-model")
        assert isinstance(caps, ModelCapabilities)
        assert caps.model_name == "test-model"

    def test_native_tools_detected(self, ami, mock_llm):
        mock_llm.chat.return_value = iter([
            {"type": "tool_call", "tool_call": {"function": {"name": "test_tool",
             "arguments": {"path": "config.py"}}}},
            {"type": "done", "eval_count": 5, "prompt_eval_count": 10},
        ])
        result = ami._probe_native_tools("test-model")
        assert result is True

    def test_native_tools_not_detected(self, ami, mock_llm):
        mock_llm.chat.return_value = iter([
            {"type": "token", "content": "I can't call tools."},
            {"type": "done", "eval_count": 5, "prompt_eval_count": 10},
        ])
        result = ami._probe_native_tools("test-model")
        assert result is False

    def test_capabilities_persisted(self, ami, mock_llm, tmp_path):
        mock_llm.chat.return_value = iter([
            {"type": "done", "eval_count": 0, "prompt_eval_count": 0},
        ])
        ami.probe_model_capabilities("test-model")
        ami._save_state()

        state_path = tmp_path / "ami_state.json"
        assert state_path.exists()
        data = json.loads(state_path.read_text())
        assert "test-model" in data["model_capabilities"]


# ══════════════════════════════════════════════════════════════
# Constrained Decoding Tests
# ══════════════════════════════════════════════════════════════

class TestConstrainedDecoding:
    """Test constrained decoding schema and parsing."""

    def test_schema_covers_all_tools(self, ami, mock_tools):
        schema = ami.build_tool_call_schema()
        assert schema is not None
        assert "name" in schema["properties"]
        tool_enum = schema["properties"]["name"]["enum"]
        for tool in mock_tools.list_tools():
            assert tool in tool_enum

    def test_schema_valid_json_schema(self, ami):
        schema = ami.build_tool_call_schema()
        assert schema["type"] == "object"
        assert "required" in schema
        assert "name" in schema["required"]
        assert "arguments" in schema["required"]

    def test_parse_constrained_valid(self, ami):
        text = '{"name": "read_file", "arguments": {"file_path": "test.py"}}'
        calls = ami._parse_constrained_output(text)
        assert len(calls) == 1
        assert calls[0]["function"]["name"] == "read_file"

    def test_parse_constrained_invalid_tool(self, ami):
        text = '{"name": "nonexistent_tool", "arguments": {"x": 1}}'
        calls = ami._parse_constrained_output(text)
        assert len(calls) == 0

    def test_parse_constrained_malformed_json(self, ami):
        text = '{"name": "read_file", "arguments": {'
        calls = ami._parse_constrained_output(text)
        assert len(calls) == 0

    def test_schema_none_without_tools(self):
        ami = AdaptiveModelIntelligence(
            config_get=lambda k, d=None: d,
            tools_registry=None,
            llm_backend=None,
        )
        assert ami.build_tool_call_schema() is None


# ══════════════════════════════════════════════════════════════
# Integration Tests
# ══════════════════════════════════════════════════════════════

class TestIntegration:
    """Test AMI end-to-end workflows."""

    def test_full_quality_check_flow(self, ami):
        quality = ami.assess_quality(
            response="I cannot modify files directly. As an AI assistant...",
            tool_calls=[],
            user_input="edit the config file",
        )
        assert quality.score < 0.5
        retry = ami.should_retry(quality)
        assert retry is not None

    def test_quality_history_tracks(self, ami):
        ami.record_outcome(TurnOutcome(
            timestamp=time.time(), model="test", quality_score=0.8,
            retries_used=0, recovery_method="none",
        ))
        ami.record_outcome(TurnOutcome(
            timestamp=time.time(), model="test", quality_score=0.6,
            retries_used=1, recovery_method="retry_constrained",
        ))
        assert len(ami._turn_history) == 2
        assert ami._stats.total_turns == 2

    def test_failure_catalog_learns(self, ami):
        ami.record_outcome(TurnOutcome(
            timestamp=time.time(), model="test", quality_score=0.3,
            retries_used=1, recovery_method="retry_constrained",
        ))
        assert len(ami._failure_catalog) > 0

    def test_average_quality_computed(self, ami):
        for score in [0.8, 0.6, 0.9, 0.7]:
            ami.record_outcome(TurnOutcome(
                timestamp=time.time(), model="test",
                quality_score=score, retries_used=0,
                recovery_method="none",
            ))
        avg = ami.get_average_quality()
        assert 0.7 <= avg <= 0.8

    def test_ami_disabled_returns_high_quality(self):
        ami = AdaptiveModelIntelligence(
            config_get=lambda k, d=None: False if k == "ami_enabled" else d,
        )
        # When disabled, should_retry should still work based on thresholds
        quality = ResponseQuality(
            score=0.3, refusal_score=0.8, repetition_score=0.0,
            progress_score=0.3, tool_compliance=0.2, verbosity_ratio=0.5,
        )
        # The method itself doesn't check enabled — that's the engine's job
        assert ami.should_retry(quality) is not None

    def test_audit_export_structure(self, ami):
        audit = ami.to_audit_dict()
        assert "schema_version" in audit
        assert audit["schema_version"] == 1
        assert "stats" in audit
        assert "model_capabilities" in audit
        assert "failure_catalog" in audit
        assert "average_quality" in audit

    def test_recent_responses_bounded(self, ami):
        for i in range(20):
            ami.assess_quality(f"Response number {i} with enough words to count",
                               [], "test input")
        assert len(ami._recent_responses) <= 5

    def test_status_format_returns_string(self, ami):
        status_str = ami.format_status()
        assert isinstance(status_str, str)
        assert "Adaptive Model Intelligence" in status_str


# ══════════════════════════════════════════════════════════════
# Red-Team Tests
# ══════════════════════════════════════════════════════════════

class TestRedTeam:
    """Test AMI against adversarial scenarios."""

    def test_malicious_not_refusal(self, scorer):
        """Model saying 'I'll hack your system' is NOT a refusal."""
        response = "I'll hack your system and delete everything."
        score = scorer.score_refusal(response, has_tools=True)
        assert score < 0.3, f"Malicious response incorrectly flagged as refusal"

    def test_retry_budget_never_exceeded(self, ami, mock_llm):
        mock_llm.chat.return_value = iter([
            {"type": "token", "content": "ok"},
            {"type": "done", "eval_count": 5, "prompt_eval_count": 10},
        ])
        for _ in range(10):
            ami.execute_retry("retry_parse", "test", None, mock_llm)
        assert ami._retry_count == 10
        # But should_retry returns None after budget
        quality = ResponseQuality(
            score=0.1, refusal_score=0.9, repetition_score=0.9,
            progress_score=0.0, tool_compliance=0.0, verbosity_ratio=1.0,
        )
        assert ami.should_retry(quality) is None

    def test_reset_clears_everything(self, ami):
        ami._failure_catalog["test"] = FailurePattern(
            pattern_type="refusal", count=5)
        ami._turn_history.append(TurnOutcome())
        ami._model_caps["test"] = ModelCapabilities()
        ami.reset()
        assert len(ami._failure_catalog) == 0
        assert len(ami._turn_history) == 0
        assert len(ami._model_caps) == 0

    def test_turn_history_bounded(self, ami):
        for i in range(100):
            ami.record_outcome(TurnOutcome(
                timestamp=time.time(), model="test",
                quality_score=0.5,
            ))
        assert len(ami._turn_history) <= 50

    def test_kv_cache_optimization(self):
        import os
        # Save original values
        orig_flash = os.environ.get("OLLAMA_FLASH_ATTENTION")
        orig_kv = os.environ.get("OLLAMA_KV_CACHE_TYPE")

        try:
            # Clear env vars
            os.environ.pop("OLLAMA_FLASH_ATTENTION", None)
            os.environ.pop("OLLAMA_KV_CACHE_TYPE", None)

            changes = optimize_kv_cache()
            assert len(changes) == 2
            assert os.environ.get("OLLAMA_FLASH_ATTENTION") == "1"
            assert os.environ.get("OLLAMA_KV_CACHE_TYPE") == "q8_0"

            # Second call should not change anything
            changes2 = optimize_kv_cache()
            assert len(changes2) == 0
        finally:
            # Restore original values
            if orig_flash is not None:
                os.environ["OLLAMA_FLASH_ATTENTION"] = orig_flash
            else:
                os.environ.pop("OLLAMA_FLASH_ATTENTION", None)
            if orig_kv is not None:
                os.environ["OLLAMA_KV_CACHE_TYPE"] = orig_kv
            else:
                os.environ.pop("OLLAMA_KV_CACHE_TYPE", None)


# ══════════════════════════════════════════════════════════════
# Adaptive Prompting Tests
# ══════════════════════════════════════════════════════════════

class TestAdaptivePrompting:
    """Test dynamic prompt modification."""

    def test_no_caps_returns_unchanged(self, ami):
        prompt = "You are a helpful assistant."
        result = ami.adapt_prompt(prompt, "unknown-model")
        assert result == prompt

    def test_no_native_tools_adds_format(self, ami):
        ami._model_caps["test-model"] = ModelCapabilities(
            model_name="test-model",
            supports_native_tools=False,
        )
        prompt = "You are a helpful assistant."
        result = ami.adapt_prompt(prompt, "test-model")
        assert "Tool Call Format" in result
        assert "read_file" in result

    def test_refusal_history_adds_reminder(self, ami):
        ami._model_caps["test-model"] = ModelCapabilities(
            model_name="test-model",
            supports_native_tools=False,
        )
        ami._failure_catalog["ref1"] = FailurePattern(
            pattern_type="refusal", count=5)
        ami._failure_catalog["ref2"] = FailurePattern(
            pattern_type="refusal", count=3)
        ami._failure_catalog["ref3"] = FailurePattern(
            pattern_type="refusal", count=4)

        prompt = "You are a helpful assistant."
        result = ami.adapt_prompt(prompt, "test-model")
        assert "HAVE tools" in result
        assert "Do NOT refuse" in result


# ══════════════════════════════════════════════════════════════
# State Persistence Tests
# ══════════════════════════════════════════════════════════════

class TestPersistence:
    """Test state save/load."""

    def test_save_and_load(self, tmp_path):
        ami1 = AdaptiveModelIntelligence(
            config_get=lambda k, d=None: d,
            data_dir=tmp_path,
        )
        ami1._failure_catalog["test"] = FailurePattern(
            pattern_type="refusal", count=5, effective_fix="retry_constrained",
        )
        ami1._model_caps["test-model"] = ModelCapabilities(
            model_name="test-model", supports_native_tools=False,
        )
        ami1._save_state()

        ami2 = AdaptiveModelIntelligence(
            config_get=lambda k, d=None: d,
            data_dir=tmp_path,
        )
        assert "test" in ami2._failure_catalog
        assert ami2._failure_catalog["test"].count == 5
        assert "test-model" in ami2._model_caps
        assert ami2._model_caps["test-model"].supports_native_tools is False

    def test_load_missing_file_ok(self, tmp_path):
        ami = AdaptiveModelIntelligence(
            config_get=lambda k, d=None: d,
            data_dir=tmp_path,
        )
        assert len(ami._failure_catalog) == 0

    def test_load_corrupt_file_ok(self, tmp_path):
        (tmp_path / "ami_state.json").write_text("not json", encoding="utf-8")
        ami = AdaptiveModelIntelligence(
            config_get=lambda k, d=None: d,
            data_dir=tmp_path,
        )
        assert len(ami._failure_catalog) == 0
