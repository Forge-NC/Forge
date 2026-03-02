"""Plan mode — structured planning before execution.

When activated, the AI generates a step-by-step plan for the user
to review before any code changes are made.  Three modes:

  1. Manual: User triggers with /plan before a prompt.
  2. Auto: Complex prompts (based on router score) automatically
     enter plan mode.
  3. Always: Every prompt goes through plan mode.

Flow:
  user input -> plan prompt -> model outputs plan -> display plan
  -> user [A]pproves / [E]dits / [R]ejects / [S]tep-by-step
  -> execute (all at once or step by step)
"""

import re
import sys
import time
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable

log = logging.getLogger(__name__)


# ── Plan data structures ──────────────────────────────────────────

@dataclass
class PlanStep:
    """A single step in a plan."""
    number: int
    title: str
    detail: str = ""
    status: str = "pending"   # pending | in_progress | done | skipped
    result: str = ""
    verified: bool = False
    verification_result: Optional[dict] = None


@dataclass
class Plan:
    """A structured plan parsed from model output."""
    summary: str = ""
    steps: list[PlanStep] = field(default_factory=list)
    raw_text: str = ""
    created_at: float = field(default_factory=time.time)
    approved: bool = False
    step_by_step: bool = False

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == "done")

    @property
    def current_step(self) -> Optional[PlanStep]:
        for s in self.steps:
            if s.status == "pending":
                return s
        return None

    def progress_pct(self) -> float:
        if not self.steps:
            return 100.0
        return (self.completed_steps / self.total_steps) * 100


# ── Plan parser ───────────────────────────────────────────────────

def parse_plan(text: str) -> Plan:
    """Parse a model's plan output into a structured Plan.

    Handles various numbered-list formats:
      1. Step description
      1) Step description
      Step 1: Description
      - Step description (numbered sequentially)
    """
    lines = text.strip().splitlines()
    plan = Plan(raw_text=text)
    steps: list[PlanStep] = []

    # Try to extract a summary (text before the first numbered item)
    summary_lines = []
    plan_started = False

    # Patterns for numbered steps
    patterns = [
        re.compile(r"^\s*(\d+)\.\s+(.+)"),          # 1. text
        re.compile(r"^\s*(\d+)\)\s+(.+)"),           # 1) text
        re.compile(r"^\s*[Ss]tep\s+(\d+)[:\s]+(.+)"),  # Step 1: text
    ]

    # Bullet pattern (unnumbered steps)
    bullet_re = re.compile(r"^\s*[-*]\s+(.+)")

    current_step = None
    auto_num = 0

    for line in lines:
        matched = False

        # Try numbered patterns
        for pat in patterns:
            m = pat.match(line)
            if m:
                if current_step:
                    steps.append(current_step)
                num = int(m.group(1))
                title = m.group(2).strip()
                current_step = PlanStep(number=num, title=title)
                plan_started = True
                matched = True
                break

        # Try bullet pattern
        if not matched:
            m = bullet_re.match(line)
            if m and plan_started:
                if current_step:
                    steps.append(current_step)
                auto_num += 1
                current_step = PlanStep(
                    number=auto_num, title=m.group(1).strip())
                matched = True

        if not matched:
            if plan_started and current_step:
                # Continuation line — append as detail
                stripped = line.strip()
                if stripped:
                    if current_step.detail:
                        current_step.detail += " " + stripped
                    else:
                        current_step.detail = stripped
            elif not plan_started:
                if line.strip():
                    summary_lines.append(line.strip())

    if current_step:
        steps.append(current_step)

    # Renumber if auto-numbered
    if steps and steps[0].number == 0:
        for i, s in enumerate(steps, 1):
            s.number = i

    plan.summary = " ".join(summary_lines) if summary_lines else ""
    plan.steps = steps
    return plan


# ── Plan mode controller ──────────────────────────────────────────

PLAN_PROMPT = """\
Before executing anything, create a step-by-step plan for the following task.

IMPORTANT RULES:
- Output ONLY a numbered plan (1. 2. 3. etc.)
- Each step should be a specific, concrete action
- Include which files you will read, modify, or create
- Do NOT execute any tools or make any changes yet
- Start with a one-line summary of the overall approach
- Keep each step to 1-2 sentences

Task: {user_input}"""


class PlanMode:
    """Controls plan mode activation and execution."""

    # Mode constants
    OFF = "off"
    MANUAL = "manual"     # /plan triggers before next prompt
    AUTO = "auto"         # auto-plan for complex prompts
    ALWAYS = "always"     # plan every prompt

    def __init__(self, mode: str = "off",
                 auto_threshold: int = 3,
                 on_display: Optional[Callable] = None):
        """
        Args:
            mode: "off", "manual", "auto", or "always"
            auto_threshold: Router complexity score above which auto-plan triggers.
                           Uses router's score directly (positive = complex).
            on_display: Optional callback for displaying plan to user.
        """
        self.mode = mode
        self.auto_threshold = auto_threshold
        self._armed = False      # True when /plan was typed (manual trigger)
        self._current_plan: Optional[Plan] = None
        self._on_display = on_display
        self._history: list[Plan] = []

    @property
    def current_plan(self) -> Optional[Plan]:
        return self._current_plan

    def arm(self):
        """Arm plan mode for the next prompt (manual trigger via /plan)."""
        self._armed = True

    def disarm(self):
        """Cancel manual plan mode trigger."""
        self._armed = False

    def should_plan(self, user_input: str,
                    complexity_score: Optional[int] = None) -> bool:
        """Determine if plan mode should activate for this input.

        Args:
            user_input: The user's input text.
            complexity_score: Router's complexity score (if available).

        Returns:
            True if the AI should plan before executing.
        """
        if self.mode == PlanMode.OFF:
            return self._armed

        if self.mode == PlanMode.ALWAYS:
            return True

        if self.mode == PlanMode.MANUAL:
            return self._armed

        if self.mode == PlanMode.AUTO:
            if self._armed:
                return True
            if complexity_score is not None:
                return complexity_score >= self.auto_threshold
            return False

        return self._armed

    def get_plan_prompt(self, user_input: str) -> str:
        """Generate the system prompt that asks the model to plan."""
        self._armed = False  # consume the arm
        return PLAN_PROMPT.format(user_input=user_input)

    def receive_plan(self, model_output: str) -> Plan:
        """Parse the model's plan output and store it."""
        plan = parse_plan(model_output)
        self._current_plan = plan
        return plan

    def approve(self, step_by_step: bool = False):
        """User approved the plan."""
        if self._current_plan:
            self._current_plan.approved = True
            self._current_plan.step_by_step = step_by_step

    def reject(self):
        """User rejected the plan."""
        self._armed = False  # Reset arm to avoid unintended re-trigger
        if self._current_plan:
            self._history.append(self._current_plan)
            self._current_plan = None

    def mark_step_done(self, step_num: int, result: str = ""):
        """Mark a step as completed."""
        if self._current_plan:
            for s in self._current_plan.steps:
                if s.number == step_num:
                    s.status = "done"
                    s.result = result
                    break

    def mark_step_in_progress(self, step_num: int):
        """Mark a step as in-progress."""
        if self._current_plan:
            for s in self._current_plan.steps:
                if s.number == step_num:
                    s.status = "in_progress"
                    break

    def skip_step(self, step_num: int):
        """Skip a step."""
        if self._current_plan:
            for s in self._current_plan.steps:
                if s.number == step_num:
                    s.status = "skipped"
                    break

    def complete(self):
        """Mark the plan as fully done and archive it."""
        if self._current_plan:
            self._history.append(self._current_plan)
            self._current_plan = None

    def get_step_prompt(self, step: PlanStep,
                        original_input: str) -> str:
        """Generate a prompt for executing a single plan step."""
        return (
            f"Execute step {step.number} of the plan: {step.title}\n"
            f"{step.detail}\n\n"
            f"Original task: {original_input}\n\n"
            f"Execute this step now. Use the appropriate tools."
        )

    def get_full_execution_prompt(self, original_input: str) -> str:
        """Generate a prompt that tells the model to execute the full plan."""
        if not self._current_plan:
            return original_input

        steps_text = "\n".join(
            f"{s.number}. {s.title}"
            + (f" — {s.detail}" if s.detail else "")
            for s in self._current_plan.steps
        )
        return (
            f"Execute the following approved plan:\n\n"
            f"{steps_text}\n\n"
            f"Original task: {original_input}\n\n"
            f"Execute all steps now using the appropriate tools. "
            f"Work through them in order."
        )

    # ── Display helpers ───────────────────────────────────────────

    def format_plan(self, plan: Optional[Plan] = None) -> str:
        """Format a plan for terminal display."""
        p = plan or self._current_plan
        if not p:
            return "No plan available."

        lines = []
        lines.append("")
        lines.append("  ╔══════════════════════════════════════════╗")
        lines.append("  ║             EXECUTION PLAN               ║")
        lines.append("  ╚══════════════════════════════════════════╝")

        if p.summary:
            lines.append(f"  {p.summary}")
            lines.append("")

        for step in p.steps:
            status_icon = {
                "pending": "○",
                "in_progress": "◐",
                "done": "●",
                "skipped": "○",
            }.get(step.status, "○")

            lines.append(f"  {status_icon} {step.number}. {step.title}")
            if step.detail:
                lines.append(f"      {step.detail}")

        lines.append("")
        return "\n".join(lines)

    def format_progress(self) -> str:
        """Format current plan progress for display."""
        p = self._current_plan
        if not p:
            return ""

        pct = p.progress_pct()
        done = p.completed_steps
        total = p.total_steps
        bar_len = 20
        filled = int(bar_len * pct / 100)
        bar = "█" * filled + "░" * (bar_len - filled)

        return f"  Plan: [{bar}] {done}/{total} steps ({pct:.0f}%)"

    def format_status(self) -> str:
        """Format plan mode status for /plan command."""
        lines = []
        lines.append(f"  Plan mode: {self.mode}")
        if self.mode == PlanMode.AUTO:
            lines.append(
                f"  Auto threshold: {self.auto_threshold} "
                f"(complexity score)")
        if self._armed:
            lines.append("  Armed: next prompt will generate a plan")
        if self._current_plan:
            lines.append(
                f"  Active plan: {self._current_plan.total_steps} steps "
                f"({self._current_plan.completed_steps} done)")
        lines.append(f"  Plans executed: {len(self._history)}")
        return "\n".join(lines)
