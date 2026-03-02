"""Tests for forge.planner — Plan mode structured planning."""

import pytest
from forge.planner import PlanMode, Plan, PlanStep, parse_plan


# ---------------------------------------------------------------------------
# test_parse_plan
# ---------------------------------------------------------------------------

class TestParsePlan:
    def test_numbered_list(self):
        text = """Here is the plan:
1. Read main.py to understand structure
2. Modify the auth module
3. Add tests
4. Run test suite"""
        plan = parse_plan(text)
        assert len(plan.steps) == 4
        assert plan.steps[0].number == 1
        assert plan.steps[0].title == "Read main.py to understand structure"
        assert plan.steps[3].title == "Run test suite"

    def test_parenthesis_format(self):
        text = """1) Read the config file
2) Update settings
3) Write changes"""
        plan = parse_plan(text)
        assert len(plan.steps) == 3
        assert plan.steps[1].title == "Update settings"

    def test_step_prefix_format(self):
        text = """Step 1: Read the code
Step 2: Analyze patterns
Step 3: Refactor"""
        plan = parse_plan(text)
        assert len(plan.steps) == 3
        assert plan.steps[0].title == "Read the code"

    def test_summary_extraction(self):
        text = """I will refactor the authentication system.
1. Read auth.py
2. Extract token logic"""
        plan = parse_plan(text)
        assert "refactor" in plan.summary.lower()
        assert len(plan.steps) == 2

    def test_continuation_lines(self):
        text = """1. Read main.py
   This file contains the entry point
2. Modify config"""
        plan = parse_plan(text)
        assert len(plan.steps) == 2
        assert "entry point" in plan.steps[0].detail

    def test_empty_input(self):
        plan = parse_plan("")
        assert len(plan.steps) == 0

    def test_no_numbered_steps(self):
        text = "Just do the thing without any plan structure"
        plan = parse_plan(text)
        assert len(plan.steps) == 0

    def test_raw_text_preserved(self):
        text = "1. Step one\n2. Step two"
        plan = parse_plan(text)
        assert plan.raw_text == text


# ---------------------------------------------------------------------------
# test_plan_data
# ---------------------------------------------------------------------------

class TestPlanData:
    def test_plan_progress(self):
        plan = Plan(steps=[
            PlanStep(number=1, title="A", status="done"),
            PlanStep(number=2, title="B", status="done"),
            PlanStep(number=3, title="C", status="pending"),
            PlanStep(number=4, title="D", status="pending"),
        ])
        assert plan.total_steps == 4
        assert plan.completed_steps == 2
        assert plan.progress_pct() == 50.0

    def test_current_step(self):
        plan = Plan(steps=[
            PlanStep(number=1, title="A", status="done"),
            PlanStep(number=2, title="B", status="pending"),
            PlanStep(number=3, title="C", status="pending"),
        ])
        assert plan.current_step.number == 2

    def test_all_done_no_current(self):
        plan = Plan(steps=[
            PlanStep(number=1, title="A", status="done"),
        ])
        assert plan.current_step is None

    def test_empty_plan_progress(self):
        plan = Plan()
        assert plan.progress_pct() == 100.0


# ---------------------------------------------------------------------------
# test_plan_mode_controller
# ---------------------------------------------------------------------------

class TestPlanModeController:
    def test_off_mode_does_not_plan(self):
        pm = PlanMode(mode="off")
        assert not pm.should_plan("do stuff")

    def test_off_mode_armed_plans(self):
        pm = PlanMode(mode="off")
        pm.arm()
        assert pm.should_plan("do stuff")

    def test_manual_mode_only_when_armed(self):
        pm = PlanMode(mode="manual")
        assert not pm.should_plan("do stuff")
        pm.arm()
        assert pm.should_plan("do stuff")

    def test_always_mode(self):
        pm = PlanMode(mode="always")
        assert pm.should_plan("hi")
        assert pm.should_plan("refactor everything")

    def test_auto_mode_uses_score(self):
        pm = PlanMode(mode="auto", auto_threshold=3)
        assert not pm.should_plan("hi", complexity_score=1)
        assert pm.should_plan("big task", complexity_score=5)

    def test_auto_mode_armed_overrides(self):
        pm = PlanMode(mode="auto", auto_threshold=10)
        pm.arm()
        assert pm.should_plan("hi", complexity_score=0)

    def test_get_plan_prompt_consumes_arm(self):
        pm = PlanMode(mode="off")
        pm.arm()
        prompt = pm.get_plan_prompt("refactor auth")
        assert "refactor auth" in prompt
        assert not pm._armed  # consumed

    def test_approve_and_reject(self):
        pm = PlanMode()
        plan = pm.receive_plan("1. A\n2. B")
        assert pm.current_plan is not None
        pm.reject()
        assert pm.current_plan is None
        assert len(pm._history) == 1

    def test_approve_step_by_step(self):
        pm = PlanMode()
        pm.receive_plan("1. A\n2. B")
        pm.approve(step_by_step=True)
        assert pm.current_plan.approved
        assert pm.current_plan.step_by_step

    def test_mark_steps(self):
        pm = PlanMode()
        pm.receive_plan("1. Read\n2. Write\n3. Test")
        pm.mark_step_in_progress(1)
        assert pm.current_plan.steps[0].status == "in_progress"
        pm.mark_step_done(1, "ok")
        assert pm.current_plan.steps[0].status == "done"
        assert pm.current_plan.steps[0].result == "ok"
        pm.skip_step(3)
        assert pm.current_plan.steps[2].status == "skipped"

    def test_complete_archives(self):
        pm = PlanMode()
        pm.receive_plan("1. A\n2. B")
        pm.complete()
        assert pm.current_plan is None
        assert len(pm._history) == 1


# ---------------------------------------------------------------------------
# test_format
# ---------------------------------------------------------------------------

class TestFormat:
    def test_format_plan_contains_steps(self):
        pm = PlanMode()
        pm.receive_plan("1. Read code\n2. Write tests")
        output = pm.format_plan()
        assert "EXECUTION PLAN" in output
        assert "Read code" in output
        assert "Write tests" in output

    def test_format_progress(self):
        pm = PlanMode()
        pm.receive_plan("1. A\n2. B\n3. C\n4. D")
        pm.mark_step_done(1)
        pm.mark_step_done(2)
        output = pm.format_progress()
        assert "2/4" in output
        assert "50%" in output

    def test_format_status(self):
        pm = PlanMode(mode="auto", auto_threshold=5)
        output = pm.format_status()
        assert "auto" in output
        assert "5" in output

    def test_format_no_plan(self):
        pm = PlanMode()
        output = pm.format_plan()
        assert "No plan" in output

    def test_get_execution_prompts(self):
        pm = PlanMode()
        pm.receive_plan("1. Read files\n2. Make changes")
        pm.approve()

        full = pm.get_full_execution_prompt("refactor auth")
        assert "refactor auth" in full
        assert "Read files" in full

        step = pm.get_step_prompt(pm.current_plan.steps[0], "refactor auth")
        assert "step 1" in step.lower()
        assert "Read files" in step
