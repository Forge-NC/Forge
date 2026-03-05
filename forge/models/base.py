"""Abstract base for LLM backends — enables multi-provider benchmarking.

Any backend that implements this protocol can be used with the benchmark
execution bridge, quality scorer, and AMI retry system.
"""

import logging
from typing import Generator, Protocol, runtime_checkable

log = logging.getLogger(__name__)


@runtime_checkable
class LLMBackend(Protocol):
    """Minimal interface every LLM backend must implement.

    The chat() generator yields dicts with:
      {"type": "token",     "content": str}
      {"type": "tool_call", "tool_call": dict}
      {"type": "done",      "eval_count": int, "prompt_eval_count": int}
      {"type": "error",     "content": str}
    """

    model: str

    def chat(self, messages: list[dict],
             tools: list[dict] | None = None,
             temperature: float = 0.1,
             stream: bool = True,
             format: dict | None = None,
             ) -> Generator[dict, None, None]: ...

    def list_models(self) -> list[str]: ...

    def is_available(self) -> bool: ...

    def get_context_length(self) -> int: ...


def collect_response(backend: LLMBackend, messages: list[dict],
                     tools: list[dict] | None = None,
                     temperature: float = 0.1,
                     ) -> dict:
    """Convenience: call chat() and collect the full response.

    Returns:
        {
            "text": str,
            "tool_calls": list[dict],
            "tokens_in": int,
            "tokens_out": int,
            "error": str | None,
        }
    """
    text = ""
    tool_calls: list[dict] = []
    tokens_in = 0
    tokens_out = 0
    error = None

    try:
        for chunk in backend.chat(messages, tools=tools,
                                  temperature=temperature, stream=False):
            if chunk["type"] == "token":
                text += chunk.get("content", "")
            elif chunk["type"] == "tool_call":
                tool_calls.append(chunk["tool_call"])
            elif chunk["type"] == "done":
                tokens_in = chunk.get("prompt_eval_count", 0)
                tokens_out = chunk.get("eval_count", 0)
            elif chunk["type"] == "error":
                error = chunk.get("content", "unknown error")
    except Exception as exc:
        error = str(exc)

    return {
        "text": text,
        "tool_calls": tool_calls,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "error": error,
    }
