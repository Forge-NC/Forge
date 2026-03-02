"""Forge Test Suite Runner — enterprise-grade test GUI for the Neural Cortex.

CTkToplevel dialog with:
  - Left panel: collapsible test tree (file > class > method) with status icons
  - Right panel: real-time pytest output console
  - Top bar: Run All / Run Selected / Stop + progress bar + pass/fail/skip counters
  - Background subprocess: python -m pytest with line-by-line parsing

MIT-licensed dependencies only: customtkinter.
"""

import logging
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

try:
    import customtkinter as ctk
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from forge.ui.themes import (
    get_colors, get_fonts, add_theme_listener, remove_theme_listener,
    recolor_widget_tree,
)

log = logging.getLogger(__name__)

# ── Colors & fonts from central theme system ──

COLORS = get_colors()

_F = get_fonts()
FONT_MONO = _F["mono"]
FONT_MONO_SM = _F["mono_sm"]
FONT_MONO_XS = _F["mono_xs"]
FONT_MONO_BOLD = _F["mono_bold"]
FONT_TITLE = _F["title_sm"]

# Status indicators
STATUS_PENDING  = ("--", COLORS["gray"])
STATUS_RUNNING  = ("..", COLORS["cyan"])
STATUS_PASSED   = ("OK", COLORS["green"])
STATUS_FAILED   = ("XX", COLORS["red"])
STATUS_SKIPPED  = ("--", COLORS["yellow"])
STATUS_ERROR    = ("!!", COLORS["red"])

# Regex for pytest verbose output
_RE_RESULT = re.compile(
    r"^(tests[\\/]\S+\.py)::([\w]+)::([\w]+)\s+(PASSED|FAILED|SKIPPED|ERROR)",
)
_RE_SUMMARY = re.compile(r"^[=]+ (.+) [=]+$")
_RE_CLASS_DEF = re.compile(r"^class\s+(Test\w+)")
_RE_TEST_DEF = re.compile(r"^    def\s+(test_\w+)")


class TestRunnerDialog:
    """Non-modal test suite runner window."""

    def __init__(self, parent):
        if not HAS_CTK:
            return

        self._parent = parent
        self._proc: Optional[subprocess.Popen] = None
        self._running = False
        self._stop_requested = False

        # Test tree data: {file: {class: {method: status_key}}}
        self._tree_data: dict = {}
        # Widget refs for status updates: {(file, cls, method): label_widget}
        self._status_labels: dict = {}
        # Expanded state per file: {file: bool}
        self._expanded: dict = {}
        # Counters
        self._count_pass = 0
        self._count_fail = 0
        self._count_skip = 0
        self._count_total = 0

        self._effects = None
        self._build_window()
        self._init_effects()
        self._discover_tests()
        self._build_tree()

    # ──────────────────────────────────────────────────────────
    # Window construction
    # ──────────────────────────────────────────────────────────

    def _build_window(self):
        self._win = ctk.CTkToplevel(self._parent)
        self._win.title("Forge — Test Suite Runner")
        self._win.geometry("920x620")
        self._win.minsize(700, 450)
        self._win.configure(fg_color=COLORS["bg_dark"])
        self._win.after(50, self._win.lift)
        self._win.after(50, self._win.focus_force)
        self._win.protocol("WM_DELETE_WINDOW", self._on_close)
        self._win.bind("<Control-r>", lambda e: self._run_all())

        # Register for live theme hot-swap
        self._theme_cb = lambda cm: self._win.after(
            0, self._apply_theme, cm)
        add_theme_listener(self._theme_cb)

        # ── Top bar ──
        top = ctk.CTkFrame(self._win, fg_color=COLORS["bg_panel"], height=50,
                           corner_radius=0,
                           border_width=1, border_color=COLORS["border"])
        top.pack(fill="x", padx=0, pady=0)
        top.pack_propagate(False)
        self._top_bar = top

        btn_frame = ctk.CTkFrame(top, fg_color="transparent")
        btn_frame.pack(side="left", padx=8, pady=6)

        self._btn_run_all = ctk.CTkButton(
            btn_frame, text="Run All", width=80, height=30,
            fg_color=COLORS["cyan_dim"], hover_color=COLORS["cyan"],
            text_color=COLORS["white"], font=ctk.CTkFont(*FONT_MONO_BOLD),
            command=self._run_all)
        self._btn_run_all.pack(side="left", padx=(0, 4))

        self._btn_run_sel = ctk.CTkButton(
            btn_frame, text="Run Selected", width=110, height=30,
            fg_color=COLORS["bg_card"], hover_color=COLORS["border"],
            text_color=COLORS["white"], font=ctk.CTkFont(*FONT_MONO),
            command=self._run_selected)
        self._btn_run_sel.pack(side="left", padx=(0, 4))

        self._btn_stop = ctk.CTkButton(
            btn_frame, text="Stop", width=60, height=30,
            fg_color=COLORS["bg_card"], hover_color=COLORS["red"],
            text_color=COLORS["gray"], font=ctk.CTkFont(*FONT_MONO),
            command=self._stop_run, state="disabled")
        self._btn_stop.pack(side="left", padx=(0, 4))

        # Progress bar
        self._progress = ctk.CTkProgressBar(
            top, width=160, height=12,
            fg_color=COLORS["bg_card"], progress_color=COLORS["cyan_dim"],
            corner_radius=3)
        self._progress.pack(side="left", padx=8, pady=6)
        self._progress.set(0)

        # Counters
        counter_frame = ctk.CTkFrame(top, fg_color="transparent")
        counter_frame.pack(side="right", padx=12, pady=6)

        self._lbl_pass = ctk.CTkLabel(
            counter_frame, text="0", font=ctk.CTkFont(*FONT_MONO_BOLD),
            text_color=COLORS["green"], width=40)
        self._lbl_pass.pack(side="left")
        ctk.CTkLabel(counter_frame, text="OK", font=ctk.CTkFont(*FONT_MONO_XS),
                     text_color=COLORS["gray"]).pack(side="left", padx=(0, 8))

        self._lbl_fail = ctk.CTkLabel(
            counter_frame, text="0", font=ctk.CTkFont(*FONT_MONO_BOLD),
            text_color=COLORS["red"], width=40)
        self._lbl_fail.pack(side="left")
        ctk.CTkLabel(counter_frame, text="XX", font=ctk.CTkFont(*FONT_MONO_XS),
                     text_color=COLORS["gray"]).pack(side="left", padx=(0, 8))

        self._lbl_skip = ctk.CTkLabel(
            counter_frame, text="0", font=ctk.CTkFont(*FONT_MONO_BOLD),
            text_color=COLORS["yellow"], width=40)
        self._lbl_skip.pack(side="left")
        ctk.CTkLabel(counter_frame, text="--", font=ctk.CTkFont(*FONT_MONO_XS),
                     text_color=COLORS["gray"]).pack(side="left")

        # ── Separator ──
        self._separator = ctk.CTkFrame(self._win, fg_color=COLORS["border"],
                                        height=1, corner_radius=0)
        self._separator.pack(fill="x")

        # ── Body: left tree + right output ──
        body = ctk.CTkFrame(self._win, fg_color=COLORS["bg_dark"], corner_radius=0)
        body.pack(fill="both", expand=True, padx=0, pady=0)

        # Left panel — test tree
        left = ctk.CTkFrame(body, fg_color=COLORS["bg_panel"], width=260,
                            corner_radius=0, border_color=COLORS["border"],
                            border_width=1)
        left.pack(side="left", fill="y", padx=0, pady=0)
        left.pack_propagate(False)
        self._left_panel = left

        ctk.CTkLabel(left, text="  TEST FILES",
                     font=ctk.CTkFont(*FONT_MONO_SM),
                     text_color=COLORS["gray"], anchor="w").pack(
            fill="x", padx=4, pady=(8, 4))

        self._tree_scroll = ctk.CTkScrollableFrame(
            left, fg_color=COLORS["bg_panel"],
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["cyan_dim"])
        self._tree_scroll.pack(fill="both", expand=True, padx=2, pady=2)

        # Right panel — output console
        right = ctk.CTkFrame(body, fg_color=COLORS["bg_dark"], corner_radius=0)
        right.pack(side="left", fill="both", expand=True, padx=0, pady=0)

        self._output = ctk.CTkTextbox(
            right, fg_color=COLORS["bg_card"],
            text_color=COLORS["white"],
            font=ctk.CTkFont(*FONT_MONO_SM),
            corner_radius=0, border_color=COLORS["border"], border_width=1,
            state="disabled", wrap="none",
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["cyan_dim"])
        self._output.pack(fill="both", expand=True, padx=0, pady=0)

        # ── Status bar ──
        status = ctk.CTkFrame(self._win, fg_color=COLORS["bg_panel"], height=28,
                              corner_radius=0,
                              border_width=1, border_color=COLORS["border"])
        status.pack(fill="x", padx=0, pady=0)
        status.pack_propagate(False)
        self._status_bar = status

        self._lbl_status = ctk.CTkLabel(
            status, text="  Ready", font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["gray"], anchor="w")
        self._lbl_status.pack(side="left", fill="x", expand=True, padx=4)

        self._lbl_time = ctk.CTkLabel(
            status, text="", font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["gray"], anchor="e")
        self._lbl_time.pack(side="right", padx=8)

    def _init_effects(self):
        """Set up visual effects for the test runner window."""
        try:
            from forge.config import ForgeConfig
            from forge.ui.effects import EffectsEngine, WidgetGlow
            fx_enabled = ForgeConfig().get("effects_enabled", True)
            self._effects = EffectsEngine(self._win, enabled=fx_enabled)
            # Register top bar with separator (border glow + hover + pulse)
            self._effects.register_card(self._top_bar, self._separator)
            # Register left panel (border glow + hover)
            self._effects.register_card(self._left_panel)
            # Register status bar (border glow + hover)
            self._effects.register_card(self._status_bar)
            # Crackling edge glow on window
            self._effects.register_window_edge_glow(self._win)
            # OS-level window border color animation
            self._effects.register_window_border_color(self._win)
            # Test progress bar glow
            self._effects.register_widget(
                self._progress, WidgetGlow.PROGRESS)
            self._effects.start()
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────
    # Test discovery
    # ──────────────────────────────────────────────────────────

    def _discover_tests(self):
        """Parse test files to build the tree structure."""
        tests_dir = Path.cwd() / "tests"
        if not tests_dir.is_dir():
            # Try relative to the forge package
            forge_root = Path(__file__).parent.parent.parent
            tests_dir = forge_root / "tests"
        if not tests_dir.is_dir():
            return

        self._tests_dir = tests_dir
        self._tree_data = {}

        for tf in sorted(tests_dir.glob("test_*.py")):
            fname = tf.name
            classes: dict = {}
            current_class = None
            try:
                for line in tf.read_text(encoding="utf-8").splitlines():
                    cm = _RE_CLASS_DEF.match(line)
                    if cm:
                        current_class = cm.group(1)
                        classes[current_class] = {}
                        continue
                    tm = _RE_TEST_DEF.match(line)
                    if tm and current_class:
                        test_name = tm.group(1)
                        classes[current_class][test_name] = "pending"
            except Exception:
                continue
            if classes:
                self._tree_data[fname] = classes
                self._expanded[fname] = False  # collapsed by default

    def _build_tree(self):
        """Render the test tree in the left panel."""
        # Clear existing
        for w in self._tree_scroll.winfo_children():
            w.destroy()
        self._status_labels.clear()

        for fname, classes in self._tree_data.items():
            total = sum(len(methods) for methods in classes.values())
            self._build_file_row(fname, total, classes)

    def _build_file_row(self, fname: str, total: int, classes: dict):
        """Build a collapsible file header + its test rows."""
        display_name = fname.replace("test_", "").replace(".py", "").title()

        # File header row
        hdr = ctk.CTkFrame(self._tree_scroll, fg_color=COLORS["bg_card"],
                           corner_radius=4, height=28, cursor="hand2")
        hdr.pack(fill="x", padx=2, pady=(3, 0))
        hdr.pack_propagate(False)

        arrow_lbl = ctk.CTkLabel(
            hdr, text=">", font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["cyan_dim"], width=16)
        arrow_lbl.pack(side="left", padx=(6, 2))

        ctk.CTkLabel(hdr, text=display_name, font=ctk.CTkFont(*FONT_MONO_BOLD),
                     text_color=COLORS["white"], anchor="w"
                     ).pack(side="left", fill="x", expand=True)

        count_lbl = ctk.CTkLabel(
            hdr, text=f"({total})", font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["gray"])
        count_lbl.pack(side="right", padx=6)

        # File-level status (aggregated after runs)
        file_status = ctk.CTkLabel(
            hdr, text="", font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["gray"], width=24)
        file_status.pack(side="right", padx=(0, 2))
        self._status_labels[(fname, None, None)] = file_status

        # Container for test rows (initially hidden)
        container = ctk.CTkFrame(self._tree_scroll, fg_color="transparent")

        def toggle(e=None, f=fname, c=container, a=arrow_lbl):
            if self._expanded.get(f, False):
                c.pack_forget()
                self._expanded[f] = False
                a.configure(text=">")
            else:
                c.pack(fill="x", padx=2, pady=0, after=hdr)
                self._expanded[f] = True
                a.configure(text="v")

        for w in (hdr, arrow_lbl):
            w.bind("<Button-1>", toggle)

        # Build test method rows inside container
        for cls_name, methods in classes.items():
            # Class label
            cls_row = ctk.CTkFrame(container, fg_color="transparent", height=20)
            cls_row.pack(fill="x", padx=(16, 2), pady=(2, 0))
            cls_row.pack_propagate(False)
            cls_display = cls_name.replace("Test", "")
            ctk.CTkLabel(cls_row, text=cls_display,
                         font=ctk.CTkFont(*FONT_MONO_SM),
                         text_color=COLORS["cyan_dim"], anchor="w"
                         ).pack(side="left", fill="x", expand=True)

            for method_name in methods:
                self._build_test_row(container, fname, cls_name, method_name)

    def _build_test_row(self, parent, fname, cls_name, method_name):
        """Build a single test method row with status indicator."""
        row = ctk.CTkFrame(parent, fg_color="transparent", height=20,
                           cursor="hand2")
        row.pack(fill="x", padx=(28, 2), pady=0)
        row.pack_propagate(False)

        # Status indicator
        st_text, st_color = STATUS_PENDING
        status_lbl = ctk.CTkLabel(
            row, text=st_text, font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=st_color, width=22)
        status_lbl.pack(side="left", padx=(0, 4))

        # Test name (stripped of test_ prefix)
        display = method_name.replace("test_", "", 1)
        name_lbl = ctk.CTkLabel(
            row, text=display, font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["text_dim"], anchor="w")
        name_lbl.pack(side="left", fill="x", expand=True)

        self._status_labels[(fname, cls_name, method_name)] = status_lbl

        # Click to select for Run Selected
        def on_click(e, f=fname, c=cls_name, m=method_name, r=row):
            self._toggle_select(f, c, m, r)
        for w in (row, name_lbl, status_lbl):
            w.bind("<Button-1>", on_click)

        # Hover
        def on_enter(e, r=row, nl=name_lbl):
            nl.configure(text_color=COLORS["white"])
        def on_leave(e, r=row, nl=name_lbl):
            nl.configure(text_color=COLORS["text_dim"])
        for w in (row, name_lbl, status_lbl):
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)

    # ──────────────────────────────────────────────────────────
    # Selection for Run Selected
    # ──────────────────────────────────────────────────────────

    _selected: set = set()  # (fname, cls_name, method_name)

    def _toggle_select(self, fname, cls_name, method_name, row_widget):
        key = (fname, cls_name, method_name)
        if key in self._selected:
            self._selected.discard(key)
            row_widget.configure(fg_color="transparent")
        else:
            self._selected.add(key)
            row_widget.configure(fg_color=COLORS["border"])

    # ──────────────────────────────────────────────────────────
    # Run controls
    # ──────────────────────────────────────────────────────────

    def _run_all(self):
        """Run all tests via pytest."""
        if self._running:
            return
        self._reset_state()
        self._start_pytest([])

    def _run_selected(self):
        """Run only selected tests."""
        if self._running or not self._selected:
            return
        self._reset_state()
        # Build pytest node IDs: tests/test_foo.py::TestClass::test_method
        node_ids = []
        for fname, cls_name, method_name in self._selected:
            node_ids.append(f"tests/{fname}::{cls_name}::{method_name}")
        self._start_pytest(node_ids)

    def _stop_run(self):
        """Request stop of the running pytest process."""
        self._stop_requested = True
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                pass
        self._set_status("Stopped by user", COLORS["yellow"])

    def _reset_state(self):
        """Reset all counters and status indicators."""
        self._count_pass = 0
        self._count_fail = 0
        self._count_skip = 0
        self._stop_requested = False

        self._lbl_pass.configure(text="0")
        self._lbl_fail.configure(text="0")
        self._lbl_skip.configure(text="0")
        self._progress.set(0)

        # Clear output
        self._output.configure(state="normal")
        self._output.delete("1.0", "end")
        self._output.configure(state="disabled")

        # Reset all status labels to pending
        for key, lbl in self._status_labels.items():
            if key[2] is not None:  # test method labels only
                st_text, st_color = STATUS_PENDING
                lbl.configure(text=st_text, text_color=st_color)
            else:  # file-level labels
                lbl.configure(text="", text_color=COLORS["gray"])

    def _start_pytest(self, extra_args: list):
        """Launch pytest in a background thread."""
        self._running = True
        self._btn_run_all.configure(state="disabled")
        self._btn_run_sel.configure(state="disabled")
        self._btn_stop.configure(state="normal", text_color=COLORS["red"])
        self._set_status("Running tests...", COLORS["cyan"])
        self._start_time = time.time()

        # Expand all file sections so user can see progress
        for fname in self._tree_data:
            if not self._expanded.get(fname, False):
                # Find the header and toggle it
                self._expanded[fname] = True

        # Rebuild tree to show expanded state
        self._build_tree()

        # Count total tests
        if extra_args:
            self._count_total = len(extra_args)
        else:
            self._count_total = sum(
                len(methods)
                for classes in self._tree_data.values()
                for methods in classes.values()
            )

        def _run():
            try:
                self._run_pytest_subprocess(extra_args)
            except Exception as exc:
                self._append_output(f"\nError: {exc}\n", COLORS["red"])
            finally:
                self._win.after(0, self._on_run_complete)

        threading.Thread(target=_run, daemon=True,
                         name="ForgeTestRunner").start()

    def _run_pytest_subprocess(self, extra_args: list):
        """Execute pytest and parse output line by line."""
        # Find python executable — on Windows, pythonw.exe (used by GUI apps)
        # can't run console modules like pytest, so swap to python.exe
        python = sys.executable
        if sys.platform == "win32" and python.lower().endswith("pythonw.exe"):
            python = python[:-5] + ".exe"  # pythonw.exe -> python.exe

        cmd = [python, "-m", "pytest", "-v", "--tb=short", "--no-header"]
        if extra_args:
            cmd.extend(extra_args)
        else:
            cmd.append("tests/")

        # Run from the project root
        project_root = Path(__file__).parent.parent.parent
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"

        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(project_root),
            env=env,
            text=True,
            bufsize=1,
        )

        for line in self._proc.stdout:
            if self._stop_requested:
                break
            line = line.rstrip("\n")
            self._parse_and_display(line)

        self._proc.wait()

    def _parse_and_display(self, line: str):
        """Parse a pytest output line and update tree + output."""
        # Check for test result line
        m = _RE_RESULT.match(line)
        if m:
            fpath, cls_name, method_name, result = m.groups()
            fname = Path(fpath).name
            self._update_test_status(fname, cls_name, method_name, result)

            # Color the output line
            color = {
                "PASSED": COLORS["green"],
                "FAILED": COLORS["red"],
                "SKIPPED": COLORS["yellow"],
                "ERROR": COLORS["red"],
            }.get(result, COLORS["white"])
            self._append_output(line + "\n", color)
            return

        # Check for summary line
        sm = _RE_SUMMARY.match(line)
        if sm:
            self._append_output(line + "\n", COLORS["cyan"])
            return

        # Check for FAILURES header
        if line.startswith("FAILED") or "FAILURES" in line:
            self._append_output(line + "\n", COLORS["red"])
            return

        # Default output
        self._append_output(line + "\n", COLORS["text_dim"])

    def _update_test_status(self, fname, cls_name, method_name, result):
        """Update a test's status icon in the tree."""
        status_map = {
            "PASSED":  STATUS_PASSED,
            "FAILED":  STATUS_FAILED,
            "SKIPPED": STATUS_SKIPPED,
            "ERROR":   STATUS_ERROR,
        }
        st_text, st_color = status_map.get(result, STATUS_PENDING)

        # Update counter
        if result == "PASSED":
            self._count_pass += 1
        elif result == "FAILED":
            self._count_fail += 1
        elif result in ("SKIPPED", "ERROR"):
            self._count_skip += 1

        processed = self._count_pass + self._count_fail + self._count_skip

        def _update():
            # Update test status label
            key = (fname, cls_name, method_name)
            if key in self._status_labels:
                self._status_labels[key].configure(text=st_text,
                                                    text_color=st_color)
            # Update counters
            self._lbl_pass.configure(text=str(self._count_pass))
            self._lbl_fail.configure(text=str(self._count_fail))
            self._lbl_skip.configure(text=str(self._count_skip))

            # Update progress bar
            if self._count_total > 0:
                frac = min(processed / self._count_total, 1.0)
                self._progress.set(frac)
                if self._count_fail > 0:
                    self._progress.configure(progress_color=COLORS["red"])
                else:
                    self._progress.configure(progress_color=COLORS["green"])

        self._win.after(0, _update)

    def _append_output(self, text: str, color: str = None):
        """Thread-safe append to output textbox."""
        def _do():
            self._output.configure(state="normal")
            self._output.insert("end", text)
            self._output.see("end")
            self._output.configure(state="disabled")
        self._win.after(0, _do)

    def _on_run_complete(self):
        """Called when the pytest process finishes."""
        self._running = False
        self._proc = None
        self._btn_run_all.configure(state="normal")
        self._btn_run_sel.configure(state="normal")
        self._btn_stop.configure(state="disabled", text_color=COLORS["gray"])

        elapsed = time.time() - self._start_time
        total = self._count_pass + self._count_fail + self._count_skip

        # Update file-level status aggregates
        for fname, classes in self._tree_data.items():
            file_pass = 0
            file_fail = 0
            for cls_name, methods in classes.items():
                for method_name in methods:
                    key = (fname, cls_name, method_name)
                    lbl = self._status_labels.get(key)
                    if lbl:
                        txt = lbl.cget("text")
                        if txt == "OK":
                            file_pass += 1
                        elif txt == "XX" or txt == "!!":
                            file_fail += 1
            file_key = (fname, None, None)
            if file_key in self._status_labels:
                if file_fail > 0:
                    self._status_labels[file_key].configure(
                        text="XX", text_color=COLORS["red"])
                elif file_pass > 0:
                    self._status_labels[file_key].configure(
                        text="OK", text_color=COLORS["green"])

        if self._count_fail > 0:
            self._set_status(
                f"  {total} tests | {self._count_fail} failed | {elapsed:.1f}s",
                COLORS["red"])
        else:
            self._set_status(
                f"  {total} passed | {elapsed:.1f}s",
                COLORS["green"])

        self._lbl_time.configure(
            text=f"{elapsed:.1f}s",
            text_color=COLORS["gray"])

    def _set_status(self, text: str, color: str):
        """Update the status bar text."""
        try:
            self._lbl_status.configure(text=text, text_color=color)
        except Exception:
            pass

    def _apply_theme(self, color_map: dict):
        """Hot-swap theme colours on the test runner."""
        if self._win:
            recolor_widget_tree(self._win, color_map)

    def _on_close(self):
        """Clean up effects, theme listener, and destroy."""
        if self._effects:
            try:
                self._effects.shutdown()
            except Exception:
                pass
            self._effects = None
        if hasattr(self, "_theme_cb"):
            remove_theme_listener(self._theme_cb)
        self._stop_requested = True
        try:
            self._win.destroy()
        except Exception:
            pass
