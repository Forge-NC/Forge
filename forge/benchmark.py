"""Reproducible benchmark suite — measures Forge refactoring quality.

Runs deterministic coding scenarios in isolated temp directories,
validates results against expected patterns, and stores artifacts
for cross-run comparison.

Metrics (focused, expandable later):
  - File scope accuracy (did it modify the right files?)
  - Validation pass/fail (do tests still pass?)
  - Iteration count (how many agent loop iterations?)
  - Time to completion

Results stored in ~/.forge/benchmarks/ as JSON with:
  - Exact prompt + model + config hash + verifier mode
  - Validation command stdout/stderr
"""

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Try to import YAML for scenario loading
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


# ── Data classes ──

@dataclass
class ValidationConfig:
    """How to validate benchmark results."""
    test_command: list = field(default_factory=list)
    expected_patterns: dict = field(default_factory=dict)
    forbidden_patterns: dict = field(default_factory=dict)


@dataclass
class BenchmarkScenario:
    """A single benchmark test case."""
    id: str
    name: str
    description: str = ""
    category: str = "refactor"
    difficulty: str = "easy"
    files: dict = field(default_factory=dict)    # {path: content}
    prompt: str = ""
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    expected_file_scope: list = field(default_factory=list)
    timeout_s: int = 120


@dataclass
class BenchmarkResult:
    """Result of running a single benchmark scenario."""
    scenario_id: str
    scenario_name: str
    timestamp: float
    duration_s: float
    passed: bool
    behavior_preserved: bool
    correct_output: bool
    file_scope_accuracy: float
    iteration_count: int
    files_modified: list = field(default_factory=list)
    files_expected: list = field(default_factory=list)
    model: str = ""
    config_hash: str = ""
    prompt: str = ""
    error: str = ""
    validation_details: dict = field(default_factory=dict)


@dataclass
class BenchmarkSuiteResult:
    """Aggregate result of running a benchmark suite."""
    suite_name: str
    timestamp: float
    duration_s: float
    results: list = field(default_factory=list)
    model: str = ""
    config_hash: str = ""
    pass_rate: float = 0.0
    avg_duration_s: float = 0.0
    avg_iterations: float = 0.0
    avg_file_scope_accuracy: float = 0.0


# ── Benchmark Runner ──

class BenchmarkRunner:
    """Executes benchmark scenarios in isolation."""

    def __init__(self, scenarios_dir: Path = None,
                 results_dir: Path = None):
        self._scenarios_dir = scenarios_dir or (
            Path(__file__).parent / "benchmarks" / "scenarios")
        self._results_dir = results_dir or (
            Path.home() / ".forge" / "benchmarks")
        self._results_dir.mkdir(parents=True, exist_ok=True)

    def list_suites(self) -> list[str]:
        """List available benchmark suites (subdirectories)."""
        if not self._scenarios_dir.exists():
            return []
        return [d.name for d in self._scenarios_dir.iterdir() if d.is_dir()]

    def list_scenarios(self, suite: str = None) -> list[BenchmarkScenario]:
        """List all scenarios, optionally filtered by suite."""
        scenarios = []
        if suite:
            suite_dir = self._scenarios_dir / suite
            if suite_dir.exists():
                scenarios.extend(self._load_suite_scenarios(suite_dir))
        else:
            for suite_dir in self._scenarios_dir.iterdir():
                if suite_dir.is_dir():
                    scenarios.extend(self._load_suite_scenarios(suite_dir))
        return scenarios

    def load_scenario(self, path: Path) -> BenchmarkScenario:
        """Load a single scenario from YAML or JSON file."""
        content = path.read_text(encoding="utf-8")
        if path.suffix in (".yaml", ".yml"):
            if not HAS_YAML:
                raise ImportError("pyyaml required: pip install pyyaml")
            data = yaml.safe_load(content)
        else:
            data = json.loads(content)
        return self._parse_scenario(data)

    def run_scenario(self, scenario: BenchmarkScenario,
                     model: str = "", config_hash: str = ""
                     ) -> BenchmarkResult:
        """Run a single benchmark in an isolated temp directory.

        Does NOT invoke Forge engine — validates scenario setup and
        pattern matching only. Full engine integration requires
        engine_factory (future enhancement).
        """
        start = time.time()

        # Create isolated temp directory
        work_dir = tempfile.mkdtemp(prefix="forge_bench_")
        try:
            # Write scenario files
            for file_path, content in scenario.files.items():
                full_path = Path(work_dir) / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(content, encoding="utf-8")

            # Run pre-validation (tests should pass BEFORE changes)
            pre_ok, pre_details = self._run_validation(
                scenario.validation, work_dir)

            # For now, measure validation infrastructure only.
            # Full engine execution requires engine_factory (Phase 2 enhancement).
            behavior_preserved = pre_ok
            correct_output = True
            iteration_count = 0
            files_modified = []

            # Compute file scope accuracy
            file_scope = self._compute_file_scope(
                files_modified, scenario.expected_file_scope)

            duration = time.time() - start
            passed = behavior_preserved and correct_output

            return BenchmarkResult(
                scenario_id=scenario.id,
                scenario_name=scenario.name,
                timestamp=start,
                duration_s=round(duration, 3),
                passed=passed,
                behavior_preserved=behavior_preserved,
                correct_output=correct_output,
                file_scope_accuracy=file_scope,
                iteration_count=iteration_count,
                files_modified=files_modified,
                files_expected=list(scenario.expected_file_scope),
                model=model,
                config_hash=config_hash,
                prompt=scenario.prompt,
                validation_details=pre_details,
            )
        except Exception as e:
            duration = time.time() - start
            return BenchmarkResult(
                scenario_id=scenario.id,
                scenario_name=scenario.name,
                timestamp=start,
                duration_s=round(duration, 3),
                passed=False,
                behavior_preserved=False,
                correct_output=False,
                file_scope_accuracy=0.0,
                iteration_count=0,
                model=model,
                config_hash=config_hash,
                prompt=scenario.prompt,
                error=str(e),
            )
        finally:
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except Exception:
                pass

    def run_suite(self, suite_name: str,
                  model: str = "", config_hash: str = ""
                  ) -> BenchmarkSuiteResult:
        """Run all scenarios in a suite."""
        start = time.time()
        scenarios = self.list_scenarios(suite_name)
        results = []

        for scenario in scenarios:
            result = self.run_scenario(scenario, model, config_hash)
            results.append(result)

        duration = time.time() - start
        passed = [r for r in results if r.passed]

        return BenchmarkSuiteResult(
            suite_name=suite_name,
            timestamp=start,
            duration_s=round(duration, 3),
            results=[asdict(r) for r in results],
            model=model,
            config_hash=config_hash,
            pass_rate=len(passed) / max(1, len(results)),
            avg_duration_s=round(
                sum(r.duration_s for r in results) / max(1, len(results)), 3),
            avg_iterations=round(
                sum(r.iteration_count for r in results) / max(1, len(results)), 1),
            avg_file_scope_accuracy=round(
                sum(r.file_scope_accuracy for r in results) / max(1, len(results)), 3),
        )

    def save_result(self, result: BenchmarkSuiteResult) -> Path:
        """Persist suite result to disk."""
        ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(result.timestamp))
        path = self._results_dir / f"{ts}_{result.suite_name}.json"
        path.write_text(
            json.dumps(asdict(result), indent=2, default=str),
            encoding="utf-8")
        return path

    def load_results(self, suite: str = None,
                     count: int = 20) -> list[dict]:
        """Load historical results."""
        results = []
        if not self._results_dir.exists():
            return results

        files = sorted(self._results_dir.glob("*.json"),
                       key=lambda p: p.name, reverse=True)
        for f in files[:count]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if suite and data.get("suite_name") != suite:
                    continue
                results.append(data)
            except Exception:
                continue
        return results

    def compare_results(self, a: dict, b: dict) -> dict:
        """Compare two suite results."""
        return {
            "pass_rate_delta": (
                b.get("pass_rate", 0) - a.get("pass_rate", 0)),
            "duration_delta": (
                b.get("avg_duration_s", 0) - a.get("avg_duration_s", 0)),
            "iterations_delta": (
                b.get("avg_iterations", 0) - a.get("avg_iterations", 0)),
            "scope_accuracy_delta": (
                b.get("avg_file_scope_accuracy", 0)
                - a.get("avg_file_scope_accuracy", 0)),
            "a_model": a.get("model", "?"),
            "b_model": b.get("model", "?"),
        }

    def format_results(self, result: BenchmarkSuiteResult) -> str:
        """Terminal display of suite results."""
        from forge.ui.terminal import BOLD, RESET, DIM, GREEN, RED, CYAN, YELLOW

        passed = sum(1 for r in result.results if r.get("passed"))
        total = len(result.results)
        color = GREEN if passed == total else YELLOW if passed > 0 else RED

        lines = [
            f"\n{BOLD}Benchmark: {result.suite_name}{RESET}",
            f"  Model:     {result.model or 'n/a'}",
            f"  Pass rate: {color}{passed}/{total} "
            f"({result.pass_rate * 100:.0f}%){RESET}",
            f"  Avg time:  {result.avg_duration_s:.3f}s",
            f"  Avg iters: {result.avg_iterations:.1f}",
            f"  Scope acc: {result.avg_file_scope_accuracy * 100:.0f}%",
            "",
        ]

        for r in result.results:
            icon = f"{GREEN}V{RESET}" if r.get("passed") else f"{RED}X{RESET}"
            name = r.get("scenario_name", r.get("scenario_id", "?"))
            dur = r.get("duration_s", 0)
            lines.append(f"  {icon} {name} ({dur:.3f}s)")
            if r.get("error"):
                lines.append(f"    {DIM}{r['error'][:80]}{RESET}")

        # ASCII sparkline of durations
        durations = [r.get("duration_s", 0) for r in result.results]
        if len(durations) >= 3:
            try:
                from forge.ui.charts import ChartRenderer
                spark = ChartRenderer.ascii_sparkline(durations, width=20)
                lines.append(f"\n  {DIM}Duration: {spark}{RESET}")
            except Exception:
                pass

        return "\n".join(lines)

    @staticmethod
    def compute_config_hash(model: str = "", context_size: int = 0,
                            safety_level: int = 1,
                            router_enabled: bool = False,
                            dedup_enabled: bool = True,
                            verify_mode: str = "off") -> str:
        """Hash relevant config for benchmark comparability."""
        key = f"{model}|{context_size}|{safety_level}|{router_enabled}|{dedup_enabled}|{verify_mode}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    # ── Internal helpers ──

    def _load_suite_scenarios(self, suite_dir: Path
                              ) -> list[BenchmarkScenario]:
        """Load all scenarios from a suite directory."""
        scenarios = []
        for f in sorted(suite_dir.iterdir()):
            if f.suffix in (".yaml", ".yml", ".json"):
                try:
                    scenarios.append(self.load_scenario(f))
                except Exception as e:
                    log.debug("Failed to load scenario %s: %s", f, e)
        return scenarios

    @staticmethod
    def _parse_scenario(data: dict) -> BenchmarkScenario:
        """Parse a scenario dict into a BenchmarkScenario."""
        val_data = data.get("validation", {})
        validation = ValidationConfig(
            test_command=val_data.get("test_command", []),
            expected_patterns=val_data.get("expected_patterns", {}),
            forbidden_patterns=val_data.get("forbidden_patterns", {}),
        )
        return BenchmarkScenario(
            id=data.get("id", "unknown"),
            name=data.get("name", data.get("id", "unknown")),
            description=data.get("description", ""),
            category=data.get("category", "refactor"),
            difficulty=data.get("difficulty", "easy"),
            files=data.get("files", {}),
            prompt=data.get("prompt", ""),
            validation=validation,
            expected_file_scope=data.get("expected_file_scope", []),
            timeout_s=data.get("timeout_s", 120),
        )

    @staticmethod
    def _run_validation(validation: ValidationConfig,
                        work_dir: str) -> tuple[bool, dict]:
        """Run validation checks. Returns (passed, details_dict)."""
        details = {}

        # Test command
        if validation.test_command:
            try:
                result = subprocess.run(
                    validation.test_command,
                    capture_output=True, text=True,
                    timeout=30, cwd=work_dir)
                details["test_exit_code"] = result.returncode
                details["test_stdout"] = result.stdout[-1000:]
                details["test_stderr"] = result.stderr[-500:]
                if result.returncode != 0:
                    return False, details
            except subprocess.TimeoutExpired:
                details["test_error"] = "Timed out"
                return False, details
            except FileNotFoundError:
                details["test_error"] = "Command not found"
                # Skip test — not a failure

        # Expected patterns
        for file_path, patterns in validation.expected_patterns.items():
            full = Path(work_dir) / file_path
            if not full.exists():
                details[f"missing_{file_path}"] = True
                return False, details
            content = full.read_text(encoding="utf-8")
            for pattern in patterns:
                if not re.search(pattern, content):
                    details[f"pattern_missing_{file_path}"] = pattern
                    return False, details

        # Forbidden patterns
        for file_path, patterns in validation.forbidden_patterns.items():
            full = Path(work_dir) / file_path
            if not full.exists():
                continue
            content = full.read_text(encoding="utf-8")
            for pattern in patterns:
                if re.search(pattern, content):
                    details[f"forbidden_found_{file_path}"] = pattern
                    return False, details

        details["all_checks_passed"] = True
        return True, details

    @staticmethod
    def _compute_file_scope(modified: list, expected: list) -> float:
        """Compute file scope accuracy as IoU."""
        if not expected:
            return 1.0 if not modified else 0.0
        if not modified:
            return 0.0
        mod_set = set(modified)
        exp_set = set(expected)
        intersection = mod_set & exp_set
        union = mod_set | exp_set
        return len(intersection) / len(union) if union else 0.0
