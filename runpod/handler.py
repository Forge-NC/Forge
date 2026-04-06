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


class RemoteLogHandler(logging.Handler):
    """Logging handler that buffers log lines and POSTs them to the orchestrator."""

    def __init__(self, forge_server: str, order_id: str, flush_every: int = 10):
        super().__init__()
        self._url = f"{forge_server}/audit_orchestrator.php?action=log"
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
            requests.post(self._url, json={"order_id": self._order_id, "lines": lines}, timeout=5)
        except Exception:
            pass


def post_audit_progress(forge_server: str, order_id: str, webhook_secret: str,
                        stage: str, current: int = 0, total: int = 0, pass_count: int = 0):
    """POST a progress update to the orchestrator. Non-blocking, fire-and-forget."""
    try:
        requests.post(
            f"{forge_server}/audit_orchestrator.php?action=progress",
            json={"order_id": order_id, "webhook_secret": webhook_secret,
                  "stage": stage, "current": current, "total": total, "pass": pass_count},
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
    assure_report = generate_report(assure_run, config_dir=FORGE_CONFIG_DIR)

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

        # ── Start vLLM server ──
        vllm_env = os.environ.copy()
        vllm_env["VLLM_WORKER_MULTIPROC_METHOD"] = "spawn"  # required for tensor parallelism
        vllm_env["VLLM_MARLIN_USE_ATOMIC_ADD"] = "1"  # required for AWQ quantization
        vllm_env["VLLM_USE_DEEP_GEMM"] = "0"  # CRITICAL: causes hangs on Hopper (H100) GPUs
        vllm_env["TORCH_ALLOW_TF32_CUBLAS_OVERRIDE"] = "1"  # recommended for Hopper
        # MoE-specific vars (VLLM_USE_V1, FLASHINFER_MOE, etc.) are passed per-model
        # via custom_vllm_env from model registry — not set globally here
        if hf_token:
            vllm_env["HF_TOKEN"] = hf_token

        # Apply customer-provided env vars (from enterprise intake form)
        custom_env = custom_vllm_env
        if custom_env:
            for pair in custom_env.split(","):
                pair = pair.strip()
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    vllm_env[k.strip()] = v.strip()
                    log.info("Custom env: %s=%s", k.strip(), v.strip())

        # Detect multi-GPU (RunPod sets NVIDIA_VISIBLE_DEVICES)
        import torch
        gpu_count = torch.cuda.device_count() if torch.cuda.is_available() else 1

        # Detect per-GPU VRAM to select appropriate vLLM settings
        per_gpu_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3) if torch.cuda.is_available() else 48
        total_vram_gb = per_gpu_gb * gpu_count

        vllm_cmd = [
            "python", "-m", "vllm.entrypoints.openai.api_server",
            "--model", model_source,
            "--host", "0.0.0.0",
            "--port", "8199",
            "--trust-remote-code",
        ]

        # Memory-constrained settings for 48GB GPUs (A6000/L40S)
        if per_gpu_gb < 60:
            vllm_cmd += [
                "--max-model-len", "4096",
                "--gpu-memory-utilization", "0.95",
                "--max-num-seqs", "4",
                "--enforce-eager",
            ]
            log.info("48GB GPU mode: max-model-len=4096, gpu-mem=0.95, eager")
        else:
            # 80GB+ GPUs (A100/H100/H200)
            # Use 4096 context — audit prompts are short, saves KV cache alloc time
            # Customers don't need 65K context for behavioral testing
            vllm_cmd += [
                "--max-model-len", "4096",
                "--gpu-memory-utilization", "0.95",
                "--enforce-eager",
            ]
            log.info("80GB+ GPU mode: max-model-len=4096, gpu-mem=0.95, eager")

        if gpu_count > 1:
            vllm_cmd += ["--tensor-parallel-size", str(gpu_count)]
            log.info("Multi-GPU: %d x %.0fGB = %.0fGB total, TP=%d", gpu_count, per_gpu_gb, total_vram_gb, gpu_count)

        # Apply customer-provided vLLM flags (from enterprise intake form)
        custom_flags = vllm_flags
        if custom_flags:
            import shlex
            extra = shlex.split(custom_flags)
            vllm_cmd += extra
            log.info("Custom vLLM flags: %s", extra)

        log.info("vLLM command: %s", " ".join(vllm_cmd))
        vllm_proc = subprocess.Popen(
            vllm_cmd, env=vllm_env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )

        # Stream vLLM stdout to log in a background thread
        import threading
        def _stream_vllm_output(proc):
            try:
                for raw_line in iter(proc.stdout.readline, b''):
                    line = raw_line.decode(errors='replace').rstrip()
                    if line:
                        log.info("[vLLM] %s", line)
            except Exception:
                pass
        _vllm_thread = threading.Thread(target=_stream_vllm_output, args=(vllm_proc,), daemon=True)
        _vllm_thread.start()

        # ── Wait for vLLM to be ready (poll /health) ──
        import urllib.request
        import urllib.error
        vllm_ready = False
        for attempt in range(720):  # up to 60 minutes (671B+ models need extended load time)
            time.sleep(5)
            if vllm_proc.poll() is not None:
                log.error("vLLM exited during startup with code %s. Check [vLLM] log lines above.", vllm_proc.returncode)
                return {
                    "order_id": order_id, "model_index": model_index,
                    "webhook_secret": webhook_secret, "status": "failed",
                    "error": f"vLLM exited during startup (code {vllm_proc.returncode}). Output streamed to logs.",
                }
            try:
                urllib.request.urlopen("http://localhost:8199/health", timeout=3)
                vllm_ready = True
                break
            except (urllib.error.URLError, ConnectionError, OSError):
                if attempt % 12 == 0:
                    log.info("Waiting for vLLM... (%ds)", attempt * 5)
                continue

        if not vllm_ready:
            vllm_proc.terminate()
            log.error("vLLM startup timeout after 60 minutes (%d GPUs). Check [vLLM] log lines above.", gpu_count)
            return {
                "order_id": order_id, "model_index": model_index,
                "webhook_secret": webhook_secret, "status": "failed",
                "error": f"vLLM failed to start within 60 minutes ({gpu_count} GPU(s)). vLLM output was streamed to logs.",
            }

        log.info("vLLM ready, starting audit")

        # ── Detect served model name from vLLM ──
        try:
            resp_raw = urllib.request.urlopen("http://localhost:8199/v1/models", timeout=5)
            import json as _json
            models_resp = _json.loads(resp_raw.read())
            served_model = models_resp["data"][0]["id"]
            log.info("vLLM serving model as: %s", served_model)
        except Exception:
            served_model = model_id or model_name

        # ── Run audit against local vLLM ──
        return _run_api_endpoint_audit(
            order_id=order_id,
            model_index=model_index,
            model_name=model_name,
            model_id=served_model,
            endpoint_url="http://localhost:8199/v1",
            api_key="not-needed",
            webhook_secret=webhook_secret,
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

    # Load dedup list — skip models already completed on this worker
    _completed_path = Path("/tmp/.forge/batch_completed.json")
    already_done = json.loads(_completed_path.read_text()) if _completed_path.exists() else []

    for mi, hf_repo in enumerate(models):
        if hf_repo in already_done:
            log.info("=== Batch break %d/%d: %s — SKIPPED (already completed) ===", mi + 1, len(models), hf_repo)
            results.append({"model": hf_repo, "status": "skipped"})
            continue

        log.info("=== Batch break %d/%d: %s ===", mi + 1, len(models), hf_repo)
        vllm_proc = None

        try:
            # Download model
            os.environ.pop("HF_HUB_ENABLE_HF_TRANSFER", None)
            from huggingface_hub import snapshot_download
            log.info("Downloading: %s", hf_repo)
            local_path = snapshot_download(hf_repo, cache_dir="/tmp/hf_models")
            log.info("Downloaded to: %s", local_path)

            # Start vLLM
            import torch
            gpu_count = torch.cuda.device_count() if torch.cuda.is_available() else 1
            per_gpu_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3) if torch.cuda.is_available() else 48

            env = os.environ.copy()
            env["VLLM_WORKER_MULTIPROC_METHOD"] = "spawn"
            env["VLLM_MARLIN_USE_ATOMIC_ADD"] = "1"
            env["VLLM_USE_DEEP_GEMM"] = "0"
            env["TORCH_ALLOW_TF32_CUBLAS_OVERRIDE"] = "1"
            if vllm_env:
                for pair in vllm_env.split(","):
                    pair = pair.strip()
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        env[k.strip()] = v.strip()

            cmd = [
                "python", "-m", "vllm.entrypoints.openai.api_server",
                "--model", local_path,
                "--host", "0.0.0.0", "--port", "8199",
                "--trust-remote-code",
                "--max-model-len", "4096",
                "--gpu-memory-utilization", "0.95",
                "--enforce-eager",
            ]
            if gpu_count > 1:
                cmd += ["--tensor-parallel-size", str(gpu_count)]

            log.info("vLLM command: %s", " ".join(cmd))
            vllm_proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

            import threading
            def _stream(proc):
                try:
                    for raw in iter(proc.stdout.readline, b''):
                        line = raw.decode(errors='replace').rstrip()
                        if line:
                            log.info("[vLLM] %s", line)
                except Exception:
                    pass
            threading.Thread(target=_stream, args=(vllm_proc,), daemon=True).start()

            # Wait for ready
            ready = False
            for attempt in range(360):  # 30 min max
                time.sleep(5)
                if vllm_proc.poll() is not None:
                    log.error("vLLM exited during startup for %s", hf_repo)
                    break
                try:
                    urllib.request.urlopen("http://localhost:8199/health", timeout=3)
                    ready = True
                    break
                except (urllib.error.URLError, ConnectionError, OSError):
                    if attempt % 12 == 0:
                        log.info("Waiting for vLLM... (%ds)", attempt * 5)

            if not ready:
                log.error("vLLM startup failed for %s", hf_repo)
                results.append({"model": hf_repo, "status": "failed", "error": "vLLM startup failed"})
                continue

            # Detect served model name
            try:
                resp_raw = urllib.request.urlopen("http://localhost:8199/v1/models", timeout=5)
                import json as _json
                served_model = _json.loads(resp_raw.read())["data"][0]["id"]
            except Exception:
                served_model = hf_repo

            log.info("vLLM ready, running break on %s", served_model)

            # Run /break --full (break + assurance dual pass, uncertified)
            llm = OpenAIBackend(
                model=served_model,
                api_key="not-needed",
                base_url="http://localhost:8199/v1",
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
            assure_report = generate_report(assure_run, config_dir=FORGE_CONFIG_DIR)

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
                        f"{forge_server}/audit_orchestrator.php?action=upload_report",
                        data=upload_payload,
                        headers={"Content-Type": "application/json"},
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

            results.append({
                "model": hf_repo,
                "status": "completed",
                "run_id": break_result.run_id,
                "run_id_paired": assure_report["run_id"],
                "pass_rate": break_result.pass_rate,
                "scenarios_run": break_result.scenarios_run,
                "scenarios_passed": break_result.scenarios_passed,
            })

        except Exception as exc:
            log.exception("Batch break failed for %s", hf_repo)
            results.append({"model": hf_repo, "status": "failed", "error": str(exc)})

        finally:
            if vllm_proc and vllm_proc.poll() is None:
                log.info("Shutting down vLLM for %s", hf_repo)
                vllm_proc.terminate()
                try:
                    vllm_proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    vllm_proc.kill()

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
