"""Anthropic Claude LLM backend.

Uses raw requests — no anthropic SDK dependency. Handles Claude's
different message format (system prompt is a top-level parameter,
not a message role).

Environment variable: ANTHROPIC_API_KEY (or pass api_key directly).
"""

import json
import logging
import os
from typing import Generator

import requests

log = logging.getLogger(__name__)

_CTX_LENGTHS = {
    "claude-opus-4-6": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-haiku-4-5": 200_000,
    "claude-3-5-sonnet": 200_000,
    "claude-3-5-haiku": 200_000,
    "claude-3-opus": 200_000,
}


class AnthropicBackend:
    """Anthropic Messages API backend."""

    def __init__(self, model: str = "claude-sonnet-4-6",
                 api_key: str = "",
                 base_url: str = "https://api.anthropic.com",
                 timeout: float = 120.0):
        self.model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = requests.Session()
        self.num_ctx = None  # Ignored for cloud backends

    def is_available(self) -> bool:
        return bool(self._api_key)

    def list_models(self) -> list[str]:
        return sorted(_CTX_LENGTHS.keys())

    def get_context_length(self) -> int:
        for prefix, length in _CTX_LENGTHS.items():
            if self.model.startswith(prefix):
                return length
        return 200_000

    def chat(self, messages: list[dict],
             tools: list[dict] | None = None,
             temperature: float = 0.1,
             stream: bool = True,
             format: dict | None = None,
             ) -> Generator[dict, None, None]:
        """Messages API, yielding Forge-standard chunks."""
        if not self._api_key:
            yield {"type": "error", "content": "No ANTHROPIC_API_KEY set"}
            return

        # Claude uses system as a top-level parameter, not a message role
        system_text = ""
        user_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_text += msg.get("content", "") + "\n"
            else:
                user_messages.append({
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                })

        # Ensure messages alternate user/assistant (Claude requirement)
        user_messages = self._fix_alternation(user_messages)

        payload: dict = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": temperature,
            "stream": stream,
        }
        if system_text.strip():
            payload["system"] = system_text.strip()
        if user_messages:
            payload["messages"] = user_messages

        # Convert tools to Claude format
        if tools:
            payload["tools"] = self._convert_tools(tools)

        try:
            r = self._session.post(
                f"{self._base_url}/v1/messages",
                headers=self._headers(),
                json=payload,
                stream=stream,
                timeout=self._timeout,
            )
            if r.status_code != 200:
                yield {"type": "error",
                       "content": f"Anthropic {r.status_code}: {r.text[:300]}"}
                return

            if not stream:
                yield from self._parse_non_stream(r.json())
                return

            yield from self._parse_stream(r)

        except requests.exceptions.Timeout:
            yield {"type": "error",
                   "content": f"Anthropic timed out after {self._timeout}s"}
        except requests.exceptions.ConnectionError:
            yield {"type": "error",
                   "content": f"Cannot connect to {self._base_url}"}
        except Exception as exc:
            yield {"type": "error", "content": f"Anthropic error: {exc}"}

    # ── Internal helpers ──

    def _headers(self) -> dict:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    def _parse_non_stream(self, data: dict) -> Generator[dict, None, None]:
        usage = data.get("usage", {})

        for block in data.get("content", []):
            if block.get("type") == "text":
                yield {"type": "token", "content": block.get("text", "")}
            elif block.get("type") == "tool_use":
                yield {
                    "type": "tool_call",
                    "tool_call": {
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": block.get("input", {}),
                        },
                    },
                }

        yield {
            "type": "done",
            "eval_count": usage.get("output_tokens", 0),
            "prompt_eval_count": usage.get("input_tokens", 0),
        }

    def _parse_stream(self, r) -> Generator[dict, None, None]:
        tool_calls: list[dict] = []
        current_tool: dict | None = None
        current_tool_json = ""
        tokens_out = 0
        tokens_in = 0

        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload.strip() == "[DONE]":
                break

            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue

            event_type = event.get("type", "")

            if event_type == "message_start":
                # Capture input tokens from the opening message event
                msg_usage = event.get("message", {}).get("usage", {})
                tokens_in = msg_usage.get("input_tokens", tokens_in)

            elif event_type == "content_block_start":
                block = event.get("content_block", {})
                if block.get("type") == "tool_use":
                    current_tool = {"name": block.get("name", ""),
                                    "id": block.get("id", "")}
                    current_tool_json = ""

            elif event_type == "content_block_delta":
                delta = event.get("delta", {})
                if delta.get("type") == "text_delta":
                    text = delta.get("text", "")
                    if text:
                        tokens_out += 1
                        yield {"type": "token", "content": text}
                elif delta.get("type") == "input_json_delta":
                    current_tool_json += delta.get("partial_json", "")

            elif event_type == "content_block_stop":
                if current_tool:
                    try:
                        args = json.loads(current_tool_json) if current_tool_json else {}
                    except json.JSONDecodeError:
                        args = {}
                    tool_calls.append({
                        "name": current_tool["name"],
                        "arguments": args,
                    })
                    current_tool = None
                    current_tool_json = ""

            elif event_type == "message_delta":
                usage = event.get("usage", {})
                tokens_out = usage.get("output_tokens", tokens_out)

            elif event_type == "message_stop":
                break

        # Emit tool calls
        for tc in tool_calls:
            yield {
                "type": "tool_call",
                "tool_call": {"function": tc},
            }

        yield {
            "type": "done",
            "eval_count": tokens_out,
            "prompt_eval_count": tokens_in,
        }

    @staticmethod
    def _fix_alternation(messages: list[dict]) -> list[dict]:
        """Ensure messages alternate user/assistant (Claude requirement)."""
        if not messages:
            return [{"role": "user", "content": "(empty)"}]

        fixed = []
        prev_role = None
        for msg in messages:
            role = msg["role"]
            if role == prev_role:
                # Merge consecutive same-role messages
                fixed[-1]["content"] += "\n" + msg["content"]
            else:
                fixed.append(dict(msg))
                prev_role = role

        # Must start with user
        if fixed and fixed[0]["role"] != "user":
            fixed.insert(0, {"role": "user", "content": "(context)"})

        return fixed

    @staticmethod
    def _convert_tools(ollama_tools: list[dict]) -> list[dict]:
        """Convert Ollama/OpenAI tool format to Anthropic format.

        Ollama: {"type": "function", "function": {"name", "description", "parameters"}}
        Claude: {"name", "description", "input_schema"}
        """
        converted = []
        for tool in ollama_tools:
            fn = tool.get("function", tool)
            converted.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object"}),
            })
        return converted
