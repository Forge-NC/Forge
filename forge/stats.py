"""Forge analytics — session history, performance trends, tool analytics.

Tracks everything across sessions so you can see how your coding workflow
evolves over time: throughput, context efficiency, tool usage, cost savings.
"""

import json
import time
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from forge.ui.terminal import (
    BOLD, CYAN, DIM, GRAY, GREEN, MAGENTA, RED, RESET, WHITE, YELLOW,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SessionRecord:
    """Snapshot of a completed session."""
    session_id: str
    start_time: float
    end_time: float
    duration_s: float
    turns: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cache_tokens_saved: int
    context_swaps: int
    tool_calls: int
    files_touched: int
    journal_entries: int
    peak_context_pct: float
    avg_tok_per_sec: float
    model: str


@dataclass
class PerfSample:
    """Single LLM call performance measurement."""
    timestamp: float
    prompt_tokens: int
    eval_tokens: int
    duration_s: float
    tok_per_sec: float
    iteration: int       # which iteration of the agent loop
    model: str


# ---------------------------------------------------------------------------
# StatsCollector
# ---------------------------------------------------------------------------

class StatsCollector:
    """Collects, persists, and analyzes Forge usage statistics."""

    def __init__(self, persist_dir: Path):
        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)

        self._sessions_file = self._persist_dir / "sessions.json"
        self._perf_file = self._persist_dir / "perf_log.jsonl"

        # In-memory buffers
        self._perf_samples: list[PerfSample] = []
        self._session_tool_counts: dict[str, int] = {}
        self._peak_context_pct: float = 0.0

        # Load session history
        self._sessions: list[SessionRecord] = self._load_sessions()

    # ------------------------------------------------------------------
    # Recording API — called by engine during operation
    # ------------------------------------------------------------------

    def record_llm_call(
        self,
        prompt_tokens: int,
        eval_tokens: int,
        duration_ns: int,
        iteration: int = 1,
        model: str = "",
    ):
        """Record a single LLM call's performance."""
        duration_s = duration_ns / 1e9 if duration_ns > 0 else 0.001
        tok_s = eval_tokens / duration_s if duration_s > 0 else 0.0

        sample = PerfSample(
            timestamp=time.time(),
            prompt_tokens=prompt_tokens,
            eval_tokens=eval_tokens,
            duration_s=round(duration_s, 3),
            tok_per_sec=round(tok_s, 1),
            iteration=iteration,
            model=model,
        )
        self._perf_samples.append(sample)

        # Append to persistent log
        try:
            with open(self._perf_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(asdict(sample), ensure_ascii=False) + "\n")
        except OSError:
            pass

    def record_tool_call(self, tool_name: str):
        """Track tool usage frequency."""
        self._session_tool_counts[tool_name] = (
            self._session_tool_counts.get(tool_name, 0) + 1
        )

    def record_context_usage(self, usage_pct: float):
        """Track peak context usage for the session."""
        if usage_pct > self._peak_context_pct:
            self._peak_context_pct = usage_pct

    def record_session_end(
        self,
        session_id: str,
        start_time: float,
        turns: int,
        input_tokens: int,
        output_tokens: int,
        cache_saved: int,
        context_swaps: int,
        files_touched: int,
        journal_entries: int,
        model: str,
    ):
        """Save a session record when exiting."""
        now = time.time()
        duration = now - start_time

        # Compute average tok/s across all perf samples
        tok_s_values = [s.tok_per_sec for s in self._perf_samples if s.tok_per_sec > 0]
        avg_tok_s = sum(tok_s_values) / len(tok_s_values) if tok_s_values else 0.0

        record = SessionRecord(
            session_id=session_id,
            start_time=start_time,
            end_time=now,
            duration_s=round(duration, 1),
            turns=turns,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cache_tokens_saved=cache_saved,
            context_swaps=context_swaps,
            tool_calls=sum(self._session_tool_counts.values()),
            files_touched=files_touched,
            journal_entries=journal_entries,
            peak_context_pct=round(self._peak_context_pct, 1),
            avg_tok_per_sec=round(avg_tok_s, 1),
            model=model,
        )
        self._sessions.append(record)
        self._save_sessions()

    # ------------------------------------------------------------------
    # Analysis API — called by /stats command and GUI
    # ------------------------------------------------------------------

    def get_session_history(self, count: int = 20) -> list[dict]:
        """Return the last N session records as dicts."""
        return [asdict(s) for s in self._sessions[-count:]]

    def get_performance_trends(self, count: int = 50) -> dict:
        """Throughput trends from recent perf samples."""
        samples = self._perf_samples[-count:] if self._perf_samples else []

        # Also load historical samples if we don't have enough
        if len(samples) < count:
            historical = self._load_perf_samples(count)
            samples = historical + samples
            samples = samples[-count:]

        if not samples:
            return {"samples": 0, "avg_tok_s": 0, "min_tok_s": 0,
                    "max_tok_s": 0, "trend": "no data"}

        tok_s_values = [s.tok_per_sec for s in samples if s.tok_per_sec > 0]
        if not tok_s_values:
            return {"samples": len(samples), "avg_tok_s": 0, "min_tok_s": 0,
                    "max_tok_s": 0, "trend": "no data"}

        avg = sum(tok_s_values) / len(tok_s_values)
        # Trend: compare first half vs second half
        mid = len(tok_s_values) // 2
        if mid > 0:
            first_half = sum(tok_s_values[:mid]) / mid
            second_half = sum(tok_s_values[mid:]) / len(tok_s_values[mid:])
            if second_half > first_half * 1.05:
                trend = "improving"
            elif second_half < first_half * 0.95:
                trend = "degrading"
            else:
                trend = "stable"
        else:
            trend = "insufficient data"

        return {
            "samples": len(tok_s_values),
            "avg_tok_s": round(avg, 1),
            "min_tok_s": round(min(tok_s_values), 1),
            "max_tok_s": round(max(tok_s_values), 1),
            "trend": trend,
            "recent_5": [round(v, 1) for v in tok_s_values[-5:]],
        }

    def get_tool_analytics(self) -> dict:
        """Tool usage breakdown for current session."""
        total = sum(self._session_tool_counts.values())
        sorted_tools = sorted(
            self._session_tool_counts.items(),
            key=lambda x: -x[1],
        )
        return {
            "total_calls": total,
            "by_tool": dict(sorted_tools),
            "most_used": sorted_tools[0] if sorted_tools else ("none", 0),
        }

    def get_context_efficiency(self) -> dict:
        """Context window efficiency metrics."""
        total_sessions = len(self._sessions)
        if total_sessions == 0:
            return {
                "total_swaps": 0, "avg_swaps_per_session": 0,
                "peak_context_pct": self._peak_context_pct,
                "sessions_with_swaps": 0,
            }

        total_swaps = sum(s.context_swaps for s in self._sessions)
        sessions_with_swaps = sum(1 for s in self._sessions if s.context_swaps > 0)

        return {
            "total_swaps": total_swaps,
            "avg_swaps_per_session": round(total_swaps / total_sessions, 1),
            "peak_context_pct": self._peak_context_pct,
            "sessions_with_swaps": sessions_with_swaps,
            "total_sessions": total_sessions,
        }

    def get_cost_analysis(self) -> dict:
        """Cumulative cost savings across all sessions."""
        if not self._sessions:
            return {
                "total_tokens": 0, "total_sessions": 0,
                "opus_cost": 0, "sonnet_cost": 0,
                "forge_cost": 0, "total_saved_vs_opus": 0,
            }

        total_input = sum(s.input_tokens for s in self._sessions)
        total_output = sum(s.output_tokens for s in self._sessions)
        total_cached = sum(s.cache_tokens_saved for s in self._sessions)

        # Price per 1M tokens
        opus_in, opus_out = 15.0, 75.0
        sonnet_in, sonnet_out = 3.0, 15.0

        # Cloud providers would re-read cached files
        cloud_input = total_input + total_cached

        opus_cost = (cloud_input / 1e6 * opus_in) + (total_output / 1e6 * opus_out)
        sonnet_cost = (cloud_input / 1e6 * sonnet_in) + (total_output / 1e6 * sonnet_out)

        return {
            "total_tokens": total_input + total_output,
            "total_input": total_input,
            "total_output": total_output,
            "total_cached": total_cached,
            "total_sessions": len(self._sessions),
            "opus_cost": round(opus_cost, 4),
            "sonnet_cost": round(sonnet_cost, 4),
            "forge_cost": 0.0,
            "total_saved_vs_opus": round(opus_cost, 4),
            "total_saved_vs_sonnet": round(sonnet_cost, 4),
            "avg_tokens_per_session": round(
                (total_input + total_output) / len(self._sessions)),
        }

    def get_dashboard_data(self) -> dict:
        """All stats bundled for the GUI dashboard."""
        return {
            "performance": self.get_performance_trends(),
            "tools": self.get_tool_analytics(),
            "context": self.get_context_efficiency(),
            "cost": self.get_cost_analysis(),
            "sessions": self.get_session_history(count=10),
            "current_perf_samples": len(self._perf_samples),
            "peak_context_pct": self._peak_context_pct,
        }

    # ------------------------------------------------------------------
    # Terminal display
    # ------------------------------------------------------------------

    def to_audit_dict(self) -> dict:
        """Return a JSON-serializable audit snapshot.

        Stable API contract for the audit exporter.
        """
        return {
            "schema_version": 1,
            "perf_samples": [asdict(s) for s in self._perf_samples[-50:]],
            "tool_analytics": self.get_tool_analytics(),
            "context_efficiency": self.get_context_efficiency(),
        }

    def format_stats_display(self) -> str:
        """Format comprehensive stats for terminal output."""
        lines: list[str] = []

        # --- Performance ---
        perf = self.get_performance_trends()
        lines.append(f"\n{BOLD}Performance{RESET}")
        if perf["samples"] > 0:
            trend_color = (GREEN if perf["trend"] == "improving"
                          else RED if perf["trend"] == "degrading"
                          else CYAN)
            lines.append(f"  Avg throughput:  {GREEN}{perf['avg_tok_s']}{RESET} tok/s")
            lines.append(f"  Range:           {perf['min_tok_s']} - {perf['max_tok_s']} tok/s")
            lines.append(f"  Trend:           {trend_color}{perf['trend']}{RESET}")
            # ASCII sparkline for throughput
            tok_values = [s.tok_per_sec for s in self._perf_samples[-30:]
                          if s.tok_per_sec > 0]
            if len(tok_values) >= 3:
                try:
                    from forge.ui.charts import ChartRenderer
                    spark = ChartRenderer.ascii_sparkline(tok_values, width=30)
                    lines.append(f"  Throughput:      {DIM}{spark}{RESET}")
                except Exception:
                    pass
        else:
            lines.append(f"  {DIM}No performance data yet.{RESET}")

        # --- Tool Usage ---
        tools = self.get_tool_analytics()
        lines.append(f"\n{BOLD}Tool Usage (this session){RESET}")
        if tools["total_calls"] > 0:
            lines.append(f"  Total calls:     {tools['total_calls']}")
            for name, count in list(tools["by_tool"].items())[:8]:
                bar_len = int(count / max(tools["by_tool"].values()) * 20)
                bar = "=" * bar_len
                lines.append(f"  {CYAN}{name:18}{RESET} {bar} {count}")
        else:
            lines.append(f"  {DIM}No tool calls yet.{RESET}")

        # --- Context Efficiency ---
        ctx = self.get_context_efficiency()
        lines.append(f"\n{BOLD}Context Efficiency{RESET}")
        lines.append(f"  Peak usage:      {ctx['peak_context_pct']:.0f}%")
        lines.append(f"  Auto-swaps:      {ctx['total_swaps']} "
                     f"(across {ctx.get('total_sessions', 0)} sessions)")
        if ctx.get("total_sessions", 0) > 0:
            lines.append(f"  Avg swaps/sess:  {ctx['avg_swaps_per_session']}")

        # --- Cost Savings ---
        cost = self.get_cost_analysis()
        lines.append(f"\n{BOLD}Cumulative Cost Savings{RESET}")
        if cost["total_sessions"] > 0:
            lines.append(f"  Total tokens:    {cost['total_tokens']:,} "
                         f"across {cost['total_sessions']} sessions")
            lines.append(f"  Cache saved:     {cost['total_cached']:,} tokens")
            lines.append(f"  vs Claude Opus:  {GREEN}${cost['total_saved_vs_opus']:.4f} saved{RESET}")
            lines.append(f"  vs Claude Sonnet:{GREEN}${cost['total_saved_vs_sonnet']:.4f} saved{RESET}")
            lines.append(f"  Forge cost:      {GREEN}$0.00{RESET} (it's YOUR GPU)")
        else:
            lines.append(f"  {DIM}No completed sessions yet. Stats appear after first exit.{RESET}")

        # --- Session History ---
        sessions = self.get_session_history(count=5)
        if sessions:
            lines.append(f"\n{BOLD}Recent Sessions{RESET}")
            lines.append(f"  {'#':>3}  {'Duration':>8}  {'Turns':>5}  "
                         f"{'Tokens':>9}  {'tok/s':>6}  {'Swaps':>5}  Model")
            lines.append(f"  {DIM}{'-' * 65}{RESET}")
            for i, s in enumerate(reversed(sessions), 1):
                dur_m = s["duration_s"] / 60
                lines.append(
                    f"  {i:>3}  {dur_m:>7.1f}m  {s['turns']:>5}  "
                    f"{s['total_tokens']:>9,}  {s['avg_tok_per_sec']:>5.1f}  "
                    f"{s['context_swaps']:>5}  {DIM}{s['model']}{RESET}"
                )

        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_sessions(self):
        """Persist session records."""
        try:
            data = [asdict(s) for s in self._sessions]
            self._sessions_file.write_text(
                json.dumps(data, indent=2), encoding="utf-8")
        except OSError as e:
            log.warning("Failed to save session stats: %s", e)

    def _load_sessions(self) -> list[SessionRecord]:
        """Load session records from disk."""
        if not self._sessions_file.exists():
            return []
        try:
            data = json.loads(self._sessions_file.read_text(encoding="utf-8"))
            records = []
            for d in data:
                records.append(SessionRecord(
                    session_id=d.get("session_id", ""),
                    start_time=d.get("start_time", 0),
                    end_time=d.get("end_time", 0),
                    duration_s=d.get("duration_s", 0),
                    turns=d.get("turns", 0),
                    input_tokens=d.get("input_tokens", 0),
                    output_tokens=d.get("output_tokens", 0),
                    total_tokens=d.get("total_tokens", 0),
                    cache_tokens_saved=d.get("cache_tokens_saved", 0),
                    context_swaps=d.get("context_swaps", 0),
                    tool_calls=d.get("tool_calls", 0),
                    files_touched=d.get("files_touched", 0),
                    journal_entries=d.get("journal_entries", 0),
                    peak_context_pct=d.get("peak_context_pct", 0),
                    avg_tok_per_sec=d.get("avg_tok_per_sec", 0),
                    model=d.get("model", ""),
                ))
            return records
        except (OSError, json.JSONDecodeError) as e:
            log.warning("Failed to load session stats: %s", e)
            return []

    def _load_perf_samples(self, count: int = 50) -> list[PerfSample]:
        """Load recent perf samples from JSONL log."""
        samples: list[PerfSample] = []
        if not self._perf_file.exists():
            return samples
        try:
            lines = self._perf_file.read_text(encoding="utf-8").strip().split("\n")
            for line in lines[-count:]:
                if not line.strip():
                    continue
                d = json.loads(line)
                samples.append(PerfSample(
                    timestamp=d.get("timestamp", 0),
                    prompt_tokens=d.get("prompt_tokens", 0),
                    eval_tokens=d.get("eval_tokens", 0),
                    duration_s=d.get("duration_s", 0),
                    tok_per_sec=d.get("tok_per_sec", 0),
                    iteration=d.get("iteration", 0),
                    model=d.get("model", ""),
                ))
        except (OSError, json.JSONDecodeError) as e:
            log.debug("Failed to load perf log: %s", e)
        return samples
