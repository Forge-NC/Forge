"""Convert harness_runs/ data into matrix-compatible assurance report format.

Reads ~/.forge/harness_runs/*/summary.json + meta.json and generates
assurance-compatible JSON files in ~/.forge/assurance/ so rebuild_index.php
can index them alongside /assure reports.

Scenario → Category mapping:
  crash_recovery  → reliability
  malicious_repo  → adversarial
  repair_loop     → tool_misuse
  context_storm   → context_integrity
  endurance       → reliability
"""

import json
import hashlib
import platform
import sys
from datetime import datetime
from pathlib import Path

HARNESS_DIR = Path.home() / ".forge" / "harness_runs"
ASSURANCE_DIR = Path.home() / ".forge" / "assurance"

# Map harness scenario names to the 6 matrix categories
SCENARIO_TO_CATEGORY = {
    "crash_recovery":  "reliability",
    "malicious_repo":  "adversarial",
    "repair_loop":     "tool_misuse",
    "context_storm":   "context_integrity",
    "endurance":       "reliability",
}

ALL_CATEGORIES = ["safety", "reliability", "adversarial",
                  "tool_misuse", "exfiltration", "context_integrity"]


def _iso_to_unix(iso_str):
    """Convert ISO timestamp string to Unix float."""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.timestamp()
    except Exception:
        return 0.0


def _run_id_from_timestamp(ts_dir_name):
    """Generate a stable 16-char hex run_id from directory name."""
    h = hashlib.sha256(f"harness_{ts_dir_name}".encode()).hexdigest()
    return h[:16]


def convert_adaptive_run(run_dir):
    """Convert a run with per-scenario results[] (adaptive/fallback_smoke)."""
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))

    s = summary.get("summary", summary)
    results_list = summary.get("results", [])
    if not results_list:
        return None

    model = s.get("model", meta.get("model", "unknown"))
    mode = s.get("mode", meta.get("mode", "unknown"))
    machine_id = s.get("machine_id", meta.get("machine_id", ""))
    started = s.get("started", meta.get("started", ""))
    finished = s.get("finished", "")
    duration = s.get("total_time_s", 0)

    started_at = _iso_to_unix(started)
    completed_at = _iso_to_unix(finished) if finished else started_at + duration

    # Build per-scenario results and compute category pass rates
    cat_scores = {}  # {category: [1.0, 0.0, ...]}
    report_results = []
    prev_hash = ""

    for r in results_list:
        scenario = r.get("scenario", r.get("test_file", "").replace("test_", "").replace(".py", ""))
        category = SCENARIO_TO_CATEGORY.get(scenario, "reliability")
        passed = r.get("success", False)

        if category not in cat_scores:
            cat_scores[category] = []
        cat_scores[category].append(1.0 if passed else 0.0)

        reason = "passed" if passed else (r.get("failure_tail", "failed") or "failed")
        if r.get("error_categories"):
            reason = ", ".join(r["error_categories"])

        entry_data = f"{scenario}:{passed}:{reason}"
        entry_hash = hashlib.sha256(entry_data.encode()).hexdigest()

        report_results.append({
            "scenario_id": f"harness_{scenario}",
            "category": category,
            "passed": passed,
            "reason": reason[:200],
            "response_preview": f"Harness scenario: {scenario} ({r.get('elapsed_s', 0):.1f}s, {r.get('passed', 0)} tests passed)",
            "latency_ms": int(r.get("elapsed_s", 0) * 1000),
            "entry_hash": entry_hash,
            "prev_hash": prev_hash,
        })
        prev_hash = entry_hash

    # Compute category_pass_rates
    category_pass_rates = {}
    for cat in ALL_CATEGORIES:
        if cat in cat_scores:
            scores = cat_scores[cat]
            category_pass_rates[cat] = round(sum(scores) / len(scores), 4)

    scenarios_run = len(report_results)
    scenarios_passed = sum(1 for r in report_results if r["passed"])
    pass_rate = round(scenarios_passed / scenarios_run, 4) if scenarios_run > 0 else 0.0

    run_id = _run_id_from_timestamp(run_dir.name)

    report = {
        "run_id": run_id,
        "model": model,
        "forge_version": "0.9.0",
        "platform_info": {
            "system": platform.system(),
            "python": platform.python_version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_s": round(duration, 2),
        "machine_id": machine_id,
        "passport_id": "",
        "pass_rate": pass_rate,
        "category_pass_rates": category_pass_rates,
        "scenarios_run": scenarios_run,
        "scenarios_passed": scenarios_passed,
        "results": report_results,
        "generated_at": completed_at,
        "harness_mode": mode,
        "harness_source": run_dir.name,
        "pub_key_b64": "",
        "signature": "",
    }
    return report


def convert_iteration_run(run_dir):
    """Convert a run with per-iteration runs[] (live-smoke/live-full/stub)."""
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))

    s = summary.get("summary", summary)
    runs_list = summary.get("runs", [])
    if not runs_list:
        return None

    model = s.get("model", meta.get("model", "unknown"))
    mode = s.get("mode", meta.get("mode", "unknown"))
    machine_id = meta.get("machine_id", "")
    started = s.get("started", meta.get("started", ""))
    finished = s.get("finished", "")
    duration = s.get("total_time_s", 0)

    started_at = _iso_to_unix(started)
    completed_at = _iso_to_unix(finished) if finished else started_at + duration

    # Get scenario names from meta
    scenarios_meta = meta.get("scenarios", [])
    scenario_names = []
    for sc in scenarios_meta:
        if isinstance(sc, dict):
            scenario_names.append(sc.get("name", sc.get("test_file", "").replace("test_", "").replace(".py", "")))
        elif isinstance(sc, str):
            scenario_names.append(sc.replace("test_", "").replace(".py", ""))

    # Compute overall pass rate from iterations
    total_passed_iters = s.get("total_passed", sum(1 for r in runs_list if r.get("success", False)))
    total_iters = s.get("total_iterations", len(runs_list))
    overall_pass_rate = total_passed_iters / total_iters if total_iters > 0 else 0.0

    # Build synthetic per-scenario results (we only have iteration-level data)
    # Distribute the overall pass rate across scenarios
    cat_scores = {}
    report_results = []
    prev_hash = ""

    for sc_name in scenario_names:
        category = SCENARIO_TO_CATEGORY.get(sc_name, "reliability")
        # Since we don't have per-scenario breakdown, use overall success rate
        passed = overall_pass_rate >= 0.5

        if category not in cat_scores:
            cat_scores[category] = []
        cat_scores[category].append(1.0 if passed else 0.0)

        entry_data = f"{sc_name}:{passed}:{overall_pass_rate}"
        entry_hash = hashlib.sha256(entry_data.encode()).hexdigest()

        report_results.append({
            "scenario_id": f"harness_{sc_name}",
            "category": category,
            "passed": passed,
            "reason": f"{'passed' if passed else 'failed'} ({total_passed_iters}/{total_iters} iterations)",
            "response_preview": f"Harness {mode}: {total_iters} iterations, {total_passed_iters} passed",
            "latency_ms": int((duration / max(total_iters, 1)) * 1000),
            "entry_hash": entry_hash,
            "prev_hash": prev_hash,
        })
        prev_hash = entry_hash

    # Compute category_pass_rates
    category_pass_rates = {}
    for cat in ALL_CATEGORIES:
        if cat in cat_scores:
            scores = cat_scores[cat]
            category_pass_rates[cat] = round(sum(scores) / len(scores), 4)

    scenarios_run = len(report_results)
    scenarios_passed = sum(1 for r in report_results if r["passed"])
    pass_rate = round(scenarios_passed / scenarios_run, 4) if scenarios_run > 0 else 0.0

    run_id = _run_id_from_timestamp(run_dir.name)

    report = {
        "run_id": run_id,
        "model": model,
        "forge_version": "0.9.0",
        "platform_info": {
            "system": platform.system(),
            "python": platform.python_version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_s": round(duration, 2),
        "machine_id": machine_id,
        "passport_id": "",
        "pass_rate": pass_rate,
        "category_pass_rates": category_pass_rates,
        "scenarios_run": scenarios_run,
        "scenarios_passed": scenarios_passed,
        "results": report_results,
        "generated_at": completed_at,
        "harness_mode": mode,
        "harness_source": run_dir.name,
        "pub_key_b64": "",
        "signature": "",
    }
    return report


def main():
    if not HARNESS_DIR.is_dir():
        print(f"No harness_runs directory at {HARNESS_DIR}")
        return

    ASSURANCE_DIR.mkdir(parents=True, exist_ok=True)
    converted = 0
    skipped = 0

    for run_dir in sorted(HARNESS_DIR.iterdir()):
        if not run_dir.is_dir():
            continue
        summary_path = run_dir / "summary.json"
        if not summary_path.exists():
            continue

        run_id = _run_id_from_timestamp(run_dir.name)
        out_path = ASSURANCE_DIR / f"{run_id}.json"

        # Skip if already converted
        if out_path.exists():
            print(f"  SKIP {run_dir.name} -> {run_id} (already exists)")
            skipped += 1
            continue

        summary = json.loads(summary_path.read_text(encoding="utf-8"))

        # Determine format: results[] = adaptive, runs[] = iteration-based
        if "results" in summary:
            report = convert_adaptive_run(run_dir)
        elif "runs" in summary:
            report = convert_iteration_run(run_dir)
        else:
            print(f"  SKIP {run_dir.name} (unknown format)")
            skipped += 1
            continue

        if report is None:
            print(f"  SKIP {run_dir.name} (empty results)")
            skipped += 1
            continue

        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        mode = report.get("harness_mode", "?")
        pr = report["pass_rate"]
        cats = ", ".join(f"{k}:{v}" for k, v in report["category_pass_rates"].items())
        print(f"  OK   {run_dir.name} -> {run_id} | {report['model']} | {mode} | pass_rate={pr} | {cats}")
        converted += 1

    print(f"\nDone: {converted} converted, {skipped} skipped")
    print(f"Total reports in {ASSURANCE_DIR}: {len(list(ASSURANCE_DIR.glob('*.json')))}")


if __name__ == "__main__":
    main()
