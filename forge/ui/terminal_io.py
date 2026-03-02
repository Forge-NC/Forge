"""Terminal I/O abstraction layer — decouples ForgeEngine from stdout.

TerminalIO defines the display surface that the engine writes to.
ConsoleTerminalIO wraps the existing terminal.py functions (zero change).
GuiTerminalIO (in gui_terminal.py) redirects everything to CTk widgets.

Usage in engine.py:
    from forge.ui.terminal_io import ConsoleTerminalIO
    engine = ForgeEngine(terminal_io=ConsoleTerminalIO())
    # engine.io.print_info("hello")
"""

import sys
import logging
from abc import ABC, abstractmethod
from typing import Optional

log = logging.getLogger(__name__)


class TerminalIO(ABC):
    """Abstract I/O surface between ForgeEngine and its display."""

    # ── Startup / Init ──

    @abstractmethod
    def init_readline(self, config_dir: str = None) -> None:
        """Initialize command history and tab completion."""

    @abstractmethod
    def setup_completer(self, slash_commands: list) -> None:
        """Register slash commands for tab completion."""

    @abstractmethod
    def enable_ansi(self) -> None:
        """Enable ANSI escape codes (Windows console only)."""

    # ── Banner / Status ──

    @abstractmethod
    def print_banner(self) -> None:
        """Print the startup banner."""

    @abstractmethod
    def print_context_bar(self, ctx_status: dict) -> None:
        """Print the context usage status bar."""

    # ── Messages ──

    @abstractmethod
    def print_info(self, msg: str) -> None:
        """Print an informational message (cyan)."""

    @abstractmethod
    def print_warning(self, msg: str) -> None:
        """Print a warning message (yellow)."""

    @abstractmethod
    def print_error(self, msg: str) -> None:
        """Print an error message (red)."""

    # ── Tool execution ──

    @abstractmethod
    def print_tool_call(self, name: str, args: dict) -> None:
        """Print a tool invocation header."""

    @abstractmethod
    def print_tool_result(self, result: str,
                          max_lines: int = 30) -> None:
        """Print a tool result (possibly truncated)."""

    @abstractmethod
    def print_tool_error(self, result: str,
                         max_lines: int = 15) -> None:
        """Print a tool error result."""

    # ── LLM output ──

    @abstractmethod
    def print_assistant(self, text: str) -> None:
        """Print the assistant's final response text."""

    @abstractmethod
    def print_streaming_token(self, token: str) -> None:
        """Print a single streaming token (no newline)."""

    @abstractmethod
    def print_stats(self, eval_count: int, prompt_tokens: int,
                    duration_ns: int = 0) -> None:
        """Print generation statistics."""

    # ── Interrupts ──

    @abstractmethod
    def print_interrupt_banner(self, word_count: int = 0,
                               entries_added: int = 0,
                               modified_files: list = None,
                               created_files: list = None) -> None:
        """Print the escape-interrupt summary banner."""

    # ── Help / Detail ──

    @abstractmethod
    def print_help(self) -> None:
        """Print the full help text."""

    @abstractmethod
    def print_context_detail(self, entries: list) -> None:
        """Print detailed context entries as a table."""

    # ── Input ──

    @abstractmethod
    def prompt_user(self, cwd: str) -> str:
        """Show prompt and block for user input.

        Returns the user's text, or raises EOFError / KeyboardInterrupt.
        """

    # ── Raw output ──

    def print_raw(self, text: str) -> None:
        """Write raw text to the output surface.

        Default: sys.stdout.  Override for GUI capture.
        """
        sys.stdout.write(text)
        sys.stdout.flush()

    # ── State (optional) ──

    def set_state(self, state: str) -> None:
        """Notify display of engine state change.

        *state* is one of: idle, thinking, tool_exec, indexing,
        swapping, error, threat.

        Default: no-op.  GUI uses this for spinner / status bar.
        Console uses this for animated spinner when ansi_effects_enabled.
        """


# ──────────────────────────────────────────────────────────────────
# Console implementation — wraps existing terminal.py functions
# ──────────────────────────────────────────────────────────────────

class ConsoleTerminalIO(TerminalIO):
    """Default console I/O — delegates to forge.ui.terminal functions.

    This is the zero-change path: every method simply calls the
    corresponding function in terminal.py.  Existing behavior is
    preserved exactly.
    """

    def init_readline(self, config_dir=None):
        from forge.ui.terminal import init_readline
        init_readline(config_dir)

    def setup_completer(self, slash_commands):
        from forge.ui.terminal import setup_completer
        setup_completer(slash_commands)

    def enable_ansi(self):
        from forge.ui.terminal import enable_ansi_windows
        enable_ansi_windows()

    def print_banner(self):
        from forge.ui.terminal import print_banner
        print_banner()

    def print_context_bar(self, ctx_status):
        from forge.ui.terminal import print_context_bar
        print_context_bar(ctx_status)

    def print_info(self, msg):
        from forge.ui.terminal import print_info
        print_info(msg)

    def print_warning(self, msg):
        from forge.ui.terminal import print_warning
        print_warning(msg)

    def print_error(self, msg):
        from forge.ui.terminal import print_error
        print_error(msg)

    def print_tool_call(self, name, args):
        from forge.ui.terminal import print_tool_call
        print_tool_call(name, args)

    def print_tool_result(self, result, max_lines=30):
        from forge.ui.terminal import print_tool_result
        print_tool_result(result, max_lines)

    def print_tool_error(self, result, max_lines=15):
        from forge.ui.terminal import print_tool_error
        print_tool_error(result, max_lines)

    def print_assistant(self, text):
        from forge.ui.terminal import print_assistant
        print_assistant(text)

    def print_streaming_token(self, token):
        from forge.ui.terminal import print_streaming_token
        print_streaming_token(token)

    def print_stats(self, eval_count, prompt_tokens, duration_ns=0):
        from forge.ui.terminal import print_stats
        print_stats(eval_count, prompt_tokens, duration_ns)

    def print_interrupt_banner(self, word_count=0, entries_added=0,
                               modified_files=None,
                               created_files=None):
        from forge.ui.terminal import print_interrupt_banner
        print_interrupt_banner(word_count, entries_added,
                               modified_files, created_files)

    def print_help(self):
        from forge.ui.terminal import print_help
        print_help()

    def print_context_detail(self, entries):
        from forge.ui.terminal import print_context_detail
        print_context_detail(entries)

    def prompt_user(self, cwd):
        from forge.ui.terminal import prompt_user
        return prompt_user(cwd)

    def set_state(self, state: str) -> None:
        """Start/stop animated spinner on state changes.

        Only active when ansi_effects_enabled is True in config.
        """
        try:
            from forge.config import ForgeConfig
            if not ForgeConfig().get("ansi_effects_enabled", False):
                return
        except Exception:
            return

        from forge.ui.terminal import _spinner

        spinner_states = {
            "thinking": "Thinking...",
            "tool_exec": "Executing tool...",
            "indexing": "Indexing...",
            "swapping": "Swapping context...",
        }

        if state in spinner_states:
            _spinner.start(spinner_states[state])
        else:
            _spinner.stop()
