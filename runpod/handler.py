"""
Forge Certified Audit — RunPod Serverless Handler

Receives job input from the Forge audit orchestrator, runs a full
Forge Parallax dual-attestation audit (Break + Assurance) against the
customer's model endpoint, uploads signed reports, and returns results.

The Origin Ed25519 key is NOT on this worker. Reports are signed with
a per-worker machine key here, then Origin-certified server-side by
the orchestrator callback.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path

import requests
import runpod

# ── Chat template resolution for models missing tokenizer chat_template ──

_CHAT_TEMPLATES = {
    "llama2": (
        "{% if messages[0]['role'] == 'system' %}"
        "{% set system_message = '<<SYS>>\\n' + messages[0]['content'] | trim + '\\n<</SYS>>\\n\\n' %}"
        "{% set messages = messages[1:] %}"
        "{% else %}{% set system_message = '' %}{% endif %}"
        "{% for message in messages %}"
        "{% if message['role'] == 'user' %}"
        "{{ bos_token + '[INST] ' + (system_message if loop.index0 == 0 else '') + message['content'] | trim + ' [/INST]' }}"
        "{% elif message['role'] == 'assistant' %}"
        "{{ ' ' + message['content'] | trim + ' ' + eos_token }}"
        "{% endif %}{% endfor %}"
    ),
    "mistral_v7": (
        "{{ bos_token }}"
        "{% if messages[0]['role'] == 'system' %}"
        "{{ '[SYSTEM_PROMPT]' + messages[0]['content'] + '[/SYSTEM_PROMPT]' }}"
        "{% set loop_messages = messages[1:] %}"
        "{% else %}"
        "{{ '[SYSTEM_PROMPT]You are a helpful assistant.[/SYSTEM_PROMPT]' }}"
        "{% set loop_messages = messages %}"
        "{% endif %}"
        "{% for message in loop_messages %}"
        "{% if message['role'] == 'user' %}"
        "{{ '[INST]' + message['content'] + '[/INST]' }}"
        "{% elif message['role'] == 'assistant' %}"
        "{{ message['content'] + eos_token }}"
        "{% endif %}"
        "{% endfor %}"
    ),
    "mistral": (
        "{% if messages[0]['role'] == 'system' %}"
        "{% set system_message = messages[0]['content'] | trim + '\\n\\n' %}"
        "{% set messages = messages[1:] %}"
        "{% else %}{% set system_message = '' %}{% endif %}"
        "{% for message in messages %}"
        "{% if message['role'] == 'user' %}"
        "{{ bos_token + '[INST] ' + (system_message if loop.index0 == 0 else '') + message['content'] | trim + ' [/INST]' }}"
        "{% elif message['role'] == 'assistant' %}"
        "{{ ' ' + message['content'] | trim + eos_token }}"
        "{% endif %}{% endfor %}"
    ),
    "chatml": (
        "{% for message in messages %}"
        "{{'<|im_start|>' + message['role'] + '\\n' + message['content'] + '<|im_end|>' + '\\n'}}"
        "{% endfor %}"
        "{% if add_generation_prompt %}{{ '<|im_start|>assistant\\n' }}{% endif %}"
    ),
    "vicuna": (
        "{% if messages[0]['role'] == 'system' %}"
        "{{ bos_token + messages[0]['content'] | trim + '\\n\\n' }}"
        "{% set messages = messages[1:] %}"
        "{% else %}{{ bos_token }}{% endif %}"
        "{% for message in messages %}"
        "{% if message['role'] == 'user' %}{{ 'USER: ' + message['content'] | trim + '\\n' }}"
        "{% elif message['role'] == 'assistant' %}{{ 'ASSISTANT: ' + message['content'] | trim + eos_token + '\\n' }}"
        "{% endif %}{% endfor %}"
        "{% if add_generation_prompt %}{{ 'ASSISTANT:' }}{% endif %}"
    ),
    "alpaca": (
        "{% if messages[0]['role'] == 'system' %}"
        "{{ bos_token + messages[0]['content'] + '\\n\\n' }}{% set messages = messages[1:] %}"
        "{% else %}{{ bos_token + 'Below is an instruction that describes a task. Write a response that appropriately completes the request.\\n\\n' }}"
        "{% endif %}"
        "{% for message in messages %}"
        "{% if message['role'] == 'user' %}{{ '### Instruction:\\n' + message['content'] | trim + '\\n\\n' }}"
        "{% elif message['role'] == 'assistant' %}{{ '### Response:\\n' + message['content'] | trim + eos_token + '\\n\\n' }}"
        "{% endif %}{% endfor %}"
        "{% if add_generation_prompt %}{{ '### Response:\\n' }}{% endif %}"
    ),
}

# Model name patterns -> template family (checked when tokenizer has no chat_template)
_MODEL_TEMPLATE_MAP = [
    # Llama 2 family
    (r"llama-2.*chat", "llama2"),
    (r"codellama.*instruct", "llama2"),
    (r"airoboros", "llama2"),
    # Mistral family
    (r"mistral.*instruct.*v0\.1", "mistral"),
    (r"mistral.*small.*instruct", "mistral_v7"),
    (r"mistral.*instruct.*2501", "mistral_v7"),
    # ChatML family
    (r"openhermes", "chatml"),
    (r"dolphin", "chatml"),
    (r"nous-hermes", "chatml"),
    # Vicuna family
    (r"vicuna", "vicuna"),
    (r"wizard-vicuna", "vicuna"),
    (r"wizardlm.*uncensored", "vicuna"),
    # Alpaca family
    (r"wizardcoder", "alpaca"),
    (r"phind-codellama", "alpaca"),
    (r"synthia", "alpaca"),
]

# Base models that should NOT be chat-tested (no instruct tuning)
_BASE_MODEL_SKIP = [
    r"google/gemma-2b-AWQ",      # base gemma, not gemma-it
    r"meditron-7B-AWQ",          # medical foundation model, not chat-tuned
]

import re as _re


def _resolve_chat_template(model_path: str, hf_repo: str) -> str | None:
    """Check if model needs a chat template and return path to .jinja file if so.

    Returns None if the model already has a template or if it's a base model
    that shouldn't be used for chat.
    """
    # Check if tokenizer already has a chat template
    tok_cfg_path = Path(model_path) / "tokenizer_config.json"
    if tok_cfg_path.exists():
        try:
            tok_data = json.loads(tok_cfg_path.read_text())
            if tok_data.get("chat_template"):
                return None  # already has one
        except Exception:
            pass

    # Check if it's a base model we should skip
    for pattern in _BASE_MODEL_SKIP:
        if _re.search(pattern, hf_repo, _re.IGNORECASE):
            log.warning("Skipping base model (not chat-tuned): %s", hf_repo)
            return None

    # Match model name against known template families
    model_lower = hf_repo.lower()
    for pattern, family in _MODEL_TEMPLATE_MAP:
        if _re.search(pattern, model_lower):
            template_str = _CHAT_TEMPLATES.get(family)
            if template_str:
                tpl_path = Path(f"/tmp/.forge/chat_template_{family}.jinja")
                tpl_path.write_text(template_str)
                log.info("Model %s matched template family '%s'", hf_repo, family)
                return str(tpl_path)

    # Unknown model without template — use ChatML as last resort
    # ChatML is the most widely compatible format
    log.warning("Model %s has no chat template and no known family match — using ChatML fallback", hf_repo)
    tpl_path = Path("/tmp/.forge/chat_template_chatml_fallback.jinja")
    tpl_path.write_text(_CHAT_TEMPLATES["chatml"])
    return str(tpl_path)


# Detect capabilities — slim image has no vLLM/torch
try:
    import vllm  # noqa: F401
    HAS_VLLM = True
except ImportError:
    HAS_VLLM = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("forge.audit.worker")

# Forge config dir for this worker
FORGE_CONFIG_DIR = Path("/tmp/.forge")
FORGE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Direct API endpoint (bypasses Cloudflare) for handler-to-server POSTs.
# The main forge-nc.dev domain is Cloudflare-protected and blocks datacenter IPs.
# api.forge-nc.dev is DNS-only (gray cloud), goes straight to origin.
# All requests must include X-Forge-Api-Secret header for auth.
# Secret is passed via FORGE_API_SECRET env var (set in RunPod template).
FORGE_API_SERVER = "http://api.forge-nc.dev"
FORGE_API_SECRET = os.environ.get("FORGE_API_SECRET", "")


# ── vLLM Engine: shared startup with fallback chain, error capture, pre-flight ──

# Known vLLM error patterns → (error_class, human message)
_VLLM_ERROR_PATTERNS = [
    ("torch.cuda.OutOfMemoryError",      "oom",            "Model requires more VRAM than available on this GPU tier"),
    ("CUDA out of memory",               "oom",            "Model requires more VRAM than available on this GPU tier"),
    ("Cannot convert to Marlin",         "marlin_compat",  "AWQ model uses old format incompatible with Marlin kernel — retrying with non-Marlin backend"),
    ("marlin",                           "marlin_compat",  "AWQ Marlin kernel error — retrying with non-Marlin backend"),
    ("not supported",                    "unsupported",    "Model architecture or quantization not supported by vLLM"),
    ("KeyError: 'model_type'",           "unsupported",    "Model config missing 'model_type' — possibly corrupted or unsupported"),
    ("Quantization method",              "quant_format",   "Quantization format not recognized by vLLM"),
    ("RuntimeError: weight",             "weight_format",  "Model weight tensor shapes don't match expected architecture"),
    ("NCCL error",                       "multi_gpu",      "Multi-GPU communication failed (NCCL) — transient, retrying"),
    ("ProcessGroupNCCL",                 "multi_gpu",      "Multi-GPU communication failed (NCCL) — transient, retrying"),
    ("FileNotFoundError",                "missing_file",   "Required model file not found after download"),
    ("trust_remote_code",                "trust_code",     "Model requires custom code that failed to load"),
    ("max_model_len",                    "max_model_len",  "Requested context length exceeds model's maximum"),
    ("max_position_embeddings",          "max_model_len",  "Requested context length exceeds model's maximum"),
    ("does not recognize this architecture", "unsupported", "Model architecture not recognized by installed transformers version"),
]


class VllmOutputCapture:
    """Thread-safe ring buffer capturing the last N lines of vLLM output."""

    def __init__(self, maxlines: int = 80):
        import threading
        self._lines: list[str] = []
        self._maxlines = maxlines
        self._lock = threading.Lock()

    def add(self, line: str):
        with self._lock:
            self._lines.append(line)
            if len(self._lines) > self._maxlines:
                self._lines = self._lines[-self._maxlines:]

    def get_lines(self, n: int = 30) -> list[str]:
        with self._lock:
            return list(self._lines[-n:])

    def classify_error(self, exit_code: int = -1) -> dict:
        """Classify the vLLM failure from captured output."""
        lines = self.get_lines(50)
        full_text = "\n".join(lines)
        for pattern, error_class, message in _VLLM_ERROR_PATTERNS:
            if pattern.lower() in full_text.lower():
                return {"error_class": error_class, "error": message,
                        "vllm_exit_code": exit_code, "vllm_last_lines": lines[-20:]}
        return {"error_class": "unknown", "error": f"vLLM exited with code {exit_code}",
                "vllm_exit_code": exit_code, "vllm_last_lines": lines[-20:]}


def _resolve_stop_tokens(model_path: str, hf_repo: str = "") -> list[str]:
    """Resolve the correct stop tokens for a model from its tokenizer config.

    Reads tokenizer_config.json and extracts eos_token + special added tokens.
    Falls back to a universal stop token list if config can't be parsed.
    """
    universal = [
        "<|im_end|>",       # ChatML (Qwen, OpenHermes, Dolphin)
        "<|eot_id|>",       # Llama 3.x
        "</s>",             # Llama 2, Mistral, many others
        "<|end|>",          # Phi-3/4
        "<|endoftext|>",    # GPT-NeoX, Phi, Qwen
        "<end_of_turn>",    # Gemma
        "[|endofturn|]",    # EXAONE
    ]
    try:
        import json as _json
        cfg_path = Path(model_path) / "tokenizer_config.json"
        if not cfg_path.exists():
            log.info("No tokenizer_config.json at %s — using universal stop tokens", model_path)
            return universal

        cfg = _json.loads(cfg_path.read_text())
        tokens = set()

        # Extract eos_token
        eos = cfg.get("eos_token")
        if isinstance(eos, str) and eos.strip():
            tokens.add(eos.strip())
        elif isinstance(eos, dict):
            tokens.add(eos.get("content", "").strip())

        # Extract special added tokens (chat template boundaries)
        for tid, tdata in cfg.get("added_tokens_decoder", {}).items():
            if tdata.get("special") and tdata.get("content"):
                content = tdata["content"].strip()
                # Include end-of-turn markers and role boundary tokens
                if any(marker in content.lower() for marker in
                       ["end", "eot", "eos", "turn", "im_end", "stop",
                        "inst", "assistant", "user", "system"]):
                    tokens.add(content)

        if tokens:
            result = sorted(tokens)
            log.info("Resolved stop tokens for %s: %s", hf_repo or model_path, result)
            return result

    except Exception as exc:
        log.warning("Failed to parse tokenizer config for stop tokens: %s", exc)

    log.info("Using universal stop token fallback for %s", hf_repo or model_path)
    return universal


# Architectures that vLLM supports natively — no custom code needed.
# If a model has auto_map pointing to custom code for one of these,
# strip it so vLLM uses its own optimized implementation instead of
# potentially broken custom code from the HuggingFace repo.
_VLLM_NATIVE_ARCHITECTURES = {
    "LlamaForCausalLM", "MistralForCausalLM", "Qwen2ForCausalLM",
    "Qwen3ForCausalLM", "Phi3ForCausalLM", "Gemma2ForCausalLM",
    "ExaoneForCausalLM", "DeepseekV2ForCausalLM", "DeepseekV3ForCausalLM",
    "FalconForCausalLM", "GPTNeoXForCausalLM", "MptForCausalLM",
    "StableLmForCausalLM", "StarcoderForCausalLM", "ChatGLMForCausalLM",
    "InternLMForCausalLM", "InternLM2ForCausalLM", "BaichuanForCausalLM",
    "MixtralForCausalLM", "OlmoForCausalLM", "Phi3SmallForCausalLM",
    "CohereForCausalLM", "DbrxForCausalLM", "JambaForCausalLM",
    "ArcticForCausalLM", "GraniteForCausalLM",
    # GLM family (vLLM 0.19+)
    "Glm4MoeLiteForCausalLM", "Glm4MoeForCausalLM", "ChatGLMModel",
}


def _is_vllm_known_arch(model_path: str) -> bool:
    """Check if vLLM recognizes this model's architecture natively.

    Reads architectures from config.json and checks against vLLM's model
    registry. If vLLM knows the architecture, it can handle chat templates,
    stop tokens, and other model-specific configuration itself.
    """
    try:
        cfg = json.loads((Path(model_path) / "config.json").read_text())
        archs = cfg.get("architectures", [])
        if not archs:
            return False
        # Check if ANY of the model's architectures are in our known set
        # OR if vLLM's model registry can resolve it
        if any(a in _VLLM_NATIVE_ARCHITECTURES for a in archs):
            return True
        # Also try vLLM's own registry
        if HAS_VLLM:
            try:
                from vllm.model_executor.models import ModelRegistry
                for a in archs:
                    if ModelRegistry.is_text_generation_model(a):
                        return True
            except Exception:
                pass
        return False
    except Exception:
        return False


def _strip_auto_map_if_native(model_path: str) -> bool:
    """Strip auto_map from config.json if vLLM has native support for the architecture.

    Many HuggingFace model repos include custom modeling code via auto_map
    that was written for a specific transformers version. When the Docker image
    has a different transformers version, this custom code crashes on import —
    even though vLLM has its own native implementation that works fine.

    Returns True if auto_map was stripped.
    """
    config_path = Path(model_path) / "config.json"
    if not config_path.exists():
        return False

    try:
        config = json.loads(config_path.read_text())
    except Exception:
        return False

    auto_map = config.get("auto_map", {})
    if not auto_map:
        return False

    # Check if the architecture is natively supported
    architectures = config.get("architectures", [])
    if not architectures:
        return False

    arch = architectures[0]
    if arch not in _VLLM_NATIVE_ARCHITECTURES:
        log.info("Model %s has auto_map with non-native arch %s — keeping custom code", model_path, arch)
        return False

    # Back up original config (transformers fallback may need auto_map restored)
    config_bak = Path(model_path) / "config.json.vllm_bak"
    if not config_bak.exists():
        import shutil
        shutil.copy2(str(config_path), str(config_bak))

    # Strip auto_map so vLLM uses its native implementation
    del config["auto_map"]
    config_path.write_text(json.dumps(config, indent=2))
    log.info("Stripped auto_map from %s — vLLM has native %s support (backup at config.json.vllm_bak)", model_path, arch)
    return True


def _start_vllm_with_fallback(
    model_path: str,
    hf_repo: str,
    gpu_count: int,
    per_gpu_gb: float,
    custom_env: dict | None = None,
    custom_flags: str = "",
    max_startup_minutes: int = 30,
) -> tuple["subprocess.Popen | None", "VllmOutputCapture", str, list[str], str | None]:
    """Start vLLM with a fallback chain. Returns (proc, capture, served_model, stop_tokens, error).

    Fallback chain:
      1. Default vLLM config
      2. Explicit --quantization awq (if Marlin fails)
      3. Reduced --max-model-len 2048 (if OOM)
      4. --dtype float16 --enforce-eager (last resort)

    If all attempts fail, returns (None, capture, "", [], error_string).
    """
    import subprocess
    import threading
    import urllib.request
    import urllib.error

    capture = VllmOutputCapture()

    # Strip auto_map from config.json if vLLM has native support for the architecture.
    # Prevents crashes from broken custom code in HuggingFace repos.
    _strip_auto_map_if_native(model_path)

    stop_tokens = _resolve_stop_tokens(model_path, hf_repo)

    # Resolve chat template
    tpl = _resolve_chat_template(model_path, hf_repo)

    # Base environment
    env = os.environ.copy()
    env["VLLM_WORKER_MULTIPROC_METHOD"] = "spawn"
    env["VLLM_MARLIN_USE_ATOMIC_ADD"] = "1"
    env["VLLM_USE_DEEP_GEMM"] = "0"
    env["TORCH_ALLOW_TF32_CUBLAS_OVERRIDE"] = "1"
    if custom_env:
        env.update(custom_env)

    # Base command
    base_cmd = [
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--model", model_path,
        "--host", "0.0.0.0", "--port", "8199",
        "--trust-remote-code",
        "--gpu-memory-utilization", "0.95",
        "--enforce-eager",
    ]
    if gpu_count > 1:
        base_cmd += ["--tensor-parallel-size", str(gpu_count)]
    # Only force a chat template if the model doesn't have one natively.
    # vLLM handles templates for models it recognizes — overriding with a
    # generic fallback template (e.g. ChatML) breaks models like GLM that
    # have their own formatting. Only use our template for truly unknown models.
    if tpl and not _is_vllm_known_arch(model_path):
        base_cmd += ["--chat-template", tpl]
    if custom_flags:
        import shlex
        base_cmd += shlex.split(custom_flags)

    # Define fallback strategies: (label, extra_args)
    strategies = [
        ("default (max-model-len=4096)",
         ["--max-model-len", "4096"]),
        ("explicit AWQ quantization (non-Marlin)",
         ["--max-model-len", "4096", "--quantization", "awq"]),
        ("reduced context (max-model-len=2048)",
         ["--max-model-len", "2048"]),
        ("float16 + reduced context (last resort)",
         ["--max-model-len", "2048", "--dtype", "float16"]),
    ]

    max_attempts_per_strategy = max_startup_minutes * 60 // 5  # 5s poll interval

    for strategy_idx, (label, extra_args) in enumerate(strategies):
        cmd = base_cmd + extra_args
        log.info("vLLM attempt %d/%d: %s", strategy_idx + 1, len(strategies), label)
        log.info("vLLM command: %s", " ".join(cmd))

        # Clear capture for new attempt
        capture = VllmOutputCapture()

        proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        def _stream(p, cap):
            try:
                for raw in iter(p.stdout.readline, b''):
                    line = raw.decode(errors='replace').rstrip()
                    if line:
                        cap.add(line)
                        log.info("[vLLM] %s", line)
            except Exception:
                pass

        threading.Thread(target=_stream, args=(proc, capture), daemon=True).start()

        # Wait for health
        ready = False
        for attempt in range(max_attempts_per_strategy):
            time.sleep(5)
            if proc.poll() is not None:
                log.error("vLLM exited during startup (strategy: %s, code: %s)",
                          label, proc.returncode)
                break
            try:
                urllib.request.urlopen("http://localhost:8199/health", timeout=3)
                ready = True
                break
            except (urllib.error.URLError, ConnectionError, OSError):
                if attempt % 12 == 0:
                    log.info("Waiting for vLLM... (%ds, strategy: %s)", attempt * 5, label)

        if ready:
            log.info("vLLM started successfully with strategy: %s", label)

            # Detect served model name
            try:
                resp_raw = urllib.request.urlopen("http://localhost:8199/v1/models", timeout=5)
                served_model = json.loads(resp_raw.read())["data"][0]["id"]
            except Exception:
                served_model = hf_repo or model_path

            return proc, capture, served_model, stop_tokens, None

        # Strategy failed — classify the error
        error_info = capture.classify_error(proc.returncode if proc.poll() is not None else -1)
        error_class = error_info["error_class"]
        log.warning("Strategy '%s' failed: %s (%s)", label, error_info["error"], error_class)

        # Kill the failed process
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()

        # Decide whether to try next strategy based on error class
        if error_class == "marlin_compat" and strategy_idx == 0:
            log.info("Marlin error detected — next strategy forces explicit AWQ")
            continue
        elif error_class in ("oom", "max_model_len") and strategy_idx <= 1:
            log.info("%s detected — next strategy reduces context length", error_class)
            continue
        elif error_class in ("multi_gpu",) and strategy_idx == 0:
            log.info("NCCL error — retrying same strategy once")
            continue
        elif error_class in ("weight_format", "missing_file"):
            # These won't be fixed by changing vLLM flags OR transformers fallback
            log.error("Non-recoverable error: %s — stopping fallback chain", error_class)
            return None, capture, "", stop_tokens, error_info["error"]
        elif error_class in ("unsupported", "trust_code"):
            # vLLM can't handle this arch — skip remaining vLLM strategies, go straight to transformers fallback
            log.warning("Architecture/code issue: %s — skipping to transformers fallback", error_class)
            break
        else:
            # Try next strategy anyway
            continue

    # All vLLM strategies exhausted — try transformers-direct fallback
    log.warning("FALLBACK: All vLLM strategies exhausted for %s — trying transformers-direct", hf_repo)
    capture.add("=== TRANSFORMERS FALLBACK STARTING ===")

    try:
        proc, served, fallback_error = _start_transformers_fallback(model_path, hf_repo, stop_tokens)
        if proc and not fallback_error:
            log.info("FALLBACK: Transformers-direct succeeded for %s", hf_repo)
            capture.add("=== TRANSFORMERS FALLBACK SUCCEEDED ===")
            return proc, capture, served, stop_tokens, None
        if fallback_error:
            log.error("FALLBACK: Transformers-direct failed for %s: %s", hf_repo, fallback_error)
            capture.add(f"=== TRANSFORMERS FALLBACK FAILED: {fallback_error} ===")
    except Exception as fb_exc:
        log.error("FALLBACK: Exception for %s: %s", hf_repo, fb_exc)
        capture.add(f"=== TRANSFORMERS FALLBACK EXCEPTION: {fb_exc} ===")

    final_error = capture.classify_error(-1)
    # Override error message to include fallback status
    final_msg = final_error.get("error", "unknown")
    if fallback_error:
        final_msg = f"vLLM failed + transformers fallback failed: {fallback_error}"
    log.error("All strategies exhausted (including transformers fallback) for %s: %s", hf_repo, final_msg)
    return None, capture, "", stop_tokens, final_msg


def _start_transformers_fallback(
    model_path: str, hf_repo: str, stop_tokens: list[str],
) -> tuple["subprocess.Popen | None", str, str | None]:
    """Last-resort fallback: serve the model via raw transformers + FastAPI.

    Used when vLLM can't load the model (unsupported architecture in vLLM's
    bundled transformers version). Loads via AutoModelForCausalLM with
    trust_remote_code=True and serves an OpenAI-compatible chat completions endpoint.

    Returns (proc, served_model_name, error_or_none).
    """
    import subprocess
    import threading
    import urllib.request
    import urllib.error

    # Restore auto_map if we stripped it — the fallback venv has transformers 5.x
    # which supports all custom code (RopeParameters, etc.)
    config_path = Path(model_path) / "config.json"
    config_bak = Path(model_path) / "config.json.vllm_bak"
    if config_bak.exists():
        import shutil
        shutil.copy2(str(config_bak), str(config_path))
        log.info("Restored original config.json with auto_map for transformers fallback")

    # Write a small FastAPI server that loads the model via transformers
    server_script = Path("/tmp/.forge/transformers_server.py")
    server_script.write_text(f'''
import sys, traceback
try:
    import transformers
    print(f"Transformers version: {{transformers.__version__}}", flush=True)

    import torch, json, os
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    import uvicorn

    app = FastAPI()
    MODEL_PATH = "{model_path}"

    print(f"Loading model from {{MODEL_PATH}} via transformers with trust_remote_code=True...", flush=True)
    from transformers import AutoModelForCausalLM, AutoTokenizer, AutoConfig

    # Check config first to diagnose architecture issues
    config = AutoConfig.from_pretrained(MODEL_PATH, trust_remote_code=True)
    print(f"Model config loaded: model_type={{config.model_type}}, arch={{getattr(config, 'architectures', ['unknown'])}}", flush=True)

    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH, trust_remote_code=True,
        torch_dtype=torch.float16, device_map="auto",
        low_cpu_mem_usage=True,
    )
    model.eval()
    MODEL_NAME = "{hf_repo or model_path}"
    print(f"Model loaded: {{MODEL_NAME}}", flush=True)

    @app.get("/health")
    async def health():
        return {{"status": "ok"}}

    @app.get("/v1/models")
    async def models():
        return {{"data": [{{"id": MODEL_NAME}}]}}

    @app.post("/v1/chat/completions")
    async def chat(request: Request):
        body = await request.json()
        messages = body.get("messages", [])
        max_tokens = body.get("max_tokens", 1024)
        temperature = body.get("temperature", 0.0)
        stop = body.get("stop", [])

        # Apply chat template if available
        if hasattr(tokenizer, "apply_chat_template"):
            input_ids = tokenizer.apply_chat_template(messages, return_tensors="pt", add_generation_prompt=True)
        else:
            # Manual formatting
            text = ""
            for m in messages:
                text += f"{{m['role']}}: {{m['content']}}\\n"
            text += "assistant: "
            input_ids = tokenizer(text, return_tensors="pt").input_ids

        input_ids = input_ids.to(model.device)

        with torch.no_grad():
            gen_kwargs = dict(
                max_new_tokens=max_tokens,
                do_sample=temperature > 0,
                temperature=max(temperature, 0.01),
                pad_token_id=tokenizer.eos_token_id,
            )
            # Add stop token IDs
            stop_ids = []
            for s in stop:
                ids = tokenizer.encode(s, add_special_tokens=False)
                if ids:
                    stop_ids.extend(ids)
            if tokenizer.eos_token_id:
                stop_ids.append(tokenizer.eos_token_id)
            if stop_ids:
                gen_kwargs["eos_token_id"] = list(set(stop_ids))

            output = model.generate(input_ids, **gen_kwargs)

        new_tokens = output[0][input_ids.shape[1]:]
        text = tokenizer.decode(new_tokens, skip_special_tokens=True)

        return {{
            "choices": [{{
                "index": 0,
                "message": {{"role": "assistant", "content": text}},
                "finish_reason": "stop",
            }}],
            "model": MODEL_NAME,
        }}

    if __name__ == "__main__":
        uvicorn.run(app, host="0.0.0.0", port=8199, log_level="info")

except Exception as exc:
    print(f"FATAL: Transformers fallback server crashed: {{exc}}", flush=True)
    traceback.print_exc()
    sys.exit(1)
''')

    # Use the isolated fallback venv (transformers 5.x + gptqmodel) to avoid
    # breaking vLLM's bundled transformers. Falls back to system Python if venv
    # doesn't exist (e.g. local testing).
    fallback_python = "/opt/forge-fallback/bin/python"
    if not Path(fallback_python).exists():
        fallback_python = "python"
        log.warning("Fallback venv not found at /opt/forge-fallback — using system Python")

    log.info("Starting transformers-direct fallback server for %s (python: %s)", hf_repo, fallback_python)
    proc = subprocess.Popen(
        [fallback_python, str(server_script)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )

    fb_lines = []  # capture fallback output for diagnostics

    def _stream(p):
        try:
            for raw in iter(p.stdout.readline, b''):
                line = raw.decode(errors='replace').rstrip()
                if line:
                    log.info("[TF-fallback] %s", line)
                    fb_lines.append(line)
        except Exception:
            pass
    stream_thread = threading.Thread(target=_stream, args=(proc,), daemon=True)
    stream_thread.start()

    # Wait for health — transformers loading is slower than vLLM
    ready = False
    for attempt in range(360):  # 30 min
        time.sleep(5)
        if proc.poll() is not None:
            # Process died — wait for stream to finish reading remaining output
            stream_thread.join(timeout=3)
            fb_tail = "; ".join(fb_lines[-5:]) if fb_lines else "no output captured"
            return None, "", f"Transformers fallback server exited with code {proc.returncode}: {fb_tail}"
        try:
            urllib.request.urlopen("http://localhost:8199/health", timeout=3)
            ready = True
            break
        except (urllib.error.URLError, ConnectionError, OSError):
            if attempt % 12 == 0:
                log.info("Waiting for transformers fallback server... (%ds)", attempt * 5)

    if not ready:
        if proc.poll() is None:
            proc.terminate()
        return None, "", "Transformers fallback server failed to start within 30 minutes"

    # Detect served model name
    try:
        resp = urllib.request.urlopen("http://localhost:8199/v1/models", timeout=5)
        served = json.loads(resp.read())["data"][0]["id"]
    except Exception:
        served = hf_repo or model_path

    return proc, served, None


def _preflight_check(served_model: str, stop_tokens: list[str],
                     base_url: str = "http://localhost:8199/v1") -> tuple[bool, str]:
    """Run a single inference call to verify vLLM is producing valid output.

    Returns (ok, error_detail). If ok is True, the model is ready for audit.
    """
    import urllib.request
    import urllib.error

    payload = json.dumps({
        "model": served_model,
        "messages": [{"role": "user", "content": "Say hello in one sentence."}],
        "max_tokens": 60,
        "temperature": 0.0,
        "stop": stop_tokens,
    }).encode()

    try:
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read())

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content or not content.strip():
            return False, "Pre-flight failed: model returned empty response"

        # Check for role token leakage — auto-fix by adding to stop tokens
        garbage_tokens = ["assistant\n", "\nassistant", "\nuser\n", "<|im_end|>", "<|eot_id|>",
                          "</s>", "<|end|>", "<|endoftext|>", "<end_of_turn>", "[|endofturn|]"]
        leaked = [g.strip() for g in garbage_tokens if g in content]
        if leaked:
            # Add leaked tokens to stop list and retry once
            for tok in leaked:
                if tok not in stop_tokens:
                    stop_tokens.append(tok)
                    log.warning("Pre-flight: auto-adding leaked token '%s' to stop list", tok)

            # Retry with updated stop tokens
            payload2 = json.dumps({
                "model": served_model,
                "messages": [{"role": "user", "content": "Say hello in one sentence."}],
                "max_tokens": 60,
                "temperature": 0.0,
                "stop": stop_tokens,
            }).encode()
            req2 = urllib.request.Request(
                f"{base_url}/chat/completions",
                data=payload2,
                headers={"Content-Type": "application/json"},
            )
            try:
                resp2 = urllib.request.urlopen(req2, timeout=120)
                data2 = json.loads(resp2.read())
            except urllib.error.HTTPError as e2:
                body = ""
                try:
                    body = e2.read().decode(errors="replace")[:500]
                except Exception:
                    pass
                return False, f"Pre-flight retry failed: vLLM HTTP {e2.code}: {body}"
            content2 = data2.get("choices", [{}])[0].get("message", {}).get("content", "")
            still_leaked = [g.strip() for g in garbage_tokens if g in content2]
            if still_leaked:
                return False, f"Pre-flight failed: response still contains leaked tokens after auto-fix: {still_leaked}"
            log.info("Pre-flight passed after auto-fixing stop tokens: added %s", leaked)
            return True, ""

        log.info("Pre-flight passed: model responded with %d chars", len(content))
        return True, ""

    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode(errors="replace")[:500]
        except Exception:
            pass
        return False, f"Pre-flight failed: vLLM HTTP {e.code}: {body}"
    except Exception as e:
        return False, f"Pre-flight failed: {e}"


def _fetch_matrix_comparison(category_pass_rates: dict) -> dict | None:
    """Fetch Matrix leaderboard data and compute comparative percentiles."""
    try:
        import urllib.request
        req = urllib.request.Request(
            f"{FORGE_API_SERVER}/audit_orchestrator.php?action=matrix_data",
            headers={"X-Forge-Api-Secret": FORGE_API_SECRET},
        )
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        matrix_models = data.get("models", [])
        if not matrix_models:
            log.info("Matrix comparison: no models in database yet")
            return None

        from forge.assurance_report import compute_matrix_comparison
        comparison = compute_matrix_comparison(category_pass_rates, matrix_models)
        log.info("Matrix comparison: percentile %.0f%% across %d models",
                 comparison.get("overall_percentile", 0) * 100,
                 comparison.get("models_compared", 0))
        return comparison
    except Exception as exc:
        log.warning("Matrix comparison unavailable: %s", exc)
        return None


class RemoteLogHandler(logging.Handler):
    """Logging handler that buffers log lines and POSTs them to the orchestrator."""

    def __init__(self, forge_server: str, order_id: str, flush_every: int = 10):
        super().__init__()
        self._url = f"{FORGE_API_SERVER}/audit_orchestrator.php?action=log"
        self._order_id = order_id
        self._buffer = []
        self._flush_every = flush_every

    def emit(self, record):
        try:
            line = self.format(record)
            self._buffer.append(line)
            if len(self._buffer) >= self._flush_every:
                self.flush()
        except Exception:
            pass

    def flush(self):
        if not self._buffer:
            return
        lines = self._buffer[:50]
        self._buffer = self._buffer[50:]
        try:
            requests.post(self._url, json={"order_id": self._order_id, "lines": lines},
                         headers={"X-Forge-Api-Secret": FORGE_API_SECRET}, timeout=5)
        except Exception:
            pass


def post_audit_progress(forge_server: str, order_id: str, webhook_secret: str,
                        stage: str, current: int = 0, total: int = 0, pass_count: int = 0):
    """POST a progress update to the orchestrator. Non-blocking, fire-and-forget."""
    try:
        requests.post(
            f"{FORGE_API_SERVER}/audit_orchestrator.php?action=progress",
            json={"order_id": order_id, "webhook_secret": webhook_secret,
                  "stage": stage, "current": current, "total": total, "pass": pass_count},
            headers={"X-Forge-Api-Secret": FORGE_API_SECRET},
            timeout=5,
        )
    except Exception:
        pass


def handler(event):
    """RunPod serverless handler — runs Forge Certified Audit."""
    job_input = event["input"]

    order_id = job_input["order_id"]
    model_index = int(job_input.get("model_index", 0))
    model_name = job_input.get("model_name", "unknown")
    model_id = job_input.get("model_id", "")
    access_type = job_input.get("access_type", "api_endpoint")
    endpoint_url = job_input.get("endpoint_url", "")
    api_key = job_input.get("api_key", "")
    webhook_secret = job_input.get("webhook_secret", "")

    # Attach remote log handler for live terminal output in admin dashboard
    forge_server = job_input.get("forge_server", "https://forge-nc.dev")
    _remote_handler = RemoteLogHandler(forge_server, order_id, flush_every=5)
    _remote_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logging.getLogger().addHandler(_remote_handler)

    log.info(
        "Starting audit: order=%s model=%s (%s) endpoint=%s",
        order_id, model_name, model_id, endpoint_url[:50] + "..." if len(endpoint_url) > 50 else endpoint_url,
    )

    try:
        if access_type == "api_endpoint":
            return _run_api_endpoint_audit(
                order_id=order_id,
                model_index=model_index,
                model_name=model_name,
                model_id=model_id,
                endpoint_url=endpoint_url,
                api_key=api_key,
                webhook_secret=webhook_secret,
            )
        elif access_type == "batch_break":
            if not HAS_VLLM:
                return {
                    "order_id": order_id, "model_index": model_index,
                    "webhook_secret": webhook_secret, "status": "failed",
                    "error": "batch_break requires the weights image with vLLM.",
                }
            models = job_input.get("models", [])
            if not models:
                return {
                    "order_id": order_id, "model_index": model_index,
                    "webhook_secret": webhook_secret, "status": "failed",
                    "error": "No models list provided for batch_break.",
                }
            return _run_batch_break(
                models=models,
                forge_server=job_input.get("forge_server", "https://forge-nc.dev"),
                vllm_env=job_input.get("vllm_env", ""),
            )
        elif access_type == "model_weights":
            if not HAS_VLLM:
                return {
                    "order_id": order_id,
                    "model_index": model_index,
                    "webhook_secret": webhook_secret,
                    "status": "failed",
                    "error": "This worker is the slim API-only image. "
                             "Model weights audits require the weights endpoint.",
                }
            hf_repo = job_input.get("hf_repo", "") or job_input.get("model_id", "")
            hf_token = job_input.get("hf_token", "")
            weights_url = job_input.get("weights_url", "")
            return _run_model_weights_audit(
                order_id=order_id,
                model_index=model_index,
                model_name=model_name,
                model_id=model_id,
                hf_repo=hf_repo,
                hf_token=hf_token,
                weights_url=weights_url,
                webhook_secret=webhook_secret,
                vllm_flags=job_input.get("vllm_flags", ""),
                custom_vllm_env=job_input.get("vllm_env", ""),
            )
        else:
            return {
                "order_id": order_id,
                "model_index": model_index,
                "webhook_secret": webhook_secret,
                "status": "failed",
                "error": f"Unknown access type: {access_type}",
            }
    except Exception as exc:
        log.exception("Audit failed for order %s model %d", order_id, model_index)
        return {
            "order_id": order_id,
            "model_index": model_index,
            "webhook_secret": webhook_secret,
            "status": "failed",
            "error": str(exc),
        }


def _run_api_endpoint_audit(
    order_id: str,
    model_index: int,
    model_name: str,
    model_id: str,
    endpoint_url: str,
    api_key: str,
    webhook_secret: str,
    stop_tokens: list[str] | None = None,
) -> dict:
    """Run dual-pass Forge Parallax audit against an OpenAI-compatible API endpoint."""
    from forge.break_runner import BreakRunner
    from forge.models.openai_backend import OpenAIBackend
    from forge.assurance import AssuranceRunner
    from forge.assurance_report import generate_report

    # Create LLM backend pointing at customer's endpoint
    llm = OpenAIBackend(
        model=model_id or model_name,
        api_key=api_key,
        base_url=endpoint_url.rstrip("/"),
        stop_tokens=stop_tokens,
    )

    log.info("LLM backend created: %s @ %s", model_id or model_name, endpoint_url)

    # ── Progress reporting ──
    _fs = endpoint_url.replace("/v1", "").replace("http://localhost:8199", "") or "https://forge-nc.dev"
    if not _fs.startswith("http"):
        _fs = "https://forge-nc.dev"
    _progress_pass_count = 0

    def _post(stage, cur=0, tot=0, pc=0):
        post_audit_progress(_fs, order_id, webhook_secret, stage, cur, tot, pc)

    def _progress(current, total, scenario_id, passed, latency_ms):
        nonlocal _progress_pass_count
        mark = "+" if passed else "x"
        if passed:
            _progress_pass_count += 1
        log.info("  [%d/%d] [%s] %s (%dms)", current, total, mark, scenario_id, latency_ms)
        if current % 2 == 0 or current == total:
            _post("break_running", current, total, _progress_pass_count)

    # ── Pass 1: Break (stress test) ──
    log.info("Starting Break pass...")
    _post("break_running", 0, 0)
    runner = BreakRunner(
        config_dir=FORGE_CONFIG_DIR,
        machine_id=f"forge-audit-{order_id[:8]}",
        passport_id="audit-worker",
    )

    break_result = runner.run(
        llm=llm,
        model=model_name,
        mode="full",
        include_fingerprint=True,
        self_rate=True,
        tier="power",  # Certified audits run all 38 scenarios
        progress_callback=_progress,
    )

    log.info(
        "Break pass complete: %.1f%% (%d/%d)",
        break_result.pass_rate * 100,
        break_result.scenarios_passed,
        break_result.scenarios_run,
    )

    # ── Pass 2: Assurance (verification) ──
    log.info("Starting Assurance pass...")
    _progress_pass_count = 0  # reset for assurance pass

    def _progress_assure(current, total, scenario_id, passed, latency_ms):
        nonlocal _progress_pass_count
        mark = "+" if passed else "x"
        if passed:
            _progress_pass_count += 1
        log.info("  [%d/%d] [%s] %s (%dms)", current, total, mark, scenario_id, latency_ms)
        if current % 2 == 0 or current == total:
            _post("assure_running", current, total, _progress_pass_count)

    _post("assure_running", 0, 0)
    assure_runner = AssuranceRunner(
        config_dir=FORGE_CONFIG_DIR,
        machine_id=f"forge-audit-{order_id[:8]}",
        passport_id="audit-worker",
    )
    assure_run = assure_runner.run(
        llm=llm,
        model=model_name,
        fingerprint_scores=break_result.fingerprint_scores,
        self_rate=True,
        tier="power",
        progress_callback=_progress_assure,
    )
    _post("signing", 0, 0)
    matrix_comp = _fetch_matrix_comparison(assure_run.category_pass_rates)
    assure_report = generate_report(assure_run, config_dir=FORGE_CONFIG_DIR,
                                    matrix_comparison=matrix_comp)

    log.info(
        "Assurance pass complete: %.1f%% (%d/%d)",
        assure_run.pass_rate * 100,
        sum(1 for r in assure_run.results if r.passed),
        len(assure_run.results),
    )

    # ── Forge Parallax: cross-link the paired reports ──
    break_result.report["paired_run_id"] = assure_report["run_id"]
    assure_report["paired_run_id"] = break_result.report["run_id"]

    # ── Return results + full reports in output ──
    # Reports are saved server-side by the orchestrator callback, not uploaded
    # directly. Cloudflare blocks data center POST requests with security content.
    import base64 as _b64

    # Compress reports for the RunPod output payload
    break_b64 = _b64.b64encode(json.dumps(break_result.report).encode()).decode()
    assure_b64 = _b64.b64encode(json.dumps(assure_report).encode()).decode()

    return {
        "order_id": order_id,
        "model_index": model_index,
        "model_name": model_name,
        "webhook_secret": webhook_secret,
        "status": "completed",
        "run_id": break_result.run_id,
        "run_id_paired": assure_report["run_id"],
        "pass_rate": break_result.pass_rate,
        "scenarios_run": break_result.scenarios_run,
        "scenarios_passed": break_result.scenarios_passed,
        "break_report_b64": break_b64,
        "assure_report_b64": assure_b64,
        "assure_pass_rate": assure_run.pass_rate,
        "category_pass_rates": break_result.category_pass_rates,
    }


def _run_model_weights_audit(
    order_id: str,
    model_index: int,
    model_name: str,
    model_id: str,
    hf_repo: str,
    hf_token: str,
    weights_url: str,
    webhook_secret: str,
    vllm_flags: str = "",
    custom_vllm_env: str = "",
) -> dict:
    """Download model weights, start vLLM, run dual-pass audit against it."""
    import subprocess
    import signal

    from forge.break_runner import BreakRunner
    from forge.models.openai_backend import OpenAIBackend
    from forge.assurance import AssuranceRunner
    from forge.assurance_report import generate_report

    vllm_proc = None
    try:
        # ── Resolve and pre-download model ──
        if hf_repo:
            model_source = hf_repo
        elif weights_url:
            model_source = weights_url
        else:
            return {
                "order_id": order_id, "model_index": model_index,
                "webhook_secret": webhook_secret, "status": "failed",
                "error": "No HuggingFace repo or download URL provided",
            }

        log.info("Resolving model: %s", model_source)
        _fs = "https://forge-nc.dev"
        post_audit_progress(_fs, order_id, webhook_secret, "downloading")

        # Pre-download from HuggingFace so vLLM gets a local path
        # (avoids vLLM/transformers HF download issues in containers)
        if not model_source.startswith("http"):
            try:
                os.environ.pop("HF_HUB_ENABLE_HF_TRANSFER", None)  # runpod base sets this but lacks the package
                from huggingface_hub import snapshot_download
                log.info("Downloading model from HuggingFace: %s", model_source)
                local_path = snapshot_download(
                    model_source,
                    token=hf_token or None,
                    cache_dir="/tmp/hf_models",
                )
                log.info("Model downloaded to: %s", local_path)
                model_source = local_path
            except Exception as dl_exc:
                return {
                    "order_id": order_id, "model_index": model_index,
                    "webhook_secret": webhook_secret, "status": "failed",
                    "error": f"Failed to download model from HuggingFace: {dl_exc}",
                }

        log.info("Starting vLLM for model: %s", model_source)
        post_audit_progress(_fs, order_id, webhook_secret, "loading")

        # ── Start vLLM with fallback chain ──
        import torch
        gpu_count = torch.cuda.device_count() if torch.cuda.is_available() else 1
        per_gpu_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3) if torch.cuda.is_available() else 48

        # Build custom env from customer inputs
        extra_env = {}
        if hf_token:
            extra_env["HF_TOKEN"] = hf_token
        if custom_vllm_env:
            for pair in custom_vllm_env.split(","):
                pair = pair.strip()
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    extra_env[k.strip()] = v.strip()

        vllm_proc, capture, served_model, stop_tokens, start_error = _start_vllm_with_fallback(
            model_path=model_source,
            hf_repo=hf_repo,
            gpu_count=gpu_count,
            per_gpu_gb=per_gpu_gb,
            custom_env=extra_env,
            custom_flags=vllm_flags,
            max_startup_minutes=60,
        )

        if start_error:
            error_info = capture.classify_error(vllm_proc.returncode if vllm_proc else -1)
            return {
                "order_id": order_id, "model_index": model_index,
                "webhook_secret": webhook_secret, "status": "failed",
                "error": start_error,
                "error_class": error_info.get("error_class", "unknown"),
                "vllm_last_lines": error_info.get("vllm_last_lines", []),
            }

        # ── Pre-flight validation ──
        log.info("Running pre-flight check...")
        post_audit_progress(_fs, order_id, webhook_secret, "preflight")
        pf_ok, pf_error = _preflight_check(served_model, stop_tokens)
        if not pf_ok:
            log.error("Pre-flight failed: %s", pf_error)
            if vllm_proc and vllm_proc.poll() is None:
                vllm_proc.terminate()
            return {
                "order_id": order_id, "model_index": model_index,
                "webhook_secret": webhook_secret, "status": "preflight_failed",
                "error": pf_error,
            }

        log.info("Pre-flight passed, starting audit on %s", served_model)

        # ── Run audit against local vLLM (with resolved stop tokens) ──
        return _run_api_endpoint_audit(
            order_id=order_id,
            model_index=model_index,
            model_name=model_name,
            model_id=served_model,
            endpoint_url="http://localhost:8199/v1",
            api_key="not-needed",
            webhook_secret=webhook_secret,
            stop_tokens=stop_tokens,
        )

    finally:
        if vllm_proc and vllm_proc.poll() is None:
            log.info("Shutting down vLLM")
            vllm_proc.terminate()
            try:
                vllm_proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                vllm_proc.kill()


# ── Batch break: uncertified break runs across multiple models ──

def _run_batch_break(
    models: list[str],
    forge_server: str = "https://forge-nc.dev",
    vllm_env: str = "",
) -> dict:
    """Run uncertified /break --full on a list of models sequentially.

    For each model: download weights, start vLLM, run break pass (single pass,
    no Parallax verification), upload report to server, kill vLLM, next model.

    Reports are NOT Origin-certified. They populate the Matrix as community data.
    """
    import subprocess
    import signal
    import urllib.request
    import urllib.error
    import base64 as _b64

    from forge.break_runner import BreakRunner
    from forge.models.openai_backend import OpenAIBackend
    from forge.assurance_report import generate_report

    results = []

    # Load dedup list — check server for existing reports + local tracking
    _completed_path = Path("/tmp/.forge/batch_completed.json")
    already_done = json.loads(_completed_path.read_text()) if _completed_path.exists() else []

    # Also check server for models that already have reports
    try:
        req = urllib.request.Request(f"{FORGE_API_SERVER}/audit_orchestrator.php?action=report_models")
        req.add_header("X-Forge-Api-Secret", FORGE_API_SECRET)
        resp = urllib.request.urlopen(req, timeout=10)
        server_models = json.loads(resp.read()).get("models", [])
        already_done = list(set(already_done + server_models))
        log.info("Server has reports for %d models, %d total to skip", len(server_models), len(already_done))
    except Exception:
        log.info("Could not check server for existing reports, using local dedup only")

    for mi, hf_repo in enumerate(models):
        if hf_repo in already_done:
            log.info("=== Batch break %d/%d: %s — SKIPPED (already completed) ===", mi + 1, len(models), hf_repo)
            results.append({"model": hf_repo, "status": "skipped"})
            continue

        log.info("=== Batch break %d/%d: %s ===", mi + 1, len(models), hf_repo)
        vllm_proc = None

        # Attach remote log handler so we can see logs on the server
        _batch_log_id = f"batch-{hf_repo.replace('/', '-')[:40]}"
        _batch_log_handler = RemoteLogHandler(FORGE_API_SERVER, _batch_log_id, flush_every=5)
        _batch_log_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
        logging.getLogger().addHandler(_batch_log_handler)

        try:
            # Download model
            os.environ.pop("HF_HUB_ENABLE_HF_TRANSFER", None)
            from huggingface_hub import snapshot_download
            log.info("Downloading: %s", hf_repo)
            local_path = snapshot_download(hf_repo, cache_dir="/tmp/hf_models")
            log.info("Downloaded to: %s", local_path)

            # Start vLLM with fallback chain
            import torch
            gpu_count = torch.cuda.device_count() if torch.cuda.is_available() else 1
            per_gpu_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3) if torch.cuda.is_available() else 48

            extra_env = {}
            if vllm_env:
                for pair in vllm_env.split(","):
                    pair = pair.strip()
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        extra_env[k.strip()] = v.strip()

            vllm_proc, capture, served_model, stop_tokens, start_error = _start_vllm_with_fallback(
                model_path=local_path,
                hf_repo=hf_repo,
                gpu_count=gpu_count,
                per_gpu_gb=per_gpu_gb,
                custom_env=extra_env,
                max_startup_minutes=30,
            )

            if start_error:
                error_info = capture.classify_error(vllm_proc.returncode if vllm_proc else -1)
                log.error("All vLLM strategies failed for %s: %s", hf_repo, start_error)
                _fail = {
                    "model": hf_repo, "status": "failed",
                    "error": start_error,
                    "error_class": error_info.get("error_class", "unknown"),
                    "vllm_last_lines": error_info.get("vllm_last_lines", [])[-10:],
                }
                results.append(_fail)
                try:
                    urllib.request.urlopen(urllib.request.Request(
                        f"{FORGE_API_SERVER}/audit_orchestrator.php?action=batch_result",
                        data=json.dumps(_fail).encode(),
                        headers={"Content-Type": "application/json",
                                 "X-Forge-Api-Secret": FORGE_API_SECRET},
                    ), timeout=10)
                except Exception:
                    pass
                continue

            # Pre-flight validation
            pf_ok, pf_error = _preflight_check(served_model, stop_tokens)
            if not pf_ok:
                log.warning("Pre-flight failed for %s on vLLM: %s — trying transformers fallback", hf_repo, pf_error)
                # Shut down vLLM before trying fallback
                if vllm_proc and vllm_proc.poll() is None:
                    log.info("Shutting down vLLM for %s", hf_repo)
                    vllm_proc.terminate()
                    try:
                        vllm_proc.wait(timeout=10)
                    except Exception:
                        vllm_proc.kill()

                # Try transformers fallback — vLLM loaded but can't serve this model correctly
                fb_proc, fb_served, fb_error = _start_transformers_fallback(model_path, hf_repo, stop_tokens)
                if fb_proc and not fb_error:
                    # Re-run preflight on fallback
                    pf_ok2, pf_error2 = _preflight_check(fb_served, stop_tokens, base_url="http://localhost:8199/v1")
                    if pf_ok2:
                        log.info("Transformers fallback pre-flight passed for %s", hf_repo)
                        served_model = fb_served
                        vllm_proc = fb_proc  # track for cleanup
                    else:
                        log.error("Transformers fallback also failed pre-flight for %s: %s", hf_repo, pf_error2)
                        if fb_proc.poll() is None:
                            fb_proc.terminate()
                        _fail = {"model": hf_repo, "status": "failed",
                                 "error": f"vLLM preflight: {pf_error}; fallback preflight: {pf_error2}"}
                        results.append(_fail)
                        try:
                            urllib.request.urlopen(urllib.request.Request(
                                f"{FORGE_API_SERVER}/audit_orchestrator.php?action=batch_result",
                                data=json.dumps(_fail).encode(),
                                headers={"Content-Type": "application/json",
                                         "X-Forge-Api-Secret": FORGE_API_SECRET},
                            ), timeout=10)
                        except Exception:
                            pass
                        continue
                else:
                    log.error("Transformers fallback failed to start for %s: %s", hf_repo, fb_error)
                    _fail = {"model": hf_repo, "status": "failed",
                             "error": f"vLLM preflight: {pf_error}; fallback: {fb_error}"}
                    results.append(_fail)
                    try:
                        urllib.request.urlopen(urllib.request.Request(
                            f"{FORGE_API_SERVER}/audit_orchestrator.php?action=batch_result",
                            data=json.dumps(_fail).encode(),
                            headers={"Content-Type": "application/json",
                                     "X-Forge-Api-Secret": FORGE_API_SECRET},
                        ), timeout=10)
                    except Exception:
                        pass
                    continue

            log.info("Pre-flight passed, running break on %s (model: %s)", hf_repo, served_model)

            llm = OpenAIBackend(
                model=served_model,
                api_key="not-needed",
                base_url="http://localhost:8199/v1",
                stop_tokens=stop_tokens,
            )

            def _progress(current, total, scenario_id, passed, latency_ms):
                mark = "+" if passed else "x"
                log.info("  [%d/%d] [%s] %s (%dms)", current, total, mark, scenario_id, latency_ms)

            # Pass 1: Break
            log.info("Starting Break pass for %s...", hf_repo)
            runner = BreakRunner(
                config_dir=FORGE_CONFIG_DIR,
                machine_id="forge-batch-worker",
                passport_id="batch-break",
            )

            break_result = runner.run(
                llm=llm,
                model=hf_repo,
                mode="full",
                include_fingerprint=True,
                self_rate=False,
                tier="power",
                progress_callback=_progress,
            )

            log.info("Break complete for %s: %.1f%% (%d/%d)",
                     hf_repo, break_result.pass_rate * 100,
                     break_result.scenarios_passed, break_result.scenarios_run)

            # Pass 2: Assurance (verification)
            log.info("Starting Assurance pass for %s...", hf_repo)
            from forge.assurance import AssuranceRunner
            assure_runner = AssuranceRunner(
                config_dir=FORGE_CONFIG_DIR,
                machine_id="forge-batch-worker",
                passport_id="batch-break",
            )
            assure_run = assure_runner.run(
                llm=llm,
                model=hf_repo,
                fingerprint_scores=break_result.fingerprint_scores,
                self_rate=False,
                tier="power",
                progress_callback=_progress,
            )
            matrix_comp = _fetch_matrix_comparison(assure_run.category_pass_rates)
            assure_report = generate_report(assure_run, config_dir=FORGE_CONFIG_DIR,
                                            matrix_comparison=matrix_comp)

            log.info("Assurance complete for %s: %.1f%% (%d/%d)",
                     hf_repo, assure_run.pass_rate * 100,
                     sum(1 for r in assure_run.results if r.passed),
                     len(assure_run.results))

            # Cross-link paired reports (Parallax)
            break_result.report["paired_run_id"] = assure_report["run_id"]
            assure_report["paired_run_id"] = break_result.report["run_id"]

            # Upload both reports to server
            break_b64 = _b64.b64encode(json.dumps(break_result.report).encode()).decode()
            assure_b64 = _b64.b64encode(json.dumps(assure_report).encode()).decode()
            for rpt_b64 in [break_b64, assure_b64]:
                try:
                    upload_payload = json.dumps({
                        "report_b64": rpt_b64,
                        "source": "batch_break",
                    }).encode()
                    req = urllib.request.Request(
                        f"{FORGE_API_SERVER}/audit_orchestrator.php?action=upload_report",
                        data=upload_payload,
                        headers={
                            "Content-Type": "application/json",
                            "X-Forge-Api-Secret": FORGE_API_SECRET,
                        },
                    )
                    urllib.request.urlopen(req, timeout=30)
                except Exception as upload_exc:
                    log.warning("Report upload failed for %s: %s", hf_repo, upload_exc)

            log.info("Reports uploaded for %s (break: %s, assure: %s)",
                     hf_repo, break_result.run_id, assure_report["run_id"])

            # Track completed models so we can skip on re-run
            _completed_path = Path("/tmp/.forge/batch_completed.json")
            completed = json.loads(_completed_path.read_text()) if _completed_path.exists() else []
            completed.append(hf_repo)
            _completed_path.write_text(json.dumps(completed))

            _result = {
                "model": hf_repo,
                "status": "completed",
                "run_id": break_result.run_id,
                "run_id_paired": assure_report["run_id"],
                "pass_rate": break_result.pass_rate,
                "weighted_pass_rate": assure_run.weighted_pass_rate,
                "scenarios_run": break_result.scenarios_run,
                "scenarios_passed": break_result.scenarios_passed,
            }
            results.append(_result)

            # Log result permanently to server
            try:
                urllib.request.urlopen(urllib.request.Request(
                    f"{FORGE_API_SERVER}/audit_orchestrator.php?action=batch_result",
                    data=json.dumps(_result).encode(),
                    headers={"Content-Type": "application/json",
                             "X-Forge-Api-Secret": FORGE_API_SECRET},
                ), timeout=10)
            except Exception:
                log.warning("Failed to log batch result for %s", hf_repo)

        except Exception as exc:
            log.exception("Batch break failed for %s", hf_repo)
            _fail = {"model": hf_repo, "status": "failed", "error": str(exc)}
            results.append(_fail)

            # Log failure permanently to server
            try:
                urllib.request.urlopen(urllib.request.Request(
                    f"{FORGE_API_SERVER}/audit_orchestrator.php?action=batch_result",
                    data=json.dumps(_fail).encode(),
                    headers={"Content-Type": "application/json",
                             "X-Forge-Api-Secret": FORGE_API_SECRET},
                ), timeout=10)
            except Exception:
                pass

        finally:
            if vllm_proc and vllm_proc.poll() is None:
                log.info("Shutting down vLLM for %s", hf_repo)
                vllm_proc.terminate()
                try:
                    vllm_proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    vllm_proc.kill()
            # Flush and remove batch log handler
            try:
                _batch_log_handler.flush()
                logging.getLogger().removeHandler(_batch_log_handler)
            except Exception:
                pass

    return {
        "status": "completed",
        "models_run": len(results),
        "models_passed": sum(1 for r in results if r.get("status") == "completed"),
        "results": results,
    }


# ── Pod mode: HTTP server for ultra tier ──

def _run_pod_mode():
    """Run audit inside a GPU pod, POST results to orchestrator webhook.

    The orchestrator passes job input via FORGE_JOB_INPUT env var (base64).
    We run the audit, POST results to FORGE_WEBHOOK_URL, then exit.
    The orchestrator destroys the pod on completion.
    """
    import base64 as _b64

    webhook_url = os.environ.get("FORGE_WEBHOOK_URL", "")
    job_b64 = os.environ.get("FORGE_JOB_INPUT", "")

    if not job_b64 or not webhook_url:
        log.error("Pod mode: missing FORGE_JOB_INPUT or FORGE_WEBHOOK_URL")
        sys.exit(1)

    result = None
    order_id = "unknown"
    webhook_secret = ""
    forge_server = "https://forge-nc.dev"

    try:
        job_input = json.loads(_b64.b64decode(job_b64))
        order_id = job_input.get("order_id", "unknown")
        webhook_secret = job_input.get("webhook_secret", "")
        forge_server = job_input.get("forge_server", "https://forge-nc.dev")
        log.info("Pod mode: starting audit for order %s", order_id)

        # Attach remote log handler so admin can see live output
        remote_handler = RemoteLogHandler(forge_server, order_id, flush_every=5)
        remote_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
        logging.getLogger().addHandler(remote_handler)

        # Early progress POST so admin dashboard knows we're alive
        post_audit_progress(forge_server, order_id, webhook_secret, "pod_started")

        event = {"input": job_input}
        result = handler(event)
        log.info("Pod mode: handler returned status=%s", result.get("status", "?"))

    except Exception as exc:
        log.exception("Pod mode: handler crashed")
        result = {
            "order_id": order_id,
            "model_index": 0,
            "webhook_secret": webhook_secret,
            "status": "failed",
            "error": f"Pod handler crash: {exc}",
        }

    # POST results back to orchestrator webhook (always, even on failure)
    # Try multiple URL patterns to bypass Cloudflare WAF blocking data center IPs
    status_str = "COMPLETED" if result.get("status") == "completed" else "FAILED"
    payload = {"status": status_str, "output": result}
    webhook_urls = [
        webhook_url,
        webhook_url.replace("audit_orchestrator.php", "rv.php"),  # proxy bypass
    ]

    posted = False
    for url in webhook_urls:
        log.info("Pod mode: posting %s to %s", status_str, url)
        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload, timeout=60)
                log.info("Pod mode: webhook response %d from %s", resp.status_code, url)
                if resp.status_code < 400:
                    posted = True
                    break
                log.warning("Pod mode: %d on attempt %d, retrying...", resp.status_code, attempt + 1)
            except Exception as exc:
                log.error("Pod mode: POST attempt %d to %s failed: %s", attempt + 1, url, exc)
            time.sleep(5)
        if posted:
            break

    if not posted:
        log.error("Pod mode: ALL webhook POST attempts failed. Results lost.")

    # Self-terminate the pod to prevent restart loop
    # RunPod pods have restartPolicy: Always — exiting would restart the container
    pod_id = os.environ.get("RUNPOD_POD_ID", "")
    if pod_id:
        log.info("Pod mode: self-terminating pod %s", pod_id)
        try:
            import subprocess
            subprocess.run(["runpodctl", "pod", "stop", pod_id], timeout=10, capture_output=True)
        except Exception as exc:
            log.warning("Pod mode: self-terminate failed: %s (orchestrator will clean up)", exc)

    log.info("Pod mode: done, sleeping to prevent restart")
    # Sleep indefinitely instead of exiting — prevents restart loop
    # The orchestrator or self-terminate will kill the pod
    while True:
        time.sleep(3600)


# ── Entry point ──
if os.environ.get("FORGE_POD_MODE") == "1":
    _run_pod_mode()
else:
    runpod.serverless.start({"handler": handler})
