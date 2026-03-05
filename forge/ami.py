"""Adaptive Model Intelligence — self-healing agent orchestration.

Sits between the engine's agent loop and the LLM to detect failures,
force compliance, and recover gracefully. Think of it as a supervisor
for an unreliable worker — it watches output quality in real-time and
intervenes when the model refuses to act, loops, or ignores its tools.

Key capabilities:
  - Real-time response quality scoring (refusal, repetition, stasis)
  - 3-tier retry engine (parse fix → constrained decoding → context reset)
  - Model capability probing (detect native tool support, JSON format, etc.)
  - Adaptive prompt modification based on learned failure patterns
  - Failure catalog that learns which recovery methods work per model
  - KV cache optimization for sustained VRAM performance

Uses Ollama's `format` parameter for constrained decoding — forces the
model to output valid tool-call JSON via GBNF grammar enforcement.
"""

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Callable

from forge.quality import ResponseQualityScorer, ResponseQuality

log = logging.getLogger(__name__)


# ── Dataclasses ──

@dataclass
class TurnOutcome:
    """Record of a completed turn for trend analysis."""
    timestamp: float = 0.0
    model: str = ""
    tool_calls_expected: bool = False
    tool_calls_made: int = 0
    quality_score: float = 1.0
    retries_used: int = 0
    recovery_method: str = "none"


@dataclass
class FailurePattern:
    """A learned failure mode for a specific model."""
    pattern_type: str = ""       # "refusal", "no_tools", "repetition"
    trigger_context: str = ""    # What kind of prompt triggers this
    count: int = 0
    last_seen: float = 0.0
    effective_fix: str = ""      # Which recovery method worked


@dataclass
class ModelCapabilities:
    """Detected capabilities of a model (learned, not hardcoded)."""
    model_name: str = ""
    supports_native_tools: bool = False
    supports_json_format: bool = True   # Assume true until proven otherwise
    supports_text_tool_calls: bool = False
    avg_tool_compliance: float = 0.5
    preferred_tool_format: str = "json_format"
    detected_at: float = 0.0


@dataclass
class AMIStats:
    """Session-level AMI statistics."""
    total_turns: int = 0
    retries_triggered: int = 0
    retries_succeeded: int = 0
    tier1_attempts: int = 0
    tier1_successes: int = 0
    tier2_attempts: int = 0
    tier2_successes: int = 0
    tier3_attempts: int = 0
    tier3_successes: int = 0
    total_quality_sum: float = 0.0
    worst_quality: float = 1.0
    best_quality: float = 0.0


class AdaptiveModelIntelligence:
    """Self-healing model orchestration — detect failures, force compliance.

    Integrates into the engine's agent loop to monitor LLM output quality
    and automatically recover from common failure modes like refusals,
    repetition loops, and tool non-compliance.
    """

    # Quality thresholds
    REFUSAL_THRESHOLD = 0.6
    REPETITION_THRESHOLD = 0.25
    STASIS_THRESHOLD = 3
    MIN_USEFUL_LENGTH = 20

    # Retry budget
    MAX_RETRIES_PER_TURN = 3
    RETRY_TEMP_BUMP = 0.15

    def __init__(self, config_get: Callable, tools_registry=None,
                 llm_backend=None, data_dir: Path = None):
        self._config_get = config_get
        self._tools = tools_registry
        self._llm = llm_backend
        self._data_dir = data_dir or (Path.home() / ".forge")

        # State
        self._failure_catalog: dict[str, FailurePattern] = {}
        self._turn_history: list[TurnOutcome] = []
        self._retry_count: int = 0
        self._model_caps: dict[str, ModelCapabilities] = {}
        self._stats = AMIStats()
        self._recent_responses: list[str] = []  # Last 5 for repetition check
        self._last_user_input: str = ""
        self._scorer = ResponseQualityScorer()

        # Load persisted state
        self._load_state()

    # ── Quality Assessment ──

    def assess_quality(self, response: str, tool_calls: list,
                       user_input: str) -> ResponseQuality:
        """Assess quality of an LLM response in real-time.

        Called after each LLM response, before tool execution.
        Returns a ResponseQuality with composite score and sub-scores.
        """
        has_tools = self._tools is not None and bool(self._tools.list_tools())

        quality = self._scorer.assess(
            response=response,
            tool_calls=tool_calls,
            user_input=user_input,
            recent_responses=self._recent_responses,
            has_tools=has_tools,
        )

        # Update recent responses for repetition tracking
        if response and len(response.strip()) > 10:
            self._recent_responses.append(response)
            if len(self._recent_responses) > 5:
                self._recent_responses = self._recent_responses[-5:]

        self._last_user_input = user_input
        return quality

    def should_retry(self, quality: ResponseQuality) -> Optional[str]:
        """Decide whether to retry based on quality score.

        Returns None (accept), or retry method string.
        """
        max_retries = self._config_get("ami_max_retries", self.MAX_RETRIES_PER_TURN)
        threshold = self._config_get("ami_quality_threshold", 0.7)

        if quality.score >= threshold:
            return None

        if self._retry_count >= max_retries:
            log.info("AMI: retry budget exhausted (%d/%d), accepting low quality %.2f",
                     self._retry_count, max_retries, quality.score)
            return None

        # Route to appropriate recovery tier
        if quality.refusal_score > self.REFUSAL_THRESHOLD:
            return "retry_constrained"
        if quality.tool_compliance < 0.3:
            return "retry_constrained"
        if quality.repetition_score > self.REPETITION_THRESHOLD:
            return "retry_reset"
        if quality.progress_score < 0.2 and len(self._turn_history) >= self.STASIS_THRESHOLD:
            recent_progress = [h.quality_score for h in self._turn_history[-3:]]
            if all(p < 0.5 for p in recent_progress):
                return "retry_reset"

        return "retry_parse"

    # ── Retry Engine ──

    def execute_retry(self, method: str, user_input: str,
                      context=None, llm=None) -> Optional[dict]:
        """Execute a recovery attempt using the specified method.

        Returns dict with 'tool_calls' and 'response' if successful,
        or None if recovery failed.
        """
        self._retry_count += 1
        llm = llm or self._llm
        if llm is None:
            return None

        log.info("AMI: executing %s (attempt %d)", method, self._retry_count)

        if method == "retry_parse":
            return self._retry_parse(user_input, context, llm)
        elif method == "retry_constrained":
            return self._retry_constrained(user_input, context, llm)
        elif method == "retry_reset":
            return self._retry_reset(user_input, context, llm)
        else:
            log.warning("AMI: unknown retry method: %s", method)
            return None

    def _retry_parse(self, user_input: str, context, llm) -> Optional[dict]:
        """Tier 1: Inject nudge asking model to use tools."""
        self._stats.tier1_attempts += 1

        nudge = (
            "[System] You have tools available for file operations. "
            "Use them directly instead of printing code. "
            "Call read_file, edit_file, write_file, run_shell, etc. "
            "Do NOT tell the user to run scripts manually — you can do it yourself.\n\n"
            "Example tool call format:\n"
            '{"name": "read_file", "arguments": {"file_path": "path/to/file.py"}}\n'
            '{"name": "edit_file", "arguments": {"file_path": "path/to/file.py", '
            '"old_string": "old text", "new_string": "new text"}}'
        )

        messages = self._build_retry_messages(context, nudge, user_input)
        result = self._call_llm(llm, messages, temperature=0.1)

        if result and result.get("tool_calls"):
            self._stats.tier1_successes += 1
            self._record_fix("no_tools", "retry_parse")
        return result

    def _retry_constrained(self, user_input: str, context, llm) -> Optional[dict]:
        """Tier 2: Force tool-call JSON via constrained decoding."""
        self._stats.tier2_attempts += 1

        if not self._config_get("ami_constrained_fallback", True):
            return self._retry_parse(user_input, context, llm)

        schema = self.build_tool_call_schema()
        if not schema:
            return self._retry_parse(user_input, context, llm)

        # Build focused prompt for constrained mode
        instruction = (
            "Based on the user's request, select the most appropriate tool "
            "and respond with a single JSON tool call. "
            "Available tools: " +
            ", ".join(self._get_tool_names()) + ". "
            "User request: " + user_input
        )

        messages = self._build_retry_messages(context, instruction, user_input,
                                               strip_bad_responses=True)
        temp = 0.1 + self.RETRY_TEMP_BUMP * self._retry_count
        result = self._call_llm(llm, messages, temperature=temp, format_schema=schema)

        if result:
            # Parse constrained output as tool call
            tool_calls = self._parse_constrained_output(result.get("response", ""))
            if tool_calls:
                result["tool_calls"] = tool_calls
                self._stats.tier2_successes += 1
                self._record_fix("refusal", "retry_constrained")
                return result

        return result

    def _retry_reset(self, user_input: str, context, llm) -> Optional[dict]:
        """Tier 3: Context reset — fresh start with few-shot examples."""
        self._stats.tier3_attempts += 1

        # Build minimal context: system prompt + few-shot + user request
        system_msg = None
        if context:
            messages = context.get_messages() if hasattr(context, 'get_messages') else context
            for msg in messages:
                if msg.get("role") == "system":
                    system_msg = msg["content"]
                    break

        few_shot = self._get_few_shot_examples()
        fresh_messages = []

        if system_msg:
            fresh_messages.append({"role": "system", "content": system_msg})

        # Add few-shot examples
        for example in few_shot:
            fresh_messages.append({"role": "user", "content": example["user"]})
            fresh_messages.append({"role": "assistant", "content": example["assistant"]})

        # Add the actual user request with explicit instruction
        fresh_messages.append({
            "role": "user",
            "content": (
                f"{user_input}\n\n"
                "[Reminder: You HAVE tools. Use them. "
                "Do NOT describe what to do — DO it.]"
            ),
        })

        temp = 0.1 + self.RETRY_TEMP_BUMP * 2
        result = self._call_llm(llm, fresh_messages, temperature=temp)

        if result and result.get("tool_calls"):
            self._stats.tier3_successes += 1
            self._record_fix("repetition", "retry_reset")
        return result

    def _call_llm(self, llm, messages: list, temperature: float = 0.1,
                  format_schema: dict = None) -> Optional[dict]:
        """Call LLM and collect response + tool calls."""
        try:
            kwargs = {
                "messages": messages,
                "temperature": temperature,
                "stream": False,
            }
            if format_schema:
                kwargs["format"] = format_schema
            else:
                # Only send tools if not using format constraint
                if self._tools:
                    kwargs["tools"] = self._tools.get_ollama_tools()

            full_response = ""
            tool_calls = []

            for chunk in llm.chat(**kwargs):
                if chunk["type"] == "token":
                    full_response += chunk["content"]
                elif chunk["type"] == "tool_call":
                    tool_calls.append(chunk["tool_call"])
                elif chunk["type"] == "error":
                    log.warning("AMI retry LLM error: %s", chunk["content"])
                    return None

            # Try text parsing if no structured tool calls
            if not tool_calls and full_response and self._tools:
                tool_calls = self._parse_text_tool_calls(full_response)

            return {
                "response": full_response,
                "tool_calls": tool_calls,
            }

        except Exception as e:
            log.warning("AMI retry failed: %s", e)
            return None

    def _parse_text_tool_calls(self, text: str) -> list:
        """Parse tool calls from model text output (mirrors engine logic)."""
        tool_names = set(self._get_tool_names())
        if not tool_names:
            return []

        calls = []
        cleaned = re.sub(r'```(?:json)?\s*', '', text)
        cleaned = re.sub(r'```', '', cleaned)

        depth = 0
        start = -1
        candidates = []
        for i, ch in enumerate(cleaned):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start >= 0:
                    candidates.append(cleaned[start:i + 1])
                    start = -1

        for candidate in candidates:
            try:
                obj = json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                continue
            name = obj.get("name", "")
            args = obj.get("arguments", None)
            if name in tool_names and isinstance(args, dict):
                calls.append({"function": {"name": name, "arguments": args}})

        return calls

    def _parse_constrained_output(self, text: str) -> list:
        """Parse tool calls from constrained decoding output."""
        if not text:
            return []

        text = text.strip()
        try:
            obj = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return self._parse_text_tool_calls(text)

        tool_names = set(self._get_tool_names())
        name = obj.get("name", "")
        args = obj.get("arguments", None)

        if name in tool_names and isinstance(args, dict):
            return [{"function": {"name": name, "arguments": args}}]

        return []

    def _build_retry_messages(self, context, nudge: str, user_input: str,
                               strip_bad_responses: bool = False) -> list:
        """Build message list for retry attempt."""
        messages = []

        if context and hasattr(context, 'get_messages'):
            src = context.get_messages()
        elif context and isinstance(context, list):
            src = context
        else:
            src = []

        for msg in src:
            if strip_bad_responses and msg.get("role") == "assistant":
                continue
            messages.append(msg)

        # Add nudge as system message
        messages.append({"role": "system", "content": nudge})

        # Re-add user input if stripped
        if strip_bad_responses:
            messages.append({"role": "user", "content": user_input})

        return messages

    def _get_few_shot_examples(self) -> list:
        """Return few-shot examples of correct tool usage."""
        return [
            {
                "user": "Read the file config.py",
                "assistant": '{"name": "read_file", "arguments": '
                             '{"file_path": "config.py"}}',
            },
            {
                "user": "Fix the typo in main.py — change 'teh' to 'the'",
                "assistant": '{"name": "edit_file", "arguments": '
                             '{"file_path": "main.py", '
                             '"old_string": "teh", '
                             '"new_string": "the"}}',
            },
            {
                "user": "Run the tests",
                "assistant": '{"name": "run_shell", "arguments": '
                             '{"command": "python -m pytest tests/ -x -q"}}',
            },
        ]

    # ── Model Capability Probing ──

    def probe_model_capabilities(self, model_name: str,
                                  force: bool = False) -> ModelCapabilities:
        """Probe a model's tool-calling capabilities.

        Sends 3 test prompts to detect what works. Results are cached.
        """
        if not force and model_name in self._model_caps:
            return self._model_caps[model_name]

        caps = ModelCapabilities(
            model_name=model_name,
            detected_at=time.time(),
        )

        if self._llm is None:
            self._model_caps[model_name] = caps
            return caps

        log.info("AMI: probing capabilities for %s", model_name)

        # Test 1: Native tool calling
        caps.supports_native_tools = self._probe_native_tools(model_name)

        # Test 2: JSON format constraint
        caps.supports_json_format = self._probe_json_format(model_name)

        # Test 3: Text-based tool calls
        caps.supports_text_tool_calls = self._probe_text_tools(model_name)

        # Determine preferred format
        if caps.supports_native_tools:
            caps.preferred_tool_format = "native"
        elif caps.supports_json_format:
            caps.preferred_tool_format = "json_format"
        elif caps.supports_text_tool_calls:
            caps.preferred_tool_format = "text_json"
        else:
            caps.preferred_tool_format = "text_json"  # Best effort

        self._model_caps[model_name] = caps
        self._save_state()

        log.info("AMI: %s capabilities: native=%s, json=%s, text=%s, preferred=%s",
                 model_name, caps.supports_native_tools,
                 caps.supports_json_format, caps.supports_text_tool_calls,
                 caps.preferred_tool_format)

        return caps

    def _probe_native_tools(self, model_name: str) -> bool:
        """Test if model supports Ollama's structured tool_calls."""
        try:
            test_tools = [{
                "type": "function",
                "function": {
                    "name": "test_tool",
                    "description": "A test tool that reads a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path"},
                        },
                        "required": ["path"],
                    },
                },
            }]
            messages = [
                {"role": "system", "content": "You are a helpful assistant with tools."},
                {"role": "user", "content": "Read the file config.py using the test_tool"},
            ]

            for chunk in self._llm.chat(messages, tools=test_tools, stream=False):
                if chunk["type"] == "tool_call":
                    return True
            return False
        except Exception:
            return False

    def _probe_json_format(self, model_name: str) -> bool:
        """Test if model supports Ollama's format parameter."""
        try:
            schema = {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "value": {"type": "integer"},
                },
                "required": ["name", "value"],
            }
            messages = [
                {"role": "user",
                 "content": "Return a JSON object with name='test' and value=42"},
            ]

            full = ""
            for chunk in self._llm.chat(messages, stream=False, format=schema):
                if chunk["type"] == "token":
                    full += chunk["content"]

            if full:
                obj = json.loads(full.strip())
                return "name" in obj and "value" in obj
            return False
        except Exception:
            return False

    def _probe_text_tools(self, model_name: str) -> bool:
        """Test if model outputs parseable JSON tool calls in text."""
        try:
            messages = [
                {"role": "system",
                 "content": "When asked to use a tool, respond with JSON: "
                            '{"name": "tool_name", "arguments": {...}}'},
                {"role": "user",
                 "content": 'Call the read_file tool with path "test.py". '
                            "Respond only with the JSON tool call."},
            ]

            full = ""
            for chunk in self._llm.chat(messages, stream=False):
                if chunk["type"] == "token":
                    full += chunk["content"]

            if full:
                calls = self._parse_text_tool_calls(full)
                return len(calls) > 0
            return False
        except Exception:
            return False

    # ── Adaptive Prompting ──

    def adapt_prompt(self, system_prompt: str, model_name: str) -> str:
        """Modify system prompt based on learned model capabilities."""
        caps = self._model_caps.get(model_name)
        if not caps:
            return system_prompt

        additions = []

        if not caps.supports_native_tools:
            additions.append(
                "\n## Tool Call Format\n"
                "This model does not support structured tool calls. "
                "When you need to use a tool, output a JSON object:\n"
                '{"name": "tool_name", "arguments": {"param": "value"}}\n\n'
                "Available tools: " + ", ".join(self._get_tool_names()) + "\n"
                "ALWAYS use tools for file operations. NEVER tell the user "
                "to run scripts manually — you can do it yourself."
            )

        # Check failure catalog for this model's common issues
        refusal_count = sum(
            1 for fp in self._failure_catalog.values()
            if fp.pattern_type == "refusal" and fp.count >= 3
        )
        if refusal_count > 0:
            additions.append(
                "\nIMPORTANT: You HAVE tools that can read, write, and edit files. "
                "You CAN execute shell commands. You are NOT a text-only assistant. "
                "Do NOT refuse to make changes. Do NOT tell the user to do it manually."
            )

        if additions:
            return system_prompt + "\n".join(additions)
        return system_prompt

    # ── Tool Call Schema ──

    def build_tool_call_schema(self) -> Optional[dict]:
        """Build JSON schema for constrained tool-call output."""
        tool_names = self._get_tool_names()
        if not tool_names:
            return None

        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "enum": tool_names,
                },
                "arguments": {
                    "type": "object",
                },
            },
            "required": ["name", "arguments"],
        }

    # ── Outcome Tracking ──

    def record_outcome(self, outcome: TurnOutcome):
        """Record turn outcome for trend analysis and learning."""
        self._turn_history.append(outcome)
        if len(self._turn_history) > 50:
            self._turn_history = self._turn_history[-50:]

        self._stats.total_turns += 1
        self._stats.total_quality_sum += outcome.quality_score
        self._stats.worst_quality = min(self._stats.worst_quality,
                                         outcome.quality_score)
        self._stats.best_quality = max(self._stats.best_quality,
                                        outcome.quality_score)

        if outcome.retries_used > 0:
            self._stats.retries_triggered += 1
            if outcome.quality_score >= 0.5:
                self._stats.retries_succeeded += 1

        # Learn failure pattern
        if outcome.recovery_method != "none" and outcome.quality_score < 0.5:
            key = f"{outcome.model}:{outcome.recovery_method}"
            if key not in self._failure_catalog:
                self._failure_catalog[key] = FailurePattern(
                    pattern_type=outcome.recovery_method.replace("retry_", ""),
                    count=0,
                )
            self._failure_catalog[key].count += 1
            self._failure_catalog[key].last_seen = outcome.timestamp

        self._save_state()

    def _record_fix(self, failure_type: str, fix_method: str):
        """Record that a specific fix worked for a failure type."""
        key = f"{failure_type}:{fix_method}"
        if key not in self._failure_catalog:
            self._failure_catalog[key] = FailurePattern(
                pattern_type=failure_type,
                effective_fix=fix_method,
                count=0,
            )
        fp = self._failure_catalog[key]
        fp.count += 1
        fp.last_seen = time.time()
        fp.effective_fix = fix_method

    def reset_turn(self):
        """Reset per-turn state. Call at start of each user turn."""
        self._retry_count = 0

    # ── Status & Analytics ──

    def get_average_quality(self) -> float:
        """Get average quality score from recent turns."""
        if not self._turn_history:
            return 1.0
        recent = self._turn_history[-10:]
        return sum(t.quality_score for t in recent) / len(recent)

    def get_quality_for_model(self, model: str) -> float:
        """Get average quality score for a specific model."""
        model_turns = [t for t in self._turn_history if t.model == model]
        if not model_turns:
            return 1.0
        recent = model_turns[-10:]
        return sum(t.quality_score for t in recent) / len(recent)

    def get_status(self) -> dict:
        """Return AMI system status."""
        model = self._llm.model if self._llm else "unknown"
        caps = self._model_caps.get(model, ModelCapabilities())

        avg_quality = self.get_average_quality()
        recovery_rate = (
            self._stats.retries_succeeded / max(1, self._stats.retries_triggered)
        )

        return {
            "enabled": self._config_get("ami_enabled", True),
            "model": model,
            "capabilities": {
                "native_tools": caps.supports_native_tools,
                "json_format": caps.supports_json_format,
                "text_tool_calls": caps.supports_text_tool_calls,
                "preferred_format": caps.preferred_tool_format,
            },
            "quality": {
                "average": round(avg_quality, 3),
                "worst": round(self._stats.worst_quality, 3),
                "best": round(self._stats.best_quality, 3),
            },
            "retries": {
                "total": self._stats.retries_triggered,
                "succeeded": self._stats.retries_succeeded,
                "recovery_rate": round(recovery_rate, 3),
                "tier1": {"attempts": self._stats.tier1_attempts,
                          "successes": self._stats.tier1_successes},
                "tier2": {"attempts": self._stats.tier2_attempts,
                          "successes": self._stats.tier2_successes},
                "tier3": {"attempts": self._stats.tier3_attempts,
                          "successes": self._stats.tier3_successes},
            },
            "failure_catalog": {
                k: {"type": v.pattern_type, "count": v.count,
                     "fix": v.effective_fix}
                for k, v in self._failure_catalog.items()
            },
            "turns_tracked": len(self._turn_history),
        }

    def format_status(self) -> str:
        """Format AMI status for terminal display."""
        from forge.ui.terminal import BOLD, RESET, DIM, GREEN, YELLOW, RED, CYAN

        status = self.get_status()
        enabled = status["enabled"]
        sc = GREEN if enabled else DIM

        lines = [
            f"\n{BOLD}Adaptive Model Intelligence{RESET}",
            f"  Status:     {sc}{'ACTIVE' if enabled else 'DISABLED'}{RESET}",
            f"  Model:      {status['model']}",
        ]

        # Capabilities
        caps = status["capabilities"]
        lines.append(f"  {BOLD}Capabilities:{RESET}")
        native_c = GREEN if caps["native_tools"] else RED
        json_c = GREEN if caps["json_format"] else RED
        text_c = GREEN if caps["text_tool_calls"] else YELLOW
        lines.append(f"    Native tools:  {native_c}"
                     f"{'YES' if caps['native_tools'] else 'NO'}{RESET}")
        lines.append(f"    JSON format:   {json_c}"
                     f"{'YES' if caps['json_format'] else 'NO'}{RESET}")
        lines.append(f"    Text parsing:  {text_c}"
                     f"{'YES' if caps['text_tool_calls'] else 'PARTIAL'}{RESET}")
        lines.append(f"    Preferred:     {CYAN}{caps['preferred_format']}{RESET}")

        # Quality
        q = status["quality"]
        if self._stats.total_turns > 0:
            qc = GREEN if q["average"] >= 0.7 else (YELLOW if q["average"] >= 0.4 else RED)
            lines.append(f"  {BOLD}Quality (last {len(self._turn_history)} turns):{RESET}")
            lines.append(f"    Average:    {qc}{q['average']:.2f}{RESET}")
            lines.append(f"    Best:       {q['best']:.2f}")
            lines.append(f"    Worst:      {q['worst']:.2f}")

        # Retries
        r = status["retries"]
        if r["total"] > 0:
            rc = GREEN if r["recovery_rate"] >= 0.7 else YELLOW
            lines.append(f"  {BOLD}Recovery:{RESET}")
            lines.append(f"    Retries:    {r['total']} triggered, "
                         f"{rc}{r['succeeded']} succeeded "
                         f"({r['recovery_rate']:.0%}){RESET}")
            lines.append(f"    Tier 1:     {r['tier1']['attempts']} attempts, "
                         f"{r['tier1']['successes']} success")
            lines.append(f"    Tier 2:     {r['tier2']['attempts']} attempts, "
                         f"{r['tier2']['successes']} success")
            lines.append(f"    Tier 3:     {r['tier3']['attempts']} attempts, "
                         f"{r['tier3']['successes']} success")

        # Failure catalog
        catalog = status["failure_catalog"]
        if catalog:
            lines.append(f"  {BOLD}Failure Catalog:{RESET}")
            for key, info in catalog.items():
                lines.append(f"    {info['type']:12s}  "
                             f"{info['count']}x  (fix: {info['fix'] or 'unknown'})")

        lines.append(f"\n  {DIM}Use /ami probe to re-detect capabilities{RESET}")
        lines.append(f"  {DIM}Use /ami reset to clear learned patterns{RESET}")

        return "\n".join(lines)

    def to_audit_dict(self) -> dict:
        """Serializable snapshot for audit export."""
        return {
            "schema_version": 1,
            "enabled": self._config_get("ami_enabled", True),
            "stats": asdict(self._stats),
            "model_capabilities": {
                k: asdict(v) for k, v in self._model_caps.items()
            },
            "failure_catalog": {
                k: asdict(v) for k, v in self._failure_catalog.items()
            },
            "turn_history_count": len(self._turn_history),
            "average_quality": self.get_average_quality(),
        }

    def reset(self):
        """Clear all learned patterns and state."""
        self._failure_catalog.clear()
        self._turn_history.clear()
        self._model_caps.clear()
        self._stats = AMIStats()
        self._recent_responses.clear()
        self._retry_count = 0
        self._save_state()

    # ── Helpers ──

    def _get_tool_names(self) -> list:
        """Get list of registered tool names."""
        if self._tools and hasattr(self._tools, 'list_tools'):
            return list(self._tools.list_tools())
        return []

    # ── Persistence ──

    def _save_state(self):
        """Persist failure catalog and model capabilities."""
        state_path = self._data_dir / "ami_state.json"
        try:
            state = {
                "failure_catalog": {
                    k: asdict(v) for k, v in self._failure_catalog.items()
                },
                "model_capabilities": {
                    k: asdict(v) for k, v in self._model_caps.items()
                },
            }
            tmp = state_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
            tmp.replace(state_path)
        except Exception as e:
            log.debug("AMI: failed to save state: %s", e)

    def _load_state(self):
        """Load persisted failure catalog and model capabilities."""
        state_path = self._data_dir / "ami_state.json"
        if not state_path.exists():
            return

        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))

            for k, v in data.get("failure_catalog", {}).items():
                self._failure_catalog[k] = FailurePattern(**v)

            for k, v in data.get("model_capabilities", {}).items():
                self._model_caps[k] = ModelCapabilities(**v)

            log.debug("AMI: loaded %d failure patterns, %d model caps",
                      len(self._failure_catalog), len(self._model_caps))
        except Exception as e:
            log.debug("AMI: failed to load state: %s", e)


# ── KV Cache Optimization ──

def optimize_kv_cache():
    """Set Ollama environment variables for optimal VRAM usage.

    Must be called before Ollama processes its first request.
    Returns list of changes made.
    """
    changes = []

    if not os.environ.get("OLLAMA_FLASH_ATTENTION"):
        os.environ["OLLAMA_FLASH_ATTENTION"] = "1"
        changes.append("Flash Attention enabled")
        log.info("AMI: enabled Flash Attention (OLLAMA_FLASH_ATTENTION=1)")

    if not os.environ.get("OLLAMA_KV_CACHE_TYPE"):
        os.environ["OLLAMA_KV_CACHE_TYPE"] = "q8_0"
        changes.append("KV cache quantized to Q8_0")
        log.info("AMI: set KV cache quantization (OLLAMA_KV_CACHE_TYPE=q8_0)")

    return changes
