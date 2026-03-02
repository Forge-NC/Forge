"""GUI Terminal Window — runs ForgeEngine in-process with visual effects.

ForgeTerminalWindow is a CustomTkinter window that replaces the system
console. All engine I/O is redirected to styled text widgets via
GuiTerminalIO.

Thread model:
  - CTk mainloop runs on the MAIN thread (required by tkinter).
  - ForgeEngine.run() runs on a DAEMON background thread.
  - All widget updates are marshaled via root.after(0, callback).
  - prompt_user() blocks the engine thread on threading.Event,
    wakes when the user presses Enter or submits voice input.

Cross-platform: no msvcrt, no subprocess, no Windows-only APIs.
"""

import sys
import os
import io
import re
import logging
import threading
import time
import math
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

try:
    import customtkinter as ctk
    from PIL import Image
    import numpy as np
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from forge.ui.terminal_io import TerminalIO
from forge.ui.themes import (
    get_colors, get_fonts, add_theme_listener, remove_theme_listener,
    _MONO_FAMILY, _BODY_FAMILY,
)


COLORS = get_colors()
_F = get_fonts()
FONT_MONO = _F["mono"]
FONT_MONO_BOLD = _F["mono_bold"]
FONT_MONO_SM = _F["mono_sm"]
FONT_TITLE = _F["title"]

BRAIN_IMAGE_PATH = Path(__file__).parent / "assets" / "brain.png"
BRAIN_SIZE = (48, 48)  # Small brain for the status bar

# ANSI escape regex for stripping codes from redirected stdout
_ANSI_RE = re.compile(r'\033\[[0-9;]*m')


class _GuiStdoutRedirect(io.TextIOBase):
    """Redirect stdout/stderr writes to the GUI output area.

    Captures direct print() calls from engine code that bypass
    the TerminalIO abstraction (e.g. hardware scan, model download).
    """

    def __init__(self, append_fn, root):
        self._append = append_fn
        self._root = root
        self._shutting_down = False

    def write(self, text):
        if self._shutting_down or not text:
            return len(text) if text else 0
        # Strip ANSI codes for clean GUI display
        clean = _ANSI_RE.sub('', text)
        if clean:
            try:
                self._root.after(0, self._append, clean, "stats")
            except Exception:
                pass
        return len(text) if text else 0

    def flush(self):
        pass

    def isatty(self):
        return False


# ──────────────────────────────────────────────────────────────────
# ForgeTerminalWindow — the GUI window itself
# ──────────────────────────────────────────────────────────────────

class ForgeTerminalWindow:
    """CustomTkinter terminal window with rich text output."""

    def __init__(self, root, on_close=None):
        self._root = root
        self._on_close_cb = on_close
        self._shutting_down = False

        # Effects engine (optional)
        self._effects = None

        # Brain animation
        self._brain_label = None
        self._brain_ctk_img = None
        self._brain_engine = None
        self._brain_running = False

        # Build the window
        self._build_ui()

        # Tag configuration for rich text
        self._setup_tags()

        # Track code block state for streaming
        self._in_code_block = False

    def _build_ui(self):
        """Build the terminal window layout."""
        self._root.title("Forge Terminal")
        self._root.geometry("800x600")
        self._root.minsize(600, 400)
        self._root.configure(fg_color=COLORS["bg_dark"])
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        ico_path = Path(__file__).parent / "assets" / "forge.ico"
        if ico_path.exists():
            try:
                self._root.iconbitmap(str(ico_path))
            except Exception:
                pass

        # ── Status bar (top) with mini brain ──
        self._status_frame = ctk.CTkFrame(
            self._root, fg_color=COLORS["bg_panel"],
            corner_radius=0, height=56,
            border_width=1, border_color=COLORS["border"])
        self._status_frame.pack(fill="x")
        self._status_frame.pack_propagate(False)

        # Mini brain animation in status bar
        self._brain_label = ctk.CTkLabel(
            self._status_frame, text="", width=48)
        self._brain_label.pack(side="left", padx=(6, 2), pady=2)
        self._load_brain()

        self._model_label = ctk.CTkLabel(
            self._status_frame, text="Forge Terminal",
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            text_color=COLORS["cyan"])
        self._model_label.pack(side="left", padx=(2, 8), pady=4)

        self._state_label = ctk.CTkLabel(
            self._status_frame, text="booting...",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["cyan"])
        self._state_label.pack(side="right", padx=8, pady=4)

        # ── Divider between status bar and output ──
        self._status_divider = ctk.CTkFrame(
            self._root, fg_color=COLORS["border"],
            height=1, corner_radius=0)
        self._status_divider.pack(fill="x")

        # ── Output area wrapper (CTkFrame for border glow effects) ──
        self._output_wrapper = ctk.CTkFrame(
            self._root, fg_color=COLORS["bg_dark"],
            corner_radius=0,
            border_width=1, border_color=COLORS["border"])
        self._output_wrapper.pack(fill="both", expand=True, padx=2, pady=1)

        import tkinter as tk
        self._output = tk.Text(
            self._output_wrapper,
            bg=COLORS["bg_dark"],
            fg=COLORS["white"],
            font=(_MONO_FAMILY, 10),
            wrap="word",
            state="disabled",
            insertbackground=COLORS["cyan"],
            selectbackground=COLORS["cyan_dim"],
            selectforeground=COLORS["white"],
            borderwidth=0,
            highlightthickness=0,
            padx=8, pady=4)
        self._output.pack(fill="both", expand=True)

        # Scrollbar
        self._scrollbar = ctk.CTkScrollbar(
            self._output_wrapper, command=self._output.yview)
        self._scrollbar.place(relx=1.0, rely=0.0, relheight=1.0, anchor="ne")
        self._output.configure(yscrollcommand=self._scrollbar.set)

        # ── Divider between output and input ──
        self._input_divider = ctk.CTkFrame(
            self._root, fg_color=COLORS["border"],
            height=1, corner_radius=0)
        self._input_divider.pack(fill="x", side="bottom")

        # ── Input frame (bottom) ──
        self._input_frame = ctk.CTkFrame(
            self._root, fg_color=COLORS["bg_panel"],
            corner_radius=0, height=40,
            border_width=1, border_color=COLORS["border"])
        self._input_frame.pack(fill="x", side="bottom")
        self._input_frame.pack_propagate(False)

        # Re-pack input divider above input frame
        self._input_divider.pack_forget()
        self._input_divider.pack(fill="x", side="bottom", before=self._input_frame)

        self._cwd_label = ctk.CTkLabel(
            self._input_frame, text="~/",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["green"])
        self._cwd_label.pack(side="left", padx=(8, 4), pady=4)

        self._input_entry = ctk.CTkEntry(
            self._input_frame,
            font=ctk.CTkFont(_MONO_FAMILY, 11),
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["white"],
            border_color=COLORS["border"],
            border_width=1,
            corner_radius=4,
            placeholder_text="Initializing...")
        self._input_entry.pack(
            side="left", fill="x", expand=True, padx=4, pady=4)

        self._send_btn = ctk.CTkButton(
            self._input_frame, text=">",
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            fg_color=COLORS["cyan_dim"],
            hover_color=COLORS["cyan"],
            text_color=COLORS["bg_dark"],
            corner_radius=4, width=36, height=28,
            command=self._on_send)
        self._send_btn.pack(side="right", padx=(4, 8), pady=4)

        # Bind Enter and Escape
        self._input_entry.bind("<Return>", lambda e: self._on_send())
        self._root.bind("<Escape>", self._on_escape)

        # Command history
        self._history = []
        self._history_idx = -1
        self._input_entry.bind("<Up>", self._history_up)
        self._input_entry.bind("<Down>", self._history_down)
        self._root.bind("<Control-l>", lambda e: self.clear_output())

        # Input state — managed by GuiTerminalIO
        self._input_ready = threading.Event()
        self._input_text = ""
        self._escape_pressed = threading.Event()
        self._input_enabled = False

        # Start with input disabled
        self._disable_input()

        # ── Initialize effects engine ──
        self._init_effects()

    def _init_effects(self):
        """Set up the visual effects engine and register all frames."""
        try:
            from forge.config import ForgeConfig
            from forge.ui.effects import EffectsEngine, WidgetGlow
            cfg = ForgeConfig()
            fx_enabled = cfg.get("effects_enabled", True)
            gui_fx = cfg.get("gui_terminal_effects", True)
            if not gui_fx:
                return
            self._effects = EffectsEngine(self._root, enabled=fx_enabled)
            # Register output wrapper as main card with status divider
            self._effects.register_card(
                self._output_wrapper, self._status_divider)
            # Register status bar (border glow + hover)
            self._effects.register_card(self._status_frame)
            # Register input bar with its divider
            self._effects.register_card(
                self._input_frame, self._input_divider)
            # Crackling edge glow on the window itself
            self._effects.register_window_edge_glow(self._root)
            # OS-level window border color animation
            self._effects.register_window_border_color(self._root)
            # Scrollbar glow
            self._effects.register_widget(
                self._scrollbar, WidgetGlow.SCROLLBAR)
            # Start effects (only animates if current theme has effects)
            self._effects.start()
        except Exception as e:
            log.debug("Effects init failed: %s", e)

    # ── Mini brain animation ──

    def _load_brain(self):
        """Load and start the mini brain animation."""
        if not BRAIN_IMAGE_PATH.exists():
            return
        try:
            from forge.ui.dashboard import _build_anim_engine_from_image
            # Monkey-patch BRAIN_SIZE for the mini version
            import forge.ui.dashboard as _dash
            orig_size = _dash.BRAIN_SIZE
            _dash.BRAIN_SIZE = BRAIN_SIZE
            self._brain_engine = _build_anim_engine_from_image(
                BRAIN_IMAGE_PATH)
            _dash.BRAIN_SIZE = orig_size

            # Render first frame
            frame_arr = self._brain_engine.render_frame()
            frame_pil = Image.fromarray(frame_arr, "RGBA")
            ctk_img = ctk.CTkImage(
                light_image=frame_pil, dark_image=frame_pil,
                size=BRAIN_SIZE)
            self._brain_label.configure(image=ctk_img, text="")
            self._brain_ctk_img = ctk_img

            # Start animation loop
            self._brain_running = True
            self._schedule_brain_animation()
        except Exception as e:
            log.debug("Mini brain load failed: %s", e)

    def _schedule_brain_animation(self):
        """Tick the brain animation."""
        if not self._brain_running or not self._brain_engine:
            return
        if self._shutting_down:
            return

        fps = self._brain_engine.fps
        interval_ms = max(50, int(1000 / fps))
        self._brain_engine.advance(1.0 / fps)

        try:
            frame_arr = self._brain_engine.render_frame()
            frame_pil = Image.fromarray(frame_arr, "RGBA")
            ctk_img = ctk.CTkImage(
                light_image=frame_pil, dark_image=frame_pil,
                size=BRAIN_SIZE)
            self._brain_label.configure(image=ctk_img)
            self._brain_ctk_img = ctk_img
        except Exception:
            pass

        if self._brain_running and not self._shutting_down:
            self._root.after(interval_ms, self._schedule_brain_animation)

    def set_brain_state(self, state_name: str):
        """Set the brain animation state (matches dashboard states)."""
        if not self._brain_engine:
            return
        try:
            from forge.ui.dashboard import AnimState
            state_map = {
                "idle": AnimState.IDLE,
                "thinking": AnimState.THINKING,
                "tool_exec": AnimState.TOOL_EXEC,
                "indexing": AnimState.INDEXING,
                "swapping": AnimState.SWAPPING,
                "error": AnimState.ERROR,
                "threat": AnimState.THREAT,
            }
            new_state = state_map.get(state_name)
            if new_state:
                self._brain_engine.set_state(new_state)
        except Exception:
            pass

    def _setup_tags(self):
        """Configure text tags for rich output."""
        import tkinter.font as tkfont

        mono = tkfont.Font(family=_MONO_FAMILY, size=10)
        mono_bold = tkfont.Font(family=_MONO_FAMILY, size=10, weight="bold")

        tags = {
            "assistant":    {"foreground": COLORS["white"],
                             "font": mono},
            "tool_header":  {"foreground": COLORS["magenta"],
                             "font": mono_bold},
            "tool_body":    {"foreground": COLORS["gray"],
                             "font": mono},
            "tool_error":   {"foreground": COLORS["red"],
                             "font": mono},
            "error":        {"foreground": COLORS["red"],
                             "font": mono_bold},
            "warning":      {"foreground": COLORS["yellow"],
                             "font": mono},
            "info":         {"foreground": COLORS["cyan"],
                             "font": mono},
            "user":         {"foreground": COLORS["green"],
                             "font": mono_bold},
            "stats":        {"foreground": COLORS["gray"],
                             "font": mono},
            "banner":       {"foreground": COLORS["cyan"],
                             "font": mono_bold},
            "code":         {"foreground": COLORS["white"],
                             "font": mono,
                             "background": "#1a1a2e"},
        }

        for tag_name, config in tags.items():
            self._output.tag_configure(tag_name, **config)

    # ── Output methods (called from GuiTerminalIO via root.after) ──

    def append_text(self, text: str, tag: str = "assistant"):
        """Append text to the output area with a tag."""
        if self._shutting_down:
            return
        self._output.configure(state="normal")
        self._output.insert("end", text, tag)
        self._output.see("end")
        self._output.configure(state="disabled")

    def append_token(self, token: str):
        """Append a streaming token — handles code block detection."""
        if self._shutting_down:
            return

        # Simple code fence detection
        if "```" in token:
            self._in_code_block = not self._in_code_block

        tag = "code" if self._in_code_block else "assistant"
        self._output.configure(state="normal")
        self._output.insert("end", token, tag)
        self._output.see("end")
        self._output.configure(state="disabled")

    def clear_output(self):
        """Clear all output text."""
        self._output.configure(state="normal")
        self._output.delete("1.0", "end")
        self._output.configure(state="disabled")

    def update_status(self, state: str):
        """Update the status bar state indicator + brain animation."""
        if self._shutting_down:
            return

        state_display = {
            "idle": ("idle", COLORS["gray"]),
            "thinking": ("thinking...", COLORS["cyan"]),
            "tool_exec": ("executing...", COLORS["green"]),
            "indexing": ("indexing...", COLORS["magenta"]),
            "swapping": ("swapping...", COLORS["yellow"]),
            "error": ("error", COLORS["red"]),
            "threat": ("THREAT", COLORS["red"]),
        }

        text, color = state_display.get(state, ("idle", COLORS["gray"]))
        self._state_label.configure(text=text, text_color=color)

        # Update brain animation state
        self.set_brain_state(state)

    def update_cwd(self, cwd: str):
        """Update the working directory label."""
        try:
            home = str(Path.home())
            display = cwd
            if cwd.startswith(home):
                display = "~" + cwd[len(home):]
            parts = display.replace("\\", "/").split("/")
            if len(parts) > 3:
                display = "/".join(parts[-2:])
        except Exception:
            display = cwd
        self._cwd_label.configure(text=display)

    # ── Input management ──

    def enable_input(self, cwd: str = ""):
        """Enable the input entry and update cwd label."""
        self._input_enabled = True
        if cwd:
            self.update_cwd(cwd)
        self._input_entry.configure(
            state="normal",
            border_color=COLORS["cyan_dim"],
            placeholder_text="Type a message...")
        # CTkEntry placeholder can stick if the entry already had focus
        # (FocusIn won't re-fire). Force-clear and cycle focus to guarantee
        # the placeholder mechanism resets properly.
        self._input_entry.delete(0, "end")
        self._output.focus_set()             # yield to event loop
        self._input_entry.after(10, self._focus_input_clean)

    def _focus_input_clean(self):
        """Give focus to the input entry with a clean state.

        Called via after() so that the FocusOut event on the output area
        has time to fire first, allowing CTkEntry to properly activate
        the placeholder.  When the entry then gets FocusIn, the
        placeholder is cleared and the user types into a clean field.
        """
        try:
            self._input_entry.focus_set()
        except Exception:
            pass

    def _disable_input(self):
        """Disable the input entry."""
        self._input_enabled = False
        self._input_entry.configure(
            state="disabled",
            border_color=COLORS["border"])

    def _on_send(self):
        """Handle Enter / Send button."""
        if not self._input_enabled:
            return
        text = self._input_entry.get().strip()

        # CTkEntry's placeholder text is inserted as real text — filter it out.
        # Also strip any prefix in case the placeholder stuck and user typed
        # after it (e.g. "Type a message...actual input").
        for placeholder in ("Type a message...", "Initializing..."):
            if text == placeholder:
                text = ""
                break
            if text.startswith(placeholder):
                text = text[len(placeholder):].strip()
                break

        self._input_entry.delete(0, "end")

        if not text:
            # Don't send blank prompts — just re-enable input
            self._input_entry.after(10, self._focus_input_clean)
            return

        self._disable_input()

        # Add to history
        self._history.append(text)
        if len(self._history) > 200:
            self._history = self._history[-200:]
        self._history_idx = -1

        # Show user input in output
        self.append_text(f"\n> {text}\n", "user")

        # Signal the engine thread
        self._input_text = text
        self._input_ready.set()

    def _on_escape(self, event=None):
        """Handle Escape key — signal interrupt to engine."""
        self._escape_pressed.set()

    def _history_up(self, event=None):
        if not self._history:
            return "break"
        if self._history_idx == -1:
            self._history_idx = len(self._history) - 1
        elif self._history_idx > 0:
            self._history_idx -= 1
        self._input_entry.delete(0, "end")
        self._input_entry.insert(0, self._history[self._history_idx])
        return "break"

    def _history_down(self, event=None):
        if self._history_idx == -1:
            return "break"
        if self._history_idx < len(self._history) - 1:
            self._history_idx += 1
            self._input_entry.delete(0, "end")
            self._input_entry.insert(0, self._history[self._history_idx])
        else:
            self._history_idx = -1
            self._input_entry.delete(0, "end")
        return "break"

    def _on_close(self):
        """Handle window close."""
        self._shutting_down = True
        self._brain_running = False
        # Wake up any blocked prompt_user
        self._input_text = "/quit"
        self._input_ready.set()
        self._escape_pressed.set()

        if self._effects:
            try:
                self._effects.shutdown()
            except Exception:
                pass

        if self._on_close_cb:
            self._on_close_cb()


# ──────────────────────────────────────────────────────────────────
# GuiTerminalIO — routes engine I/O to ForgeTerminalWindow
# ──────────────────────────────────────────────────────────────────

class GuiTerminalIO(TerminalIO):
    """Routes all engine I/O to a ForgeTerminalWindow.

    Thread-safe: all widget updates are marshaled through root.after().
    prompt_user() blocks the engine thread via threading.Event.
    """

    def __init__(self, root, window: ForgeTerminalWindow):
        self._root = root
        self._win = window
        self._shutting_down = False
        # stdout/stderr redirect for capturing direct print() calls
        self._stdout_redirect = _GuiStdoutRedirect(
            window.append_text, root)

    def _safe_after(self, callback, *args):
        """Schedule callback on the GUI thread, safely."""
        if self._shutting_down:
            return
        try:
            self._root.after(0, callback, *args)
        except Exception as e:
            log.debug("safe_after failed: %s", e)

    # ── Startup / Init ──

    def init_readline(self, config_dir=None):
        pass  # GUI has its own input handling

    def setup_completer(self, slash_commands):
        pass

    def enable_ansi(self):
        pass  # Not needed for GUI

    # ── Banner / Status ──

    def print_banner(self):
        def _do():
            self._win.append_text(
                "=" * 60 + "\n", "banner")
            self._win.append_text(
                "  F O R G E  \u2014 Local AI Coding Assistant\n", "banner")
            self._win.append_text(
                "  No tokens. No compaction. No bullshit.\n", "stats")
            self._win.append_text(
                "=" * 60 + "\n\n", "banner")
        self._safe_after(_do)

    def print_context_bar(self, ctx_status):
        pct = ctx_status["usage_pct"]
        total = ctx_status["total_tokens"]
        maximum = ctx_status["max_tokens"]
        remaining = ctx_status["remaining_tokens"]
        entries = ctx_status["entry_count"]

        bar_width = 20
        filled = int(bar_width * pct / 100)
        bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
        text = (f"[CTX] {bar} {pct:.0f}% "
                f"({total:,}/{maximum:,} tokens, "
                f"{remaining:,} remaining, {entries} entries)\n")

        tag = "error" if pct > 90 else "warning" if pct > 75 else "info"
        self._safe_after(self._win.append_text, text, tag)

    # ── Messages ──

    def print_info(self, msg):
        # Strip ANSI codes that may be embedded in the message
        clean = _ANSI_RE.sub('', msg)
        self._safe_after(self._win.append_text, f"{clean}\n", "info")

    def print_warning(self, msg):
        clean = _ANSI_RE.sub('', msg)
        self._safe_after(
            self._win.append_text, f"WARNING: {clean}\n", "warning")

    def print_error(self, msg):
        clean = _ANSI_RE.sub('', msg)
        self._safe_after(
            self._win.append_text, f"ERROR: {clean}\n", "error")

    # ── Tool execution ──

    def print_tool_call(self, name, args):
        args_str = ", ".join(
            f"{k}={repr(v)[:60]}" for k, v in args.items())
        text = f"\n\u250c\u2500 {name}({args_str})\n"
        self._safe_after(self._win.append_text, text, "tool_header")

    def print_tool_result(self, result, max_lines=30):
        lines = result.splitlines()
        if len(lines) > max_lines:
            text = "\n".join(
                f"\u2502 {l}" for l in lines[:max_lines])
            text += f"\n\u2502 ... ({len(lines) - max_lines} more lines)\n"
        else:
            text = "\n".join(f"\u2502 {l}" for l in lines) + "\n"
        text += "\u2514" + "\u2500" * 40 + "\n"
        self._safe_after(self._win.append_text, text, "tool_body")

    def print_tool_error(self, result, max_lines=15):
        lines = result.splitlines()
        if len(lines) > max_lines:
            text = "\n".join(
                f"| {l}" for l in lines[:max_lines])
            text += f"\n| ... ({len(lines) - max_lines} more lines)\n"
        else:
            text = "\n".join(f"| {l}" for l in lines) + "\n"
        text += "=" * 40 + "\n"
        self._safe_after(self._win.append_text, text, "tool_error")

    # ── LLM output ──

    def print_assistant(self, text):
        self._safe_after(
            self._win.append_text, f"\n{text}\n", "assistant")

    def print_streaming_token(self, token):
        # Strip ANSI codes from tokens (engine wraps in WHITE/RESET)
        clean = _ANSI_RE.sub('', token)
        self._safe_after(self._win.append_token, clean)

    def print_stats(self, eval_count, prompt_tokens, duration_ns=0):
        parts = [f"[generated {eval_count} tokens"]
        parts.append(f", prompt {prompt_tokens} tokens")
        if duration_ns > 0:
            duration_s = duration_ns / 1e9
            tok_s = eval_count / duration_s if duration_s > 0 else 0
            parts.append(f", {tok_s:.1f} tok/s")
            parts.append(f", {duration_s:.1f}s")
        parts.append("]\n")
        text = "".join(parts)
        self._safe_after(self._win.append_text, text, "stats")

    # ── Interrupts ──

    def print_interrupt_banner(self, word_count=0, entries_added=0,
                               modified_files=None, created_files=None):
        lines = ["\n" + "=" * 40,
                 "  --- INTERRUPTED ---",
                 "=" * 40]
        if word_count:
            lines.append(f"  Partial response: {word_count} words")
        if entries_added:
            lines.append(f"  Context entries added: {entries_added}")
        if modified_files:
            for f in modified_files:
                fname = f.replace("\\", "/").split("/")[-1]
                lines.append(f"  Modified: {fname}")
        if created_files:
            for f in created_files:
                fname = f.replace("\\", "/").split("/")[-1]
                lines.append(f"  Created: {fname}")
        lines.extend([
            "",
            "  Type new input to redirect (changes kept)",
            "  Type 'undo' to rollback all changes from this turn",
            "  Press Enter to stop",
            "",
        ])
        text = "\n".join(lines) + "\n"
        self._safe_after(self._win.append_text, text, "warning")

    # ── Help / Detail ──

    def print_help(self):
        from forge.ui.terminal import print_help as _console_help
        buf = io.StringIO()
        old_stdout = sys.stdout
        try:
            sys.stdout = buf
            _console_help()
        finally:
            sys.stdout = old_stdout
        clean = _ANSI_RE.sub('', buf.getvalue())
        self._safe_after(self._win.append_text, clean, "info")

    def print_context_detail(self, entries):
        if not entries:
            self._safe_after(
                self._win.append_text, "(context is empty)\n", "stats")
            return

        header = (f"{'#':>4}  {'Role':8}  {'Tag':12}  "
                  f"{'Tokens':>7}  {'Pin':3}  Preview\n")
        header += "\u2500" * 80 + "\n"
        self._safe_after(self._win.append_text, header, "info")

        for e in entries:
            pin = "*" if e["pinned"] else " "
            line = (f"{e['index']:>4}  {e['role']:8}  "
                    f"{e['tag']:12}  {e['tokens']:>7,}   "
                    f"{pin}   {e['preview'][:40]}\n")
            self._safe_after(self._win.append_text, line, "tool_body")

    # ── Input ──

    def prompt_user(self, cwd: str) -> str:
        """Block engine thread until user enters text."""
        self._win._input_ready.clear()
        self._win._escape_pressed.clear()
        self._safe_after(self._win.enable_input, cwd)

        # Block engine thread until input is ready
        self._win._input_ready.wait()
        return self._win._input_text

    # ── Raw output ──

    def print_raw(self, text: str):
        clean = _ANSI_RE.sub('', text)
        self._safe_after(self._win.append_text, clean, "assistant")

    # ── State ──

    def set_state(self, state: str):
        self._safe_after(self._win.update_status, state)

    def shutdown(self):
        """Signal shutdown — stop accepting new after() calls."""
        self._shutting_down = True
        self._stdout_redirect._shutting_down = True


# ──────────────────────────────────────────────────────────────────
# Launch helpers
# ──────────────────────────────────────────────────────────────────

def _run_engine_thread(gui_io, model, cwd, win):
    """Run ForgeEngine on a background thread with stdout redirect."""
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    # Redirect stdout/stderr so direct print() calls show in the GUI
    sys.stdout = gui_io._stdout_redirect
    sys.stderr = gui_io._stdout_redirect

    try:
        from forge.engine import ForgeEngine
        engine = ForgeEngine(
            model=model,
            cwd=cwd or os.getcwd(),
            terminal_io=gui_io)
        engine.run()
    except Exception as e:
        # Show errors in the GUI window
        import traceback
        tb = traceback.format_exc()
        log.warning("GUI terminal engine error: %s", e)
        try:
            gui_io._root.after(0, win.append_text,
                               f"\n[Engine Error]\n{tb}\n", "error")
        except Exception:
            pass
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        gui_io.shutdown()


def launch_gui_terminal(model: str = None, cwd: str = None):
    """Launch the GUI terminal as a standalone window.

    CTk mainloop on main thread, ForgeEngine on daemon thread.
    """
    if not HAS_CTK:
        print("GUI Terminal requires: pip install customtkinter Pillow numpy")
        return

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    root = ctk.CTk()
    win = ForgeTerminalWindow(root, on_close=lambda: _shutdown(root))

    gui_io = GuiTerminalIO(root, win)

    # Theme listener
    theme_cb = lambda cm: root.after(0, _apply_theme, root, cm)
    add_theme_listener(theme_cb)

    engine_thread = threading.Thread(
        target=_run_engine_thread,
        args=(gui_io, model, cwd, win),
        daemon=True, name="ForgeEngine")
    engine_thread.start()

    root.mainloop()

    # Cleanup
    remove_theme_listener(theme_cb)


def _apply_theme(root, color_map):
    """Hot-swap theme on the terminal window."""
    from forge.ui.themes import recolor_widget_tree
    recolor_widget_tree(root, color_map)


def _shutdown(root):
    """Shutdown the GUI terminal."""
    try:
        root.destroy()
    except Exception:
        pass
