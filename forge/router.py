"""Multi-model router — use the right model for the right task.

Routes simple tasks to a fast small model (7B) and complex tasks to the
large model (32B/14B). Estimates task complexity from the user's input
and recent context to pick the optimal model.

This saves VRAM, reduces latency for simple operations, and lets
the big model focus on what it's best at: complex multi-file reasoning.

Complexity signals (higher = use big model):
  - Multi-file references ("change X and Y")
  - Architecture keywords ("refactor", "redesign", "migrate")
  - Long input (>200 words)
  - Multiple questions in one turn
  - References to previous complex context
  - Explicit "think hard" / "careful" cues

Simplicity signals (higher = use small model):
  - Single-file operations ("fix the typo in X")
  - Quick questions ("what does this function do")
  - Short input (<50 words)
  - Formatting/style tasks
  - Simple lookups and searches
"""

import re
import logging
from typing import Optional

log = logging.getLogger(__name__)


# ── Complexity scoring ──

# Patterns that suggest complex reasoning
COMPLEX_PATTERNS = [
    (r"\b(?:refactor|redesign|rewrite|migrate|restructure|architect)\b", 3),
    (r"\b(?:and also|then also|additionally|furthermore)\b", 2),
    (r"\b(?:compare|contrast|trade-?off|pros?\s+(?:and|&)\s+cons?)\b", 2),
    (r"\b(?:optimize|performance|benchmark|profile)\b", 2),
    (r"\b(?:security|vulnerability|audit|review)\b", 2),
    (r"\b(?:debug|investigate|diagnose|root cause)\b", 2),
    (r"\b(?:implement|build|create|develop)\s+(?:a|an|the)\s+\w+\s+\w+", 2),
    (r"\b(?:think (?:hard|carefully)|be (?:careful|thorough))\b", 3),
    (r"\b(?:all|every|each|entire)\s+(?:file|module|class|function)\b", 2),
    (r"\bmulti(?:-|\s)?(?:file|module|step)\b", 3),
]

# Patterns that suggest simple tasks
SIMPLE_PATTERNS = [
    (r"\b(?:fix|correct)\s+(?:the|a|this)\s+(?:typo|spelling|indent)", -3),
    (r"\b(?:what (?:does|is)|explain|show me|tell me about)\b", -2),
    (r"\b(?:rename|move|delete|remove)\s+(?:the|a|this)\s+\w+\b", -1),
    (r"\b(?:add|insert)\s+(?:a|an)\s+(?:comment|docstring|import|print)\b", -2),
    (r"\b(?:format|lint|style|indent)\b", -2),
    (r"\b(?:run|execute|test)\s+(?:the|this|it)\b", -1),
    (r"\b(?:list|show|display|print)\s+(?:the|all)\b", -1),
    (r"^\s*(?:yes|no|ok|sure|thanks|done)\s*$", -5),
]

_COMPILED_COMPLEX = [(re.compile(p, re.IGNORECASE), w) for p, w in COMPLEX_PATTERNS]
_COMPILED_SIMPLE = [(re.compile(p, re.IGNORECASE), w) for p, w in SIMPLE_PATTERNS]


def estimate_complexity(user_input: str, context_entries: int = 0,
                        active_files: int = 0) -> dict:
    """Estimate the complexity of a user request.

    Returns:
        dict with:
          score: int (negative = simple, positive = complex)
          level: str ("simple", "moderate", "complex")
          reason: str (why this complexity was assigned)
    """
    score = 0
    reasons = []

    # Word count signal
    words = len(user_input.split())
    if words > 200:
        score += 3
        reasons.append(f"long input ({words} words)")
    elif words > 80:
        score += 1
    elif words < 20:
        score -= 1
        reasons.append("short input")
    if words < 5:
        score -= 2
        reasons.append("very short input")

    # Pattern matching
    for pattern, weight in _COMPILED_COMPLEX:
        if pattern.search(user_input):
            score += weight
            if abs(weight) >= 2:
                reasons.append(f"'{pattern.pattern[:30]}' match")

    for pattern, weight in _COMPILED_SIMPLE:
        if pattern.search(user_input):
            score += weight  # weight is already negative
            if abs(weight) >= 2:
                reasons.append(f"simple pattern match")

    # Multi-file references (count file extensions or path-like patterns)
    file_refs = len(re.findall(r'\b\w+\.(?:py|js|ts|go|rs|java|c|cpp|rb|php)\b',
                               user_input))
    if file_refs >= 3:
        score += 3
        reasons.append(f"{file_refs} file references")
    elif file_refs >= 2:
        score += 1

    # Question count (multiple questions = complex)
    questions = user_input.count("?")
    if questions >= 3:
        score += 2
        reasons.append(f"{questions} questions")

    # Context signals
    if context_entries > 30:
        score += 1
    if active_files > 5:
        score += 1

    # Classify
    if score <= -2:
        level = "simple"
    elif score <= 2:
        level = "moderate"
    else:
        level = "complex"

    return {
        "score": score,
        "level": level,
        "reason": ", ".join(reasons[:3]) if reasons else "balanced signals",
    }


class ModelRouter:
    """Routes tasks to the appropriate model based on complexity."""

    def __init__(self, big_model: str = "", small_model: str = "",
                 enabled: bool = False):
        """
        Args:
            big_model: The large/capable model for complex tasks.
            small_model: The fast/small model for simple tasks.
            enabled: Whether routing is active. When disabled, always
                     uses the big model (default Forge behavior).
        """
        self.big_model = big_model
        self.small_model = small_model
        self.enabled = enabled

        # Stats
        self.big_routes = 0
        self.small_routes = 0
        self._route_log: list[dict] = []

    def route(self, user_input: str, context_entries: int = 0,
              active_files: int = 0, model_quality: float = 1.0) -> str:
        """Decide which model to use for this input.

        Args:
            model_quality: AMI average quality (0-1). When low, prefer
                           small model for simple/moderate tasks since the
                           big model is struggling.

        Returns the model name to use.
        """
        if not self.enabled or not self.small_model:
            return self.big_model

        est = estimate_complexity(user_input, context_entries, active_files)

        # Quality-aware routing: if big model quality is degraded,
        # prefer small model for non-complex tasks
        if model_quality < 0.5 and est["level"] != "complex":
            model = self.small_model
            self.small_routes += 1
            est["reason"] += ", big model quality degraded"
        elif est["level"] == "simple":
            model = self.small_model
            self.small_routes += 1
        else:
            model = self.big_model
            self.big_routes += 1

        self._route_log.append({
            "input_preview": user_input[:60],
            "score": est["score"],
            "level": est["level"],
            "model": model,
            "reason": est["reason"],
        })

        # Keep log bounded
        if len(self._route_log) > 100:
            self._route_log = self._route_log[-50:]

        return model

    def format_status(self) -> str:
        """Format router status for terminal display."""
        from forge.ui.terminal import (
            BOLD, RESET, DIM, GREEN, YELLOW, CYAN, WHITE
        )

        status = "ACTIVE" if self.enabled else "DISABLED"
        sc = GREEN if self.enabled else DIM

        lines = [
            f"\n{BOLD}Model Router{RESET}",
            f"  Status:  {sc}{status}{RESET}",
            f"  Big:     {self.big_model or '(not set)'}",
            f"  Small:   {self.small_model or '(not set)'}",
            f"  Routes:  {self.big_routes} big, {self.small_routes} small",
        ]

        if self._route_log:
            total = self.big_routes + self.small_routes
            pct_small = (self.small_routes / max(1, total)) * 100
            lines.append(f"  Savings: {pct_small:.0f}% of turns used small model")

            lines.append(f"\n  {BOLD}Recent Routing:{RESET}")
            for entry in self._route_log[-5:]:
                model_tag = (f"{GREEN}fast{RESET}" if "small" in entry["level"]
                            else f"{CYAN}big{RESET}")
                lines.append(
                    f"    [{entry['score']:+d}] {model_tag} "
                    f"{DIM}{entry['input_preview'][:40]}...{RESET}")

        lines.append(f"\n  {DIM}Enable: /router on{RESET}")
        lines.append(f"  {DIM}Set models: /router big <model> | small <model>{RESET}")

        return "\n".join(lines)
