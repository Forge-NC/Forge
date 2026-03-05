"""Tests for benchmark execution bridge and reporting."""
import json
import re
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from forge.benchmark import BenchmarkRunner, BenchmarkScenario, ValidationConfig


@pytest.fixture
def runner(tmp_path):
    scenarios_dir = tmp_path / "scenarios"
    results_dir = tmp_path / "results"
    scenarios_dir.mkdir()
    results_dir.mkdir()
    return BenchmarkRunner(scenarios_dir=scenarios_dir, results_dir=results_dir)


@pytest.fixture
def simple_scenario():
    return BenchmarkScenario(
        id="test_rename",
        name="Rename variable",
        category="refactor",
        difficulty="easy",
        files={"main.py": "x = 1\nprint(x)\n"},
        prompt="Rename the variable 'x' to 'count' in main.py",
        validation=ValidationConfig(
            expected_patterns={"main.py": [r"count\s*=\s*1"]},
            forbidden_patterns={"main.py": [r"^x\s*=\s*1"]},
        ),
        expected_file_scope=["main.py"],
    )


def _make_mock_backend(response_text):
    """Create a mock LLM backend that returns the given text."""
    mock = MagicMock()
    mock.model = "test-model"
    mock.chat.return_value = iter([
        {"type": "token", "content": response_text},
        {"type": "done", "eval_count": 50, "prompt_eval_count": 100},
    ])
    return mock


# ── Live execution bridge ──

class TestRunScenarioLive:
    def test_successful_refactor(self, runner, simple_scenario):
        response = "```main.py\ncount = 1\nprint(count)\n```"
        backend = _make_mock_backend(response)
        result = runner.run_scenario_live(simple_scenario, backend)
        assert result.passed
        assert result.model == "test-model"
        assert "main.py" in result.files_modified
        assert result.quality_score > 0
        assert result.tokens_out == 50

    def test_wrong_file_modified(self, runner, simple_scenario):
        response = "```other.py\ncount = 1\n```"
        backend = _make_mock_backend(response)
        result = runner.run_scenario_live(simple_scenario, backend)
        assert not result.passed
        assert result.file_scope_accuracy == 0.0

    def test_refusal_response(self, runner, simple_scenario):
        response = "I cannot modify files directly. You should rename x to count."
        backend = _make_mock_backend(response)
        result = runner.run_scenario_live(simple_scenario, backend)
        assert not result.passed
        assert result.quality_score < 0.5

    def test_error_from_backend(self, runner, simple_scenario):
        mock = MagicMock()
        mock.model = "broken-model"
        mock.chat.return_value = iter([
            {"type": "error", "content": "connection refused"},
        ])
        result = runner.run_scenario_live(simple_scenario, mock)
        assert not result.passed
        assert "connection refused" in result.error

    def test_exception_in_backend(self, runner, simple_scenario):
        mock = MagicMock()
        mock.model = "crash-model"
        mock.chat.side_effect = RuntimeError("boom")
        result = runner.run_scenario_live(simple_scenario, mock)
        assert not result.passed
        assert "boom" in result.error

    def test_backend_type_recorded(self, runner, simple_scenario):
        response = "```main.py\ncount = 1\nprint(count)\n```"
        backend = _make_mock_backend(response)
        result = runner.run_scenario_live(simple_scenario, backend)
        assert result.backend_type == "MagicMock"

    def test_custom_system_prompt(self, runner, simple_scenario):
        response = "```main.py\ncount = 1\nprint(count)\n```"
        backend = _make_mock_backend(response)
        result = runner.run_scenario_live(
            simple_scenario, backend,
            system_prompt="You are a Python expert.")
        assert result.passed
        # Verify system prompt was used
        call_args = backend.chat.call_args
        messages = call_args[0][0] if call_args[0] else call_args[1].get("messages", [])
        assert any("Python expert" in m.get("content", "") for m in messages)


class TestRunSuiteLive:
    def test_runs_all_scenarios(self, runner, tmp_path):
        # Create a suite directory with 2 scenarios
        suite_dir = tmp_path / "scenarios" / "test_suite"
        suite_dir.mkdir(parents=True)
        for i in range(2):
            scenario = {
                "id": f"test_{i}",
                "name": f"Test {i}",
                "files": {"file.py": f"x = {i}"},
                "prompt": f"Change x to {i + 10}",
                "expected_file_scope": ["file.py"],
                "validation": {"expected_patterns": {}, "forbidden_patterns": {}},
            }
            (suite_dir / f"scenario_{i}.json").write_text(
                json.dumps(scenario), encoding="utf-8")

        response = "```file.py\nx = 99\n```"
        backend = _make_mock_backend(response)
        result = runner.run_suite_live("test_suite", backend)
        assert len(result.results) == 2
        assert result.model == "test-model"


# ── Code block extraction ──

class TestCodeBlockExtraction:
    def test_extracts_python(self):
        response = "Here's the fix:\n```main.py\ncount = 1\n```\nDone."
        modified = BenchmarkRunner._extract_code_blocks(
            response, tempfile.mkdtemp())
        assert "main.py" in modified

    def test_extracts_multiple_files(self):
        response = "```a.py\nx = 1\n```\n```b.js\nlet y = 2;\n```"
        modified = BenchmarkRunner._extract_code_blocks(
            response, tempfile.mkdtemp())
        assert "a.py" in modified
        assert "b.js" in modified

    def test_extracts_nested_paths(self):
        response = "```src/utils/helper.py\ndef help(): pass\n```"
        work_dir = tempfile.mkdtemp()
        modified = BenchmarkRunner._extract_code_blocks(response, work_dir)
        assert "src/utils/helper.py" in modified
        assert (Path(work_dir) / "src" / "utils" / "helper.py").exists()

    def test_no_code_blocks(self):
        response = "Just rename x to count."
        modified = BenchmarkRunner._extract_code_blocks(
            response, tempfile.mkdtemp())
        assert modified == []

    def test_ignores_plain_code_blocks(self):
        response = "```\nsome code\n```"
        modified = BenchmarkRunner._extract_code_blocks(
            response, tempfile.mkdtemp())
        assert modified == []


# ── Response scoring ──

class TestBenchmarkResponseScoring:
    def test_perfect_response(self, simple_scenario):
        response = "```main.py\ncount = 1\nprint(count)\n```"
        score = BenchmarkRunner._score_benchmark_response(
            response, simple_scenario, ["main.py"])
        assert score >= 0.7

    def test_refusal_penalized(self, simple_scenario):
        response = "I cannot modify files. Please do it yourself."
        score = BenchmarkRunner._score_benchmark_response(
            response, simple_scenario, [])
        assert score < 0.3

    def test_empty_response(self, simple_scenario):
        score = BenchmarkRunner._score_benchmark_response(
            "", simple_scenario, [])
        assert score < 0.3  # No code, no file scope, no substance

    def test_partial_file_scope(self, simple_scenario):
        response = "```other.py\ncount = 1\n```"
        score = BenchmarkRunner._score_benchmark_response(
            response, simple_scenario, ["other.py"])
        # Has code blocks but wrong file
        assert 0.2 < score < 0.7


# ── Benchmark report ──

class TestBenchmarkReport:
    def test_generates_html(self):
        from forge.benchmark_report import build_comparison_report
        results = [{
            "suite_name": "test",
            "model": "model-a",
            "results": [
                {"scenario_name": "s1", "passed": True,
                 "duration_s": 1.0, "quality_score": 0.8, "tokens_out": 100},
                {"scenario_name": "s2", "passed": False,
                 "duration_s": 2.0, "quality_score": 0.3, "tokens_out": 50},
            ],
        }]
        html = build_comparison_report(results)
        assert "<html" in html
        assert "model-a" in html
        assert "Chart.js" in html or "chart.js" in html

    def test_multiple_models(self):
        from forge.benchmark_report import build_comparison_report
        results = [
            {"model": "m1", "results": [
                {"passed": True, "duration_s": 1.0, "quality_score": 0.9,
                 "tokens_out": 100, "scenario_name": "s1"}]},
            {"model": "m2", "results": [
                {"passed": False, "duration_s": 3.0, "quality_score": 0.4,
                 "tokens_out": 200, "scenario_name": "s1"}]},
        ]
        html = build_comparison_report(results)
        assert "m1" in html
        assert "m2" in html

    def test_save_report(self, tmp_path):
        from forge.benchmark_report import save_report
        path = save_report("<html>test</html>", tmp_path / "report.html")
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "<html>test</html>"
