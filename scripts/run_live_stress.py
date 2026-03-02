#!/usr/bin/env python3
"""Forge Integration Stress Runner.

Runs the integration test suite N times back-to-back in stub or live mode.
Produces per-run folders, an append-only JSONL trendline, and a summary.

Presets:
    --stub          All 13 scenarios against OllamaStub        (~40s/iter)
    --live --smoke  Endurance-short + crash + malicious repo    (~3min/iter)
    --live --full   All 6 live-compatible scenarios              (~10min/iter)
    --live --soak   Endurance 220-turn + context storm maxed    (~15min/iter)

Usage:
    python scripts/run_live_stress.py                        # 20 iter, stub
    python scripts/run_live_stress.py --live --full -n 20    # 20 iter, live full
    python scripts/run_live_stress.py --live --smoke -n 5    # 5 iter, live smoke
    python scripts/run_live_stress.py --live --soak -n 3     # 3 iter, live soak
    python scripts/run_live_stress.py --fail-fast            # Stop on first fail

Output:
    ~/.forge/harness_runs/<timestamp>/   per-run folder
    ~/.forge/harness_trend.jsonl         append-only trendline
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home()
HARNESS_DIR = HOME / ".forge" / "harness_runs"
TRENDLINE_FILE = HOME / ".forge" / "harness_trend.jsonl"

# All 13 scenario test files in order
ALL_SCENARIOS = [
    "test_endurance.py",             # 1
    "test_model_swap.py",            # 2  (stub_only)
    "test_context_storm.py",         # 3
    "test_plugin_chaos.py",          # 4  (stub_only)
    "test_crash_recovery.py",        # 5
    "test_malicious_repo.py",        # 6
    "test_oscillation.py",           # 7  (stub_only)
    "test_repair_loop.py",           # 8
    "test_embedding_loss.py",        # 9  (stub_only)
    "test_network_chaos.py",         # 10 (stub_only)
    "test_tool_corruption.py",       # 11 (stub_only)
    "test_verification_theater.py",  # 12 (stub_only)
    "test_policy_drift.py",          # 13 (stub_only)
]

# Live-compatible scenarios (not marked stub_only)
LIVE_SCENARIOS = [
    "test_endurance.py",        # 1
    "test_context_storm.py",    # 3
    "test_crash_recovery.py",   # 5
    "test_malicious_repo.py",   # 6
    "test_repair_loop.py",      # 8
]

# Presets
PRESET_SMOKE = [
    "test_crash_recovery.py",   # 5  (quick, 20 turns)
    "test_malicious_repo.py",   # 6  (no model needed)
    "test_repair_loop.py",      # 8  (no model needed)
]

PRESET_SOAK = [
    "test_endurance.py",        # 1  (220 turns)
    "test_context_storm.py",    # 3  (60 turns, rapid swaps)
]


def parse_scenario_range(spec: str) -> list[str]:
    """Parse '1-5' or '3,7,11' into test file list."""
    indices = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            indices.update(range(int(lo), int(hi) + 1))
        else:
            indices.add(int(part))
    return [ALL_SCENARIOS[i - 1] for i in sorted(indices)
            if 1 <= i <= len(ALL_SCENARIOS)]


def create_run_dir(run_id: str) -> Path:
    """Create a timestamped run directory."""
    run_dir = HARNESS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "artifacts").mkdir(exist_ok=True)
    return run_dir


def parse_pytest_output(stdout: str) -> dict:
    """Parse pytest summary line for pass/fail/skip counts."""
    passed = failed = errors = skipped = 0

    # Look for summary line: "X passed, Y failed, Z skipped in Ns"
    for line in stdout.splitlines():
        if "=" in line and ("passed" in line or "failed" in line
                            or "error" in line):
            # Parse each count
            for match in re.finditer(r'(\d+)\s+(passed|failed|error|skipped)',
                                     line):
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

    return {
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
    }


def parse_failure_details(stdout: str) -> list[dict]:
    """Extract individual test failure info from pytest output."""
    failures = []
    lines = stdout.splitlines()

    for i, line in enumerate(lines):
        if line.strip().startswith("FAILED "):
            # e.g. "FAILED tests/integration/test_endurance.py::TestEndurance::test_..."
            test_path = line.strip().replace("FAILED ", "")
            # Try to get the scenario name
            parts = test_path.split("::")
            scenario = parts[0].split("/")[-1] if parts else "unknown"
            test_name = parts[-1] if len(parts) > 1 else "unknown"
            failures.append({
                "scenario": scenario,
                "test": test_name,
                "error": "",  # Could parse short traceback if needed
            })

    return failures


def run_iteration(iteration: int, test_files: list[str],
                  live: bool, timeout: int, model: str,
                  run_dir: Path) -> dict:
    """Run one full pytest iteration and return results."""
    test_dir = REPO_ROOT / "tests" / "integration"
    targets = [str(test_dir / f) for f in test_files]

    # Compute per-iteration timeout: sum of per-test timeouts
    # Live mode needs much more time for inference-heavy tests
    iter_timeout = timeout * len(test_files) + 120  # Buffer

    cmd = [
        sys.executable, "-m", "pytest",
        *targets,
        "-v",
        "--tb=short",
        f"--timeout={timeout}",
        "-x",  # Stop on first failure within iteration
    ]
    if live:
        cmd.extend(["--live", f"--live-model={model}"])

    start = time.perf_counter()
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=iter_timeout,
    )
    elapsed = time.perf_counter() - start

    # Parse output
    counts = parse_pytest_output(proc.stdout)
    failure_details = parse_failure_details(proc.stdout)

    result = {
        "iteration": iteration,
        "timestamp": datetime.now().isoformat(),
        "elapsed_s": round(elapsed, 2),
        "returncode": proc.returncode,
        "passed": counts["passed"],
        "failed": counts["failed"],
        "errors": counts["errors"],
        "skipped": counts["skipped"],
        "success": proc.returncode == 0,
        "invariant_pass": proc.returncode == 0,
    }

    if failure_details:
        result["failures"] = failure_details

    # Save full logs to run directory
    log_path = run_dir / f"iter_{iteration:04d}.log"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"=== Iteration {iteration} ===\n")
        f.write(f"Command: {' '.join(cmd)}\n")
        f.write(f"Return code: {proc.returncode}\n")
        f.write(f"Elapsed: {elapsed:.2f}s\n")
        f.write(f"\n=== STDOUT ===\n{proc.stdout}\n")
        if proc.stderr:
            f.write(f"\n=== STDERR ===\n{proc.stderr}\n")

    # If failed, capture the failure output in result
    if proc.returncode != 0:
        fail_lines = proc.stdout.splitlines()[-50:]
        result["failure_tail"] = "\n".join(fail_lines)

    return result


def append_trendline(entry: dict, mode: str, model: str,
                     scenario_count: int, test_count: int):
    """Append one line to the JSONL trendline."""
    TRENDLINE_FILE.parent.mkdir(parents=True, exist_ok=True)

    trend_entry = {
        "timestamp": entry["timestamp"],
        "mode": mode,
        "model": model,
        "scenario_count": scenario_count,
        "test_count": entry["passed"] + entry["failed"] + entry["skipped"],
        "duration_s": entry["elapsed_s"],
        "invariant_pass": entry["success"],
        "invariant_failures": entry.get("failures", []),
        "passed": entry["passed"],
        "failed": entry["failed"],
        "skipped": entry["skipped"],
    }

    with open(TRENDLINE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(trend_entry) + "\n")


def print_summary(results: list[dict], mode: str, model: str):
    """Print a summary table of all iterations."""
    total = len(results)
    if total == 0:
        return

    successes = sum(1 for r in results if r["success"])
    failures = total - successes
    total_time = sum(r["elapsed_s"] for r in results)
    avg_time = total_time / total
    total_tests = sum(r["passed"] for r in results)

    print("\n" + "=" * 64)
    print(f"  FORGE STRESS TEST RESULTS -- {total} iterations")
    print("=" * 64)
    print(f"  Mode:        {mode}")
    print(f"  Model:       {model}")
    print(f"  Passed:      {successes}/{total} iterations")
    print(f"  Failed:      {failures}/{total} iterations")
    print(f"  Total tests: {total_tests} test runs across all iterations")
    print(f"  Total time:  {total_time:.1f}s ({total_time/60:.1f}m)")
    print(f"  Avg/iter:    {avg_time:.1f}s")
    print(f"  Success:     {100*successes/total:.1f}%")

    if failures > 0:
        print(f"\n  FAILED ITERATIONS:")
        for r in results:
            if not r["success"]:
                fail_info = ""
                if "failures" in r:
                    names = [f["test"] for f in r["failures"]]
                    fail_info = f" [{', '.join(names[:3])}]"
                print(f"    #{r['iteration']}: "
                      f"rc={r['returncode']}, "
                      f"passed={r['passed']}, "
                      f"failed={r['failed']}{fail_info}")

    times = [r["elapsed_s"] for r in results]
    print(f"\n  Timing: min={min(times):.1f}s, "
          f"max={max(times):.1f}s, "
          f"median={sorted(times)[len(times)//2]:.1f}s")
    print("=" * 64)


def main():
    parser = argparse.ArgumentParser(
        description="Forge Integration Stress Runner")
    parser.add_argument(
        "-n", "--iterations", type=int, default=20,
        help="Number of iterations (default: 20)")
    parser.add_argument(
        "--live", action="store_true",
        help="Use real Ollama instead of stub")
    parser.add_argument(
        "--model", type=str, default="qwen2.5-coder:14b",
        help="Model for live mode (default: qwen2.5-coder:14b)")

    # Presets (mutually exclusive)
    preset_group = parser.add_mutually_exclusive_group()
    preset_group.add_argument(
        "--smoke", action="store_true",
        help="Live smoke: crash recovery + malicious repo + repair (~3min/iter)")
    preset_group.add_argument(
        "--full", action="store_true",
        help="Live full: all live-compatible scenarios (~10min/iter)")
    preset_group.add_argument(
        "--soak", action="store_true",
        help="Live soak: endurance + context storm (~15min/iter)")

    parser.add_argument(
        "--scenarios", type=str, default=None,
        help="Scenario range, e.g. '1-5' or '3,7,11' (overrides presets)")
    parser.add_argument(
        "--full-sweep", action="store_true",
        help="Run ALL live + stub scenarios at max turns (delegates to nightly_smart.py)")
    parser.add_argument(
        "--fail-fast", action="store_true",
        help="Stop on first failed iteration")
    parser.add_argument(
        "--timeout", type=int, default=None,
        help="Timeout per test in seconds (auto-detected by default)")

    args = parser.parse_args()

    # Full-sweep delegates to nightly_smart.py
    if args.full_sweep:
        smart_script = REPO_ROOT / "scripts" / "nightly_smart.py"
        sys.exit(subprocess.run(
            [sys.executable, str(smart_script), "--full-sweep"],
            cwd=str(REPO_ROOT),
        ).returncode)

    # Resolve test file list
    if args.scenarios:
        test_files = parse_scenario_range(args.scenarios)
        mode_name = f"custom({args.scenarios})"
    elif args.smoke:
        test_files = PRESET_SMOKE
        mode_name = "live-smoke"
    elif args.soak:
        test_files = PRESET_SOAK
        mode_name = "live-soak"
    elif args.full and args.live:
        test_files = LIVE_SCENARIOS
        mode_name = "live-full"
    elif args.live:
        test_files = LIVE_SCENARIOS
        mode_name = "live-full"
    else:
        test_files = ALL_SCENARIOS
        mode_name = "stub"

    # Auto-detect timeout
    if args.timeout:
        timeout = args.timeout
    elif args.live:
        timeout = 600  # 10min per test for live mode
    else:
        timeout = 300  # 5min per test for stub mode

    model = args.model
    is_live = args.live

    # Create run directory
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = create_run_dir(run_id)

    print(f"Forge Integration Stress Runner")
    print(f"  Mode:       {mode_name}")
    print(f"  Model:      {model}")
    print(f"  Iterations: {args.iterations}")
    print(f"  Scenarios:  {len(test_files)} ({', '.join(f.replace('test_','').replace('.py','') for f in test_files)})")
    print(f"  Timeout:    {timeout}s per test")
    print(f"  Run dir:    {run_dir}")
    print(f"  Trendline:  {TRENDLINE_FILE}")
    print()

    # Save run metadata
    meta = {
        "run_id": run_id,
        "mode": mode_name,
        "model": model,
        "iterations": args.iterations,
        "scenarios": test_files,
        "timeout": timeout,
        "live": is_live,
        "started": datetime.now().isoformat(),
    }
    (run_dir / "meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8")

    run_results = []
    start_time = time.perf_counter()

    for i in range(1, args.iterations + 1):
        print(f"[{i}/{args.iterations}] Running... ", end="", flush=True)

        try:
            result = run_iteration(
                i, test_files, is_live, timeout, model, run_dir)
        except subprocess.TimeoutExpired:
            result = {
                "iteration": i,
                "timestamp": datetime.now().isoformat(),
                "elapsed_s": timeout,
                "returncode": -1,
                "passed": 0,
                "failed": 0,
                "errors": 0,
                "skipped": 0,
                "success": False,
                "invariant_pass": False,
                "failure_tail": "TIMEOUT: iteration exceeded time limit",
            }
        except Exception as e:
            result = {
                "iteration": i,
                "timestamp": datetime.now().isoformat(),
                "elapsed_s": 0,
                "returncode": -2,
                "passed": 0,
                "failed": 0,
                "errors": 0,
                "skipped": 0,
                "success": False,
                "invariant_pass": False,
                "failure_tail": f"EXCEPTION: {e}",
            }

        run_results.append(result)

        # Print status
        status = "PASS" if result["success"] else "FAIL"
        fail_str = f", {result['failed']} failed" if result["failed"] else ""
        skip_str = f", {result['skipped']} skipped" if result["skipped"] else ""
        print(f"{status}  ({result['elapsed_s']:.1f}s, "
              f"{result['passed']} passed{fail_str}{skip_str})")

        # Append to trendline (crash-resilient, one line at a time)
        append_trendline(result, mode_name, model, len(test_files),
                         result["passed"] + result["failed"])

        if not result["success"] and args.fail_fast:
            print(f"\n  Stopping early (--fail-fast)")
            if "failure_tail" in result:
                print(f"\n  Last output:\n{result['failure_tail']}")
            break

    total_elapsed = time.perf_counter() - start_time

    # Save run summary
    summary = {
        "total_iterations": len(run_results),
        "total_passed": sum(1 for r in run_results if r["success"]),
        "total_failed": sum(1 for r in run_results if not r["success"]),
        "total_time_s": round(total_elapsed, 2),
        "avg_iteration_s": round(total_elapsed / len(run_results), 2),
        "success_rate_pct": round(
            100 * sum(1 for r in run_results if r["success"])
            / len(run_results), 1),
        "mode": mode_name,
        "model": model,
        "scenarios": len(test_files),
        "started": run_results[0]["timestamp"] if run_results else "",
        "finished": datetime.now().isoformat(),
    }
    (run_dir / "summary.json").write_text(
        json.dumps({"summary": summary, "runs": run_results}, indent=2),
        encoding="utf-8")

    print_summary(run_results, mode_name, model)
    print(f"\n  Run folder: {run_dir}")
    print(f"  Trendline:  {TRENDLINE_FILE}")

    # Exit code: 0 if all passed, 1 if any failed
    sys.exit(0 if all(r["success"] for r in run_results) else 1)


if __name__ == "__main__":
    main()
