"""Terminal UI with context status bar.

Shows a persistent status line with token usage, and renders
tool calls and responses with clear formatting.

Includes input history (up/down arrow), tab completion for /commands
and file paths, and multi-line paste detection on Windows.
"""

import os
import sys
import time
import shutil
import threading

# ── Readline setup for history + tab completion ──
_readline_available = False
_history_file = None

try:
    import readline
    _readline_available = True
except ImportError:
    try:
        import pyreadline3  # noqa: F401 — importing installs readline hook
        import readline
        _readline_available = True
    except ImportError:
        pass


def init_readline(config_dir: str = None):
    """Initialize readline for history and tab completion.

    Call once at startup. On Windows, requires pyreadline3.
    """
    global _history_file
    if not _readline_available:
        return

    from pathlib import Path
    forge_dir = Path(config_dir) if config_dir else Path.home() / ".forge"
    forge_dir.mkdir(parents=True, exist_ok=True)
    _history_file = str(forge_dir / "cmd_history.txt")

    try:
        readline.read_history_file(_history_file)
    except (FileNotFoundError, OSError):
        pass

    readline.set_history_length(500)
    _patch_history_end_clear()


def _patch_history_end_clear():
    """Patch pyreadline3 so down-arrow past end of history clears input.

    Standard GNU readline clears to a fresh line when you press
    down-arrow past the newest history entry.  pyreadline3 on Windows
    stops at the last entry instead.  This monkey-patches the internal
    ``next_history`` to match the GNU behavior.
    """
    try:
        rl_mod = sys.modules.get("readline")
        if rl_mod is None:
            return
        rl = getattr(rl_mod, "rl", None)
        if rl is None:
            return
        mode = getattr(rl, "mode", None)
        if mode is None:
            return
        hist = getattr(mode, "_history", None)
        if hist is None:
            return

        _original_next = hist.next_history

        def _next_history_clear(current):
            """Clear line when pressing down past the end of history."""
            if hist.history_cursor >= len(hist.history) - 1:
                # Pop the saved "current typing" entry that previous_history
                # appended, so history stays clean.
                if (hist.history and
                        hist.history_cursor == len(hist.history) - 1):
                    hist.history.pop()
                hist.history_cursor = len(hist.history)
                current.set_line("")
                current.point = 0
            else:
                _original_next(current)

        hist.next_history = _next_history_clear
    except Exception:
        pass  # Cosmetic feature — fail silently


def _save_history():
    """Save command history to disk after each input."""
    if not _readline_available or not _history_file:
        return
    try:
        readline.write_history_file(_history_file)
    except Exception:
        pass


def setup_completer(slash_commands: list):
    """Set up tab completion for slash commands and file paths."""
    if not _readline_available:
        return

    def completer(text, state):
        if text.startswith("/"):
            matches = [c for c in slash_commands if c.startswith(text)]
        else:
            import glob as glob_mod
            expanded = os.path.expanduser(text)
            matches = glob_mod.glob(expanded + "*")
        if state < len(matches):
            return matches[state]
        return None

    readline.set_completer(completer)
    readline.set_completer_delims(" \t")
    readline.parse_and_bind("tab: complete")


def _drain_paste_buffer(first_line: str) -> str:
    """Drain additional pasted lines after input() returned.

    On Windows, pasted multi-line text splits across multiple input()
    calls because each line ends with Enter.  Uses msvcrt.kbhit() for
    non-blocking detection — no orphaned threads that could steal
    subsequent input events.
    """
    if sys.platform != "win32":
        return first_line

    try:
        import msvcrt
    except ImportError:
        return first_line

    lines = [first_line]
    current_chars: list = []
    deadline = time.monotonic() + 0.12  # 120ms — paste arrives fast

    while time.monotonic() < deadline:
        if not msvcrt.kbhit():
            time.sleep(0.008)
            continue

        ch = msvcrt.getwch()
        if ch in ("\r", "\n"):
            if current_chars:
                lines.append("".join(current_chars))
                current_chars = []
            # Extend window for more pasted lines
            deadline = time.monotonic() + 0.05
        elif ch == "\x00" or ch == "\xe0":
            # Extended key prefix (arrow keys, function keys) — ignore
            msvcrt.getwch()  # consume the second byte
        else:
            current_chars.append(ch)
            deadline = time.monotonic() + 0.05

    if current_chars:
        lines.append("".join(current_chars))

    return "\n".join(lines) if len(lines) > 1 else first_line

# ANSI color codes (work on Windows 10+ and Linux)
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"
BG_RED = "\033[41m"
BG_GREEN = "\033[42m"
BG_YELLOW = "\033[43m"
BG_BLUE = "\033[44m"
GRAY = "\033[90m"


# ── Animated Spinner ──────────────────────────────────────────────

class Spinner:
    """Animated Unicode spinner for terminal — non-blocking, daemon thread.

    Usage:
        spinner = Spinner()
        spinner.start("Thinking")
        # ... long operation ...
        spinner.stop()
    """

    # Braille dots (preferred — smooth animation)
    UNICODE_FRAMES = ["\u280b", "\u2819", "\u2839", "\u2838",
                      "\u283c", "\u2834", "\u2826", "\u2827",
                      "\u2807", "\u280f"]
    # ASCII fallback for terminals that can't handle Unicode
    ASCII_FRAMES = ["|", "/", "-", "\\"]

    def __init__(self, interval: float = 0.08):
        self._interval = interval
        self._running = False
        self._thread = None
        self._message = ""
        # Test if stdout supports unicode braille
        self._frames = self.UNICODE_FRAMES
        try:
            self.UNICODE_FRAMES[0].encode(
                sys.stdout.encoding or "utf-8")
        except (UnicodeEncodeError, LookupError):
            self._frames = self.ASCII_FRAMES

    def start(self, message: str = ""):
        """Start the spinner with an optional message."""
        if self._running:
            self.stop()
        self._message = message
        self._running = True
        self._thread = threading.Thread(
            target=self._spin, daemon=True, name="TermSpinner")
        self._thread.start()

    def stop(self):
        """Stop the spinner and clear the line."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.5)
            self._thread = None
        # Clear the spinner line
        try:
            cols = shutil.get_terminal_size((80, 24)).columns
            sys.stdout.write(f"\r{' ' * cols}\r")
            sys.stdout.flush()
        except Exception:
            pass

    def _spin(self):
        idx = 0
        while self._running:
            frame = self._frames[idx % len(self._frames)]
            text = f"\r{CYAN}{frame}{RESET} {DIM}{self._message}{RESET}"
            try:
                sys.stdout.write(text)
                sys.stdout.flush()
            except Exception:
                pass
            idx += 1
            time.sleep(self._interval)


# ── Gradient ANSI Text ────────────────────────────────────────────

def _hex_to_rgb(h: str):
    """Convert '#rrggbb' to (r, g, b) tuple."""
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def gradient_text(text: str, colors: list) -> str:
    """Apply a smooth 24-bit ANSI color gradient across text.

    Args:
        text: The text to colorize.
        colors: List of hex colors, e.g. ['#00ffff', '#ff00ff'].

    Returns:
        String with embedded ANSI 24-bit color codes.
    """
    if not text or not colors:
        return text
    if len(colors) == 1:
        r, g, b = _hex_to_rgb(colors[0])
        return f"\033[38;2;{r};{g};{b}m{text}{RESET}"

    rgb_list = [_hex_to_rgb(c) for c in colors]
    n = len(text)
    if n <= 1:
        r, g, b = rgb_list[0]
        return f"\033[38;2;{r};{g};{b}m{text}{RESET}"

    result = []
    segments = len(rgb_list) - 1
    for i, ch in enumerate(text):
        t = i / (n - 1) * segments
        seg = min(int(t), segments - 1)
        frac = t - seg
        r1, g1, b1 = rgb_list[seg]
        r2, g2, b2 = rgb_list[seg + 1]
        r = int(r1 + (r2 - r1) * frac)
        g = int(g1 + (g2 - g1) * frac)
        b = int(b1 + (b2 - b1) * frac)
        result.append(f"\033[38;2;{r};{g};{b}m{ch}")
    result.append(RESET)
    return "".join(result)


# Global spinner instance for ConsoleTerminalIO
_spinner = Spinner()


def enable_ansi_windows():
    """Enable ANSI escape sequences on Windows."""
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # Enable ENABLE_VIRTUAL_TERMINAL_PROCESSING
            kernel32.SetConsoleMode(
                kernel32.GetStdHandle(-11), 0x0007)
        except Exception:
            pass


def term_width() -> int:
    """Get terminal width."""
    return shutil.get_terminal_size((80, 24)).columns


def print_banner():
    """Print the startup banner."""
    w = term_width()

    use_gradient = False
    try:
        from forge.config import ForgeConfig
        use_gradient = ForgeConfig().get("ansi_effects_enabled", False)
    except Exception:
        pass

    if use_gradient:
        bar = gradient_text("=" * w, ["#00ffff", "#ff00ff", "#00ffff"])
        title = gradient_text("  F O R G E",
                              ["#00ffff", "#ffffff", "#ff00ff"])
        print(f"\n{bar}")
        print(f"{title} {DIM}\u2014 Local AI Coding Assistant{RESET}")
        print(f"{DIM}  No tokens. No compaction. No bullshit.{RESET}")
        print(f"{bar}\n")
    else:
        print(f"\n{BOLD}{CYAN}{'=' * w}{RESET}")
        print(f"{BOLD}{WHITE}  FORGE{RESET} {DIM}\u2014 Local AI Coding Assistant{RESET}")
        print(f"{DIM}  No tokens. No compaction. No bullshit.{RESET}")
        print(f"{BOLD}{CYAN}{'=' * w}{RESET}\n")


def print_context_bar(ctx_status: dict):
    """Print the context status bar."""
    pct = ctx_status["usage_pct"]
    total = ctx_status["total_tokens"]
    maximum = ctx_status["max_tokens"]
    remaining = ctx_status["remaining_tokens"]
    entries = ctx_status["entry_count"]
    pinned = ctx_status["pinned_count"]

    # Color based on usage
    if pct > 90:
        color = RED
        icon = "!!"
    elif pct > 75:
        color = YELLOW
        icon = "! "
    elif pct > 50:
        color = CYAN
        icon = "  "
    else:
        color = GREEN
        icon = "  "

    # Build the bar
    bar_width = 20
    filled = int(bar_width * pct / 100)
    bar = "\u2588" * filled + "\u2591" * (bar_width - filled)

    # Check if ANSI effects enabled for gradient bars
    use_gradient = False
    try:
        from forge.config import ForgeConfig
        use_gradient = ForgeConfig().get("ansi_effects_enabled", False)
    except Exception:
        pass

    if use_gradient:
        # Gradient bar from green -> cyan -> yellow -> red based on fill
        bar_colors = ["#00ff88", "#00ffff", "#ffcc00", "#ff4444"]
        bar_str = gradient_text(bar, bar_colors)
        info = (f"({total:,}/{maximum:,} tokens, "
                f"{remaining:,} remaining, {entries} entries")
        if pinned:
            info += f", {pinned} pinned"
        info += ")"
        line = (f"{DIM}[CTX{icon}]{RESET} "
                f"{bar_str} "
                f"{color}{pct:.0f}%{RESET} "
                f"{DIM}{info}{RESET}")
    else:
        line = (f"{DIM}[CTX{icon}]{RESET} "
                f"{color}{bar}{RESET} "
                f"{color}{pct:.0f}%{RESET} "
                f"{DIM}({total:,}/{maximum:,} tokens, "
                f"{remaining:,} remaining, "
                f"{entries} entries")
        if pinned:
            line += f", {pinned} pinned"
        line += f"){RESET}"

    print(line)


def print_warning(msg: str):
    """Print a warning message."""
    print(f"{YELLOW}{BOLD}WARNING:{RESET} {YELLOW}{msg}{RESET}")


def print_error(msg: str):
    """Print an error message."""
    print(f"{RED}{BOLD}ERROR:{RESET} {RED}{msg}{RESET}")


def print_info(msg: str):
    """Print an info message."""
    print(f"{CYAN}{msg}{RESET}")


def print_tool_call(name: str, args: dict):
    """Print a tool call."""
    args_str = ", ".join(f"{k}={repr(v)[:60]}" for k, v in args.items())
    print(f"\n{DIM}┌─ {MAGENTA}{BOLD}{name}{RESET}{DIM}({args_str}){RESET}")


def print_tool_result(result: str, max_lines: int = 30):
    """Print a tool result."""
    lines = result.splitlines()
    if len(lines) > max_lines:
        for line in lines[:max_lines]:
            print(f"{DIM}│{RESET} {line}")
        print(f"{DIM}│ ... ({len(lines) - max_lines} more lines){RESET}")
    else:
        for line in lines:
            print(f"{DIM}│{RESET} {line}")
    print(f"{DIM}└{'─' * 40}{RESET}")


def print_tool_error(result: str, max_lines: int = 15):
    """Print a tool error result with red styling."""
    lines = result.splitlines()
    if len(lines) > max_lines:
        for line in lines[:max_lines]:
            print(f"{RED}{DIM}|{RESET} {RED}{line}{RESET}")
        print(f"{RED}{DIM}| ... ({len(lines) - max_lines} more lines){RESET}")
    else:
        for line in lines:
            print(f"{RED}{DIM}|{RESET} {RED}{line}{RESET}")
    print(f"{RED}{DIM}{'=' * 40}{RESET}")


def print_assistant(text: str):
    """Print assistant response text."""
    print(f"\n{WHITE}{text}{RESET}")


def print_streaming_token(token: str):
    """Print a single streaming token (no newline)."""
    sys.stdout.write(f"{WHITE}{token}{RESET}")
    sys.stdout.flush()


def print_interrupt_banner(word_count: int = 0, entries_added: int = 0,
                           modified_files: list = None,
                           created_files: list = None):
    """Print the Escape interrupt banner with status summary."""
    w = term_width()
    print(f"\n{YELLOW}{BOLD}{'=' * w}{RESET}")
    print(f"{YELLOW}{BOLD}  --- INTERRUPTED ---{RESET}")
    print(f"{YELLOW}{BOLD}{'=' * w}{RESET}")

    if word_count:
        print(f"  {DIM}Partial response: {word_count} words{RESET}")
    if entries_added:
        print(f"  {DIM}Context entries added: {entries_added}{RESET}")
    if modified_files:
        for f in modified_files:
            fname = f.replace("\\", "/").split("/")[-1]
            print(f"  {CYAN}Modified:{RESET} {DIM}{fname}{RESET}")
    if created_files:
        for f in created_files:
            fname = f.replace("\\", "/").split("/")[-1]
            print(f"  {GREEN}Created:{RESET} {DIM}{fname}{RESET}")

    print()
    print(f"  {WHITE}Type new input to redirect (changes kept){RESET}")
    print(f"  {WHITE}Type {BOLD}undo{RESET}{WHITE} to rollback all changes from this turn{RESET}")
    print(f"  {WHITE}Press {BOLD}Enter{RESET}{WHITE} to stop{RESET}")


def print_stats(eval_count: int, prompt_tokens: int,
                duration_ns: int = 0):
    """Print generation statistics."""
    parts = [f"{DIM}["]
    parts.append(f"generated {eval_count} tokens")
    parts.append(f", prompt {prompt_tokens} tokens")
    if duration_ns > 0:
        duration_s = duration_ns / 1e9
        tok_s = eval_count / duration_s if duration_s > 0 else 0
        parts.append(f", {tok_s:.1f} tok/s")
        parts.append(f", {duration_s:.1f}s")
    parts.append(f"]{RESET}")
    print("".join(parts))


def prompt_user(cwd: str) -> str:
    """Show the input prompt and get user input."""
    # Show abbreviated path
    try:
        home = str(Path.home()) if hasattr(Path, 'home') else ""
        display_path = cwd
        if home and cwd.startswith(home):
            display_path = "~" + cwd[len(home):]
        # Shorten to last 2 components if long
        parts = display_path.replace("\\", "/").split("/")
        if len(parts) > 3:
            display_path = "/".join(parts[-2:])
    except Exception:
        display_path = cwd

    try:
        text = input(f"\n{GREEN}{BOLD}{display_path}{RESET} {GREEN}>{RESET} ")
        _save_history()
        text = _drain_paste_buffer(text)
        return text.strip()
    except EOFError:
        # Ctrl+Z on Windows sends EOF — don't exit, just ignore
        import sys as _sys
        if _sys.platform == "win32":
            print(f"\n{YELLOW}[Ctrl+Z pressed — use /quit or Ctrl+C to exit]{RESET}")
            return ""
        return "/quit"
    except KeyboardInterrupt:
        return "/quit"


def print_help():
    """Print available commands."""
    sections = [
        ("Context Management", [
            ("/context", "Show detailed context window status"),
            ("/drop N", "Drop context entry at index N"),
            ("/pin N", "Pin entry (survives eviction)"),
            ("/unpin N", "Unpin context entry"),
            ("/clear", "Clear all unpinned entries"),
            ("/reset", "Start fresh (clear everything)"),
        ]),
        ("Session", [
            ("/save [file]", "Save session to file"),
            ("/load [file]", "Load session from file"),
        ]),
        ("Model & Tools", [
            ("/model [name]", "Show or switch model"),
            ("/models", "List available Ollama models"),
            ("/tools", "List available tools"),
        ]),
        ("Billing & Cache", [
            ("/billing", "Show sandbox billing summary"),
            ("/compare", "Compare costs: Forge vs Claude vs GPT"),
            ("/topup [amt]", "Add sandbox funds (default: $50)"),
            ("/cache", "Show file cache statistics"),
            ("/cache clear", "Clear the file cache"),
        ]),
        ("Codebase Analysis", [
            ("/scan [path]", "Scan codebase structure (classes, functions, routes, tables)"),
            ("/digest [file]", "Show digest stats, or detail for a specific file"),
        ]),
        ("Memory & Search", [
            ("/memory", "Show all memory subsystem status"),
            ("/journal [N]", "Show last N journal entries (default: 20)"),
            ("/recall <query>", "Semantic code search with previews"),
            ("/search <query>", "Quick semantic search (file list)"),
            ("/index [path]", "Index codebase for semantic search"),
            ("/tasks", "Show task state and progress"),
        ]),
        ("Analytics & Dashboard", [
            ("/stats", "Show full analytics: performance, tools, cost"),
            ("/dashboard", "Launch Neural Cortex GUI monitor"),
            ("/synapse", "Run synapse check — cycle all Neural Cortex modes"),
        ]),
        ("Voice Input", [
            ("/voice", "Show voice input status"),
            ("/voice ptt", "Push-to-talk mode (hold ` to speak)"),
            ("/voice vox", "Voice-activated mode (auto-detect)"),
            ("/voice off", "Disable voice input"),
        ]),
        ("Interrupt", [
            ("Escape", "Press during AI response to interrupt"),
            ("(then) undo", "Rollback all file changes + context from this turn"),
            ("(then) <text>", "Redirect AI with new instructions (keeps changes)"),
        ]),
        ("Safety & Config", [
            ("/safety", "Show safety level and sandbox status"),
            ("/safety <level>", "Set level: unleashed, smart_guard, confirm_writes, locked_down"),
            ("/safety sandbox on|off", "Toggle filesystem sandboxing"),
            ("/safety allow <path>", "Add a path to the sandbox allowlist"),
            ("/config", "Show current configuration"),
            ("/config reload", "Reload config.yaml from disk"),
        ]),
        ("Crucible (Threat Scanner)", [
            ("/crucible", "Show Crucible status and detection stats"),
            ("/crucible on|off", "Enable/disable threat scanning"),
            ("/crucible log", "Show threat detection log"),
            ("/crucible canary", "Check honeypot canary integrity"),
        ]),
        ("Forensics & Provenance", [
            ("/forensics", "Show session forensics summary"),
            ("/forensics save", "Save forensics report to disk"),
            ("/provenance", "Show tool call provenance chain"),
        ]),
        ("Model Router", [
            ("/router", "Show router status and routing stats"),
            ("/router on|off", "Enable/disable multi-model routing"),
            ("/router big <model>", "Set the big (complex task) model"),
            ("/router small <model>", "Set the small (simple task) model"),
        ]),
        ("Continuity Grade", [
            ("/continuity", "Show continuity grade and signal breakdown"),
            ("/continuity history", "Show last 10 continuity snapshots"),
            ("/continuity set <N>", "Set recovery threshold (0-100)"),
            ("/continuity on|off", "Enable/disable continuity monitoring"),
        ]),
        ("Audit & Benchmarks", [
            ("/export", "Export audit bundle (zip with manifest + hashes)"),
            ("/export --redact", "Export with sensitive content redacted"),
            ("/benchmark list", "List available benchmark suites"),
            ("/benchmark run [suite]", "Run benchmark scenarios"),
            ("/benchmark results", "Show historical benchmark results"),
            ("/benchmark compare", "Compare last two benchmark runs"),
            ("/stats reliability", "Show cross-session reliability score"),
        ]),
        ("Plugins", [
            ("/plugins", "Show loaded plugins and their status"),
        ]),
        ("Theme", [
            ("/theme", "List available themes"),
            ("/theme <name>", "Switch UI color theme"),
        ]),
        ("System", [
            ("/hardware", "Show GPU/CPU/RAM and model recommendation"),
            ("/cd [path]", "Change working directory"),
            ("/docs", "Open documentation window (also F1)"),
            ("/quit", "Exit Forge"),
            ("/help", "Show this help"),
        ]),
    ]
    for section_name, commands in sections:
        print(f"\n{BOLD}{section_name}:{RESET}")
        for cmd, desc in commands:
            print(f"  {CYAN}{cmd:16}{RESET} {desc}")
    print(f"\n{DIM}Everything else is sent to the AI.{RESET}")


def print_context_detail(entries: list[dict]):
    """Print detailed context entries table."""
    if not entries:
        print(f"{DIM}(context is empty){RESET}")
        return

    print(f"\n{BOLD}{'#':>4}  {'Role':8}  {'Tag':12}  "
          f"{'Tokens':>7}  {'Pin':3}  Preview{RESET}")
    print(f"{DIM}{'─' * 80}{RESET}")

    for e in entries:
        pin_mark = f"{YELLOW}*{RESET}" if e["pinned"] else " "
        role_color = {
            "system": MAGENTA,
            "user": GREEN,
            "assistant": CYAN,
            "tool": BLUE,
        }.get(e["role"], WHITE)

        print(f"{e['index']:>4}  "
              f"{role_color}{e['role']:8}{RESET}  "
              f"{DIM}{e['tag']:12}{RESET}  "
              f"{e['tokens']:>7,}  "
              f" {pin_mark}   "
              f"{DIM}{e['preview'][:40]}{RESET}")


# Import Path here for prompt_user
from pathlib import Path
