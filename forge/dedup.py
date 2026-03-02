"""Tool call deduplication — detects near-duplicate tool calls.

Prevents the model from calling the same tool with nearly identical
arguments multiple times in a row (e.g., writing the same note 5x).

Uses difflib.SequenceMatcher for content similarity scoring.
Threshold is configurable (default 0.92 = 92% similar).
"""

import json
import logging
from collections import deque
from difflib import SequenceMatcher
from typing import Optional

log = logging.getLogger(__name__)


class ToolDedup:
    """Detects and suppresses near-duplicate tool calls.

    Keeps a sliding window of recent tool calls per tool name.
    When a new call is made, compares its arguments against
    recent calls to the same tool. If similarity exceeds the
    threshold, the call is flagged as a duplicate.

    Cross-turn awareness: ``soft_reset()`` preserves previous-turn
    history and checks against it at a stricter threshold (0.98)
    to catch the model repeating the exact same actions across turns.

    Attributes:
        threshold: Similarity ratio (0.0 to 1.0) above which calls
                   are considered duplicates. Default 0.92.
        cross_turn_threshold: Higher threshold for cross-turn checks.
                              Default 0.98 (near-exact matches only).
        window_size: Number of recent calls to compare against
                     per tool name. Default 5.
        enabled: Whether dedup checking is active.
    """

    def __init__(self, threshold: float = 0.92,
                 window_size: int = 5,
                 enabled: bool = True):
        self.threshold = max(0.0, min(1.0, threshold))
        self.cross_turn_threshold = 0.98
        self.window_size = max(1, window_size)
        self.enabled = enabled

        # Per-tool sliding window of recent arg strings (current turn)
        self._recent: dict[str, deque[str]] = {}

        # Previous turn's tool calls — checked at stricter threshold
        self._prev_turn: dict[str, list[str]] = {}

        # Stats
        self.total_checked = 0
        self.total_suppressed = 0

    def check(self, tool_name: str, tool_args: dict) -> Optional[dict]:
        """Check if this tool call is a near-duplicate of a recent one.

        Args:
            tool_name: Name of the tool being called.
            tool_args: Arguments dict for the tool call.

        Returns:
            None if the call is unique (proceed with execution).
            A dict with dedup info if it's a duplicate:
                {"duplicate": True, "similarity": float,
                 "matched_against": str, "tool": str}
        """
        if not self.enabled:
            return None

        self.total_checked += 1

        # Serialize args to string for comparison
        try:
            arg_str = json.dumps(tool_args, sort_keys=True,
                                 ensure_ascii=False)
        except (TypeError, ValueError):
            arg_str = str(tool_args)

        # Get or create the window for this tool
        if tool_name not in self._recent:
            self._recent[tool_name] = deque(maxlen=self.window_size)

        window = self._recent[tool_name]

        # Compare against recent calls (current turn)
        best_ratio = 0.0
        best_match = ""
        for recent_str in window:
            ratio = self._similarity(arg_str, recent_str)
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = recent_str

        # Record this call in the window regardless
        window.append(arg_str)

        if best_ratio >= self.threshold:
            self.total_suppressed += 1
            log.debug(
                "Dedup: %s suppressed (%.1f%% similar to recent call)",
                tool_name, best_ratio * 100)
            return {
                "duplicate": True,
                "similarity": round(best_ratio, 4),
                "matched_against": best_match[:200],
                "tool": tool_name,
            }

        # Cross-turn check: compare against previous turn at stricter
        # threshold to catch the model repeating exact same work
        if tool_name in self._prev_turn:
            for prev_str in self._prev_turn[tool_name]:
                ratio = self._similarity(arg_str, prev_str)
                if ratio >= self.cross_turn_threshold:
                    self.total_suppressed += 1
                    log.debug(
                        "Dedup: %s cross-turn suppressed "
                        "(%.1f%% similar to previous turn)",
                        tool_name, ratio * 100)
                    return {
                        "duplicate": True,
                        "similarity": round(ratio, 4),
                        "matched_against": prev_str[:200],
                        "tool": tool_name,
                        "cross_turn": True,
                    }

        return None

    def soft_reset(self):
        """Partial reset for new turn — preserve previous-turn history.

        Moves current-turn entries to the previous-turn buffer so
        cross-turn duplicate detection still works.  The previous-turn
        buffer is replaced each time (only 1 turn of history kept).
        """
        self._prev_turn = {
            name: list(window) for name, window in self._recent.items()
        }
        self._recent.clear()

    def reset(self):
        """Full reset — clear all history including cross-turn data."""
        self._recent.clear()
        self._prev_turn.clear()

    def _similarity(self, a: str, b: str) -> float:
        """Compute similarity ratio between two strings.

        Uses SequenceMatcher which is O(n*m) but works well for
        the typical size of tool arguments (< 2KB).  For very large
        strings, falls back to a quick length + prefix check.
        """
        # Quick exit for identical strings
        if a == b:
            return 1.0

        # Quick exit for very different lengths
        len_a, len_b = len(a), len(b)
        if len_a == 0 or len_b == 0:
            return 0.0

        ratio = min(len_a, len_b) / max(len_a, len_b)
        if ratio < 0.5:
            # Strings are very different lengths — can't be similar enough
            return ratio

        # For very long strings, use a sampled comparison
        if len_a > 5000 or len_b > 5000:
            return self._sampled_similarity(a, b)

        return SequenceMatcher(None, a, b).ratio()

    def _sampled_similarity(self, a: str, b: str) -> float:
        """Quick similarity for very long strings.

        Compares prefix, suffix, and middle samples.
        """
        sample_size = 500

        # Compare first N chars
        prefix_ratio = SequenceMatcher(
            None, a[:sample_size], b[:sample_size]).ratio()

        # Compare last N chars
        suffix_ratio = SequenceMatcher(
            None, a[-sample_size:], b[-sample_size:]).ratio()

        # Compare middle
        mid_a = len(a) // 2
        mid_b = len(b) // 2
        half = sample_size // 2
        mid_ratio = SequenceMatcher(
            None,
            a[mid_a - half:mid_a + half],
            b[mid_b - half:mid_b + half],
        ).ratio()

        # Weighted average: prefix and suffix matter more
        return (prefix_ratio * 0.35 + mid_ratio * 0.30 +
                suffix_ratio * 0.35)

    def stats(self) -> dict:
        """Return dedup statistics."""
        return {
            "enabled": self.enabled,
            "threshold": self.threshold,
            "window_size": self.window_size,
            "total_checked": self.total_checked,
            "total_suppressed": self.total_suppressed,
            "suppression_rate": (
                round(self.total_suppressed / self.total_checked * 100, 1)
                if self.total_checked > 0 else 0.0
            ),
        }

    def format_status(self) -> str:
        """Format dedup status for display."""
        s = self.stats()
        lines = [
            f"  Dedup: {'ON' if s['enabled'] else 'OFF'}",
            f"  Threshold: {s['threshold']:.0%} similarity",
            f"  Window: {s['window_size']} recent calls per tool",
        ]
        if s["total_checked"] > 0:
            lines.append(
                f"  Checked: {s['total_checked']} | "
                f"Suppressed: {s['total_suppressed']} "
                f"({s['suppression_rate']:.1f}%)")
        return "\n".join(lines)
