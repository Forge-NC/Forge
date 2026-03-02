"""OllamaStub — fake Ollama HTTP server for integration testing.

A real HTTP server (not mocked) on localhost with a random port.
Serves all Ollama API endpoints with scripted, deterministic responses.
Supports chaos modes for network failure simulation.
"""

import json
import random
import hashlib
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from http.server import HTTPServer, BaseHTTPRequestHandler
from io import BytesIO
from typing import Optional


# ── Scripted response ──

@dataclass
class ScriptedTurn:
    """A single scripted LLM response."""
    text: str = ""
    tool_calls: list = field(default_factory=list)
    delay_ms: int = 0
    error_code: int = 0        # Non-zero = HTTP error
    timeout: bool = False      # Hang forever
    eval_count: int = 100
    prompt_eval_count: int = 200


class ChaosMode(Enum):
    NONE = "none"
    RANDOM_DELAY = "random_delay"    # 0-2s random delay per chunk
    RANDOM_DROP = "random_drop"      # Close connection mid-stream
    RANDOM_ERROR = "random_error"    # Return 500/503 randomly


# ── Default response ──

_DEFAULT_RESPONSE = ScriptedTurn(
    text="I understand. What would you like me to do next?",
    eval_count=50,
    prompt_eval_count=100,
)


class OllamaStubHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the Ollama stub."""

    # Suppress default logging
    def log_message(self, format, *args):
        pass

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length:
            return json.loads(self.rfile.read(length))
        return {}

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, status: int, msg: str = ""):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        body = json.dumps({"error": msg or f"HTTP {status}"}).encode()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        stub = self.server.stub  # type: OllamaStub

        if self.path == "/api/tags":
            models = [{"name": m, "size": 1_000_000}
                      for m in stub.models]
            self._send_json({"models": models})
            return

        if self.path == "/api/ps":
            models = [{"name": m} for m in stub.models[:1]]
            self._send_json({"models": models})
            return

        self._send_error(404, "Not found")

    def do_POST(self):
        stub = self.server.stub  # type: OllamaStub
        body = self._read_body()

        if self.path == "/api/chat":
            self._handle_chat(stub, body)
            return

        if self.path == "/api/embed":
            self._handle_embed(stub, body)
            return

        if self.path == "/api/show":
            self._handle_show(stub, body)
            return

        if self.path == "/api/pull":
            self._handle_pull(stub, body)
            return

        self._send_error(404, "Not found")

    def do_DELETE(self):
        if self.path == "/api/delete":
            self._read_body()
            self._send_json({"status": "success"})
            return
        self._send_error(404)

    # ── Endpoint handlers ──

    def _handle_chat(self, stub: 'OllamaStub', body: dict):
        """Stream a scripted chat response matching Ollama format."""
        stub.chat_call_count += 1

        # Get next scripted turn
        turn = stub._next_turn()

        # Apply chaos
        rng = random.Random(stub.chaos_seed + stub.chat_call_count)
        if stub.chaos_mode == ChaosMode.RANDOM_ERROR and rng.random() < 0.2:
            self._send_error(503, "Service temporarily unavailable")
            return

        # Scripted error
        if turn.error_code:
            self._send_error(turn.error_code, "Scripted error")
            return

        # Scripted timeout (hang)
        if turn.timeout:
            try:
                time.sleep(300)  # Will be interrupted by test timeout
            except Exception:
                pass
            return

        # Delay
        if turn.delay_ms > 0:
            time.sleep(turn.delay_ms / 1000.0)

        is_stream = body.get("stream", True)

        if not is_stream:
            # Non-streaming: single JSON response
            msg = {"role": "assistant", "content": turn.text}
            if turn.tool_calls:
                msg["tool_calls"] = [
                    {"function": tc} if "function" not in tc else tc
                    for tc in turn.tool_calls
                ]
            self._send_json({
                "message": msg,
                "done": True,
                "eval_count": turn.eval_count,
                "prompt_eval_count": turn.prompt_eval_count,
                "total_duration": 1_000_000,
            })
            return

        # Streaming response
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def write_line(data: dict):
            line = json.dumps(data) + "\n"
            chunk = f"{len(line.encode()):x}\r\n{line}\r\n"
            self.wfile.write(chunk.encode("utf-8"))
            self.wfile.flush()

        try:
            # Stream text in 3-word chunks
            if turn.text:
                words = turn.text.split()
                for i in range(0, len(words), 3):
                    chunk_text = " ".join(words[i:i+3])
                    if i + 3 < len(words):
                        chunk_text += " "

                    # Chaos: random delay
                    if stub.chaos_mode == ChaosMode.RANDOM_DELAY:
                        time.sleep(rng.uniform(0, 0.1))

                    # Chaos: random drop
                    if stub.chaos_mode == ChaosMode.RANDOM_DROP:
                        if rng.random() < 0.15:
                            return  # Close connection abruptly

                    write_line({
                        "message": {"role": "assistant", "content": chunk_text},
                        "done": False,
                    })

            # Tool calls are emitted in the done message
            done_msg = {"role": "assistant", "content": ""}
            if turn.tool_calls:
                done_msg["tool_calls"] = [
                    {"function": tc} if "function" not in tc else tc
                    for tc in turn.tool_calls
                ]

            write_line({
                "message": done_msg,
                "done": True,
                "eval_count": turn.eval_count,
                "prompt_eval_count": turn.prompt_eval_count,
                "total_duration": 1_000_000,
            })

            # End chunked encoding
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()

        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass  # Client disconnected

    def _handle_embed(self, stub: 'OllamaStub', body: dict):
        """Return deterministic embeddings or 503 if disabled."""
        if not stub.embed_enabled:
            self._send_error(503, "Embedding model not available")
            return

        inputs = body.get("input", [])
        if isinstance(inputs, str):
            inputs = [inputs]

        embeddings = []
        for text in inputs:
            # Deterministic 384-dim embedding from text hash
            h = hashlib.sha256(text.encode()).digest()
            rng = random.Random(int.from_bytes(h[:8], "big"))
            vec = [rng.gauss(0, 1) for _ in range(384)]
            # Normalize
            mag = sum(x*x for x in vec) ** 0.5
            vec = [x / mag for x in vec]
            embeddings.append(vec)

        self._send_json({"embeddings": embeddings})

    def _handle_show(self, stub: 'OllamaStub', body: dict):
        """Return model info including context length."""
        model = body.get("name", "")
        ctx_len = stub.context_lengths.get(model, 32768)
        self._send_json({
            "model_info": {
                "context_length": ctx_len,
            },
            "parameters": f"num_ctx {ctx_len}",
        })

    def _handle_pull(self, stub: 'OllamaStub', body: dict):
        """Fake model pull with progress."""
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        for pct in [0, 25, 50, 75, 100]:
            line = json.dumps({
                "status": "pulling",
                "total": 1000,
                "completed": pct * 10,
            }) + "\n"
            self.wfile.write(line.encode())
            self.wfile.flush()


class _StubHTTPServer(HTTPServer):
    """HTTPServer with a reference back to OllamaStub."""
    stub: 'OllamaStub' = None


class OllamaStub:
    """Controllable fake Ollama server.

    Usage:
        stub = OllamaStub()
        stub.start()
        # ... tests use stub.base_url ...
        stub.stop()
    """

    def __init__(self):
        self.models = ["stub-coder:14b"]
        self.context_lengths = {"stub-coder:14b": 32768}
        self.embed_enabled = True
        self.chaos_mode = ChaosMode.NONE
        self.chaos_seed = 42

        self._script: list[ScriptedTurn] = []
        self._script_index = 0
        self.chat_call_count = 0

        self._server: Optional[_StubHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.port = 0
        self.base_url = ""

    def set_script(self, turns: list[ScriptedTurn]):
        """Set the response script. Resets index."""
        self._script = list(turns)
        self._script_index = 0

    def set_default_response(self, turn: ScriptedTurn):
        """Set a single response that repeats forever."""
        self._script = [turn]
        self._script_index = 0

    def _next_turn(self) -> ScriptedTurn:
        """Get next scripted response, cycling default when exhausted."""
        if not self._script:
            return _DEFAULT_RESPONSE
        if self._script_index >= len(self._script):
            # If only one response, cycle it
            if len(self._script) == 1:
                return self._script[0]
            return _DEFAULT_RESPONSE
        turn = self._script[self._script_index]
        self._script_index += 1
        return turn

    def add_model(self, name: str, context_length: int = 32768):
        """Register an additional model."""
        if name not in self.models:
            self.models.append(name)
        self.context_lengths[name] = context_length

    def start(self):
        """Start the HTTP server on a random port."""
        self._server = _StubHTTPServer(("127.0.0.1", 0), OllamaStubHandler)
        self._server.stub = self
        self.port = self._server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        """Shut down the HTTP server."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def reset(self):
        """Reset state between tests."""
        self._script_index = 0
        self.chat_call_count = 0
        self.chaos_mode = ChaosMode.NONE
        self.embed_enabled = True
