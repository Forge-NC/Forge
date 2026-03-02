#!/usr/bin/env python3
"""Forge Adaptive Nightly Test Runner.

Fetches a per-machine test manifest from the server, validates it against
local hardware caps, runs calibrated stress tests, and uploads results.

Security model: SERVER SUGGESTS, CLIENT DECIDES.
  - Manifest is data, not instructions
  - All scenarios must be in ALLOWED_SCENARIOS (hardcoded)
  - Turns/timeout/ctx_tokens clamped to GPU-dependent safety caps
  - Reduce-only rule: server can only reduce scope unless adaptive_expand_limits

Usage:
    python scripts/nightly_smart.py                    # adaptive (server manifest)
    python scripts/nightly_smart.py --fallback-only    # smoke preset, no server
    python scripts/nightly_smart.py --full-sweep       # all scenarios, max turns
    python scripts/nightly_smart.py --dry-run          # fetch manifest, show plan
    python scripts/nightly_smart.py --max-duration 30  # 30-minute budget
"""

import argparse
import hashlib
import json
import logging
import os
import queue
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger("nightly_smart")

REPO_ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home()
FORGE_DIR = HOME / ".forge"
HARNESS_DIR = FORGE_DIR / "harness_runs"
TRENDLINE_FILE = FORGE_DIR / "harness_trend.jsonl"
NIGHTLY_LOG_DIR = FORGE_DIR / "nightly_logs"
MANIFEST_AUDIT_FILE = NIGHTLY_LOG_DIR / "manifest_audit.jsonl"

DEFAULT_MANIFEST_URL = "https://dirt-star.com/Forge/manifest.php"
DEFAULT_TELEMETRY_URL = "https://dirt-star.com/Forge/telemetry_receiver.php"
LEGACY_API_KEY = "fg_tel_2026_e7eb55900b70bd84eaeb62f7cd0153e7"

# ── Hardcoded allowlist — never run anything else ──

ALLOWED_SCENARIOS = frozenset([
    "test_endurance.py",
    "test_context_storm.py",
    "test_crash_recovery.py",
    "test_malicious_repo.py",
    "test_repair_loop.py",
    "test_model_swap.py",
    "test_plugin_chaos.py",
    "test_oscillation.py",
    "test_embedding_loss.py",
    "test_network_chaos.py",
    "test_tool_corruption.py",
    "test_verification_theater.py",
    "test_policy_drift.py",
])

LIVE_SCENARIOS = [
    "test_endurance.py",
    "test_context_storm.py",
    "test_crash_recovery.py",
    "test_malicious_repo.py",
    "test_repair_loop.py",
]

STUB_SCENARIOS = [
    "test_model_swap.py",
    "test_plugin_chaos.py",
    "test_oscillation.py",
    "test_embedding_loss.py",
    "test_network_chaos.py",
    "test_tool_corruption.py",
    "test_verification_theater.py",
    "test_policy_drift.py",
]

SMOKE_SCENARIOS = [
    {"name": "crash_recovery", "test_file": "test_crash_recovery.py",
     "turns": 5, "ctx_tokens": 4000, "timeout_s": 300, "priority": 1},
    {"name": "malicious_repo", "test_file": "test_malicious_repo.py",
     "turns": 5, "ctx_tokens": 4000, "timeout_s": 300, "priority": 2},
    {"name": "repair_loop", "test_file": "test_repair_loop.py",
     "turns": 5, "ctx_tokens": 4000, "timeout_s": 300, "priority": 3},
]

FULL_SWEEP_DEFAULTS = {
    "test_endurance.py":      {"turns": 100, "ctx_tokens": 4000, "timeout_s": 1800},
    "test_context_storm.py":  {"turns": 40,  "ctx_tokens": 1200, "timeout_s": 900},
    "test_crash_recovery.py": {"turns": 15,  "ctx_tokens": 4000, "timeout_s": 600},
    "test_malicious_repo.py": {"turns": 5,   "ctx_tokens": 4000, "timeout_s": 300},
    "test_repair_loop.py":    {"turns": 10,  "ctx_tokens": 4000, "timeout_s": 300},
}

CEILING_FILE = FORGE_DIR / "hardware_ceilings.json"


# ── Self-healing ceiling discovery (13D) ──

def _load_ceilings() -> dict:
    """Load locally discovered hardware ceilings."""
    if CEILING_FILE.exists():
        try:
            return json.loads(CEILING_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_ceilings(ceilings: dict):
    """Persist hardware ceilings."""
    CEILING_FILE.parent.mkdir(parents=True, exist_ok=True)
    CEILING_FILE.write_text(
        json.dumps(ceilings, indent=2), encoding="utf-8")


def find_ceiling(scenario_name: str, test_file: str, model: str,
                 caps: dict) -> int | None:
    """Binary search for the max stable turn count on this hardware.

    Returns the discovered ceiling, or None if the search was inconclusive.
    """
    lo = 5
    hi = caps["max_turns"]
    ceiling = lo
    ctx_tokens = FULL_SWEEP_DEFAULTS.get(test_file, {}).get("ctx_tokens", 4000)
    timeout_s = caps["max_timeout_s"]

    log.info("Ceiling search for %s: range [%d, %d]", scenario_name, lo, hi)
    steps = 0

    while lo <= hi and steps < 8:  # max 8 binary search steps
        steps += 1
        mid = (lo + hi) // 2
        log.info("  Step %d: testing %d turns...", steps, mid)

        scenario = {
            "name": scenario_name,
            "test_file": test_file,
            "turns": mid,
            "ctx_tokens": ctx_tokens,
            "timeout_s": timeout_s,
        }

        run_dir = HARNESS_DIR / f"ceiling_{scenario_name}"
        run_dir.mkdir(parents=True, exist_ok=True)
        result = _run_scenario(scenario, model, run_dir)

        if result["success"]:
            ceiling = mid
            lo = mid + 1
            log.info("    PASS at %d turns", mid)
        else:
            hi = mid - 1
            log.info("    FAIL at %d turns", mid)

    log.info("  Ceiling for %s: %d turns", scenario_name, ceiling)
    return ceiling


# ── GPU-dependent safety caps ──

def _compute_safety_caps() -> dict:
    """Derive safety caps from local GPU. Called once at startup."""
    try:
        from forge.hardware import get_hardware_summary
        hw = get_hardware_summary()
        vram_gb = hw.get("vram_gb", 0) or 0
        ram_gb = hw.get("ram_gb", 0) or 0
    except Exception:
        vram_gb = 0
        ram_gb = 0

    if vram_gb >= 20:
        tier = "high"
    elif vram_gb >= 12:
        tier = "mid"
    elif vram_gb >= 6:
        tier = "low"
    else:
        tier = "minimal"

    TIER_CAPS = {
        "high":    {"max_turns": 500, "max_ctx_tokens": 32768,
                    "max_timeout_s": 3600, "max_total_runtime_s": 14400},
        "mid":     {"max_turns": 200, "max_ctx_tokens": 16384,
                    "max_timeout_s": 1800, "max_total_runtime_s": 7200},
        "low":     {"max_turns": 100, "max_ctx_tokens": 8192,
                    "max_timeout_s": 1200, "max_total_runtime_s": 3600},
        "minimal": {"max_turns": 30,  "max_ctx_tokens": 4096,
                    "max_timeout_s": 600,  "max_total_runtime_s": 1800},
    }

    caps = dict(TIER_CAPS[tier])
    caps["tier"] = tier
    caps["vram_gb"] = vram_gb
    caps["ram_gb"] = ram_gb
    caps["max_scenarios"] = 13
    return caps


# ── Manifest validation ──

def _validate_manifest(manifest: dict, caps: dict, expand_limits: bool,
                       local_defaults: dict) -> tuple[list[dict], list[str]]:
    """Validate and clamp manifest scenarios against local caps.

    Returns (validated_scenarios, clamp_log).
    """
    if not isinstance(manifest, dict):
        return [], ["Manifest is not a dict"]

    scenarios = manifest.get("scenarios", [])
    if not isinstance(scenarios, list):
        return [], ["scenarios is not a list"]

    validated = []
    clamp_log = []

    for s in scenarios:
        test_file = s.get("test_file", "")
        if test_file not in ALLOWED_SCENARIOS:
            clamp_log.append(f"REJECTED unknown scenario: {test_file}")
            continue

        name = s.get("name", test_file.replace("test_", "").replace(".py", ""))
        turns = s.get("turns", 50)
        ctx_tokens = s.get("ctx_tokens", 4000)
        timeout_s = s.get("timeout_s", 600)
        priority = s.get("priority", 99)

        # Clamp to safety caps
        orig = {"turns": turns, "ctx_tokens": ctx_tokens, "timeout_s": timeout_s}

        turns = min(turns, caps["max_turns"])
        ctx_tokens = min(ctx_tokens, caps["max_ctx_tokens"])
        timeout_s = min(timeout_s, caps["max_timeout_s"])

        # Reduce-only rule: unless expand_limits, can only reduce below defaults
        if not expand_limits:
            defaults = local_defaults.get(test_file, {})
            if defaults:
                turns = min(turns, defaults.get("turns", turns))
                ctx_tokens = min(ctx_tokens, defaults.get("ctx_tokens", ctx_tokens))
                timeout_s = min(timeout_s, defaults.get("timeout_s", timeout_s))

        clamped = {"turns": turns, "ctx_tokens": ctx_tokens, "timeout_s": timeout_s}
        if clamped != orig:
            for k in ("turns", "ctx_tokens", "timeout_s"):
                if clamped[k] != orig[k]:
                    clamp_log.append(
                        f"{name}.{k}: {orig[k]} -> {clamped[k]}")

        validated.append({
            "name": name,
            "test_file": test_file,
            "turns": turns,
            "ctx_tokens": ctx_tokens,
            "timeout_s": timeout_s,
            "priority": priority,
            "reason": s.get("reason", ""),
        })

    validated.sort(key=lambda x: x["priority"])
    return validated, clamp_log


def _audit_log(action: str, **kwargs):
    """Append to manifest audit trail."""
    NIGHTLY_LOG_DIR.mkdir(parents=True, exist_ok=True)
    entry = {"timestamp": datetime.now().isoformat(), "action": action, **kwargs}
    with open(MANIFEST_AUDIT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ── Ollama check ──

def _check_ollama(timeout: int = 5) -> bool:
    """Check if Ollama is running at localhost:11434."""
    try:
        import requests
        resp = requests.get("http://localhost:11434/api/tags", timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


# ── Manifest fetch ──

def _fetch_manifest(machine_id: str, manifest_url: str,
                    token: str, budget_m: int) -> dict | None:
    """Fetch manifest from server. Returns parsed JSON or None."""
    try:
        import requests
        url = f"{manifest_url}?machine_id={machine_id}&budget={budget_m}"
        headers = {}
        if token:
            headers["X-Forge-Token"] = token
        else:
            headers["X-Forge-Key"] = LEGACY_API_KEY

        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            raw_hash = hashlib.sha256(
                resp.content).hexdigest()[:16]
            _audit_log("manifest_received", source="server",
                       scenarios=[s.get("name", "") for s in data.get("scenarios", [])],
                       raw_hash=f"sha256:{raw_hash}")
            return data
        else:
            log.warning("Manifest fetch failed: HTTP %d", resp.status_code)
            _audit_log("manifest_fetch_failed", status=resp.status_code)
    except Exception as e:
        log.warning("Manifest fetch error: %s", e)
        _audit_log("manifest_fetch_error", error=str(e))
    return None


# ── Test execution ──

def _parse_pytest_output(stdout: str) -> dict:
    """Parse pytest summary line for pass/fail/skip counts."""
    passed = failed = errors = skipped = 0
    for line in stdout.splitlines():
        if "=" in line and ("passed" in line or "failed" in line or "error" in line):
            for match in re.finditer(r'(\d+)\s+(passed|failed|error|skipped)', line):
                count = int(match.group(1))
                kind = match.group(2)
                if kind == "passed":
                    passed = count
                elif kind == "failed":
                    failed = count
                elif kind == "error":
                    errors = count
                elif kind == "skipped":
                    skipped = count
    return {"passed": passed, "failed": failed, "errors": errors, "skipped": skipped}


def _run_scenario(scenario: dict, model: str, run_dir: Path) -> dict:
    """Run a single test scenario as a pytest subprocess."""
    test_dir = REPO_ROOT / "tests" / "integration"
    test_path = str(test_dir / scenario["test_file"])
    timeout_s = scenario["timeout_s"]
    turns = scenario["turns"]
    ctx_tokens = scenario["ctx_tokens"]

    cmd = [
        sys.executable, "-m", "pytest",
        test_path, "-v", "--tb=short", "-x",
        f"--timeout={timeout_s}",
        "--live", f"--live-model={model}",
        f"--nightly-turns={turns}",
        f"--nightly-ctx-tokens={ctx_tokens}",
    ]

    start = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd, cwd=str(REPO_ROOT),
            capture_output=True, text=True,
            timeout=timeout_s + 60,
        )
        elapsed = time.perf_counter() - start
        counts = _parse_pytest_output(proc.stdout)
        success = proc.returncode == 0

        result = {
            "scenario": scenario["name"],
            "test_file": scenario["test_file"],
            "timestamp": datetime.now().isoformat(),
            "elapsed_s": round(elapsed, 2),
            "passed": counts["passed"],
            "failed": counts["failed"],
            "skipped": counts["skipped"],
            "success": success,
            "turns_configured": turns,
            "ctx_tokens_configured": ctx_tokens,
        }

        if not success:
            fail_lines = proc.stdout.splitlines()[-30:]
            result["failure_tail"] = "\n".join(fail_lines)

        # Save log
        log_path = run_dir / f"{scenario['name']}.log"
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(f"=== {scenario['name']} ===\n")
            f.write(f"Command: {' '.join(cmd)}\n")
            f.write(f"Return code: {proc.returncode}\n")
            f.write(f"Elapsed: {elapsed:.2f}s\n")
            f.write(f"\n=== STDOUT ===\n{proc.stdout}\n")
            if proc.stderr:
                f.write(f"\n=== STDERR ===\n{proc.stderr}\n")

        return result

    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - start
        return {
            "scenario": scenario["name"],
            "test_file": scenario["test_file"],
            "timestamp": datetime.now().isoformat(),
            "elapsed_s": round(elapsed, 2),
            "passed": 0, "failed": 0, "skipped": 0,
            "success": False,
            "turns_configured": turns,
            "ctx_tokens_configured": ctx_tokens,
            "failure_tail": "TIMEOUT: exceeded time limit",
            "error_categories": ["timeout"],
        }


# ── Telemetry upload ──

def _upload_results(results: list[dict], manifest_used: dict | None,
                    machine_id: str, model: str, full_sweep: bool,
                    run_dir: Path):
    """Build and upload a nightly telemetry bundle."""
    try:
        import requests

        now = datetime.now()
        session_data = {
            "type": "nightly_adaptive",
            "machine_id": machine_id,
            "model": model,
            "timestamp": now.isoformat(),
            "full_sweep": full_sweep,
            "scenario_count": len(results),
            "total_passed": sum(1 for r in results if r["success"]),
            "total_failed": sum(1 for r in results if not r["success"]),
            "total_duration_s": sum(r["elapsed_s"] for r in results),
        }

        bundle = {
            "session": session_data,
            "nightly_results": results,
            "manifest_used": manifest_used,
        }

        # Write audit.json to run_dir
        audit_path = run_dir / "audit.json"
        audit_path.write_text(json.dumps(bundle, indent=2, default=str),
                              encoding="utf-8")

        # Build minimal manifest.json
        import platform
        from forge.machine_id import get_machine_label

        try:
            from forge.hardware import get_hardware_summary
            hw = get_hardware_summary()
            gpu = hw.get("gpu") or {}
            hardware_info = {
                "gpu_name": gpu.get("name", "unknown"),
                "vram_total_mb": gpu.get("vram_total_mb", 0),
                "driver_version": gpu.get("driver_version", ""),
                "cuda_version": gpu.get("cuda_version", ""),
                "cpu": hw.get("cpu", ""),
                "ram_mb": hw.get("ram_mb", 0),
                "os_version": platform.platform(),
            }
        except Exception:
            hardware_info = {"gpu_name": "unknown"}

        manifest_json = {
            "forge_version": "0.9.0",
            "schema_version": 1,
            "export_timestamp": now.isoformat(),
            "machine_id": machine_id,
            "machine_label": get_machine_label(),
            "platform": platform.platform(),
            "model": model,
            "nightly_adaptive": True,
            "full_sweep": full_sweep,
            "stress_test_results": True,
            "hardware": hardware_info,
        }

        # Build zip
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json",
                        json.dumps(manifest_json, indent=2).encode("utf-8"))
            zf.writestr("audit.json",
                        json.dumps(bundle, indent=2, default=str).encode("utf-8"))

            # Include trendline tail
            if TRENDLINE_FILE.exists():
                lines = TRENDLINE_FILE.read_text(encoding="utf-8").splitlines()
                tail = "\n".join(lines[-100:]) + "\n"
                zf.writestr("stress/trendline.jsonl", tail.encode("utf-8"))

            # Include latest summary
            summary_path = run_dir / "summary.json"
            if summary_path.exists():
                zf.writestr("stress/latest_summary.json",
                            summary_path.read_bytes())

        zip_bytes = buf.getvalue()
        if len(zip_bytes) > 512 * 1024:
            log.warning("Nightly zip too large (%d bytes), skipping upload",
                        len(zip_bytes))
            return

        # Upload
        try:
            from forge.config import load_config
            token = load_config().get("telemetry_token", "")
        except Exception:
            token = ""

        headers = {}
        if token:
            headers["X-Forge-Token"] = token
        else:
            headers["X-Forge-Key"] = LEGACY_API_KEY

        resp = requests.post(
            DEFAULT_TELEMETRY_URL,
            files={"bundle": (f"forge_{machine_id}.zip", zip_bytes,
                              "application/zip")},
            headers=headers,
            data={"machine_id": machine_id},
            timeout=15,
        )
        if resp.status_code == 200:
            log.info("Nightly results uploaded successfully")
        else:
            log.warning("Nightly upload failed: HTTP %d", resp.status_code)

    except Exception as e:
        log.warning("Nightly upload error: %s", e)


# ── Trendline ──

def _append_trendline(result: dict, mode: str, model: str):
    """Append one scenario result to the JSONL trendline."""
    TRENDLINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": result["timestamp"],
        "mode": mode,
        "model": model,
        "scenario": result["scenario"],
        "duration_s": result["elapsed_s"],
        "invariant_pass": result["success"],
        "passed": result["passed"],
        "failed": result["failed"],
        "skipped": result["skipped"],
    }
    with open(TRENDLINE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ── Resource guard integration ──

def _run_resource_check(interactive: bool, config: dict) -> bool:
    """Run pre-test resource check. Returns True if safe to proceed."""
    try:
        from forge.resource_guard import check_resources, format_report, close_processes

        report = check_resources()
        if not report.heavy_processes and report.safe_to_test:
            print("  Resources: OK")
            return True

        print(format_report(report))

        if not report.safe_to_test:
            print("\n  WARNING: Insufficient resources for testing")

        if report.heavy_processes:
            auto_close = config.get("nightly_auto_close", False)
            close_list = set(config.get("nightly_auto_close_list", []))
            force_kill = config.get("nightly_force_kill", False)

            if auto_close and close_list:
                to_close = [p for p in report.heavy_processes
                            if p["name"].lower() in {n.lower() for n in close_list}]
                if to_close:
                    print(f"\n  Auto-closing {len(to_close)} process(es)...")
                    close_processes(to_close, force=force_kill)
                    time.sleep(2)
                    # Re-check
                    report = check_resources()
                    if report.safe_to_test:
                        print("  Resources after cleanup: OK")
                        return True

            if interactive:
                resp = input("\n  Continue anyway? [Y/n/skip] ").strip().lower()
                if resp in ("n", "no"):
                    return False
                if resp == "skip":
                    return False

        return True

    except ImportError:
        log.debug("resource_guard not available, skipping check")
        return True
    except Exception as e:
        log.warning("Resource check error: %s", e)
        return True


# ── Cortex overlay ──

def _start_cortex(config: dict) -> tuple[queue.Queue | None, threading.Thread | None]:
    """Start the Neural Cortex overlay if configured."""
    if not config.get("nightly_show_cortex", False):
        return None, None

    try:
        from forge.ui.cortex_overlay import CortexOverlay

        q = queue.Queue()
        position = config.get("nightly_cortex_position", "top_right")
        size = config.get("nightly_cortex_size", 180)
        overlay = CortexOverlay(cmd_queue=q, position=position, size=size)
        t = threading.Thread(target=overlay.run, daemon=True, name="cortex-overlay")
        t.start()
        return q, t
    except Exception as e:
        log.debug("Could not start cortex overlay: %s", e)
        return None, None


def _cortex(q: queue.Queue | None, *args):
    """Send a command to the cortex overlay (no-op if not running)."""
    if q is not None:
        q.put(args)


# ── Main ──

def main():
    parser = argparse.ArgumentParser(
        description="Forge Adaptive Nightly Test Runner")
    parser.add_argument(
        "--max-duration", type=int, default=None,
        help="Max total runtime in minutes (default: from config or 60)")
    parser.add_argument(
        "--model", type=str, default=None,
        help="Model for live tests (default: qwen2.5-coder:14b)")
    parser.add_argument(
        "--fallback-only", action="store_true",
        help="Skip server manifest, use smoke preset")
    parser.add_argument(
        "--full-sweep", action="store_true",
        help="Run ALL scenarios at max turns, ignore manifest + budget")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch manifest and show plan, don't run tests")
    parser.add_argument(
        "--skip-resource-check", action="store_true",
        help="Bypass pre-test resource guard")
    parser.add_argument(
        "--interactive", action="store_true", default=None,
        help="Force interactive mode (prompt user)")
    parser.add_argument(
        "--non-interactive", action="store_true",
        help="Force non-interactive mode (no prompts)")
    args = parser.parse_args()

    # Setup logging
    NIGHTLY_LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = NIGHTLY_LOG_DIR / f"nightly_smart_{timestamp}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    # Load config
    try:
        from forge.config import load_config
        config = load_config()
    except Exception:
        config = {}

    # Resolve settings
    model = args.model or config.get("default_model", "qwen2.5-coder:14b")
    max_duration_m = args.max_duration or config.get("nightly_max_duration_m", 60)
    interactive = sys.stdin.isatty() if args.interactive is None else args.interactive
    if args.non_interactive:
        interactive = False

    # Machine ID
    try:
        from forge.machine_id import get_machine_id
        machine_id = get_machine_id()
    except Exception:
        import uuid
        machine_id = uuid.uuid4().hex[:12]

    # Safety caps
    caps = _compute_safety_caps()

    print("=" * 60)
    print("  Forge Adaptive Nightly Runner")
    print("=" * 60)
    print(f"  Machine:  {machine_id}")
    print(f"  Model:    {model}")
    print(f"  GPU tier: {caps['tier']} ({caps['vram_gb']}GB VRAM)")
    print(f"  Caps:     max {caps['max_turns']} turns, "
          f"{caps['max_ctx_tokens']} ctx, "
          f"{caps['max_timeout_s']}s timeout")
    print(f"  Budget:   {max_duration_m} min")
    print(f"  Log:      {log_file}")
    print()

    # Cortex overlay
    cortex_q, cortex_t = _start_cortex(config)
    _cortex(cortex_q, "state", "initializing")
    _cortex(cortex_q, "status", "Starting up...")

    # Resource check
    if not args.skip_resource_check:
        _cortex(cortex_q, "state", "resource_check")
        _cortex(cortex_q, "status", "Checking resources...")
        if not _run_resource_check(interactive, config):
            print("  Aborted: resource check failed")
            _cortex(cortex_q, "state", "error")
            _cortex(cortex_q, "status", "Aborted: resources")
            time.sleep(3)
            _cortex(cortex_q, "close")
            return

    # Check Ollama
    _cortex(cortex_q, "state", "boot")
    _cortex(cortex_q, "status", "Checking Ollama...")
    if not _check_ollama():
        print("  ERROR: Ollama not running at localhost:11434")
        log.error("Ollama not available, aborting")
        _cortex(cortex_q, "state", "error")
        _cortex(cortex_q, "status", "Ollama not running")
        time.sleep(3)
        _cortex(cortex_q, "close")
        return

    print("  Ollama: OK")

    # Determine scenarios
    expand_limits = config.get("adaptive_expand_limits", False)
    local_defaults = FULL_SWEEP_DEFAULTS  # used for reduce-only rule

    if args.full_sweep:
        # Full sweep: all scenarios at max turns
        mode = "full_sweep"
        scenarios = []
        for i, test_file in enumerate(LIVE_SCENARIOS):
            defaults = FULL_SWEEP_DEFAULTS.get(test_file, {})
            turns = min(defaults.get("turns", 50), caps["max_turns"])
            ctx_tokens = min(defaults.get("ctx_tokens", 4000), caps["max_ctx_tokens"])
            timeout_s = min(defaults.get("timeout_s", 600), caps["max_timeout_s"])
            scenarios.append({
                "name": test_file.replace("test_", "").replace(".py", ""),
                "test_file": test_file,
                "turns": turns,
                "ctx_tokens": ctx_tokens,
                "timeout_s": timeout_s,
                "priority": i + 1,
                "reason": "full_sweep",
            })
        manifest_used = {"source": "full_sweep", "scenarios": len(scenarios)}

    elif args.fallback_only:
        mode = "fallback_smoke"
        scenarios = list(SMOKE_SCENARIOS)
        manifest_used = {"source": "fallback_smoke", "scenarios": len(scenarios)}

    else:
        # Try to fetch from server
        mode = "adaptive"
        _cortex(cortex_q, "state", "indexing")
        _cortex(cortex_q, "status", "Fetching manifest...")

        manifest_url = (config.get("nightly_manifest_url", "")
                        or DEFAULT_MANIFEST_URL)
        token = config.get("telemetry_token", "")

        raw_manifest = _fetch_manifest(machine_id, manifest_url, token,
                                       max_duration_m)

        if raw_manifest:
            scenarios, clamp_log = _validate_manifest(
                raw_manifest, caps, expand_limits, local_defaults)
            if clamp_log:
                _audit_log("manifest_applied",
                           clamped_fields=clamp_log)
                for msg in clamp_log:
                    log.info("  Clamped: %s", msg)
            manifest_used = {"source": "server", "raw": raw_manifest,
                             "clamped": clamp_log}
        else:
            print("  Server unreachable, using smoke fallback")
            scenarios = list(SMOKE_SCENARIOS)
            manifest_used = {"source": "fallback_smoke_after_server_fail"}

    # Apply time budget (skip for full-sweep)
    if not args.full_sweep:
        budget_s = max_duration_m * 60
        estimated = 0
        budgeted = []
        for s in scenarios:
            estimated += s["timeout_s"]
            if estimated > budget_s:
                log.info("Budget exceeded after %d scenarios", len(budgeted))
                break
            budgeted.append(s)
        scenarios = budgeted

    if not scenarios:
        print("  No scenarios to run")
        _cortex(cortex_q, "close")
        return

    print(f"\n  Mode: {mode}")
    print(f"  Scenarios: {len(scenarios)}")
    for s in scenarios:
        print(f"    [{s['priority']}] {s['name']} "
              f"(turns={s['turns']}, ctx={s['ctx_tokens']}, "
              f"timeout={s['timeout_s']}s)")
        if s.get("reason"):
            print(f"        reason: {s['reason']}")

    if args.dry_run:
        print("\n  DRY RUN — no tests executed")
        _cortex(cortex_q, "close")
        return

    # Create run directory
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = HARNESS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Save run metadata
    meta = {
        "run_id": run_id,
        "mode": mode,
        "model": model,
        "machine_id": machine_id,
        "caps": caps,
        "scenarios": scenarios,
        "manifest_used": manifest_used,
        "started": datetime.now().isoformat(),
    }
    (run_dir / "meta.json").write_text(
        json.dumps(meta, indent=2, default=str), encoding="utf-8")

    # Run scenarios
    print(f"\n{'=' * 60}")
    results = []
    total = len(scenarios)

    for i, scenario in enumerate(scenarios, 1):
        name = scenario["name"]
        print(f"\n  [{i}/{total}] Running: {name} "
              f"(turns={scenario['turns']})...", flush=True)

        _cortex(cortex_q, "state", "running_test")
        _cortex(cortex_q, "status", f"Running: {name} ({i}/{total})")

        result = _run_scenario(scenario, model, run_dir)
        results.append(result)

        status = "PASS" if result["success"] else "FAIL"
        state = "test_passed" if result["success"] else "test_failed"
        _cortex(cortex_q, "state", state)
        _cortex(cortex_q, "status",
                f"{status}: {name} {result['elapsed_s']:.0f}s")

        print(f"    {status}  ({result['elapsed_s']:.1f}s, "
              f"p={result['passed']} f={result['failed']})")

        _append_trendline(result, mode, model)

        # Ceiling discovery: if failed and auto_ceiling enabled, find max stable turns
        if (not result["success"]
                and config.get("nightly_auto_ceiling", False)
                and scenario["test_file"] in FULL_SWEEP_DEFAULTS):
            print(f"    Ceiling search for {name}...")
            _cortex(cortex_q, "status", f"Finding ceiling: {name}")
            ceiling = find_ceiling(name, scenario["test_file"], model, caps)
            if ceiling is not None:
                ceilings = _load_ceilings()
                ceilings[name] = {
                    "turns": ceiling,
                    "timestamp": datetime.now().isoformat(),
                    "tier": caps["tier"],
                }
                _save_ceilings(ceilings)
                print(f"    Ceiling: {ceiling} turns")

    # Summary
    total_passed = sum(1 for r in results if r["success"])
    total_failed = sum(1 for r in results if not r["success"])
    total_time = sum(r["elapsed_s"] for r in results)

    print(f"\n{'=' * 60}")
    print(f"  RESULTS: {total_passed}/{total} passed, "
          f"{total_failed} failed")
    print(f"  Duration: {total_time:.1f}s ({total_time/60:.1f}m)")
    print(f"  Run dir:  {run_dir}")

    # Save summary
    summary = {
        "summary": {
            "total_scenarios": total,
            "total_passed": total_passed,
            "total_failed": total_failed,
            "total_time_s": round(total_time, 2),
            "mode": mode,
            "model": model,
            "machine_id": machine_id,
            "caps_tier": caps["tier"],
            "full_sweep": args.full_sweep,
            "started": meta["started"],
            "finished": datetime.now().isoformat(),
        },
        "results": results,
    }
    (run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8")

    # Upload telemetry
    telemetry_enabled = config.get("telemetry_enabled", False)
    if telemetry_enabled:
        _cortex(cortex_q, "state", "indexing")
        _cortex(cortex_q, "status", "Uploading results...")
        print("\n  Uploading telemetry...")
        _upload_results(results, manifest_used, machine_id, model,
                        args.full_sweep, run_dir)

    # Regenerate dashboard
    try:
        dashboard_script = REPO_ROOT / "scripts" / "view_stress_results.py"
        if dashboard_script.exists():
            subprocess.run(
                [sys.executable, str(dashboard_script), "--no-open"],
                cwd=str(REPO_ROOT), capture_output=True, timeout=30)
    except Exception:
        pass

    # Final cortex state
    final_state = "complete" if total_failed == 0 else "test_failed"
    _cortex(cortex_q, "state", final_state)
    _cortex(cortex_q, "status",
            f"Done: {total_passed}/{total} passed")
    time.sleep(5)
    _cortex(cortex_q, "close")

    print(f"\n  Log: {log_file}")
    sys.exit(0 if total_failed == 0 else 1)


if __name__ == "__main__":
    main()
