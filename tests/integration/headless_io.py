"""HeadlessTerminalIO — queue-fed TerminalIO for non-interactive testing.

Implements every abstract method from forge.ui.terminal_io.TerminalIO.
Input comes from a pre-loaded queue; output is captured in a log
for later assertion.
"""

import queue
from typing import Optional

from forge.ui.terminal_io import TerminalIO


class HeadlessTerminalIO(TerminalIO):
    """Non-interactive TerminalIO that feeds from a queue and captures output."""

    def __init__(self):
        super().__init__()
        self._input_queue: queue.Queue[str] = queue.Queue()
        self._output_log: list[tuple[str, str]] = []  # (category, message)
        self._state: str = "idle"

    # ── Input helpers ──

    def queue_inputs(self, inputs: list[str]):
        """Bulk-enqueue user messages."""
        for text in inputs:
            self._input_queue.put(text)

    def queue_input(self, text: str):
        """Enqueue a single user message."""
        self._input_queue.put(text)

    def get_output(self, category: str = None) -> list[str]:
        """Return captured output messages, optionally filtered by category."""
        if category is None:
            return [msg for _, msg in self._output_log]
        return [msg for cat, msg in self._output_log if cat == category]

    def get_output_pairs(self) -> list[tuple[str, str]]:
        """Return raw (category, message) pairs."""
        return list(self._output_log)

    def clear_output(self):
        """Clear captured output."""
        self._output_log.clear()

    # ── Startup / Init (no-ops) ──

    def init_readline(self, config_dir: str = None) -> None:
        pass

    def setup_completer(self, slash_commands: list) -> None:
        pass

    def enable_ansi(self) -> None:
        pass

    # ── Banner / Status ──

    def print_banner(self) -> None:
        self._output_log.append(("banner", "Forge (headless)"))

    def print_context_bar(self, ctx_status: dict) -> None:
        self._output_log.append(("context_bar", str(ctx_status)))

    # ── Messages ──

    def print_info(self, msg: str) -> None:
        self._output_log.append(("info", msg))

    def print_warning(self, msg: str) -> None:
        self._output_log.append(("warning", msg))

    def print_error(self, msg: str) -> None:
        self._output_log.append(("error", msg))

    # ── Tool execution ──

    def print_tool_call(self, name: str, args: dict) -> None:
        self._output_log.append(("tool_call", f"{name}({args})"))

    def print_tool_result(self, result: str, max_lines: int = 30) -> None:
        self._output_log.append(("tool_result", result))

    def print_tool_error(self, result: str, max_lines: int = 15) -> None:
        self._output_log.append(("tool_error", result))

    # ── LLM output ──

    def print_assistant(self, text: str) -> None:
        self._output_log.append(("assistant", text))

    def print_streaming_token(self, token: str) -> None:
        self._output_log.append(("token", token))

    def print_stats(self, eval_count: int, prompt_tokens: int,
                    duration_ns: int = 0) -> None:
        self._output_log.append(("stats", f"eval={eval_count} prompt={prompt_tokens}"))

    # ── Interrupts ──

    def print_interrupt_banner(self, word_count: int = 0,
                               entries_added: int = 0,
                               modified_files: list = None,
                               created_files: list = None) -> None:
        self._output_log.append(("interrupt", f"words={word_count}"))

    # ── Help / Detail ──

    def print_help(self) -> None:
        self._output_log.append(("help", "help text"))

    def print_context_detail(self, entries: list) -> None:
        self._output_log.append(("context_detail", f"{len(entries)} entries"))

    # ── Input ──

    def prompt_user(self, cwd: str) -> str:
        """Pop from input queue. Raises EOFError when empty."""
        try:
            return self._input_queue.get_nowait()
        except queue.Empty:
            raise EOFError("Headless input queue exhausted")

    def prompt_yes_no(self, message: str, default: bool = True,
                      timeout: float = 0) -> bool:
        """Auto-accept with default in headless mode."""
        self._output_log.append(("prompt_yes_no", message))
        return default

    def prompt_choice(self, message: str, choices: list,
                      default: str = None) -> str:
        """Auto-pick default (or first choice) in headless mode."""
        self._output_log.append(("prompt_choice", message))
        return default or (choices[0][0] if choices else "")

    def prompt_text(self, message: str) -> str:
        """Return empty string in headless mode."""
        self._output_log.append(("prompt_text", message))
        return ""

    # ── Raw output ──

    def print_raw(self, text: str) -> None:
        self._output_log.append(("raw", text))

    # ── State ──

    def set_state(self, state: str) -> None:
        self._state = state
