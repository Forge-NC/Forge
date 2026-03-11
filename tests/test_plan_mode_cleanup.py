"""Tests for plan mode cleanup on error paths."""

import pytest
from forge.planner import PlanMode, Plan


def _make_plan():
    return Plan(summary="test plan", raw_text="test", steps=[],
                approved=False, step_by_step=False)


class TestPlanModeCleanup:
    """Verifies PlanMode.reject() clears state and _run_plan_mode() calls reject() on all error paths.

    reject() sets _current_plan=None, _armed=False, and appends the rejected plan to _history.
    get_plan_prompt() disarms after generating the prompt. reject() with no current plan is a
    safe no-op (no crash, empty history). arm/plan_prompt/reject cycle: should_plan()→True after arm,
    False after get_plan_prompt(), _armed=False after reject(). Source inspection: _run_plan_mode
    must call reject() on >= 3 early error return paths.
    """

    def test_reject_clears_current_plan(self):
        pm = PlanMode(mode="manual")
        pm._current_plan = _make_plan()
        pm.reject()
        assert pm._current_plan is None
        assert pm._armed is False

    def test_reject_appends_to_history(self):
        pm = PlanMode(mode="manual")
        plan = _make_plan()
        pm._current_plan = plan
        pm.reject()
        assert len(pm._history) == 1
        assert pm._history[0] is plan

    def test_get_plan_prompt_disarms(self):
        pm = PlanMode(mode="manual")
        pm.arm()
        assert pm._armed is True
        pm.get_plan_prompt("do something")
        assert pm._armed is False

    def test_error_path_calls_reject(self):
        """Verify engine.py error paths in _run_plan_mode call reject()."""
        import inspect
        from forge.engine import ForgeEngine
        source = inspect.getsource(ForgeEngine._run_plan_mode)
        lines = source.split("\n")
        return_none_count = 0
        reject_before_return = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped == "return None":
                return_none_count += 1
                # Check if reject() appears in the 3 lines before
                context = "\n".join(lines[max(0, i - 3):i + 1])
                if "reject()" in context:
                    reject_before_return += 1
        # The 3 early error paths should all have reject()
        assert reject_before_return >= 3, (
            f"Expected >= 3 reject() calls before return None, "
            f"found {reject_before_return} out of {return_none_count}")

    def test_reject_when_no_plan(self):
        """Calling reject() when no current plan should not crash."""
        pm = PlanMode(mode="manual")
        pm.reject()
        assert pm._current_plan is None
        assert len(pm._history) == 0

    def test_arm_reject_cycle(self):
        pm = PlanMode(mode="manual")
        pm.arm()
        assert pm.should_plan("test") is True
        pm.get_plan_prompt("test")  # Consumes arm
        assert pm.should_plan("test") is False
        pm.reject()
        assert pm._armed is False
