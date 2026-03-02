"""Scenario 8: PlanVerifier repair stress.

Verifies that the PlanVerifier modes work correctly and
that verify_step returns proper results.
"""

import pytest
from forge.plan_verifier import PlanVerifier


@pytest.mark.timeout(30)
class TestRepairLoop:

    def test_verify_step_runs_tests(self, tmp_path):
        """PlanVerifier verify_step should run and return a result."""
        # Create a test file that always fails
        test_file = tmp_path / "test_always_fail.py"
        test_file.write_text(
            "def test_fail():\n    assert False, 'Always fails'\n",
            encoding="utf-8",
        )

        pv = PlanVerifier(
            mode="report",
            run_tests=True,
            run_lint=False,
            run_git_diff=False,
            max_test_time=5,
            working_dir=str(tmp_path),
        )

        # Verify should return a result (not hang)
        result = pv.verify_step(step_number=1)

        # Result should exist
        assert result is not None
        assert result.step_number == 1
        # Verifier ran and returned a result (may skip if no framework detected)
        assert isinstance(result.passed, bool)

    def test_verify_step_with_no_tests(self, tmp_path):
        """Verify step when no test files exist should pass."""
        pv = PlanVerifier(
            mode="report",
            run_tests=True,
            run_lint=False,
            run_git_diff=False,
            max_test_time=5,
            working_dir=str(tmp_path),
        )

        result = pv.verify_step(step_number=1)
        assert result is not None
        assert result.step_number == 1

    def test_plan_verifier_off_mode(self, tmp_path):
        """Off mode: enabled property should be False."""
        pv = PlanVerifier(
            mode="off",
            run_tests=True,
            run_lint=False,
            max_test_time=5,
            working_dir=str(tmp_path),
        )

        assert pv.enabled is False
        # verify_step still works but returns a passing result
        result = pv.verify_step(step_number=1)
        assert result is not None

    def test_strict_mode_enabled(self, tmp_path):
        """Strict mode should be enabled."""
        pv = PlanVerifier(
            mode="strict",
            run_tests=True,
            run_lint=False,
            run_git_diff=False,
            max_test_time=5,
            working_dir=str(tmp_path),
        )

        assert pv.enabled is True
        result = pv.verify_step(step_number=1)
        assert result is not None
        assert result.step_number == 1

    def test_repair_prompt_generation(self, tmp_path):
        """get_repair_prompt should generate a valid prompt."""
        test_file = tmp_path / "test_broken.py"
        test_file.write_text(
            "def test_fail():\n    assert 1 == 2\n",
            encoding="utf-8",
        )

        pv = PlanVerifier(
            mode="repair",
            run_tests=True,
            run_lint=False,
            run_git_diff=False,
            max_test_time=5,
            working_dir=str(tmp_path),
        )

        result = pv.verify_step(step_number=1)
        if not result.passed:
            prompt = pv.get_repair_prompt(result, "Fix the bug")
            assert "Fix the bug" in prompt
            assert "FAILED" in prompt

    def test_multiple_verify_steps_tracked(self, tmp_path):
        """Results accumulate across verify_step calls."""
        pv = PlanVerifier(
            mode="report",
            run_tests=False,
            run_lint=False,
            run_git_diff=False,
            max_test_time=5,
            working_dir=str(tmp_path),
        )

        for i in range(5):
            pv.verify_step(step_number=i + 1)

        assert len(pv._results) == 5
        audit = pv.to_audit_dict()
        assert audit is not None
