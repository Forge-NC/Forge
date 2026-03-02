"""Reliability tracking — persistent cross-session stability metrics.

Accumulates per-session health metrics into a rolling 30-session window.
Computes a composite reliability score from:
  - Plan verification pass rate
  - Continuity grade average
  - Tool success rate
  - Session duration stability
  - Token efficiency

Shows BOTH composite score AND underlying metrics — transparent,
not a magic number. Persists via atomic write (tempfile -> rename).
"""

import json
import logging
import math
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class SessionHealth:
    """Health snapshot for a single completed session."""
    session_id: str
    timestamp: float
    verification_pass_rate: float   # 0.0-1.0
    continuity_grade_avg: float     # 0.0-100.0
    tool_success_rate: float        # 0.0-1.0
    duration_s: float
    token_efficiency: float         # output_tokens / turns
    total_turns: int
    total_tokens: int
    model: str
    unverified_steps: int = 0       # plan steps without verification
    rollback_count: int = 0         # strict-mode rollbacks
    repair_success_count: int = 0   # repair-mode fixes that passed


# ── Composite score weights ──

WEIGHTS = {
    "verification_pass_rate": 0.25,
    "continuity_grade_avg":   0.25,
    "tool_success_rate":      0.20,
    "duration_stability":     0.15,
    "token_efficiency":       0.15,
}


class ReliabilityTracker:
    """Persistent cross-session reliability metrics with rolling window."""

    WINDOW_SIZE = 30

    def __init__(self, persist_path: Path = None):
        self._persist_path = persist_path or (
            Path.home() / ".forge" / "reliability.json")
        self._sessions: list[SessionHealth] = []
        self._load()

    def record_session(self, *, forensics, continuity, plan_verifier,
                       billing, session_start: float, turn_count: int,
                       model: str) -> SessionHealth:
        """Record end-of-session health metrics.

        Uses to_audit_dict() on subsystems — never accesses private fields.
        """
        now = time.time()
        duration = now - session_start

        # Verification pass rate
        verifier_data = plan_verifier.to_audit_dict()
        results = verifier_data.get("results", [])
        if results:
            passed = sum(1 for r in results if r.get("passed", False))
            verify_rate = passed / len(results)
            unverified = sum(1 for r in results
                             if not r.get("checks"))
            rollbacks = sum(1 for r in results
                            if r.get("rolled_back", False))
            repairs = sum(1 for r in results
                          if r.get("auto_fixed", False))
        else:
            verify_rate = 1.0  # benefit of the doubt
            unverified = 0
            rollbacks = 0
            repairs = 0

        # Continuity grade average
        cont_data = continuity.to_audit_dict()
        history = cont_data.get("history", [])
        if history:
            scores = [h.get("score", 100) for h in history]
            cont_avg = sum(scores) / len(scores)
        else:
            cont_avg = 100.0

        # Tool success rate from forensics
        forensics_data = forensics.to_audit_dict()
        events = forensics_data.get("events", [])
        tool_events = [e for e in events if e.get("category") == "tool"]
        if tool_events:
            ok = sum(1 for e in tool_events
                     if e.get("risk_level", 0) == 0)
            tool_rate = ok / len(tool_events)
        else:
            tool_rate = 1.0

        # Token efficiency
        billing_data = billing.to_audit_dict()
        output_tokens = billing_data.get("session_output", 0)
        tok_efficiency = output_tokens / max(1, turn_count)

        health = SessionHealth(
            session_id=forensics_data.get("session_id", ""),
            timestamp=now,
            verification_pass_rate=round(verify_rate, 4),
            continuity_grade_avg=round(cont_avg, 1),
            tool_success_rate=round(tool_rate, 4),
            duration_s=round(duration, 1),
            token_efficiency=round(tok_efficiency, 1),
            total_turns=turn_count,
            total_tokens=billing_data.get("session_tokens", 0),
            model=model,
            unverified_steps=unverified,
            rollback_count=rollbacks,
            repair_success_count=repairs,
        )

        self._sessions.append(health)
        # Prune to window size
        if len(self._sessions) > self.WINDOW_SIZE:
            self._sessions = self._sessions[-self.WINDOW_SIZE:]
        self._save()
        return health

    def get_reliability_score(self) -> float:
        """Composite reliability score 0-100 from rolling window."""
        if not self._sessions:
            return 100.0  # benefit of the doubt

        return self._compute_composite(self._sessions)

    def get_underlying_metrics(self) -> dict:
        """Individual metric values — transparent, not just a magic number."""
        if not self._sessions:
            return {
                "verification_pass_rate": 1.0,
                "continuity_grade_avg": 100.0,
                "tool_success_rate": 1.0,
                "duration_stability": 1.0,
                "token_efficiency_normalized": 1.0,
                "sessions_in_window": 0,
            }

        window = self._sessions[-self.WINDOW_SIZE:]
        return {
            "verification_pass_rate": self._avg(
                [s.verification_pass_rate for s in window]),
            "continuity_grade_avg": self._avg(
                [s.continuity_grade_avg for s in window]),
            "tool_success_rate": self._avg(
                [s.tool_success_rate for s in window]),
            "duration_stability": self._duration_stability(window),
            "token_efficiency_normalized": self._token_efficiency_norm(window),
            "sessions_in_window": len(window),
            "total_rollbacks": sum(s.rollback_count for s in window),
            "total_repairs": sum(s.repair_success_count for s in window),
            "total_unverified": sum(s.unverified_steps for s in window),
        }

    def get_trend(self) -> dict:
        """30-session trend data for dashboard card."""
        if len(self._sessions) < 2:
            return {"direction": "insufficient data", "scores": []}

        window = self._sessions[-self.WINDOW_SIZE:]
        scores = [self._compute_composite([s]) for s in window]

        # Compare first half vs second half
        mid = len(scores) // 2
        if mid > 0:
            first = sum(scores[:mid]) / mid
            second = sum(scores[mid:]) / len(scores[mid:])
            if second > first * 1.05:
                direction = "improving"
            elif second < first * 0.95:
                direction = "degrading"
            else:
                direction = "stable"
        else:
            direction = "stable"

        return {"direction": direction, "scores": scores}

    def get_current_session_health(self, *, forensics, continuity,
                                    plan_verifier, billing,
                                    session_start: float,
                                    turn_count: int) -> dict:
        """Live health for the current in-progress session.

        Uses to_audit_dict() — safe to call frequently.
        """
        verifier_data = plan_verifier.to_audit_dict()
        results = verifier_data.get("results", [])
        if results:
            passed = sum(1 for r in results if r.get("passed", False))
            verify_rate = passed / len(results)
        else:
            verify_rate = 1.0

        cont_data = continuity.to_audit_dict()
        history = cont_data.get("history", [])
        if history:
            scores = [h.get("score", 100) for h in history]
            cont_avg = sum(scores) / len(scores)
        else:
            cont_avg = 100.0

        forensics_data = forensics.to_audit_dict()
        events = forensics_data.get("events", [])
        tool_events = [e for e in events if e.get("category") == "tool"]
        if tool_events:
            ok = sum(1 for e in tool_events if e.get("risk_level", 0) == 0)
            tool_rate = ok / len(tool_events)
        else:
            tool_rate = 1.0

        return {
            "verification_pass_rate": round(verify_rate, 4),
            "continuity_grade_avg": round(cont_avg, 1),
            "tool_success_rate": round(tool_rate, 4),
        }

    def format_terminal(self) -> str:
        """Full reliability report for /stats reliability."""
        from forge.ui.terminal import BOLD, RESET, DIM, GREEN, YELLOW, RED, CYAN

        score = self.get_reliability_score()
        metrics = self.get_underlying_metrics()
        trend = self.get_trend()

        color = GREEN if score >= 80 else YELLOW if score >= 60 else RED

        lines = [
            f"\n{BOLD}Reliability Score{RESET}",
            f"  Composite:  {color}{score:.0f}/100{RESET} "
            f"({trend.get('direction', 'n/a')})",
            f"  Window:     {metrics['sessions_in_window']}/{self.WINDOW_SIZE} sessions",
            "",
            f"  {BOLD}{'Metric':<28} {'Value':>10}  {'Weight':>8}{RESET}",
            f"  {'-' * 50}",
        ]

        metric_display = [
            ("Verification Pass Rate",
             f"{metrics['verification_pass_rate'] * 100:.0f}%",
             WEIGHTS["verification_pass_rate"]),
            ("Continuity Grade Avg",
             f"{metrics['continuity_grade_avg']:.0f}/100",
             WEIGHTS["continuity_grade_avg"]),
            ("Tool Success Rate",
             f"{metrics['tool_success_rate'] * 100:.0f}%",
             WEIGHTS["tool_success_rate"]),
            ("Duration Stability",
             f"{metrics['duration_stability'] * 100:.0f}%",
             WEIGHTS["duration_stability"]),
            ("Token Efficiency",
             f"{metrics['token_efficiency_normalized'] * 100:.0f}%",
             WEIGHTS["token_efficiency"]),
        ]

        for name, val, weight in metric_display:
            lines.append(f"  {name:<28} {val:>10}  {weight:>7.0%}")

        # Extra premium metrics
        lines.append("")
        lines.append(f"  {BOLD}Autonomy Metrics{RESET}")
        lines.append(f"  Rollbacks:     {metrics.get('total_rollbacks', 0)}")
        lines.append(f"  Auto-repairs:  {metrics.get('total_repairs', 0)}")
        lines.append(f"  Unverified:    {metrics.get('total_unverified', 0)} steps")

        # ASCII sparkline of trend
        trend_scores = trend.get("scores", [])
        if len(trend_scores) >= 3:
            try:
                from forge.ui.charts import ChartRenderer
                spark = ChartRenderer.ascii_sparkline(trend_scores, width=30)
                lines.append(f"\n  {DIM}Trend: {spark}{RESET}")
            except Exception:
                pass

        return "\n".join(lines)

    # ── Internal helpers ──

    def _compute_composite(self, sessions: list[SessionHealth]) -> float:
        """Weighted composite score 0-100."""
        if not sessions:
            return 100.0

        avg_verify = self._avg([s.verification_pass_rate for s in sessions])
        avg_cont = self._avg([s.continuity_grade_avg for s in sessions]) / 100.0
        avg_tool = self._avg([s.tool_success_rate for s in sessions])
        dur_stab = self._duration_stability(sessions)
        tok_eff = self._token_efficiency_norm(sessions)

        composite = (
            avg_verify * WEIGHTS["verification_pass_rate"]
            + avg_cont * WEIGHTS["continuity_grade_avg"]
            + avg_tool * WEIGHTS["tool_success_rate"]
            + dur_stab * WEIGHTS["duration_stability"]
            + tok_eff * WEIGHTS["token_efficiency"]
        )
        return round(max(0.0, min(100.0, composite * 100)), 1)

    @staticmethod
    def _avg(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _duration_stability(sessions: list[SessionHealth]) -> float:
        """1.0 - coefficient_of_variation, clamped to [0, 1]."""
        if len(sessions) < 2:
            return 1.0
        durations = [s.duration_s for s in sessions if s.duration_s > 0]
        if len(durations) < 2:
            return 1.0
        mean = sum(durations) / len(durations)
        if mean == 0:
            return 1.0
        variance = sum((d - mean) ** 2 for d in durations) / len(durations)
        std = math.sqrt(variance)
        cv = std / mean
        return max(0.0, min(1.0, 1.0 - cv))

    @staticmethod
    def _token_efficiency_norm(sessions: list[SessionHealth]) -> float:
        """Normalize token efficiency via sigmoid-like scaling."""
        if not sessions:
            return 1.0
        values = [s.token_efficiency for s in sessions if s.token_efficiency > 0]
        if not values:
            return 0.5
        avg = sum(values) / len(values)
        # Sigmoid: 100 tok/turn = ~0.5, 200 = ~0.73, 500 = ~0.91
        return 1.0 / (1.0 + math.exp(-0.01 * (avg - 100)))

    def _save(self):
        """Persist session history atomically."""
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": 1,
                "sessions": [asdict(s) for s in self._sessions],
            }
            content = json.dumps(data, indent=2)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._persist_path.parent),
                suffix=".tmp", prefix="reliability_")
            closed = False
            try:
                os.write(fd, content.encode("utf-8"))
                os.close(fd)
                closed = True
                if self._persist_path.exists():
                    self._persist_path.unlink()
                os.rename(tmp_path, str(self._persist_path))
            except Exception:
                if not closed:
                    os.close(fd)
                Path(tmp_path).unlink(missing_ok=True)
                raise
        except Exception as e:
            log.debug("Failed to save reliability data: %s", e)

    def _load(self):
        """Load session history from disk."""
        if not self._persist_path.exists():
            return
        try:
            data = json.loads(
                self._persist_path.read_text(encoding="utf-8"))
            sessions = data.get("sessions", [])
            self._sessions = []
            for s in sessions[-self.WINDOW_SIZE:]:
                self._sessions.append(SessionHealth(
                    session_id=s.get("session_id", ""),
                    timestamp=s.get("timestamp", 0),
                    verification_pass_rate=s.get("verification_pass_rate", 1.0),
                    continuity_grade_avg=s.get("continuity_grade_avg", 100.0),
                    tool_success_rate=s.get("tool_success_rate", 1.0),
                    duration_s=s.get("duration_s", 0),
                    token_efficiency=s.get("token_efficiency", 0),
                    total_turns=s.get("total_turns", 0),
                    total_tokens=s.get("total_tokens", 0),
                    model=s.get("model", ""),
                    unverified_steps=s.get("unverified_steps", 0),
                    rollback_count=s.get("rollback_count", 0),
                    repair_success_count=s.get("repair_success_count", 0),
                ))
        except Exception as e:
            log.debug("Failed to load reliability data: %s", e)
            self._sessions = []
