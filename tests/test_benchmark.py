"""Tests for the benchmark suite."""

import json
import time
from pathlib import Path

import pytest

from forge.benchmark import (
    BenchmarkRunner, BenchmarkScenario, BenchmarkResult,
    BenchmarkSuiteResult, ValidationConfig,
)


@pytest.fixture
def runner(tmp_path):
    scenarios_dir = tmp_path / "scenarios"
    results_dir = tmp_path / "results"
    return BenchmarkRunner(scenarios_dir=scenarios_dir,
                           results_dir=results_dir)


def _make_scenario(**overrides):
    defaults = dict(
        id="test-scenario",
        name="Test Scenario",
        description="A test",
        category="refactor",
        difficulty="easy",
        files={"hello.py": "print('hello')\n"},
        prompt="Refactor hello.py",
        validation=ValidationConfig(),
        expected_file_scope=["hello.py"],
        timeout_s=30,
    )
    defaults.update(overrides)
    return BenchmarkScenario(**defaults)


# ── Scenario parsing ──

class TestScenarioParsing:
    def test_parse_minimal(self):
        data = {"id": "t1", "name": "T1"}
        s = BenchmarkRunner._parse_scenario(data)
        assert s.id == "t1"
        assert s.name == "T1"
        assert s.category == "refactor"
        assert s.difficulty == "easy"

    def test_parse_with_validation(self):
        data = {
            "id": "t2", "name": "T2",
            "validation": {
                "expected_patterns": {"a.py": ["def foo"]},
                "forbidden_patterns": {"a.py": ["def bar"]},
            },
        }
        s = BenchmarkRunner._parse_scenario(data)
        assert "a.py" in s.validation.expected_patterns
        assert "a.py" in s.validation.forbidden_patterns

    def test_parse_with_files(self):
        data = {
            "id": "t3", "name": "T3",
            "files": {"main.py": "x = 1\n", "lib.py": "y = 2\n"},
        }
        s = BenchmarkRunner._parse_scenario(data)
        assert len(s.files) == 2


# ── Validation ──

class TestValidation:
    def test_empty_validation_passes(self, tmp_path):
        v = ValidationConfig()
        ok, details = BenchmarkRunner._run_validation(v, str(tmp_path))
        assert ok is True
        assert details.get("all_checks_passed") is True

    def test_expected_pattern_match(self, tmp_path):
        (tmp_path / "a.py").write_text("def foo():\n    pass\n")
        v = ValidationConfig(expected_patterns={"a.py": ["def foo"]})
        ok, _ = BenchmarkRunner._run_validation(v, str(tmp_path))
        assert ok is True

    def test_expected_pattern_missing(self, tmp_path):
        (tmp_path / "a.py").write_text("def bar():\n    pass\n")
        v = ValidationConfig(expected_patterns={"a.py": ["def foo"]})
        ok, details = BenchmarkRunner._run_validation(v, str(tmp_path))
        assert ok is False
        assert "pattern_missing_a.py" in details

    def test_forbidden_pattern_found(self, tmp_path):
        (tmp_path / "a.py").write_text("def bar():\n    pass\n")
        v = ValidationConfig(forbidden_patterns={"a.py": ["def bar"]})
        ok, details = BenchmarkRunner._run_validation(v, str(tmp_path))
        assert ok is False
        assert "forbidden_found_a.py" in details

    def test_forbidden_pattern_absent(self, tmp_path):
        (tmp_path / "a.py").write_text("def foo():\n    pass\n")
        v = ValidationConfig(forbidden_patterns={"a.py": ["def bar"]})
        ok, _ = BenchmarkRunner._run_validation(v, str(tmp_path))
        assert ok is True

    def test_missing_file_fails(self, tmp_path):
        v = ValidationConfig(expected_patterns={"missing.py": ["x"]})
        ok, details = BenchmarkRunner._run_validation(v, str(tmp_path))
        assert ok is False
        assert details.get("missing_missing.py") is True


# ── File scope accuracy ──

class TestFileScope:
    def test_perfect_match(self):
        assert BenchmarkRunner._compute_file_scope(
            ["a.py", "b.py"], ["a.py", "b.py"]) == 1.0

    def test_no_overlap(self):
        assert BenchmarkRunner._compute_file_scope(
            ["a.py"], ["b.py"]) == 0.0

    def test_partial_overlap(self):
        score = BenchmarkRunner._compute_file_scope(
            ["a.py", "b.py"], ["a.py", "c.py"])
        assert abs(score - 1 / 3) < 0.01

    def test_empty_expected_no_modified(self):
        assert BenchmarkRunner._compute_file_scope([], []) == 1.0

    def test_empty_expected_with_modified(self):
        assert BenchmarkRunner._compute_file_scope(["a.py"], []) == 0.0


# ── Run scenario ──

class TestRunScenario:
    def test_basic_run(self, runner):
        s = _make_scenario()
        result = runner.run_scenario(s)
        assert isinstance(result, BenchmarkResult)
        assert result.scenario_id == "test-scenario"
        assert result.duration_s >= 0

    def test_error_captured(self, runner):
        s = _make_scenario(
            validation=ValidationConfig(
                expected_patterns={"missing.py": ["x"]}))
        result = runner.run_scenario(s)
        # Pre-validation fails because missing.py isn't in scenario files
        assert result.passed is False


# ── Suite operations ──

class TestSuiteOperations:
    def test_list_empty_suites(self, runner):
        assert runner.list_suites() == []

    def test_list_scenarios_empty(self, runner):
        assert runner.list_scenarios("nonexistent") == []


# ── Result persistence ──

class TestResultPersistence:
    def test_save_and_load(self, runner):
        suite_result = BenchmarkSuiteResult(
            suite_name="test",
            timestamp=time.time(),
            duration_s=1.0,
            results=[],
            model="test-model",
            config_hash="abc123",
            pass_rate=1.0,
        )
        path = runner.save_result(suite_result)
        assert path.exists()

        loaded = runner.load_results(suite="test")
        assert len(loaded) == 1
        assert loaded[0]["suite_name"] == "test"
        assert loaded[0]["model"] == "test-model"


# ── Config hash ──

class TestConfigHash:
    def test_deterministic(self):
        h1 = BenchmarkRunner.compute_config_hash(model="m", context_size=8000)
        h2 = BenchmarkRunner.compute_config_hash(model="m", context_size=8000)
        assert h1 == h2

    def test_different_config(self):
        h1 = BenchmarkRunner.compute_config_hash(model="a")
        h2 = BenchmarkRunner.compute_config_hash(model="b")
        assert h1 != h2

    def test_hash_length(self):
        h = BenchmarkRunner.compute_config_hash()
        assert len(h) == 16


# ── Result comparison ──

class TestComparison:
    def test_compare_results(self, runner):
        a = {"pass_rate": 0.5, "avg_duration_s": 2.0,
             "avg_iterations": 3.0, "avg_file_scope_accuracy": 0.8,
             "model": "a"}
        b = {"pass_rate": 0.8, "avg_duration_s": 1.5,
             "avg_iterations": 2.0, "avg_file_scope_accuracy": 0.9,
             "model": "b"}
        diff = runner.compare_results(a, b)
        assert abs(diff["pass_rate_delta"] - 0.3) < 0.01
        assert abs(diff["duration_delta"] - (-0.5)) < 0.01


# ── YAML scenario loading ──

class TestYAMLLoading:
    def test_load_from_file(self, tmp_path):
        """Test loading a scenario from YAML file."""
        yaml_content = (
            "id: test-load\n"
            "name: Test Load\n"
            "files:\n"
            "  main.py: |\n"
            "    x = 1\n"
            "prompt: Do something\n"
            "expected_file_scope:\n"
            "  - main.py\n"
        )
        scenario_file = tmp_path / "test.yaml"
        scenario_file.write_text(yaml_content, encoding="utf-8")

        runner = BenchmarkRunner(scenarios_dir=tmp_path,
                                  results_dir=tmp_path / "results")
        try:
            s = runner.load_scenario(scenario_file)
            assert s.id == "test-load"
            assert "main.py" in s.files
        except ImportError:
            pytest.skip("pyyaml not installed")

    def test_load_from_json(self, tmp_path):
        """Test loading a scenario from JSON file."""
        data = {"id": "json-test", "name": "JSON Test",
                "files": {"a.py": "x = 1\n"}}
        scenario_file = tmp_path / "test.json"
        scenario_file.write_text(json.dumps(data), encoding="utf-8")

        runner = BenchmarkRunner(scenarios_dir=tmp_path,
                                  results_dir=tmp_path / "results")
        s = runner.load_scenario(scenario_file)
        assert s.id == "json-test"
