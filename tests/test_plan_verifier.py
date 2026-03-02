"""Tests for forge.plan_verifier — Plan step verification."""

import pytest
from unittest.mock import patch, MagicMock
from forge.plan_verifier import PlanVerifier, VerificationCheck, VerificationResult


# ---------------------------------------------------------------------------
# VerificationCheck / VerificationResult dataclasses
# ---------------------------------------------------------------------------

class TestVerificationDataclasses:
    def test_check_defaults(self):
        c = VerificationCheck(name="tests", passed=True)
        assert c.output == ""
        assert c.duration_ms == 0

    def test_result_str_pass(self):
        r = VerificationResult(
            step_number=1, passed=True,
            checks=[VerificationCheck(name="tests", passed=True)])
        assert "PASS" in str(r)
        assert "tests:ok" in str(r)

    def test_result_str_fail(self):
        r = VerificationResult(
            step_number=2, passed=False,
            checks=[
                VerificationCheck(name="tests", passed=False),
                VerificationCheck(name="lint", passed=True),
            ])
        assert "FAIL" in str(r)
        assert "tests:FAIL" in str(r)
        assert "lint:ok" in str(r)


# ---------------------------------------------------------------------------
# PlanVerifier — modes
# ---------------------------------------------------------------------------

class TestPlanVerifierModes:
    def test_off_mode_not_enabled(self):
        v = PlanVerifier(mode="off")
        assert not v.enabled

    def test_report_mode_enabled(self):
        v = PlanVerifier(mode="report")
        assert v.enabled

    def test_repair_mode_enabled(self):
        v = PlanVerifier(mode="repair")
        assert v.enabled

    def test_strict_mode_enabled(self):
        v = PlanVerifier(mode="strict")
        assert v.enabled


# ---------------------------------------------------------------------------
# PlanVerifier — verify_step
# ---------------------------------------------------------------------------

class TestVerifyStep:
    def test_no_checks_passes(self):
        v = PlanVerifier(mode="report", run_tests=False, run_lint=False,
                         run_typecheck=False, run_git_diff=False)
        result = v.verify_step(1)
        assert result.passed
        assert result.step_number == 1

    @patch.object(PlanVerifier, '_check_tests')
    def test_tests_pass(self, mock_tests):
        mock_tests.return_value = VerificationCheck(
            name="tests", passed=True, output="3 passed", duration_ms=100)
        v = PlanVerifier(mode="report", run_lint=False,
                         run_typecheck=False, run_git_diff=False)
        result = v.verify_step(1)
        assert result.passed
        assert len(result.checks) == 1
        assert result.checks[0].name == "tests"

    @patch.object(PlanVerifier, '_check_tests')
    def test_tests_fail(self, mock_tests):
        mock_tests.return_value = VerificationCheck(
            name="tests", passed=False, output="FAILED test_foo",
            duration_ms=200)
        v = PlanVerifier(mode="report", run_lint=False,
                         run_typecheck=False, run_git_diff=False)
        result = v.verify_step(2)
        assert not result.passed
        assert "tests" in result.error_summary

    @patch.object(PlanVerifier, '_check_tests')
    @patch.object(PlanVerifier, '_check_lint')
    def test_mixed_results(self, mock_lint, mock_tests):
        mock_tests.return_value = VerificationCheck(
            name="tests", passed=True, duration_ms=100)
        mock_lint.return_value = VerificationCheck(
            name="lint", passed=False, output="E501 line too long")
        v = PlanVerifier(mode="report", run_lint=True,
                         run_typecheck=False, run_git_diff=False)
        result = v.verify_step(1)
        assert not result.passed
        assert len(result.checks) == 2

    def test_results_accumulated(self):
        v = PlanVerifier(mode="report", run_tests=False, run_lint=False,
                         run_typecheck=False, run_git_diff=False)
        v.verify_step(1)
        v.verify_step(2)
        v.verify_step(3)
        assert len(v._results) == 3


# ---------------------------------------------------------------------------
# PlanVerifier — repair prompt
# ---------------------------------------------------------------------------

class TestRepairPrompt:
    def test_repair_prompt_contains_failures(self):
        v = PlanVerifier(mode="repair")
        result = VerificationResult(
            step_number=1, passed=False,
            checks=[
                VerificationCheck(name="tests", passed=False,
                                  output="assert 1 == 2"),
                VerificationCheck(name="lint", passed=True),
            ])
        prompt = v.get_repair_prompt(result, "Fix the parser")
        assert "Fix the parser" in prompt
        assert "tests FAILED" in prompt
        assert "assert 1 == 2" in prompt
        assert "lint" not in prompt  # lint passed, not in failures


# ---------------------------------------------------------------------------
# PlanVerifier — format_result / format_summary
# ---------------------------------------------------------------------------

class TestFormat:
    def test_format_result_pass(self):
        v = PlanVerifier(mode="report")
        result = VerificationResult(
            step_number=1, passed=True,
            checks=[VerificationCheck(name="tests", passed=True,
                                      duration_ms=150)])
        output = v.format_result(result)
        assert "VERIFIED" in output
        assert "150ms" in output

    def test_format_result_fail(self):
        v = PlanVerifier(mode="report")
        result = VerificationResult(
            step_number=2, passed=False,
            checks=[VerificationCheck(name="tests", passed=False,
                                      output="test_foo failed")])
        output = v.format_result(result)
        assert "FAILED" in output
        assert "test_foo" in output

    def test_format_result_auto_fixed(self):
        v = PlanVerifier(mode="repair")
        result = VerificationResult(
            step_number=1, passed=True, auto_fixed=True,
            checks=[VerificationCheck(name="tests", passed=True)])
        output = v.format_result(result)
        assert "auto-fixed" in output

    def test_format_result_rolled_back(self):
        v = PlanVerifier(mode="strict")
        result = VerificationResult(
            step_number=1, passed=False, rolled_back=True,
            checks=[VerificationCheck(name="tests", passed=False)])
        output = v.format_result(result)
        assert "rolled back" in output

    def test_format_summary_all_pass(self):
        v = PlanVerifier(mode="report")
        v._results = [
            VerificationResult(step_number=1, passed=True),
            VerificationResult(step_number=2, passed=True),
        ]
        summary = v.format_summary()
        assert "2/2" in summary

    def test_format_summary_partial(self):
        v = PlanVerifier(mode="report")
        v._results = [
            VerificationResult(step_number=1, passed=True),
            VerificationResult(step_number=2, passed=False),
            VerificationResult(step_number=3, passed=True),
        ]
        summary = v.format_summary()
        assert "2/3" in summary

    def test_format_summary_empty(self):
        v = PlanVerifier(mode="report")
        assert v.format_summary() == ""


# ---------------------------------------------------------------------------
# PlanVerifier — _run_command
# ---------------------------------------------------------------------------

class TestRunCommand:
    def test_command_not_found(self):
        v = PlanVerifier(mode="report")
        code, output = v._run_command(["nonexistent_command_xyz"])
        assert code == -1
        assert "not found" in output.lower() or "Command not found" in output

    @patch("subprocess.run")
    def test_command_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["test"], timeout=5)
        v = PlanVerifier(mode="report")
        code, output = v._run_command(["test"], timeout=5)
        assert code == 1
        assert "timed out" in output.lower()

    @patch("subprocess.run")
    def test_command_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="ok\n", stderr="")
        v = PlanVerifier(mode="report")
        code, output = v._run_command(["echo", "ok"])
        assert code == 0
        assert "ok" in output


# ---------------------------------------------------------------------------
# PlanVerifier — test framework detection
# ---------------------------------------------------------------------------

class TestDetectTestCommand:
    def test_detect_pytest(self, tmp_path):
        (tmp_path / "tests").mkdir()
        v = PlanVerifier(mode="report", working_dir=str(tmp_path))
        cmd = v._detect_test_command()
        assert cmd is not None
        assert "pytest" in cmd

    def test_detect_npm(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        v = PlanVerifier(mode="report", working_dir=str(tmp_path))
        cmd = v._detect_test_command()
        assert cmd is not None
        assert "npm" in cmd

    def test_detect_cargo(self, tmp_path):
        (tmp_path / "Cargo.toml").write_text("[package]")
        v = PlanVerifier(mode="report", working_dir=str(tmp_path))
        cmd = v._detect_test_command()
        assert cmd is not None
        assert "cargo" in cmd

    def test_detect_go(self, tmp_path):
        (tmp_path / "go.mod").write_text("module test")
        v = PlanVerifier(mode="report", working_dir=str(tmp_path))
        cmd = v._detect_test_command()
        assert cmd is not None
        assert "go" in cmd

    def test_detect_none(self, tmp_path):
        v = PlanVerifier(mode="report", working_dir=str(tmp_path))
        cmd = v._detect_test_command()
        assert cmd is None


# ---------------------------------------------------------------------------
# PlanVerifier — git diff check
# ---------------------------------------------------------------------------

class TestGitDiffCheck:
    @patch.object(PlanVerifier, '_run_command')
    def test_not_git_repo(self, mock_run):
        mock_run.return_value = (1, "fatal: not a git repository")
        v = PlanVerifier(mode="report")
        check = v._check_git_diff()
        assert check.passed
        assert "skipped" in check.output.lower()

    @patch.object(PlanVerifier, '_run_command')
    def test_normal_changes(self, mock_run):
        mock_run.return_value = (0,
            " 3 files changed, 50 insertions(+), 20 deletions(-)")
        v = PlanVerifier(mode="report")
        check = v._check_git_diff()
        assert check.passed

    @patch.object(PlanVerifier, '_run_command')
    def test_mass_deletion_flagged(self, mock_run):
        mock_run.return_value = (0,
            " 10 files changed, 5 insertions(+), 1000 deletions(-)")
        v = PlanVerifier(mode="report")
        check = v._check_git_diff()
        assert not check.passed
        assert "mass deletion" in check.output.lower()
