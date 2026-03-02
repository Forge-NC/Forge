"""Continuity benchmark tests — demonstrate context quality across swaps.

These tests verify that the ContinuityMonitor:
  1. Starts with a perfect score (no degradation before swaps)
  2. Degrades measurably after a swap
  3. Recovers score with added context
  4. Stabilizes across multiple swaps (doesn't spiral to 0)
  5. Uses timestamp-based recovery cooldown
"""

import time
import pytest
from dataclasses import dataclass
from typing import Optional
from forge.continuity import ContinuityMonitor, score_to_grade


# ---------------------------------------------------------------------------
# Helpers — mock context entries and task state
# ---------------------------------------------------------------------------

@dataclass
class MockEntry:
    """Simulates a ContextEntry for signal computation."""
    role: str = "user"
    content: str = ""
    partition: str = "working"
    token_count: int = 200


@dataclass
class MockTaskState:
    """Simulates engine task state for signal computation."""
    files_modified: list = None
    decisions: list = None

    def __post_init__(self):
        if self.files_modified is None:
            self.files_modified = []
        if self.decisions is None:
            self.decisions = []


def _rich_entries(n: int = 5, partition: str = "working",
                  file_names: list = None) -> list:
    """Create n substantive entries mentioning file names."""
    entries = []
    for i in range(n):
        content = f"Working on step {i+1}. "
        if file_names:
            for f in file_names:
                content += f"Modified {f}. "
        entries.append(MockEntry(
            role="assistant", content=content,
            partition=partition, token_count=200))
    return entries


# ---------------------------------------------------------------------------
# test_score_starts_perfect — A grade before any swaps
# ---------------------------------------------------------------------------

class TestScoreStartsPerfect:
    def test_no_swaps_gives_a_grade(self):
        cm = ContinuityMonitor(enabled=True)
        entries = _rich_entries(5, file_names=["main.py"])
        # Add decision terms to entries
        entries.append(MockEntry(
            content="Decided to use async for concurrency",
            token_count=150))
        task = MockTaskState(files_modified=["main.py"],
                             decisions=["Use async"])
        snap = cm.score(entries, task)
        assert snap.grade == "A"
        assert snap.score >= 90.0

    def test_working_memory_depth_perfect_before_swap(self):
        cm = ContinuityMonitor(enabled=True)
        entries = _rich_entries(3)
        task = MockTaskState()
        snap = cm.score(entries, task)
        assert snap.working_memory_depth == 1.0

    def test_swap_freshness_perfect_before_swap(self):
        cm = ContinuityMonitor(enabled=True)
        entries = _rich_entries(3)
        task = MockTaskState()
        snap = cm.score(entries, task)
        assert snap.swap_freshness == 1.0


# ---------------------------------------------------------------------------
# test_score_degrades_after_swap — measurable drop
# ---------------------------------------------------------------------------

class TestScoreDegrades:
    def test_immediate_post_swap_drops(self):
        cm = ContinuityMonitor(enabled=True)

        # Score before swap
        entries = _rich_entries(5)
        task = MockTaskState()
        snap_before = cm.score(entries, task)

        # Simulate swap
        cm.record_swap(turn=5)

        # After swap with empty working partition
        sparse_entries = [MockEntry(role="system", content="swap summary",
                                    partition="working", token_count=50)]
        snap_after = cm.score(sparse_entries, task)

        assert snap_after.score < snap_before.score
        assert snap_after.swap_freshness < 1.0

    def test_swap_freshness_zero_immediately(self):
        cm = ContinuityMonitor(enabled=True)
        cm.record_swap(turn=1)
        # 0 turns since swap
        assert cm._turns_since_swap == 0
        entries = _rich_entries(1)
        task = MockTaskState()
        snap = cm.score(entries, task)
        # Freshness should be very low right after swap
        assert snap.swap_freshness < 0.3


# ---------------------------------------------------------------------------
# test_recovery_restores_score — score improves after recovery
# ---------------------------------------------------------------------------

class TestRecoveryRestores:
    def test_score_recovers_with_turns(self):
        cm = ContinuityMonitor(enabled=True)
        cm.record_swap(turn=1)

        files = ["engine.py", "config.py"]
        task = MockTaskState(files_modified=files,
                             decisions=["Use threading locks"])

        # Immediately after swap — low freshness
        entries_sparse = _rich_entries(1, file_names=files)
        snap_low = cm.score(entries_sparse, task)

        # Advance 5 turns
        for i in range(5):
            cm.advance_turn(i + 2)

        # Re-score with richer context
        entries_rich = _rich_entries(5, file_names=files)
        # Add decision terms
        entries_rich.append(MockEntry(
            content="Applied threading locks to protect shared state",
            token_count=150))
        snap_high = cm.score(entries_rich, task)

        assert snap_high.score > snap_low.score
        assert snap_high.swap_freshness > snap_low.swap_freshness


# ---------------------------------------------------------------------------
# test_multiple_swaps_stabilize — score doesn't spiral to 0
# ---------------------------------------------------------------------------

class TestMultipleSwapsStabilize:
    def test_three_swaps_stay_above_d(self):
        cm = ContinuityMonitor(enabled=True)
        files = ["main.py", "utils.py"]
        task = MockTaskState(files_modified=files)

        scores = []
        for swap_num in range(3):
            cm.record_swap(turn=swap_num * 10)
            # Simulate recovery: 5 turns of work
            for t in range(5):
                cm.advance_turn(swap_num * 10 + t + 1)

            entries = _rich_entries(4, file_names=files)
            snap = cm.score(entries, task)
            scores.append(snap.score)

        # Score should not spiral below D territory
        assert all(s > 30.0 for s in scores), \
            f"Scores spiraled too low: {scores}"

    def test_five_swaps_no_crash(self):
        cm = ContinuityMonitor(enabled=True)
        task = MockTaskState()

        for i in range(5):
            cm.record_swap(turn=i * 5)
            for t in range(3):
                cm.advance_turn(i * 5 + t + 1)
            entries = _rich_entries(3)
            snap = cm.score(entries, task)
            # Should not raise, should produce valid grade
            assert snap.grade in ("A", "B", "C", "D", "F")


# ---------------------------------------------------------------------------
# test_recovery_cooldown — timestamp-based
# ---------------------------------------------------------------------------

class TestRecoveryCooldown:
    def test_cooldown_blocks_immediate_recovery(self):
        cm = ContinuityMonitor(enabled=True, threshold=60,
                               aggressive_threshold=40)
        cm.record_swap(turn=1)

        # Create low-score snapshot
        entries = [MockEntry(content="x", token_count=10)]
        task = MockTaskState(files_modified=["a.py", "b.py", "c.py"])
        snap = cm.score(entries, task)

        # First recovery triggers
        result1 = cm.needs_recovery(snap)
        assert result1 is not None

        # Immediate second call should be blocked by cooldown
        result2 = cm.needs_recovery(snap)
        assert result2 is None

    def test_cooldown_expires_after_timeout(self):
        cm = ContinuityMonitor(enabled=True, threshold=60,
                               aggressive_threshold=40)
        cm.record_swap(turn=1)

        entries = [MockEntry(content="x", token_count=10)]
        task = MockTaskState(files_modified=["a.py", "b.py", "c.py"])
        snap = cm.score(entries, task)

        # First recovery triggers and sets cooldown
        result1 = cm.needs_recovery(snap)
        assert result1 is not None

        # Manually expire the cooldown
        cm._recovery_cooldown_until = time.time() - 1

        # Now recovery should trigger again
        result3 = cm.needs_recovery(snap)
        assert result3 is not None

    def test_no_recovery_before_first_swap(self):
        cm = ContinuityMonitor(enabled=True, threshold=60)
        entries = _rich_entries(1)
        task = MockTaskState()
        snap = cm.score(entries, task)
        assert cm.needs_recovery(snap) is None

    def test_aggressive_vs_mild(self):
        cm = ContinuityMonitor(enabled=True, threshold=60,
                               aggressive_threshold=40)
        cm.record_swap(turn=1)

        # Create snapshot with score between 40-60 → mild
        from forge.continuity import ContinuitySnapshot
        mild_snap = ContinuitySnapshot(
            timestamp=time.time(), score=50.0, grade="C",
            objective_alignment=1.0, file_coverage=0.5,
            decision_retention=0.5, swap_freshness=0.5,
            recall_quality=1.0, working_memory_depth=0.5,
            swaps_total=1)
        result = cm.needs_recovery(mild_snap)
        assert result == "mild"

        # Reset cooldown
        cm._recovery_cooldown_until = 0.0

        # Create snapshot with score below 40 → aggressive
        aggressive_snap = ContinuitySnapshot(
            timestamp=time.time(), score=30.0, grade="F",
            objective_alignment=1.0, file_coverage=0.3,
            decision_retention=0.3, swap_freshness=0.3,
            recall_quality=1.0, working_memory_depth=0.3,
            swaps_total=1)
        result = cm.needs_recovery(aggressive_snap)
        assert result == "aggressive"


# ---------------------------------------------------------------------------
# test_file_coverage_word_boundary — no false positives
# ---------------------------------------------------------------------------

class TestFileCoverageWordBoundary:
    def test_exact_match(self):
        cm = ContinuityMonitor(enabled=True)
        cm.record_swap(turn=1)
        for t in range(3):
            cm.advance_turn(t + 2)

        entries = [MockEntry(content="Modified config.py successfully",
                             token_count=200)]
        task = MockTaskState(files_modified=["config.py"])
        snap = cm.score(entries, task)
        assert snap.file_coverage == 1.0

    def test_no_false_positive_substring(self):
        cm = ContinuityMonitor(enabled=True)
        cm.record_swap(turn=1)
        for t in range(3):
            cm.advance_turn(t + 2)

        # "a.py" should NOT match "data.py"
        entries = [MockEntry(content="Modified data.py successfully",
                             token_count=200)]
        task = MockTaskState(files_modified=["a.py"])
        snap = cm.score(entries, task)
        assert snap.file_coverage == 0.0


# ---------------------------------------------------------------------------
# test_grade_mapping
# ---------------------------------------------------------------------------

class TestGradeMapping:
    def test_score_to_grade(self):
        assert score_to_grade(95) == "A"
        assert score_to_grade(90) == "A"
        assert score_to_grade(80) == "B"
        assert score_to_grade(75) == "B"
        assert score_to_grade(65) == "C"
        assert score_to_grade(60) == "C"
        assert score_to_grade(50) == "D"
        assert score_to_grade(40) == "D"
        assert score_to_grade(30) == "F"
        assert score_to_grade(0) == "F"


# ---------------------------------------------------------------------------
# test_format
# ---------------------------------------------------------------------------

class TestFormat:
    def test_format_status_empty(self):
        cm = ContinuityMonitor(enabled=True)
        assert cm.format_status() == ""

    def test_format_detail_no_data(self):
        cm = ContinuityMonitor(enabled=True)
        output = cm.format_detail()
        assert "No continuity data" in output

    def test_format_history_empty(self):
        cm = ContinuityMonitor(enabled=True)
        output = cm.format_history()
        assert "No continuity history" in output

    def test_format_after_scoring(self):
        cm = ContinuityMonitor(enabled=True)
        cm.record_swap(turn=1)
        cm.advance_turn(2)
        entries = _rich_entries(3)
        task = MockTaskState()
        cm.score(entries, task)

        status = cm.format_status()
        assert "Continuity" in status

        detail = cm.format_detail()
        assert "Signal" in detail

        history = cm.format_history()
        assert "History" in history


# ---------------------------------------------------------------------------
# test_disabled
# ---------------------------------------------------------------------------

class TestDisabled:
    def test_disabled_returns_perfect(self):
        cm = ContinuityMonitor(enabled=False)
        entries = []
        task = MockTaskState()
        snap = cm.score(entries, task)
        assert snap.score == 100.0
        assert snap.grade == "A"

    def test_disabled_no_recovery(self):
        cm = ContinuityMonitor(enabled=False)
        cm.record_swap(turn=1)
        entries = []
        task = MockTaskState()
        snap = cm.score(entries, task)
        assert cm.needs_recovery(snap) is None
