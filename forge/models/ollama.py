"""Ollama LLM backend with tool-use support.

Handles streaming responses, tool calls, and token counting
from a local Ollama instance.
"""

import json
import re
import time
import logging
from typing import Generator, Optional

import requests

log = logging.getLogger(__name__)

# Default model — Qwen2.5-Coder-14B at Q4_K_M fits 16GB VRAM
DEFAULT_MODEL = "qwen2.5-coder:14b"
OLLAMA_BASE = "http://localhost:11434"


class OllamaBackend:
    """Interface to a local Ollama instance."""

    def __init__(self, model: str = DEFAULT_MODEL,
                 base_url: str = OLLAMA_BASE,
                 timeout: float = 120.0):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.num_ctx = None          # Set by engine after VRAM calc
        self.kv_cache_type = None    # "fp16", "q8_0", or "q4_0"
        self._session = requests.Session()

    def is_available(self) -> bool:
        """Check if Ollama is running and the model is loaded."""
        try:
            r = self._session.get(
                f"{self.base_url}/api/tags", timeout=5)
            if r.status_code != 200:
                return False
            models = r.json().get("models", [])
            names = [m.get("name", "") for m in models]
            # Check if our model (or a prefix match) is available
            return any(self.model in n for n in names)
        except Exception:
            return False

    def list_models(self) -> list[str]:
        """List all available models."""
        try:
            r = self._session.get(
                f"{self.base_url}/api/tags", timeout=5)
            models = r.json().get("models", [])
            return [m["name"] for m in models]
        except Exception:
            return []

    def pull_model(self, model: str = None) -> Generator[str, None, None]:
        """Pull a model, yielding progress lines."""
        model = model or self.model
        r = self._session.post(
            f"{self.base_url}/api/pull",
            json={"name": model, "stream": True},
            stream=True, timeout=600,
        )
        for line in r.iter_lines():
            if line:
                data = json.loads(line)
                status = data.get("status", "")
                total = data.get("total", 0)
                completed = data.get("completed", 0)
                if total:
                    pct = (completed / total) * 100
                    yield f"{status}: {pct:.0f}%"
                else:
                    yield status

    def count_tokens(self, text: str) -> int:
        """Count tokens using Ollama's tokenize endpoint.

        Falls back to approximation if endpoint unavailable.
        """
        try:
            r = self._session.post(
                f"{self.base_url}/api/embed",
                json={"model": self.model, "input": text},
                timeout=10,
            )
            if r.status_code == 200:
                # The embed response includes token count
                tokens = r.json().get("prompt_eval_count", 0)
                if tokens:
                    return tokens
        except Exception:
            pass
        # Fallback: ~4 chars per token for English/code
        return max(1, len(text) // 4)

    def _unload_model(self, model_name: str):
        """Ask Ollama to unload a model from VRAM (keep_alive=0)."""
        try:
            self._session.post(
                f"{self.base_url}/api/generate",
                json={"model": model_name, "keep_alive": 0},
                timeout=10,
            )
        except Exception:
            pass

    def embed(self, texts, embed_model: str = "nomic-embed-text",
              keep_alive: str = "0") -> list[list[float]]:
        """Generate embeddings for one or more texts.

        Uses keep_alive=0 by default so the embed model unloads immediately
        after use, freeing VRAM for the main LLM. For batch operations (>5
        texts), temporarily unloads the main LLM first and keeps the embed
        model loaded across sub-batches for speed.

        Args:
            texts: A single string or list of strings to embed.
            embed_model: Ollama model to use for embeddings.
            keep_alive: How long to keep the model loaded.

        Returns:
            List of embedding vectors (list of list of float).
            Empty list on failure.
        """
        if isinstance(texts, str):
            texts = [texts]

        # For batch embedding (indexing), free VRAM by unloading the main LLM.
        # It reloads automatically on the next chat/generate call.
        batch_mode = len(texts) > 5
        if batch_mode:
            self._unload_model(self.model)
            import time as _time
            # AMD/ROCm needs longer to release VRAM than NVIDIA/CUDA.
            # 2s is safe for both; 0.5s caused persistent 500 errors on ROCm.
            _time.sleep(2.0)

        BATCH_SIZE = 10  # Small batches to avoid context overflow on embed models
        all_embeddings: list[list[float]] = []
        total_batches = (len(texts) + BATCH_SIZE - 1) // BATCH_SIZE

        try:
            for batch_idx, i in enumerate(range(0, len(texts), BATCH_SIZE)):
                batch = texts[i:i + BATCH_SIZE]
                is_last_batch = (batch_idx == total_batches - 1)

                # In batch mode, keep embed model loaded between sub-batches
                # and only unload on the last one
                if batch_mode and not is_last_batch:
                    batch_keep_alive = "5m"
                else:
                    batch_keep_alive = keep_alive

                # Try new API first (/api/embed with "input" field)
                r = self._session.post(
                    f"{self.base_url}/api/embed",
                    json={
                        "model": embed_model,
                        "input": batch,
                        "keep_alive": batch_keep_alive,
                    },
                    timeout=max(self.timeout, 300),
                )

                if r.status_code == 404:
                    # Old Ollama: fall back to /api/embeddings (one at a time)
                    for text in batch:
                        r2 = self._session.post(
                            f"{self.base_url}/api/embeddings",
                            json={
                                "model": embed_model,
                                "prompt": text,
                            },
                            timeout=self.timeout,
                        )
                        if r2.status_code != 200:
                            log.warning("Embed request failed: %s %s",
                                        r2.status_code, r2.text[:200])
                            return []
                        emb = r2.json().get("embedding", [])
                        if emb:
                            all_embeddings.append(emb)
                    continue

                if r.status_code == 500:
                    # VRAM OOM — retry with exponential backoff.
                    # AMD/ROCm needs significantly longer than NVIDIA/CUDA to
                    # release VRAM after an unload; a single 1s retry is not
                    # enough and causes persistent 500 OOM on ROCm hardware.
                    import time as _time2
                    self._unload_model(self.model)
                    for _retry in range(3):
                        _wait = 2 ** (_retry + 1)  # 2s, 4s, 8s
                        log.info(
                            "Embed 500 (VRAM OOM) on batch %d/%d, "
                            "retry %d/3 in %ds",
                            batch_idx + 1, total_batches, _retry + 1, _wait)
                        _time2.sleep(_wait)
                        r = self._session.post(
                            f"{self.base_url}/api/embed",
                            json={
                                "model": embed_model,
                                "input": batch,
                                "keep_alive": batch_keep_alive,
                            },
                            timeout=max(self.timeout, 300),
                        )
                        if r.status_code == 200:
                            break
                        if r.status_code != 500:
                            break  # Different error — let checks below handle it

                if r.status_code == 400:
                    # Input too long for context — fall back to one-at-a-time
                    log.info("Batch embed 400 (context overflow), "
                             "falling back to individual embedding for "
                             "batch %d/%d (%d texts)",
                             batch_idx + 1, total_batches, len(batch))
                    for text in batch:
                        # Truncate aggressively if still too long
                        truncated = text[:2000]
                        r3 = self._session.post(
                            f"{self.base_url}/api/embed",
                            json={
                                "model": embed_model,
                                "input": truncated,
                                "keep_alive": batch_keep_alive,
                            },
                            timeout=self.timeout,
                        )
                        if r3.status_code != 200:
                            log.warning(
                                "Individual embed failed (%d), skipping "
                                "chunk (%.30s...)",
                                r3.status_code,
                                truncated[:30])
                            # Use zero vector as placeholder
                            all_embeddings.append([])
                            continue
                        data3 = r3.json()
                        embs = data3.get("embeddings", [])
                        if embs:
                            all_embeddings.append(embs[0])
                        else:
                            single3 = data3.get("embedding", [])
                            all_embeddings.append(single3 if single3 else [])
                    continue

                if r.status_code != 200:
                    # Don't abort the entire call — substitute empty vectors
                    # so the caller receives exactly len(texts) results.
                    # index.py replaces empty vectors with zero-vectors,
                    # keeping the index aligned and letting other batches land.
                    log.warning(
                        "Embed batch %d/%d failed (%d) — substituting "
                        "empty vectors for %d chunks",
                        batch_idx + 1, total_batches,
                        r.status_code, len(batch))
                    all_embeddings.extend([[] for _ in batch])
                    continue

                data = r.json()
                # New Ollama: "embeddings" (plural, list of vectors)
                embeddings = data.get("embeddings", [])
                if not embeddings:
                    # Some versions return "embedding" (singular)
                    single = data.get("embedding", [])
                    if single:
                        embeddings = [single]
                all_embeddings.extend(embeddings)

                if batch_mode and total_batches > 1:
                    log.info("Embedded batch %d/%d (%d chunks)",
                             batch_idx + 1, total_batches, len(batch))

        except Exception as e:
            log.warning("Embedding failed: %s", e)
            return []

        return all_embeddings

    def ensure_embed_model(self, embed_model: str = "nomic-embed-text",
                           auto_pull: bool = False) -> bool:
        """Check if an embedding model is available, optionally pulling it.

        Args:
            embed_model: Name of the embedding model to check for.
            auto_pull: If True, pull the model when it is not found.

        Returns:
            True if the model is available (or was successfully pulled).
        """
        available = self.list_models()
        if any(embed_model in name for name in available):
            return True

        if not auto_pull:
            return False

        # Pull the model
        log.info("Pulling embedding model: %s", embed_model)
        for progress in self.pull_model(embed_model):
            print(progress)

        # Verify it's now available
        available = self.list_models()
        return any(embed_model in name for name in available)

    def get_context_length(self) -> int:
        """Get the model's context length from Ollama."""
        try:
            r = self._session.post(
                f"{self.base_url}/api/show",
                json={"name": self.model},
                timeout=10,
            )
            if r.status_code == 200:
                params = r.json().get("model_info", {})
                # Different model architectures store this differently
                for key in params:
                    if "context_length" in key.lower():
                        return int(params[key])
                # Fallback: check modelfile parameters
                modelfile = r.json().get("modelfile", "")
                m = re.search(r"num_ctx\s+(\d+)", modelfile)
                if m:
                    return int(m.group(1))
        except Exception:
            pass
        return 32768  # Conservative default

    def chat(self, messages: list[dict],
             tools: list[dict] = None,
             temperature: float = 0.1,
             stream: bool = True,
             format: dict = None) -> Generator[dict, None, None]:
        """Send a chat request, yielding response chunks.

        Each yielded dict has:
          - "type": "token" | "tool_call" | "done" | "error"
          - "content": str (for tokens)
          - "tool_call": dict (for tool calls)
          - "eval_count": int (for done — tokens generated)
          - "prompt_eval_count": int (for done — tokens in prompt)

        Args:
            format: JSON schema dict for constrained decoding via Ollama's
                    GBNF grammar enforcement. When set, forces the model to
                    output valid JSON matching the schema. Cannot be used
                    simultaneously with tools (they conflict).
        """
        # Thinking/reasoning models (qwen3, deepseek-r1, qwq) consume large
        # token budgets on internal <think> blocks before producing output.
        # 4096 is far too small — raise the cap so they have room to act.
        _model_lower = self.model.lower()
        _is_thinking = any(x in _model_lower for x in
                           ("qwen3", "qwq", "deepseek-r1", "deepseek-r2",
                            "thinking", "reason"))
        num_predict = 32768 if _is_thinking else 8192

        options = {
            "temperature": temperature,
            "num_predict": num_predict,
        }
        # Set context window size if calculated from VRAM
        if self.num_ctx:
            options["num_ctx"] = self.num_ctx

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": options,
        }
        if format:
            # Constrained decoding — force JSON schema output.
            # Don't also send tools (format forces text output,
            # tools expects structured tool_calls — they conflict).
            payload["format"] = format
        elif tools:
            payload["tools"] = tools

        try:
            r = self._session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                stream=stream,
                timeout=self.timeout,
            )
            if r.status_code != 200:
                yield {
                    "type": "error",
                    "content": f"Ollama returned {r.status_code}: {r.text[:200]}",
                }
                return

            if not stream:
                data = r.json()
                msg = data.get("message", {})
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        yield {
                            "type": "tool_call",
                            "tool_call": tc,
                        }
                elif msg.get("content"):
                    yield {"type": "token", "content": msg["content"]}
                yield {
                    "type": "done",
                    "eval_count": data.get("eval_count", 0),
                    "prompt_eval_count": data.get("prompt_eval_count", 0),
                }
                return

            # Streaming mode
            full_content = ""
            tool_calls = []
            for line in r.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                msg = data.get("message", {})

                if msg.get("tool_calls"):
                    tool_calls.extend(msg["tool_calls"])

                content = msg.get("content", "")
                if content:
                    full_content += content
                    yield {"type": "token", "content": content}

                if data.get("done"):
                    for tc in tool_calls:
                        yield {"type": "tool_call", "tool_call": tc}
                    yield {
                        "type": "done",
                        "eval_count": data.get("eval_count", 0),
                        "prompt_eval_count": data.get("prompt_eval_count", 0),
                        "total_duration_ns": data.get("total_duration", 0),
                    }
                    return

        except requests.exceptions.Timeout:
            yield {
                "type": "error",
                "content": f"Ollama request timed out after {self.timeout}s",
            }
        except requests.exceptions.ConnectionError:
            yield {
                "type": "error",
                "content": "Cannot connect to Ollama. Is it running? "
                           f"Expected at {self.base_url}",
            }
        except Exception as e:
            yield {"type": "error", "content": f"Ollama error: {e}"}
