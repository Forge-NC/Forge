"""Response quality scoring — stateless analysis of LLM output quality.

Detects five failure modes in real-time:
  1. Refusal: model claims it can't do things it CAN do
  2. Repetition: model repeats itself (4-gram Jaccard overlap)
  3. Stasis: model makes no progress toward the goal
  4. Tool non-compliance: model prints code instead of calling tools
  5. Verbosity: model talks too much, does too little

All functions are static/pure — no state, no side effects, easy to test.
Used by AdaptiveModelIntelligence (forge/ami.py) for quality assessment.
"""

import re
import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


# ── Refusal patterns ──

# Critical: model claims it CANNOT do things it CAN do
REFUSAL_CRITICAL = [
    (r"(?:I |i )(?:cannot|can't|don't have|am unable to)\s+(?:directly\s+)?"
     r"(?:modify|edit|change|write|create|access|make changes to)\s+files?", 0.9),
    (r"as (?:a |an )?(?:text-based |language )?(?:AI|model|assistant)", 0.7),
    (r"(?:I |i )(?:cannot|can't)\s+(?:directly\s+)?"
     r"(?:make changes|execute|run|access)", 0.8),
    (r"beyond my (?:capabilities|ability|scope)", 0.7),
    (r"(?:I |i )don't have (?:direct )?access to (?:your|the) "
     r"(?:file ?system|computer|machine)", 0.9),
    (r"(?:I |i )(?:cannot|can't) (?:directly )?interact with "
     r"(?:your|the) (?:system|files?|environment)", 0.85),
]

# Moderate: delegation instead of action
REFUSAL_MODERATE = [
    (r"(?:you (?:can|should|need to|will need to)|please)\s+"
     r"(?:manually|yourself|run|save|copy|open|navigate)", 0.5),
    (r"(?:open a terminal|command prompt|your (?:IDE|editor))", 0.4),
    (r"(?:save (?:the|this) (?:script|code|file)|"
     r"run (?:the|this) (?:script|following|code))", 0.5),
    (r"replace .{0,30} with your (?:actual|own|real)", 0.6),
    (r"(?:copy (?:and )?paste|paste (?:the|this))", 0.4),
    (r"here(?:'s| is) (?:the|a) (?:script|code|snippet) "
     r"(?:you can|to) (?:run|use|execute)", 0.5),
]

# Soft: hedging instead of acting
REFUSAL_SOFT = [
    (r"(?:I )?(?:apologize|sorry) (?:for |but )", 0.2),
    (r"(?:if you (?:need|want|would like)|feel free to ask)", 0.15),
    (r"(?:I can (?:guide|help|assist) you (?:through|with))", 0.3),
    (r"(?:let me know if|would you like me to)", 0.1),
]

_COMPILED_CRITICAL = [(re.compile(p, re.I), w) for p, w in REFUSAL_CRITICAL]
_COMPILED_MODERATE = [(re.compile(p, re.I), w) for p, w in REFUSAL_MODERATE]
_COMPILED_SOFT = [(re.compile(p, re.I), w) for p, w in REFUSAL_SOFT]

# Tool-trigger patterns: user input that implies tool usage is needed
TOOL_TRIGGER_PATTERNS = [
    (re.compile(r"(?:read|open|look at|check|view|show me)\s+"
                r"(?:the |this |that )?\w*\s*(?:file|code|source|contents?)", re.I),
     "read_file"),
    (re.compile(r"(?:edit|modify|change|update|fix|patch|correct)\s+"
                r"(?:the |this |that |in )?\w*\s*"
                r"(?:file|code|line|function|class|method)", re.I),
     "edit_file"),
    (re.compile(r"(?:write|create|make|generate|add)\s+"
                r"(?:a |the |this |new )?\w*\s*"
                r"(?:file|script|module|class|function)", re.I),
     "write_file"),
    (re.compile(r"(?:run|execute|test|build|compile|install|pip|npm)", re.I),
     "run_shell"),
    (re.compile(r"(?:find|search|locate|grep|look for|where is)", re.I),
     "grep_files"),
]


@dataclass
class ResponseQuality:
    """Real-time quality assessment of a single LLM response."""
    score: float              # 0.0-1.0 composite quality
    refusal_score: float      # 0.0-1.0 (how much it's refusing to act)
    repetition_score: float   # 0.0-1.0 (4-gram overlap with recent responses)
    progress_score: float     # 0.0-1.0 (did it advance toward the goal?)
    tool_compliance: float    # 0.0-1.0 (did it call tools when it should have?)
    verbosity_ratio: float    # normalized 0-1 (lower = more efficient)
    issues: list = field(default_factory=list)
    recommended_action: str = "accept"


class ResponseQualityScorer:
    """Stateless response quality analysis.

    All methods are static — no instance state, purely functional.
    """

    @staticmethod
    def score_refusal(response: str, has_tools: bool = True) -> float:
        """Score how much the response is a refusal to act.

        Returns 0.0 (no refusal) to 1.0 (definite refusal).
        """
        if not response or len(response.strip()) < 10:
            return 0.0

        response_lower = response.lower()
        max_score = 0.0

        # Critical refusals — model claims it can't do things
        for pattern, weight in _COMPILED_CRITICAL:
            if pattern.search(response):
                # Weight more if refusal is in the first 200 chars
                position_boost = 1.2 if pattern.search(response[:200]) else 1.0
                score = min(1.0, weight * position_boost)
                max_score = max(max_score, score)

        # Moderate refusals — delegation
        moderate_hits = 0
        for pattern, weight in _COMPILED_MODERATE:
            if pattern.search(response):
                moderate_hits += 1
                max_score = max(max_score, weight)

        # Multiple moderate hits compound
        if moderate_hits >= 3:
            max_score = max(max_score, 0.7)
        elif moderate_hits >= 2:
            max_score = max(max_score, 0.55)

        # Soft refusals — hedging
        for pattern, weight in _COMPILED_SOFT:
            if pattern.search(response):
                # Soft patterns only matter if combined with other signals
                if max_score > 0.3:
                    max_score = min(1.0, max_score + weight * 0.5)

        # Context boost: if model has tools but claims it can't act,
        # that's maximally wrong
        if has_tools and max_score > 0.5:
            max_score = min(1.0, max_score * 1.15)

        return round(min(1.0, max_score), 3)

    @staticmethod
    def score_repetition(response: str, recent_responses: list,
                         n: int = 4) -> float:
        """Score inter-response repetition via 4-gram Jaccard similarity.

        Returns 0.0 (unique) to 1.0 (identical to a previous response).
        """
        if not response or not recent_responses:
            return 0.0

        def ngrams(text, size):
            words = text.lower().split()
            if len(words) < size:
                return set()
            return set(tuple(words[i:i + size])
                       for i in range(len(words) - size + 1))

        current = ngrams(response, n)
        if not current:
            return 0.0

        max_overlap = 0.0
        for prev in recent_responses[-3:]:
            if not prev:
                continue
            prev_ngrams = ngrams(prev, n)
            if not prev_ngrams:
                continue
            union = current | prev_ngrams
            if not union:
                continue
            jaccard = len(current & prev_ngrams) / len(union)
            max_overlap = max(max_overlap, jaccard)

        # Also check intra-response repetition (same block repeated)
        paragraphs = [p.strip() for p in response.split("\n\n") if p.strip()]
        if len(paragraphs) >= 4:
            para_ngrams = [ngrams(p, n) for p in paragraphs]
            for i in range(len(para_ngrams)):
                for j in range(i + 1, len(para_ngrams)):
                    if para_ngrams[i] and para_ngrams[j]:
                        union = para_ngrams[i] | para_ngrams[j]
                        if union:
                            sim = len(para_ngrams[i] & para_ngrams[j]) / len(union)
                            if sim > 0.6:  # Intra-response duplication
                                max_overlap = max(max_overlap, sim * 0.8)

        return round(min(1.0, max_overlap), 3)

    @staticmethod
    def score_progress(response: str, user_goal: str,
                       previous_responses: list) -> float:
        """Score whether the response advances toward the goal.

        Returns 0.0 (no progress) to 1.0 (clear advancement).
        """
        if not response:
            return 0.0

        score = 0.5  # Neutral baseline

        # Positive: new file paths mentioned (not in previous)
        file_pattern = re.compile(
            r'[A-Za-z_/\\][\w./\\-]*\.(?:py|js|ts|go|rs|java|c|cpp|rb|php|yaml|json|toml|md)',
        )
        current_paths = set(file_pattern.findall(response))
        prev_paths = set()
        for prev in previous_responses:
            prev_paths.update(file_pattern.findall(prev))
        new_paths = current_paths - prev_paths
        if new_paths:
            score += min(0.3, len(new_paths) * 0.1)

        # Positive: contains new code blocks
        code_blocks = re.findall(r'```\w*\n', response)
        if code_blocks:
            score += 0.1

        # Positive: completion signals
        completion_words = ["done", "completed", "finished", "created",
                            "updated", "fixed", "resolved", "applied"]
        for word in completion_words:
            if re.search(rf'\b{word}\b', response, re.I):
                score += 0.1
                break

        # Positive: tool call intent
        intent_patterns = [
            r"(?:let me|I'll|I will)\s+(?:read|edit|write|check|run|search)",
            r"(?:reading|editing|writing|checking|running|searching)",
        ]
        for p in intent_patterns:
            if re.search(p, response, re.I):
                score += 0.1
                break

        # Negative: rehashing — starts with same 20 words as previous
        if previous_responses:
            current_words = response.split()[:20]
            current_start = " ".join(current_words).lower()
            for prev in previous_responses[-3:]:
                prev_words = prev.split()[:20]
                prev_start = " ".join(prev_words).lower()
                if current_start and prev_start and current_start == prev_start:
                    score -= 0.3
                    break

        return round(max(0.0, min(1.0, score)), 3)

    @staticmethod
    def score_tool_compliance(response: str, tool_calls: list,
                              user_input: str,
                              has_tools: bool = True) -> float:
        """Score whether the model used tools when it should have.

        Returns 0.0 (should have used tools but didn't) to
                1.0 (appropriate tool usage or no tools needed).
        """
        if not has_tools:
            return 1.0  # No tools available, can't penalize

        # Determine if user's input implies tool usage
        should_have_tools = False
        for pattern, _tool_name in TOOL_TRIGGER_PATTERNS:
            if pattern.search(user_input):
                should_have_tools = True
                break

        if not should_have_tools:
            return 1.0  # User didn't ask for tool-like action

        # User expected tools — did model deliver?
        if tool_calls:
            return 1.0  # Model called tools — good

        # No tool calls. Check if model printed code instead
        has_inline_code = bool(
            re.search(r'```(?:python|bash|sh|json|javascript|typescript)', response))
        has_manual_instructions = bool(
            re.search(r'(?:save (?:the|this)|run (?:the|this|it)|'
                      r'open (?:a |your )|paste (?:the|this))',
                      response, re.I))

        if has_inline_code and has_manual_instructions:
            return 0.05  # Printed code AND told user to run it manually
        if has_inline_code:
            return 0.15  # Printed code instead of executing
        if has_manual_instructions:
            return 0.1   # Just gave manual instructions

        return 0.2  # No code, no tools — just talked

    @staticmethod
    def score_verbosity(response: str, tool_calls_count: int) -> float:
        """Score response verbosity (lower = more efficient).

        Returns 0.0 (perfectly concise) to 1.0 (excessively verbose).
        """
        if not response:
            return 0.0

        word_count = len(response.split())

        if tool_calls_count > 0:
            # With tool calls: ratio of words per action
            ratio = word_count / tool_calls_count
            # 0-30 words per tool call = good, 200+ = bad
            if ratio <= 30:
                return 0.0
            if ratio <= 80:
                return 0.2
            if ratio <= 150:
                return 0.5
            return min(1.0, ratio / 500)
        else:
            # No tool calls: penalize long responses more
            if word_count <= 50:
                return 0.1
            if word_count <= 150:
                return 0.3
            if word_count <= 400:
                return 0.6
            return min(1.0, 0.6 + (word_count - 400) / 1000)

    @classmethod
    def assess(cls, response: str, tool_calls: list,
               user_input: str, recent_responses: list = None,
               has_tools: bool = True) -> ResponseQuality:
        """Compute composite quality score with all sub-scores.

        This is the main entry point — call this for a full assessment.
        """
        if recent_responses is None:
            recent_responses = []

        refusal = cls.score_refusal(response, has_tools)
        repetition = cls.score_repetition(response, recent_responses)
        progress = cls.score_progress(response, user_input, recent_responses)
        compliance = cls.score_tool_compliance(
            response, tool_calls, user_input, has_tools)
        verbosity = cls.score_verbosity(response, len(tool_calls))

        # Composite score (higher = better quality)
        composite = (
            0.25 * (1.0 - refusal) +
            0.25 * (1.0 - repetition) +
            0.20 * progress +
            0.20 * compliance +
            0.10 * (1.0 - verbosity)
        )

        # Identify issues
        issues = []
        if refusal > 0.6:
            issues.append("refusal detected")
        if repetition > 0.25:
            issues.append("repeating itself")
        if progress < 0.3 and recent_responses:
            issues.append("no progress")
        if compliance < 0.3:
            issues.append("not using tools")
        if verbosity > 0.7:
            issues.append("too verbose")

        # Determine recommended action
        if composite >= 0.7:
            action = "accept"
        elif refusal > 0.6 or compliance < 0.3:
            action = "retry_constrained"
        elif repetition > 0.4:
            action = "retry_reset"
        else:
            action = "retry_parse"

        return ResponseQuality(
            score=round(composite, 3),
            refusal_score=refusal,
            repetition_score=repetition,
            progress_score=progress,
            tool_compliance=compliance,
            verbosity_ratio=verbosity,
            issues=issues,
            recommended_action=action,
        )
