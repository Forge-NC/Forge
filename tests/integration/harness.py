"""StressHarness — drives ForgeEngine non-interactively for stress tests.

Creates a fully isolated engine instance (temp dirs, stub Ollama, headless IO)
and exposes methods to drive individual turns or full conversations.
"""

import os
import logging
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from tests.integration.headless_io import HeadlessTerminalIO
from tests.integration.ollama_stub import OllamaStub

log = logging.getLogger(__name__)


@dataclass
class TurnResult:
    """Result of a single engine turn."""
    response: str = ""
    tool_calls: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    context_usage_pct: float = 0.0
    context_total_tokens: int = 0
    context_entry_count: int = 0
    eval_count: int = 0
    prompt_tokens: int = 0


class StressHarness:
    """Orchestrates ForgeEngine creation and turn-by-turn execution."""

    def __init__(self, stub: OllamaStub, tmp_path: Path,
                 live: bool = False, live_model: str = "qwen2.5-coder:14b"):
        self.stub = stub
        self.tmp_path = tmp_path
        self.live = live
        self.live_model = live_model
        self.io = HeadlessTerminalIO()
        self.engine = None
        self._forge_dir: Optional[Path] = None

    def create_engine(self, model: str = None,
                      ctx_max_tokens: int = 4000) -> 'ForgeEngine':
        """Create a fully wired ForgeEngine.

        In stub mode: points at OllamaStub.
        In live mode: points at real Ollama at localhost:11434.

        Returns the engine instance. Also stored as self.engine.
        """
        # Resolve model name
        if model is None:
            model = self.live_model if self.live else "stub-coder:14b"

        # Determine target URL
        target_url = ("http://localhost:11434" if self.live
                      else self.stub.base_url)

        # Create isolated .forge directory structure
        self._forge_dir = self.tmp_path / ".forge"
        self._forge_dir.mkdir(parents=True, exist_ok=True)
        (self._forge_dir / "plugins").mkdir(exist_ok=True)
        (self._forge_dir / "journal").mkdir(exist_ok=True)
        (self._forge_dir / "forensics").mkdir(exist_ok=True)
        (self._forge_dir / "digest").mkdir(exist_ok=True)

        # Write minimal config
        config = {
            "default_model": model,
            "ollama_url": target_url,
            "safety_level": 1,
            "sandbox_enabled": False,
            "router_enabled": False,
            "dedup_enabled": True,
            "dedup_threshold": 0.92,
            "continuity_enabled": True,
            "continuity_threshold": 60,
            "plan_mode": "off",
            "plan_verify_mode": "off",
            "max_agent_iterations": 15,
            "context_safety_margin": 1.0,  # No margin in tests
            "ansi_effects_enabled": False,
        }
        config_path = self._forge_dir / "config.yaml"
        config_path.write_text(yaml.dump(config), encoding="utf-8")

        # Import engine here to avoid circular imports at module level
        from forge.engine import ForgeEngine

        # Create engine with headless IO
        engine = ForgeEngine(
            model=model,
            cwd=str(self.tmp_path),
            terminal_io=self.io,
        )

        # Override key attributes to point at target
        engine.llm.base_url = target_url
        engine.ctx.max_tokens = ctx_max_tokens

        # Disable components that require real infrastructure
        engine._escape_monitor = _NoOpEscapeMonitor()
        engine._dashboard = None
        engine._voice = None
        engine._tts = None

        # Point forensics at temp dir
        engine.forensics._persist_dir = self._forge_dir / "forensics"

        # Point billing at temp dir
        engine.billing._persist_path = self._forge_dir / "billing.json"

        self.engine = engine
        return engine

    def run_single_turn(self, user_input: str) -> TurnResult:
        """Drive one full LLM+tool cycle and return results.

        1. Add user message to context
        2. Reset dedup for new turn
        3. Run _agent_loop()
        4. Capture results
        """
        if self.engine is None:
            raise RuntimeError("Call create_engine() first")

        result = TurnResult()

        # Capture errors from IO
        error_count_before = len(self.io.get_output("error"))

        # Run plugin user_input hook
        try:
            user_input = self.engine.plugin_manager.dispatch_user_input(user_input)
        except Exception:
            pass

        # Add user message to context
        self.engine.ctx.add("user", user_input)
        self.engine.dedup.soft_reset()

        # Run one agent loop cycle
        try:
            self.engine._agent_loop()
        except Exception as exc:
            result.errors.append(str(exc))
            log.warning("Agent loop raised: %s", exc)

        # Trigger auto context swap (normally called in run() loop)
        try:
            self.engine._auto_context_swap()
        except Exception as exc:
            log.debug("Auto context swap failed: %s", exc)

        # Capture results
        new_errors = self.io.get_output("error")[error_count_before:]
        result.errors.extend(new_errors)
        result.context_usage_pct = self.engine.ctx.usage_pct
        result.context_total_tokens = self.engine.ctx.total_tokens
        result.context_entry_count = self.engine.ctx.entry_count

        # Extract response text from token output
        tokens = self.io.get_output("token")
        if tokens:
            # Tokens after error_count_before's position in the full log
            result.response = "".join(tokens[-50:])  # Last batch of tokens

        return result

    def run_conversation(self, inputs: list[str]) -> list[TurnResult]:
        """Run a sequence of turns and return all results."""
        results = []
        for user_input in inputs:
            result = self.run_single_turn(user_input)
            results.append(result)
        return results

    def get_swap_count(self) -> int:
        """Count how many context swaps have occurred."""
        entries = self.engine.ctx._entries
        return sum(1 for e in entries if e.tag == "swap_summary")

    def get_continuity_grade(self) -> str:
        """Get current continuity letter grade."""
        if not self.engine.continuity.enabled:
            return "N/A"
        task_state = self.engine.memory.get_task_state()
        snapshot = self.engine.continuity.score(
            self.engine.ctx._entries, task_state)
        from forge.continuity import score_to_grade
        return score_to_grade(snapshot.score)


class _NoOpEscapeMonitor:
    """Escape monitor that never fires."""
    interrupted = False

    def start(self): pass
    def stop(self): pass
    def reset(self): pass
