"""Continuity Grade system — measures context quality across swaps.

Scores 6 deterministic signals (0-100) into a composite grade (A-F).
When the grade drops below configurable thresholds, triggers auto-recovery
by re-reading files and re-injecting semantic recalls.
"""

import logging
import math
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

log = logging.getLogger(__name__)


# ── Grade mapping ──

GRADE_THRESHOLDS = [
    (90, "A"),
    (75, "B"),
    (60, "C"),
    (40, "D"),
    (0,  "F"),
]

GRADE_COLORS = {
    "A": "\033[92m",   # bright green
    "B": "\033[36m",   # cyan
    "C": "\033[93m",   # yellow
    "D": "\033[33m",   # orange/dark yellow
    "F": "\033[91m",   # red
}

GRADE_COLORS_HEX = {
    "A": "#00ff88",
    "B": "#00d4ff",
    "C": "#ffaa00",
    "D": "#ff8800",
    "F": "#ff3344",
}


def score_to_grade(score: float) -> str:
    """Convert 0-100 score to letter grade."""
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


# ── Data classes ──

@dataclass
class ContinuitySnapshot:
    """Point-in-time measurement of context continuity quality."""
    timestamp: float
    score: float                    # 0-100 composite
    grade: str                      # A-F
    objective_alignment: float      # 0.0-1.0
    file_coverage: float            # 0.0-1.0
    decision_retention: float       # 0.0-1.0
    swap_freshness: float           # 0.0-1.0
    recall_quality: float           # 0.0-1.0
    working_memory_depth: float     # 0.0-1.0
    swaps_total: int
    recovery_triggered: bool = False


# ── Signal weights ──

# Full weights (with embeddings)
_WEIGHTS_FULL = {
    "objective_alignment":  0.25,
    "file_coverage":        0.25,
    "decision_retention":   0.15,
    "swap_freshness":       0.15,
    "recall_quality":       0.10,
    "working_memory_depth": 0.10,
}

# Reduced weights (no embeddings — skip signals 1 & 5)
_WEIGHTS_NO_EMBED = {
    "file_coverage":        0.40,
    "decision_retention":   0.25,
    "swap_freshness":       0.20,
    "working_memory_depth": 0.15,
}


class ContinuityMonitor:
    """Scores context quality from 6 deterministic signals."""

    def __init__(self, *, enabled: bool = True,
                 threshold: int = 60,
                 aggressive_threshold: int = 40):
        self.enabled = enabled
        self.threshold = threshold
        self.aggressive_threshold = aggressive_threshold

        # Embedding function — wired from engine after index init
        self._embed_fn: Optional[Callable] = None

        # State
        self._objective_text: Optional[str] = None
        self._objective_embedding: Optional[list[float]] = None
        self._swaps_total = 0
        self._turns_since_swap = 0
        self._last_recall_scores: list[float] = []
        self._recovery_cooldown_until = 0.0   # timestamp-based cooldown
        self._recovery_attempts = 0
        self._max_recovery_attempts = 5      # stop trying after 5 failures
        self._history: list[ContinuitySnapshot] = []
        self._current: Optional[ContinuitySnapshot] = None

    # ── Public API ──

    def set_objective(self, text: str):
        """Embed baseline objective (called once, on first turn with objective)."""
        if not text or text == self._objective_text:
            return
        self._objective_text = text
        if self._embed_fn:
            try:
                self._objective_embedding = self._embed_fn(text)
            except Exception as e:
                log.debug("Failed to embed objective: %s", e)
                self._objective_embedding = None

    def record_swap(self, turn: int, recall_scores: list[float] = None):
        """Called after each context swap."""
        self._swaps_total += 1
        self._turns_since_swap = 0
        if recall_scores:
            self._last_recall_scores = recall_scores

    def advance_turn(self, turn: int):
        """Called each turn to update freshness tracking."""
        self._turns_since_swap += 1

    def score(self, context_entries, task_state) -> ContinuitySnapshot:
        """Compute composite score from 6 signals."""
        if not self.enabled:
            snap = ContinuitySnapshot(
                timestamp=time.time(), score=100.0, grade="A",
                objective_alignment=1.0, file_coverage=1.0,
                decision_retention=1.0, swap_freshness=1.0,
                recall_quality=1.0, working_memory_depth=1.0,
                swaps_total=self._swaps_total)
            self._current = snap
            return snap

        # Compute all 6 signals
        s1 = self._signal_objective_alignment(context_entries)
        s2 = self._signal_file_coverage(context_entries, task_state)
        s3 = self._signal_decision_retention(context_entries, task_state)
        s4 = self._signal_swap_freshness()
        s5 = self._signal_recall_quality()
        s6 = self._signal_working_memory_depth(context_entries)

        # Choose weight set
        has_embed = self._embed_fn is not None
        if has_embed:
            weights = _WEIGHTS_FULL
            signals = {
                "objective_alignment": s1,
                "file_coverage": s2,
                "decision_retention": s3,
                "swap_freshness": s4,
                "recall_quality": s5,
                "working_memory_depth": s6,
            }
        else:
            weights = _WEIGHTS_NO_EMBED
            signals = {
                "file_coverage": s2,
                "decision_retention": s3,
                "swap_freshness": s4,
                "working_memory_depth": s6,
            }

        composite = sum(signals[k] * weights[k] for k in weights) * 100.0
        composite = max(0.0, min(100.0, composite))

        snap = ContinuitySnapshot(
            timestamp=time.time(),
            score=composite,
            grade=score_to_grade(composite),
            objective_alignment=s1,
            file_coverage=s2,
            decision_retention=s3,
            swap_freshness=s4,
            recall_quality=s5,
            working_memory_depth=s6,
            swaps_total=self._swaps_total,
        )
        self._current = snap
        self._history.append(snap)
        # Keep last 50 snapshots
        if len(self._history) > 50:
            self._history = self._history[-50:]
        return snap

    # Seconds to wait between recovery attempts
    RECOVERY_COOLDOWN_SECONDS = 60

    def needs_recovery(self, snapshot: ContinuitySnapshot) -> Optional[str]:
        """Check if recovery should trigger. Returns 'mild', 'aggressive', or None.

        Stops after max_recovery_attempts to prevent infinite recovery loops.
        Counter resets when grade improves above threshold.
        """
        if not self.enabled:
            return None
        if time.time() < self._recovery_cooldown_until:
            return None
        if self._swaps_total == 0:
            return None  # no swaps yet, nothing to recover from

        # Reset counter when grade is good — recovery worked
        if snapshot.score >= self.threshold:
            self._recovery_attempts = 0
            return None

        # Stop trying after too many failures
        if self._recovery_attempts >= self._max_recovery_attempts:
            return None

        if snapshot.score < self.aggressive_threshold:
            self._recovery_cooldown_until = (
                time.time() + self.RECOVERY_COOLDOWN_SECONDS)
            self._recovery_attempts += 1
            return "aggressive"
        elif snapshot.score < self.threshold:
            self._recovery_cooldown_until = (
                time.time() + self.RECOVERY_COOLDOWN_SECONDS)
            self._recovery_attempts += 1
            return "mild"
        return None

    def to_audit_dict(self) -> dict:
        """Return a JSON-serializable audit snapshot.

        Stable API contract for the audit exporter.
        """
        from dataclasses import asdict
        current = self._current
        return {
            "schema_version": 1,
            "enabled": self.enabled,
            "current_grade": current.grade if current else "A",
            "current_score": current.score if current else 100.0,
            "swaps_total": self._swaps_total,
            "turns_since_swap": self._turns_since_swap,
            "history": [asdict(s) for s in self._history],
        }

    def format_status(self) -> str:
        """One-line terminal display with bar."""
        if not self._current or self._swaps_total == 0:
            return ""
        s = self._current
        gc = GRADE_COLORS.get(s.grade, "")
        rst = "\033[0m"
        bar_len = 20
        filled = int(s.score / 100 * bar_len)
        bar = f"{gc}{'|' * filled}{rst}{'.' * (bar_len - filled)}"
        return (f"Continuity: {gc}{s.grade}{rst} "
                f"[{bar}] {s.score:.0f}/100 | "
                f"{s.swaps_total} swap{'s' if s.swaps_total != 1 else ''}")

    def format_detail(self) -> str:
        """Full breakdown table for /continuity command."""
        if not self._current:
            return "No continuity data yet. Scores appear after the first context swap."

        s = self._current
        gc = GRADE_COLORS.get(s.grade, "")
        rst = "\033[0m"
        bold = "\033[1m"
        dim = "\033[2m"
        has_embed = self._embed_fn is not None

        lines = [
            f"\n{bold}Continuity Grade{rst}",
            f"  Grade:    {gc}{bold}{s.grade}{rst}  ({s.score:.1f}/100)",
            f"  Swaps:    {s.swaps_total}",
            f"  Turns since swap: {self._turns_since_swap}",
            f"  Recovery cooldown: {max(0, int(self._recovery_cooldown_until - time.time()))}s",
            "",
            f"  {bold}{'Signal':<25} {'Value':>8}  {'Weight':>8}{rst}",
            f"  {'-' * 45}",
        ]

        weights = _WEIGHTS_FULL if has_embed else _WEIGHTS_NO_EMBED
        signals = [
            ("Objective Alignment", s.objective_alignment,
             weights.get("objective_alignment", 0)),
            ("File Coverage", s.file_coverage,
             weights.get("file_coverage", 0)),
            ("Decision Retention", s.decision_retention,
             weights.get("decision_retention", 0)),
            ("Swap Freshness", s.swap_freshness,
             weights.get("swap_freshness", 0)),
            ("Recall Quality", s.recall_quality,
             weights.get("recall_quality", 0)),
            ("Working Memory Depth", s.working_memory_depth,
             weights.get("working_memory_depth", 0)),
        ]

        for name, val, weight in signals:
            if weight == 0:
                tag = f" {dim}(skipped — no embeddings){rst}"
            else:
                tag = ""
            pct = f"{val * 100:.0f}%"
            w_str = f"{weight:.0%}" if weight > 0 else "--"
            lines.append(f"  {name:<25} {pct:>8}  {w_str:>8}{tag}")

        lines.append(f"\n  {dim}Threshold: mild < {self.threshold}, "
                     f"aggressive < {self.aggressive_threshold}{rst}")
        return "\n".join(lines)

    def format_history(self, count: int = 10) -> str:
        """Show last N snapshots."""
        if not self._history:
            return "No continuity history yet."

        rst = "\033[0m"
        bold = "\033[1m"
        dim = "\033[2m"

        entries = self._history[-count:]
        lines = [
            f"\n{bold}Continuity History (last {len(entries)}){rst}",
            f"  {'#':>3}  {'Grade':>5}  {'Score':>6}  "
            f"{'ObjAl':>5}  {'FilCv':>5}  {'DecRt':>5}  "
            f"{'SwpFr':>5}  {'RclQl':>5}  {'WMDep':>5}  {'Rcvr':>4}",
            f"  {'-' * 72}",
        ]

        for i, s in enumerate(entries, 1):
            gc = GRADE_COLORS.get(s.grade, "")
            rcvr = "Y" if s.recovery_triggered else "-"
            lines.append(
                f"  {i:>3}  {gc}{s.grade:>5}{rst}  {s.score:>5.0f}  "
                f"{s.objective_alignment * 100:>5.0f}  "
                f"{s.file_coverage * 100:>5.0f}  "
                f"{s.decision_retention * 100:>5.0f}  "
                f"{s.swap_freshness * 100:>5.0f}  "
                f"{s.recall_quality * 100:>5.0f}  "
                f"{s.working_memory_depth * 100:>5.0f}  "
                f"{rcvr:>4}")

        return "\n".join(lines)

    # ── Signal computations ──

    def _signal_objective_alignment(self, context_entries) -> float:
        """Cosine similarity: original objective embedding vs current context."""
        if not self._embed_fn or not self._objective_embedding:
            return 1.0  # sentinel — will be skipped by weight set

        # Build context text from entries
        context_text = self._entries_to_text(context_entries, max_chars=2000)
        if not context_text:
            return 0.5

        try:
            ctx_embedding = self._embed_fn(context_text)
            return self._cosine_similarity(
                self._objective_embedding, ctx_embedding)
        except Exception:
            return 0.5

    def _signal_file_coverage(self, context_entries, task_state) -> float:
        """% of TaskState.files_modified still represented in context."""
        if not task_state or not task_state.files_modified:
            return 1.0  # nothing to lose

        context_text = self._entries_to_text(context_entries, max_chars=50000)
        found = 0
        for fpath in task_state.files_modified:
            # Check by filename with word boundaries to avoid false positives
            # e.g. "a.py" should not match "data.py"
            fname = fpath.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            pattern = r'(?<![a-zA-Z0-9_])' + re.escape(fname) + r'(?![a-zA-Z0-9_])'
            if re.search(pattern, context_text):
                found += 1

        return found / len(task_state.files_modified)

    def _signal_decision_retention(self, context_entries, task_state) -> float:
        """% of TaskState.decisions whose key terms are findable in context."""
        if not task_state or not task_state.decisions:
            return 1.0

        context_text = self._entries_to_text(
            context_entries, max_chars=50000).lower()
        retained = 0
        for decision in task_state.decisions:
            # Extract key terms (words > 4 chars)
            terms = [w for w in decision.lower().split() if len(w) > 4]
            if not terms:
                retained += 1
                continue
            matches = sum(1 for t in terms if t in context_text)
            if matches / len(terms) >= 0.5:
                retained += 1

        return retained / len(task_state.decisions)

    def _signal_swap_freshness(self) -> float:
        """Exponential recovery after swap, penalized by total swap count.

        Floor at 0.2 prevents crushing to zero at high swap counts —
        even after 50 swaps, some recovery is possible.
        """
        if self._swaps_total == 0:
            return 1.0

        # Base recovery: approaches 1.0 as turns pass after swap
        base = 1.0 - math.exp(-0.4 * self._turns_since_swap)

        # Penalty for accumulated swaps (diminishing returns)
        penalty = 1.0 / (1.0 + 0.05 * self._swaps_total)

        return max(0.2, base * penalty)

    def _signal_recall_quality(self) -> float:
        """Average cosine similarity of post-swap semantic recalls."""
        if not self._embed_fn:
            return 1.0  # sentinel

        if not self._last_recall_scores:
            if self._swaps_total > 0:
                return 0.3  # swapped but no recalls
            return 1.0

        avg = sum(self._last_recall_scores) / len(self._last_recall_scores)
        return min(1.0, avg)

    def _signal_working_memory_depth(self, context_entries) -> float:
        """Ratio of substantive entries (>100 tokens) in working partition."""
        if self._swaps_total == 0:
            return 1.0  # pristine context, no degradation yet

        if not context_entries:
            return 0.0  # after swap with empty context = total loss

        working = [e for e in context_entries
                   if getattr(e, 'partition', '') == 'working']
        if not working:
            return 0.5  # after swap but no working entries is concerning

        substantive = sum(1 for e in working
                         if getattr(e, 'token_count', 0) > 100)
        return substantive / len(working)

    # ── Helpers ──

    @staticmethod
    def _entries_to_text(entries, max_chars: int = 10000) -> str:
        """Concatenate entry contents into searchable text."""
        parts = []
        total = 0
        for e in entries:
            content = getattr(e, 'content', '')
            if not content:
                continue
            parts.append(content)
            total += len(content)
            if total >= max_chars:
                break
        return "\n".join(parts)

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """Cosine similarity between two vectors."""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(x * x for x in b))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return max(0.0, min(1.0, dot / (mag_a * mag_b)))
