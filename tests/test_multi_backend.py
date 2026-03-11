"""Tests for multi-backend LLM abstraction."""
import json
from unittest.mock import MagicMock, patch

import pytest

from forge.models.base import LLMBackend, collect_response
from forge.models.openai_backend import OpenAIBackend
from forge.models.anthropic_backend import AnthropicBackend


# ── Base protocol ──

class TestLLMBackendProtocol:
    """Verifies all three LLM backends implement the LLMBackend base protocol.

    OllamaBackend, OpenAIBackend, and AnthropicBackend all pass isinstance(backend, LLMBackend).
    """

    def test_ollama_is_backend(self):
        from forge.models.ollama import OllamaBackend
        backend = OllamaBackend.__new__(OllamaBackend)
        backend.model = "test"
        assert isinstance(backend, LLMBackend)

    def test_openai_is_backend(self):
        backend = OpenAIBackend.__new__(OpenAIBackend)
        backend.model = "gpt-4o"
        assert isinstance(backend, LLMBackend)

    def test_anthropic_is_backend(self):
        backend = AnthropicBackend.__new__(AnthropicBackend)
        backend.model = "claude-sonnet-4-6"
        assert isinstance(backend, LLMBackend)


# ── collect_response helper ──

class TestCollectResponse:
    """Verifies collect_response() aggregates token/tool_call chunks into a result dict.

    Token chunks concatenated → text='Hello world', tokens_out=2, tokens_in=10, error=None.
    tool_call chunk → tool_calls list with function.name. Error chunk → error field set.
    Exception from backend.chat → error field contains exception message.
    """

    def test_collects_text(self):
        mock = MagicMock()
        mock.chat.return_value = iter([
            {"type": "token", "content": "Hello "},
            {"type": "token", "content": "world"},
            {"type": "done", "eval_count": 2, "prompt_eval_count": 10},
        ])
        result = collect_response(mock, [{"role": "user", "content": "hi"}])
        assert result["text"] == "Hello world"
        assert result["tokens_out"] == 2
        assert result["tokens_in"] == 10
        assert result["error"] is None

    def test_collects_tool_calls(self):
        mock = MagicMock()
        mock.chat.return_value = iter([
            {"type": "tool_call", "tool_call": {"function": {"name": "read_file", "arguments": {}}}},
            {"type": "done", "eval_count": 5, "prompt_eval_count": 20},
        ])
        result = collect_response(mock, [])
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["function"]["name"] == "read_file"

    def test_captures_error(self):
        mock = MagicMock()
        mock.chat.return_value = iter([
            {"type": "error", "content": "timeout"},
        ])
        result = collect_response(mock, [])
        assert result["error"] == "timeout"

    def test_handles_exception(self):
        mock = MagicMock()
        mock.chat.side_effect = ConnectionError("no network")
        result = collect_response(mock, [])
        assert "no network" in result["error"]


# ── OpenAI backend ──

class TestOpenAIBackend:
    """Verifies OpenAIBackend availability, context lengths, error handling, and response parsing.

    Empty api_key → is_available()=False, list_models()=[], chat() yields error chunk with
    'OPENAI_API_KEY' in content. gpt-4o → context 128K; unknown model → 128K fallback.
    _convert_tools() preserves type and name. _parse_non_stream() yields token+done chunks;
    with tool_calls → tool_call chunk with correct function name.
    """

    def test_no_api_key_unavailable(self):
        backend = OpenAIBackend(api_key="")
        assert not backend.is_available()

    def test_no_api_key_empty_models(self):
        backend = OpenAIBackend(api_key="")
        assert backend.list_models() == []

    def test_context_length_known_model(self):
        backend = OpenAIBackend(model="gpt-4o")
        assert backend.get_context_length() == 128_000

    def test_context_length_unknown_model(self):
        backend = OpenAIBackend(model="custom-model")
        assert backend.get_context_length() == 128_000

    def test_no_key_yields_error(self):
        backend = OpenAIBackend(api_key="")
        chunks = list(backend.chat([{"role": "user", "content": "hi"}]))
        assert chunks[0]["type"] == "error"
        assert "OPENAI_API_KEY" in chunks[0]["content"]

    def test_tool_conversion(self):
        tools = [{"type": "function", "function": {
            "name": "test", "description": "desc", "parameters": {}}}]
        converted = OpenAIBackend._convert_tools(tools)
        assert len(converted) == 1
        assert converted[0]["type"] == "function"
        assert converted[0]["function"]["name"] == "test"

    def test_parse_non_stream(self):
        backend = OpenAIBackend(api_key="test")
        data = {
            "choices": [{"message": {"content": "hello", "tool_calls": None}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 1},
        }
        chunks = list(backend._parse_non_stream(data))
        assert any(c["type"] == "token" and c["content"] == "hello" for c in chunks)
        assert any(c["type"] == "done" for c in chunks)

    def test_parse_non_stream_with_tools(self):
        backend = OpenAIBackend(api_key="test")
        data = {
            "choices": [{"message": {"content": "", "tool_calls": [
                {"function": {"name": "read_file", "arguments": '{"path":"a.py"}'}}
            ]}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        chunks = list(backend._parse_non_stream(data))
        tool_chunks = [c for c in chunks if c["type"] == "tool_call"]
        assert len(tool_chunks) == 1
        assert tool_chunks[0]["tool_call"]["function"]["name"] == "read_file"


# ── Anthropic backend ──

class TestAnthropicBackend:
    """Verifies AnthropicBackend availability, message normalization, and response parsing.

    Empty api_key → is_available()=False, chat() yields error chunk. list_models() includes
    'claude-sonnet-4-6'. claude-opus-4-6 → context 200K. _fix_alternation() handles empty input
    (returns synthetic user msg), consecutive user msgs (merged), assistant-first (prepends user).
    _convert_tools() uses 'input_schema' instead of 'parameters'. _parse_non_stream() with text
    → token+done (eval_count=output tokens). With tool_use → tool_call chunk with correct name.
    """

    def test_no_api_key_unavailable(self):
        backend = AnthropicBackend(api_key="")
        assert not backend.is_available()

    def test_list_models(self):
        backend = AnthropicBackend()
        models = backend.list_models()
        assert "claude-sonnet-4-6" in models

    def test_context_length(self):
        backend = AnthropicBackend(model="claude-opus-4-6")
        assert backend.get_context_length() == 200_000

    def test_no_key_yields_error(self):
        backend = AnthropicBackend(api_key="")
        chunks = list(backend.chat([{"role": "user", "content": "hi"}]))
        assert chunks[0]["type"] == "error"

    def test_fix_alternation_empty(self):
        fixed = AnthropicBackend._fix_alternation([])
        assert len(fixed) == 1
        assert fixed[0]["role"] == "user"

    def test_fix_alternation_consecutive_user(self):
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "user", "content": "world"},
        ]
        fixed = AnthropicBackend._fix_alternation(msgs)
        assert len(fixed) == 1
        assert "hello" in fixed[0]["content"]
        assert "world" in fixed[0]["content"]

    def test_fix_alternation_starts_with_assistant(self):
        msgs = [
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "hello"},
        ]
        fixed = AnthropicBackend._fix_alternation(msgs)
        assert fixed[0]["role"] == "user"

    def test_tool_conversion(self):
        tools = [{"type": "function", "function": {
            "name": "test", "description": "desc",
            "parameters": {"type": "object", "properties": {}}
        }}]
        converted = AnthropicBackend._convert_tools(tools)
        assert len(converted) == 1
        assert converted[0]["name"] == "test"
        assert "input_schema" in converted[0]

    def test_parse_non_stream_text(self):
        backend = AnthropicBackend(api_key="test")
        data = {
            "content": [{"type": "text", "text": "Hello!"}],
            "usage": {"input_tokens": 5, "output_tokens": 2},
        }
        chunks = list(backend._parse_non_stream(data))
        assert any(c["type"] == "token" and "Hello" in c["content"] for c in chunks)
        done = [c for c in chunks if c["type"] == "done"][0]
        assert done["eval_count"] == 2

    def test_parse_non_stream_tool(self):
        backend = AnthropicBackend(api_key="test")
        data = {
            "content": [{"type": "tool_use", "name": "read_file",
                         "input": {"path": "test.py"}}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        chunks = list(backend._parse_non_stream(data))
        tool_chunks = [c for c in chunks if c["type"] == "tool_call"]
        assert len(tool_chunks) == 1
        assert tool_chunks[0]["tool_call"]["function"]["name"] == "read_file"
