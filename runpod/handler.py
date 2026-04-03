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

    # ── Pass 1: Break (stress test) ──
    log.info("Starting Break pass...")
    runner = BreakRunner(
        config_dir=FORGE_CONFIG_DIR,
        machine_id=f"forge-audit-{order_id[:8]}",
        passport_id="audit-worker",
    )

    def _progress(current, total, scenario_id, passed, latency_ms):
        mark = "+" if passed else "x"
        log.info("  [%d/%d] [%s] %s (%dms)", current, total, mark, scenario_id, latency_ms)

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
        progress_callback=_progress,
    )
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

        # ── Start vLLM server ──
        vllm_env = os.environ.copy()
        vllm_env["VLLM_WORKER_MULTIPROC_METHOD"] = "spawn"  # required for tensor parallelism
        if hf_token:
            vllm_env["HF_TOKEN"] = hf_token

        # Detect multi-GPU (RunPod sets NVIDIA_VISIBLE_DEVICES)
        import torch
        gpu_count = torch.cuda.device_count() if torch.cuda.is_available() else 1

        vllm_cmd = [
            "python", "-m", "vllm.entrypoints.openai.api_server",
            "--model", model_source,
            "--host", "0.0.0.0",
            "--port", "8199",
            "--trust-remote-code",
        ]
        if gpu_count > 1:
            vllm_cmd += ["--tensor-parallel-size", str(gpu_count)]
            log.info("Multi-GPU detected: %d GPUs, tensor-parallel-size=%d", gpu_count, gpu_count)
        vllm_proc = subprocess.Popen(
            vllm_cmd, env=vllm_env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )

        # ── Wait for vLLM to be ready (poll /health) ──
        import urllib.request
        import urllib.error
        vllm_ready = False
        for attempt in range(720):  # up to 60 minutes (671B+ models need extended load time)
            time.sleep(5)
            if vllm_proc.poll() is not None:
                stdout = vllm_proc.stdout.read().decode(errors="replace")[-2000:]
                return {
                    "order_id": order_id, "model_index": model_index,
                    "webhook_secret": webhook_secret, "status": "failed",
                    "error": f"vLLM exited during startup (code {vllm_proc.returncode}): {stdout}",
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
            return {
                "order_id": order_id, "model_index": model_index,
                "webhook_secret": webhook_secret, "status": "failed",
                "error": f"vLLM failed to start within 60 minutes ({gpu_count} GPU(s))",
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


# ── Pod mode: HTTP server for ultra tier ──

def _run_pod_mode():
    """Run as a standalone HTTP server inside a GPU pod.

    The orchestrator passes job input via FORGE_JOB_INPUT env var (base64).
    We run the audit, POST results to FORGE_WEBHOOK_URL, then exit (pod is
    destroyed by the orchestrator on completion).
    """
    import base64 as _b64

    webhook_url = os.environ.get("FORGE_WEBHOOK_URL", "")
    job_b64 = os.environ.get("FORGE_JOB_INPUT", "")

    if not job_b64 or not webhook_url:
        log.error("Pod mode: missing FORGE_JOB_INPUT or FORGE_WEBHOOK_URL")
        sys.exit(1)

    job_input = json.loads(_b64.b64decode(job_b64))
    log.info("Pod mode: starting audit for order %s", job_input.get("order_id"))

    event = {"input": job_input}
    result = handler(event)

    # POST results back to orchestrator webhook
    log.info("Pod mode: posting results to %s", webhook_url)
    try:
        resp = requests.post(
            webhook_url,
            json={"status": "COMPLETED", "output": result},
            timeout=30,
        )
        log.info("Pod mode: webhook response %d", resp.status_code)
    except Exception as exc:
        log.error("Pod mode: webhook POST failed: %s", exc)

    log.info("Pod mode: audit complete, exiting")


# ── Entry point ──
if os.environ.get("FORGE_POD_MODE") == "1":
    _run_pod_mode()
else:
    runpod.serverless.start({"handler": handler})
