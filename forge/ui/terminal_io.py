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
    """Abstract I/O surface between ForgeEngine and its display.

    All interactive prompts must go through this interface — never call
    input() directly from engine, safety, or crucible code.
    """

    def __init__(self):
        self._escape_monitor = None  # Set by engine if needed

    def set_escape_monitor(self, monitor) -> None:
        """Register escape monitor for input contention management.

        On Windows, the escape monitor uses msvcrt.getch() which steals
        keystrokes from input().  Prompt methods pause/resume the monitor
        to prevent this.
        """
        self._escape_monitor = monitor

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

    @abstractmethod
    def prompt_yes_no(self, message: str, default: bool = True,
                      timeout: float = 0) -> bool:
        """Prompt for yes/no confirmation.

        Args:
            message: The prompt text (plain text, no ANSI codes).
            default: Value returned on empty input or timeout.
            timeout: Auto-return default after this many seconds. 0 = block forever.
        """

    @abstractmethod
    def prompt_choice(self, message: str,
                      choices: list[tuple[str, str]],
                      default: str = None) -> str:
        """Prompt user to pick from a list of choices.

        Args:
            message: The prompt label (e.g. "Choice").
            choices: List of (key, label) tuples, e.g. [("a", "Approve"), ("r", "Reject")].
            default: Key returned on empty input. None = first choice.
        Returns:
            The selected key string.
        """

    @abstractmethod
    def prompt_text(self, message: str) -> str:
        """Prompt for free-form text input.

        Args:
            message: The prompt text.
        Returns:
            User's text (stripped), or "" on EOF/interrupt.
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

    def _with_monitor_paused(self, fn):
        """Run fn() with escape monitor paused to prevent keystroke stealing."""
        monitor = self._escape_monitor
        was_active = False
        if monitor:
            was_active = monitor._active.is_set()
            if was_active:
                monitor.stop()
        try:
            return fn()
        finally:
            if monitor and was_active:
                monitor.start()

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

    def prompt_yes_no(self, message, default=True, timeout=0):
        from forge.ui.terminal import YELLOW, RESET, BOLD, DIM

        if timeout > 0:
            action = "accept" if default else "deny"
            override = "n" if default else "y"
            sys.stdout.write(
                f"{YELLOW}{BOLD}[CONFIRM]{RESET} {message} "
                f"{DIM}(auto-{action} in {timeout:.0f}s, "
                f"'{override}' to {'skip' if default else 'confirm'})"
                f"{RESET} ")
            sys.stdout.flush()
            return self._prompt_yes_no_timeout(default, timeout)

        default_str = "Y/n" if default else "y/N"
        sys.stdout.write(
            f"\n{YELLOW}{BOLD}[APPROVE?]{RESET} {message} "
            f"{YELLOW}{default_str}:{RESET} ")
        sys.stdout.flush()

        def _do_input():
            try:
                return input().strip().lower()
            except (EOFError, KeyboardInterrupt, RuntimeError):
                return ""

        answer = self._with_monitor_paused(_do_input)
        if not answer:
            return default
        if default:
            return answer not in ("n", "no")
        return answer in ("y", "yes")

    def _prompt_yes_no_timeout(self, default, timeout):
        """Timed yes/no — auto-returns default after timeout seconds."""
        if sys.platform == "win32":
            import msvcrt
            import time as _time
            end = _time.time() + timeout
            while _time.time() < end:
                if msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    print()
                    if default:
                        return ch.lower() != "n"
                    return ch.lower() == "y"
                _time.sleep(0.05)
            print()
            return default
        else:
            import select
            try:
                rlist, _, _ = select.select([sys.stdin], [], [], timeout)
                if rlist:
                    ch = sys.stdin.readline().strip().lower()
                    if default:
                        return ch != "n"
                    return ch in ("y", "yes")
            except (ValueError, TypeError, OSError):
                # sys.stdin is None or closed
                pass
            print()
            return default

    def prompt_choice(self, message, choices, default=None):
        from forge.ui.terminal import YELLOW, RESET, BOLD

        if default is None and choices:
            default = choices[0][0]

        parts = []
        for key, label in choices:
            parts.append(
                f"{YELLOW}{BOLD}[{key.upper()}]{RESET}{label[len(key):]}")
        sys.stdout.write(f"  {'  '.join(parts)}\n")
        sys.stdout.write(f"  {YELLOW}{BOLD}{message}:{RESET} ")
        sys.stdout.flush()

        def _do_input():
            try:
                return input().strip().lower()
            except (EOFError, KeyboardInterrupt, RuntimeError):
                return ""

        answer = self._with_monitor_paused(_do_input)
        if not answer:
            return default
        for key, label in choices:
            if answer == key or answer == label.lower():
                return key
        return default

    def prompt_text(self, message):
        from forge.ui.terminal import CYAN, GREEN, BOLD, RESET

        if message:
            sys.stdout.write(f"  {CYAN}{message}{RESET}\n")
        sys.stdout.write(f"  {GREEN}{BOLD}>{RESET} ")
        sys.stdout.flush()

        def _do_input():
            try:
                return input().strip()
            except (EOFError, KeyboardInterrupt, RuntimeError):
                return ""

        return self._with_monitor_paused(_do_input)

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


# ──────────────────────────────────────────────────────────────────
# Headless implementation — non-interactive (CI, scripts, subprocess)
# ──────────────────────────────────────────────────────────────────

class HeadlessTerminalIO(TerminalIO):
    """Non-interactive IO — follows policy, never blocks for input.

    Use for CI pipelines, subprocesses, or any environment where
    stdin is unavailable or should not be read.

    Args:
        policy: "deny" (prompt_yes_no returns False), "allow" (returns True),
                or "default" (returns each prompt's default argument).
    """

    def __init__(self, policy: str = "default"):
        super().__init__()
        self._policy = policy
        self._log = logging.getLogger("forge.headless")

    # ── Startup / Init ──

    def init_readline(self, config_dir=None):
        pass

    def setup_completer(self, slash_commands):
        pass

    def enable_ansi(self):
        pass

    # ── Banner / Status ──

    def print_banner(self):
        pass

    def print_context_bar(self, ctx_status):
        pass

    # ── Messages ──

    def print_info(self, msg):
        self._log.info(msg)

    def print_warning(self, msg):
        self._log.warning(msg)

    def print_error(self, msg):
        self._log.error(msg)

    # ── Tool execution ──

    def print_tool_call(self, name, args):
        self._log.debug("Tool call: %s(%s)", name, args)

    def print_tool_result(self, result, max_lines=30):
        self._log.debug("Tool result: %s", result[:200])

    def print_tool_error(self, result, max_lines=15):
        self._log.error("Tool error: %s", result[:200])

    # ── LLM output ──

    def print_assistant(self, text):
        self._log.info("Assistant: %s", text[:200])

    def print_streaming_token(self, token):
        pass

    def print_stats(self, eval_count, prompt_tokens, duration_ns=0):
        pass

    # ── Interrupts ──

    def print_interrupt_banner(self, word_count=0, entries_added=0,
                               modified_files=None, created_files=None):
        pass

    # ── Help / Detail ──

    def print_help(self):
        pass

    def print_context_detail(self, entries):
        pass

    # ── Input ──

    def prompt_user(self, cwd):
        raise EOFError("Non-interactive mode — no user input available")

    def prompt_yes_no(self, message, default=True, timeout=0):
        if self._policy == "deny":
            result = False
        elif self._policy == "allow":
            result = True
        else:
            result = default
        self._log.info("Auto-%s: %s", "yes" if result else "no", message)
        return result

    def prompt_choice(self, message, choices, default=None):
        result = default or (choices[0][0] if choices else "")
        self._log.info("Auto-choice '%s': %s", result, message)
        return result

    def prompt_text(self, message):
        self._log.info("Auto-skip text prompt: %s", message)
        return ""
