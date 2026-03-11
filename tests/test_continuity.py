"""Standalone tests for continuity monitor (forge/continuity.py)."""
import math
import time
import pytest

from forge.continuity import ContinuityMonitor, score_to_grade


# ── Mock helpers ──

class _Entry:
    """Mock context entry with content, partition, and token_count."""
    def __init__(self, content="", partition="working", token_count=50):
        self.content = content
        self.partition = partition
        self.token_count = token_count


class _TaskState:
    """Mock task state with files_modified and decisions."""
    def __init__(self, files_modified=None, decisions=None):
        self.files_modified = files_modified or []
        self.decisions = decisions or []


@pytest.fixture
def monitor():
    """Create a ContinuityMonitor with defaults."""
    return ContinuityMonitor(enabled=True)


# ── Swap freshness formula ──

class TestSwapFreshness:
    """Verifies _signal_swap_freshness() decays after context swaps and recovers over turns.

    No swaps → 1.0 (pristine). Immediately after 1 swap (turns_since_swap=0) → clamped to 0.2.
    5 turns after a swap → > 0.5 (partial recovery). 20 turns after → > 0.8 (near full recovery).
    More swaps degrade the score further for the same turn count: f(swaps=1) > f(swaps=10).
    Formula is: max(0.2, (1 - exp(-0.4*t)) * (1 / (1 + 0.05*s))) — tested for mathematical
    correctness at t=5, s=2. Floor is always >= 0.2 even with 100 swaps at turn 0.
    """

    def test_no_swaps_returns_one(self, monitor):
        # No swaps yet → pristine = 1.0
        f = monitor._signal_swap_freshness()
        assert f == 1.0

    def test_immediately_after_swap(self, monitor):
        monitor._swaps_total = 1
        monitor._turns_since_swap = 0
        f = monitor._signal_swap_freshness()
        # (1 - e^0) * penalty = 0 * penalty → clamped to 0.2
        assert f == pytest.approx(0.2, abs=0.01)

    def test_recovery_after_turns(self, monitor):
        monitor._swaps_total = 1
        monitor._turns_since_swap = 5
        f = monitor._signal_swap_freshness()
        assert f > 0.5

    def test_full_recovery(self, monitor):
        monitor._swaps_total = 1
        monitor._turns_since_swap = 20
        f = monitor._signal_swap_freshness()
        assert f > 0.8

    def test_cumulative_degradation(self, monitor):
        monitor._turns_since_swap = 10
        monitor._swaps_total = 1
        f1 = monitor._signal_swap_freshness()
        monitor._swaps_total = 10
        f10 = monitor._signal_swap_freshness()
        assert f1 > f10

    def test_floor_at_0_2(self, monitor):
        monitor._swaps_total = 100
        monitor._turns_since_swap = 0
        f = monitor._signal_swap_freshness()
        assert f >= 0.2

    def test_mathematical_correctness(self, monitor):
        t, s = 5, 2
        monitor._swaps_total = s
        monitor._turns_since_swap = t
        expected = max(0.2, (1 - math.exp(-0.4 * t)) * (1 / (1 + 0.05 * s)))
        actual = monitor._signal_swap_freshness()
        assert actual == pytest.approx(expected, abs=0.001)


# ── File coverage ──

class TestFileCoverage:
    """Verifies _signal_file_coverage() measures whether modified files are mentioned in context.

    All files mentioned → 1.0. None mentioned → 0.0. 1 of 3 mentioned → 0.2–0.5 (partial).
    No modified files at all → 1.0 (nothing to track).
    """

    def test_all_files_present(self, monitor):
        entries = [_Entry(content="Working on a.py and b.py with some changes")]
        task = _TaskState(files_modified=["a.py", "b.py"])
        score = monitor._signal_file_coverage(entries, task)
        assert score == 1.0

    def test_no_files_present(self, monitor):
        entries = [_Entry(content="nothing relevant here")]
        task = _TaskState(files_modified=["secret.py"])
        score = monitor._signal_file_coverage(entries, task)
        assert score == 0.0

    def test_partial_coverage(self, monitor):
        entries = [_Entry(content="Working on a.py only")]
        task = _TaskState(files_modified=["a.py", "b.py", "c.py"])
        score = monitor._signal_file_coverage(entries, task)
        assert 0.2 <= score <= 0.5

    def test_no_modified_files(self, monitor):
        entries = [_Entry(content="anything")]
        task = _TaskState(files_modified=[])
        score = monitor._signal_file_coverage(entries, task)
        assert score == 1.0


# ── Decision retention ──

class TestDecisionRetention:
    """Verifies _signal_decision_retention() checks whether key decisions are still in context.

    Both decisions present → > 0.5. No decisions to check → 1.0. Exactly 1 of 2 decisions
    mentioned → 0.5. Uses substring matching of decision text within context entry content.
    """

    def test_all_decisions_retained(self, monitor):
        entries = [_Entry(
            content="We decided to use HashMap for caching and refactor the parser")]
        task = _TaskState(
            decisions=["use HashMap for caching", "refactor the parser"])
        score = monitor._signal_decision_retention(entries, task)
        assert score > 0.5

    def test_no_decisions(self, monitor):
        entries = [_Entry(content="anything")]
        task = _TaskState(decisions=[])
        score = monitor._signal_decision_retention(entries, task)
        assert score == 1.0

    def test_partial_retention(self, monitor):
        entries = [_Entry(
            content="We're using HashMap for caching but nothing about migration")]
        task = _TaskState(
            decisions=["use HashMap for caching", "migrate database to PostgreSQL"])
        score = monitor._signal_decision_retention(entries, task)
        assert score == 0.5  # 1 of 2 retained


# ── Working memory depth ──

class TestWorkingMemoryDepth:
    """Verifies _signal_working_memory_depth() measures substantive context after swaps.

    No swaps → 1.0 (context was never disrupted). After a swap with no entries → 0.0.
    3 entries all with token_count >= 100 → 1.0 (all substantive). 3 entries all with
    token_count <= 50 → 0.0 (all shallow). 2 substantive + 2 shallow → 0.5.
    Threshold for 'substantive' is 100 tokens per working-partition entry.
    """

    def test_no_swaps_returns_one(self, monitor):
        # No swaps → pristine context
        score = monitor._signal_working_memory_depth([])
        assert score == 1.0

    def test_empty_after_swap(self, monitor):
        monitor._swaps_total = 1
        score = monitor._signal_working_memory_depth([])
        assert score == 0.0

    def test_all_substantive(self, monitor):
        monitor._swaps_total = 1
        entries = [
            _Entry(partition="working", token_count=150),
            _Entry(partition="working", token_count=200),
            _Entry(partition="working", token_count=120),
        ]
        score = monitor._signal_working_memory_depth(entries)
        assert score == 1.0

    def test_all_shallow(self, monitor):
        monitor._swaps_total = 1
        entries = [
            _Entry(partition="working", token_count=10),
            _Entry(partition="working", token_count=20),
            _Entry(partition="working", token_count=30),
        ]
        score = monitor._signal_working_memory_depth(entries)
        assert score == 0.0

    def test_mixed_depth(self, monitor):
        monitor._swaps_total = 1
        entries = [
            _Entry(partition="working", token_count=150),
            _Entry(partition="working", token_count=20),
            _Entry(partition="working", token_count=120),
            _Entry(partition="working", token_count=10),
        ]
        score = monitor._signal_working_memory_depth(entries)
        assert score == 0.5


# ── Grade computation ──

class TestGradeComputation:
    """Verifies score_to_grade() maps numeric scores to letter grades correctly.

    95 → A, 80 → B, 65 → C, 45 → D, 30 → F. These thresholds define the
    grade boundaries for continuity health display in the UI.
    """

    def test_grade_a(self):
        assert score_to_grade(95) == "A"

    def test_grade_b(self):
        assert score_to_grade(80) == "B"

    def test_grade_c(self):
        assert score_to_grade(65) == "C"

    def test_grade_d(self):
        assert score_to_grade(45) == "D"

    def test_grade_f(self):
        assert score_to_grade(30) == "F"


# ── to_audit_dict ──

class TestAuditDict:
    """Verifies to_audit_dict() returns a dict with all required audit fields.

    Must include: schema_version, current_score, current_grade, swaps_total.
    """

    def test_has_required_keys(self, monitor):
        audit = monitor.to_audit_dict()
        assert "schema_version" in audit
        assert "current_score" in audit
        assert "current_grade" in audit
        assert "swaps_total" in audit


# ── Recovery logic ──

class TestRecoveryLogic:
    """Verifies needs_recovery() correctly maps continuity health to recovery mode or None.

    Grade A (score=92) → None (no recovery needed). Grade C (score=55) with at least 1 swap
    → 'mild' recovery. Recovery is suppressed during cooldown period (_recovery_cooldown_until
    in the future) even with grade F. Recovery is also suppressed when _recovery_attempts >= 6
    (max attempts exhausted) to prevent infinite recovery loops.
    """

    def test_no_recovery_at_grade_a(self, monitor):
        from forge.continuity import ContinuitySnapshot
        snap = ContinuitySnapshot(
            timestamp=time.time(), score=92, grade="A",
            objective_alignment=1.0, file_coverage=1.0,
            decision_retention=1.0, swap_freshness=1.0,
            recall_quality=1.0, working_memory_depth=1.0,
            swaps_total=1)
        assert monitor.needs_recovery(snap) is None

    def test_mild_recovery_at_grade_c(self, monitor):
        from forge.continuity import ContinuitySnapshot
        monitor._swaps_total = 1  # need at least 1 swap
        snap = ContinuitySnapshot(
            timestamp=time.time(), score=55, grade="C",
            objective_alignment=0.5, file_coverage=0.5,
            decision_retention=0.5, swap_freshness=0.5,
            recall_quality=0.5, working_memory_depth=0.5,
            swaps_total=1)
        assert monitor.needs_recovery(snap) == "mild"

    def test_recovery_cooldown(self, monitor):
        from forge.continuity import ContinuitySnapshot
        monitor._swaps_total = 1
        monitor._recovery_cooldown_until = time.time() + 60
        snap = ContinuitySnapshot(
            timestamp=time.time(), score=30, grade="F",
            objective_alignment=0.3, file_coverage=0.3,
            decision_retention=0.3, swap_freshness=0.3,
            recall_quality=0.3, working_memory_depth=0.3,
            swaps_total=1)
        assert monitor.needs_recovery(snap) is None

    def test_recovery_attempt_limit(self, monitor):
        from forge.continuity import ContinuitySnapshot
        monitor._swaps_total = 1
        monitor._recovery_attempts = 6
        snap = ContinuitySnapshot(
            timestamp=time.time(), score=30, grade="F",
            objective_alignment=0.3, file_coverage=0.3,
            decision_retention=0.3, swap_freshness=0.3,
            recall_quality=0.3, working_memory_depth=0.3,
            swaps_total=1)
        assert monitor.needs_recovery(snap) is None
