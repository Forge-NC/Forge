#!/usr/bin/env python3
"""Forge Regression Bisection — find the commit that broke a scenario.

Uses git bisect programmatically to identify the exact commit that introduced
a test regression. Takes a scenario name and a "last known good" commit.

Usage:
    python scripts/bisect_failure.py context_storm abc1234
    python scripts/bisect_failure.py endurance HEAD~10
    python scripts/bisect_failure.py --list-failures   # show recent failures
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FORGE_DIR = Path.home() / ".forge"
TRENDLINE_FILE = FORGE_DIR / "harness_trend.jsonl"
BISECT_LOG = FORGE_DIR / "nightly_logs" / "bisect_log.jsonl"

SCENARIO_FILES = {
    "endurance": "test_endurance.py",
    "context_storm": "test_context_storm.py",
    "crash_recovery": "test_crash_recovery.py",
    "malicious_repo": "test_malicious_repo.py",
    "repair_loop": "test_repair_loop.py",
}


def list_recent_failures():
    """Show recent scenario failures from trendline."""
    if not TRENDLINE_FILE.exists():
        print("No trendline data found.")
        return

    failures = []
    for line in TRENDLINE_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            if not entry.get("invariant_pass", True):
                failures.append(entry)
        except json.JSONDecodeError:
            pass

    if not failures:
        print("No failures found in trendline.")
        return

    print(f"Recent failures (last 20 of {len(failures)}):\n")
    for f in failures[-20:]:
        scenario = f.get("scenario", f.get("mode", "?"))
        ts = f.get("timestamp", "?")[:19]
        model = f.get("model", "?")
        print(f"  {ts}  {scenario:<20}  model={model}")


def run_scenario(scenario_name: str, timeout: int = 600) -> bool:
    """Run a single scenario and return True if it passes."""
    test_file = SCENARIO_FILES.get(scenario_name)
    if not test_file:
        print(f"Unknown scenario: {scenario_name}")
        return False

    test_path = REPO_ROOT / "tests" / "integration" / test_file
    cmd = [
        sys.executable, "-m", "pytest",
        str(test_path), "-v", "--tb=short", "-x",
        f"--timeout={timeout}",
        "--live", "--live-model=qwen2.5-coder:14b",
        "--nightly-turns=5",
        "--nightly-ctx-tokens=2000",
    ]

    try:
        proc = subprocess.run(
            cmd, cwd=str(REPO_ROOT),
            capture_output=True, text=True,
            timeout=timeout + 60,
        )
        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def bisect(scenario_name: str, good_commit: str):
    """Run git bisect to find the regression commit."""
    print(f"Bisecting {scenario_name}: good={good_commit}, bad=HEAD")
    print()

    # Verify we're in a git repo
    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(REPO_ROOT), capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("ERROR: Not in a git repository")
        return

    # Start bisect
    subprocess.run(
        ["git", "bisect", "start", "HEAD", good_commit],
        cwd=str(REPO_ROOT), check=True)

    try:
        step = 0
        while True:
            step += 1
            # Get current commit
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(REPO_ROOT), capture_output=True, text=True)
            commit = result.stdout.strip()

            # Get commit message
            result = subprocess.run(
                ["git", "log", "--oneline", "-1"],
                cwd=str(REPO_ROOT), capture_output=True, text=True)
            commit_msg = result.stdout.strip()

            print(f"  Step {step}: testing {commit_msg}")

            passed = run_scenario(scenario_name)
            status = "good" if passed else "bad"
            print(f"    -> {status.upper()}")

            result = subprocess.run(
                ["git", "bisect", status],
                cwd=str(REPO_ROOT), capture_output=True, text=True)

            output = result.stdout.strip()
            print(f"    {output}")

            # Check if bisect is done
            if "is the first bad commit" in output:
                print(f"\n  FOUND: Regression introduced in:")
                print(f"  {output}")

                # Get changed files
                lines = output.split("\n")
                if lines:
                    bad_hash = lines[0].split()[0] if lines[0] else "?"
                    files_result = subprocess.run(
                        ["git", "diff-tree", "--no-commit-id", "--name-only",
                         "-r", bad_hash],
                        cwd=str(REPO_ROOT), capture_output=True, text=True)
                    changed = files_result.stdout.strip()
                    if changed:
                        print(f"\n  Changed files:")
                        for f in changed.splitlines():
                            print(f"    {f}")

                # Log result
                _log_bisect(scenario_name, good_commit, bad_hash, output)
                break

            if result.returncode != 0 and "is the first bad commit" not in output:
                print(f"  Bisect failed: {output}")
                break

    finally:
        # Always reset bisect
        subprocess.run(
            ["git", "bisect", "reset"],
            cwd=str(REPO_ROOT), capture_output=True)
        print("\n  git bisect reset — back to original HEAD")


def _log_bisect(scenario: str, good: str, bad: str, output: str):
    """Log bisect result to JSONL."""
    BISECT_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now().isoformat(),
        "scenario": scenario,
        "good_commit": good,
        "bad_commit": bad,
        "output": output,
    }
    with open(BISECT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Forge Regression Bisection")
    parser.add_argument(
        "scenario", nargs="?",
        help=f"Scenario name ({', '.join(SCENARIO_FILES.keys())})")
    parser.add_argument(
        "good_commit", nargs="?",
        help="Last known good commit (hash or ref like HEAD~10)")
    parser.add_argument(
        "--list-failures", action="store_true",
        help="Show recent scenario failures")
    parser.add_argument(
        "--timeout", type=int, default=600,
        help="Timeout per scenario run in seconds")
    args = parser.parse_args()

    if args.list_failures:
        list_recent_failures()
        return

    if not args.scenario or not args.good_commit:
        parser.print_help()
        print(f"\nAvailable scenarios: {', '.join(SCENARIO_FILES.keys())}")
        return

    bisect(args.scenario, args.good_commit)


if __name__ == "__main__":
    main()
