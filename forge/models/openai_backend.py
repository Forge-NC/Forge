"""OpenAI-compatible LLM backend (works with OpenAI, Together, Groq, etc.).

Uses raw requests — no openai SDK dependency. Any OpenAI-compatible API
endpoint can be used by setting base_url.

Environment variable: OPENAI_API_KEY (or pass api_key directly).
"""

import json
import logging
import os
from typing import Generator

import requests

log = logging.getLogger(__name__)

# Known context lengths for popular models
_CTX_LENGTHS = {
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
    "gpt-3.5-turbo": 16_385,
    "o1": 200_000,
    "o3": 200_000,
    "o3-mini": 200_000,
    "o4-mini": 200_000,
}


class OpenAIBackend:
    """OpenAI-compatible chat completions backend."""

    def __init__(self, model: str = "gpt-4o-mini",
                 api_key: str = "",
                 base_url: str = "https://api.openai.com/v1",
                 timeout: float = 120.0,
                 stop_tokens: list[str] | None = None):
        self.model = model
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._stop_tokens = stop_tokens
        self._session = requests.Session()
        self.num_ctx = None  # Engine sets this; ignored for cloud backends

    def is_available(self) -> bool:
        if not self._api_key:
            return False
        try:
            r = self._session.get(
                f"{self._base_url}/models",
                headers=self._headers(),
                timeout=10,
            )
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        if not self._api_key:
            return []
        try:
            r = self._session.get(
                f"{self._base_url}/models",
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code != 200:
                return []
            data = r.json().get("data", [])
            return sorted(m["id"] for m in data if "id" in m)
        except Exception:
            return []

    def get_context_length(self) -> int:
        for prefix, length in _CTX_LENGTHS.items():
            if self.model.startswith(prefix):
                return length
        return 128_000  # Conservative default for unknown models

    def chat(self, messages: list[dict],
             tools: list[dict] | None = None,
             temperature: float = 0.1,
             stream: bool = True,
             format: dict | None = None,
             ) -> Generator[dict, None, None]:
        """Chat completions, yielding Forge-standard chunks."""
        if not self._api_key:
            yield {"type": "error", "content": "No OPENAI_API_KEY set"}
            return

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 1024,
            "stream": stream,
        }

        # Stop tokens prevent models from generating past response boundaries
        # (the "391assistant\nassistant\nassistant" repetition loop problem).
        # Per-model tokens resolved from tokenizer_config.json are preferred;
        # universal fallback covers all major model families.
        if self._stop_tokens:
            payload["stop"] = self._stop_tokens

        # Convert Ollama-style tools to OpenAI format
        if tools:
            payload["tools"] = self._convert_tools(tools)

        # JSON mode (constrained output)
        if format:
            payload["response_format"] = {"type": "json_object"}

        try:
            r = self._session.post(
                f"{self._base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                stream=stream,
                timeout=self._timeout,
            )
            if r.status_code != 200:
                yield {"type": "error",
                       "content": f"OpenAI {r.status_code}: {r.text[:300]}"}
                return

            if not stream:
                yield from self._parse_non_stream(r.json())
                return

            # SSE streaming
            yield from self._parse_stream(r)

        except requests.exceptions.Timeout:
            yield {"type": "error",
                   "content": f"OpenAI timed out after {self._timeout}s"}
        except requests.exceptions.ConnectionError:
            yield {"type": "error",
                   "content": f"Cannot connect to {self._base_url}"}
        except Exception as exc:
            yield {"type": "error", "content": f"OpenAI error: {exc}"}

    # ── Internal helpers ──

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _safe_json(raw: str) -> dict:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    def _parse_non_stream(self, data: dict) -> Generator[dict, None, None]:
        usage = data.get("usage", {})
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message", {})

        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                yield {
                    "type": "tool_call",
                    "tool_call": {
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": self._safe_json(
                                tc["function"].get("arguments", "{}")),
                        },
                    },
                }

        content = msg.get("content", "")
        if content:
            yield {"type": "token", "content": content}

        yield {
            "type": "done",
            "eval_count": usage.get("completion_tokens", 0),
            "prompt_eval_count": usage.get("prompt_tokens", 0),
        }

    def _parse_stream(self, r) -> Generator[dict, None, None]:
        tool_calls: dict[int, dict] = {}  # index -> {name, arguments_str}
        tokens_out = 0

        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload.strip() == "[DONE]":
                break

            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue

            delta = (data.get("choices") or [{}])[0].get("delta", {})

            # Text content
            content = delta.get("content", "")
            if content:
                tokens_out += 1  # Approximate
                yield {"type": "token", "content": content}

            # Tool calls (streamed incrementally)
            for tc in delta.get("tool_calls", []):
                idx = tc.get("index", 0)
                if idx not in tool_calls:
                    tool_calls[idx] = {"name": "", "arguments": ""}
                fn = tc.get("function", {})
                if fn.get("name"):
                    tool_calls[idx]["name"] = fn["name"]
                if fn.get("arguments"):
                    tool_calls[idx]["arguments"] += fn["arguments"]

        # Emit accumulated tool calls in original index order
        for tc in [tool_calls[i] for i in sorted(tool_calls)]:
            try:
                args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                args = {}
            yield {
                "type": "tool_call",
                "tool_call": {"function": {"name": tc["name"],
                                           "arguments": args}},
            }

        # Usage not available in streaming mode for all providers
        yield {
            "type": "done",
            "eval_count": tokens_out,
            "prompt_eval_count": 0,
        }

    @staticmethod
    def _convert_tools(ollama_tools: list[dict]) -> list[dict]:
        """Convert Ollama tool format to OpenAI format.

        Ollama: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
        OpenAI: identical structure (Ollama adopted OpenAI's format)
        """
        # Ollama uses the same tool format as OpenAI, so minimal conversion
        converted = []
        for tool in ollama_tools:
            if isinstance(tool, dict) and "function" in tool:
                converted.append({
                    "type": "function",
                    "function": tool["function"],
                })
            elif isinstance(tool, dict) and "name" in tool:
                # Simplified format
                converted.append({
                    "type": "function",
                    "function": tool,
                })
        return converted
