"""Forge Test Intelligence Suite — Enterprise Edition.

Three-panel layout:
  Left (320px): Category-organized test tree
  Right top:    Test detail panel — shows ACTUAL test source code
  Right bottom: Live output console

Opening is fast: discovery runs in a background thread while the
window is already visible; results are cached to disk keyed by
file mtime so subsequent opens are near-instant.

Closing is fast: window withdraws immediately, then cleans up.

Individual test runs pass -s so print statements show.
"""

import ast
import json
import logging
import os
import re
import subprocess
import sys
import textwrap
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
from forge.ui.window_geo import WindowGeo as _WG

log = logging.getLogger(__name__)

COLORS = get_colors()
_F = get_fonts()
FONT_MONO      = _F["mono"]
FONT_MONO_SM   = _F["mono_sm"]
FONT_MONO_XS   = _F["mono_xs"]
FONT_MONO_BOLD = _F["mono_bold"]
FONT_TITLE     = _F["title_sm"]

_SP_FLAGS: dict = {}
if sys.platform == "win32":
    _SP_FLAGS["creationflags"] = subprocess.CREATE_NO_WINDOW

_CACHE_VERSION = 3
_CACHE_PATH = Path.home() / ".forge" / "test_cache.json"

# ── Categories ────────────────────────────────────────────────────────────────
_CATEGORIES: list[tuple] = [
    ("FORGE BREAK", "#d43f3f", [
        "break", "ami", "continuity", "reliability",
        "benchmark", "assurance", "quality", "stats",
        "plan", "router", "charts", "dedup",
    ]),
    ("CRUCIBLE", "#c96a18", [
        "crucible", "threat_intel", "pii", "safety",
        "output_scanner", "rag_scanner", "tool_fencing",
        "rate_limiter", "tool_corruption", "policy",
        "verification_theater",
    ]),
    ("INTEGRATION", "#2f78c8", ["integration"]),
    ("SUITE", "#606060", []),
]

_CATEGORY_META: dict[str, dict] = {
    "FORGE BREAK": {
        "subtitle": "Reliability  ·  Quality  ·  Performance",
        "description": (
            "Verifies that Forge produces correct, consistent results across "
            "sessions. These tests exercise the same scenarios used by the "
            "/break command and signed assurance certificates.\n\n"
            "What this protects:\n"
            "  - AI response quality scoring (AMI) stays accurate\n"
            "  - Context swaps preserve conversation continuity\n"
            "  - Benchmarks reproduce identical results on repeated runs\n"
            "  - Multi-step plans verify each step before proceeding\n"
            "  - Duplicate responses are detected and suppressed\n"
            "  - Performance metrics trend correctly over time\n\n"
            "If any of these fail, Forge's reliability guarantees are "
            "compromised. These results feed directly into /break reports "
            "and the public assurance leaderboard."
        ),
    },
    "CRUCIBLE": {
        "subtitle": "Security  ·  Threat Detection  ·  Safety",
        "description": (
            "Validates Forge's 4-layer security scanner against real-world "
            "attack patterns. Every message, file read, and AI response "
            "passes through Crucible — these tests prove it works.\n\n"
            "What this protects:\n"
            "  - Prompt injection attempts are caught before execution\n"
            "  - Data exfiltration patterns are blocked\n"
            "  - PII (emails, keys, SSNs) is detected in outputs\n"
            "  - Encoded/obfuscated payloads are decoded and flagged\n"
            "  - Behavioral anomalies (timing, frequency) trigger alerts\n"
            "  - Tool calls are rate-limited to prevent abuse\n"
            "  - Output-level scanning catches unsafe AI responses\n\n"
            "Includes adversarial red-team scenarios and false-positive "
            "rate validation. A failure here means a security gap."
        ),
    },
    "INTEGRATION": {
        "subtitle": "End-to-End  ·  Chaos  ·  Resilience",
        "description": (
            "Runs the full Forge engine under extreme and adversarial "
            "conditions to surface failures that only appear when all "
            "subsystems interact together.\n\n"
            "What this protects:\n"
            "  - Forge recovers gracefully from crashes mid-session\n"
            "  - Context storms (rapid fill/swap cycles) don't corrupt state\n"
            "  - Model swaps mid-conversation preserve context\n"
            "  - Network failures don't leave Forge in a broken state\n"
            "  - Malicious repositories can't compromise the engine\n"
            "  - Tool corruption is detected and handled safely\n"
            "  - Oscillation loops (repeated undo/redo) are broken\n\n"
            "These are the closest tests to real-world usage. They catch "
            "emergent failures that no single unit test can reveal."
        ),
    },
    "SUITE": {
        "subtitle": "Infrastructure  ·  Internals  ·  Tooling",
        "description": (
            "Tests every supporting subsystem that the higher-level features "
            "depend on. If any of these break, multiple features fail.\n\n"
            "What this covers:\n"
            "  - Billing: token counting, cost tracking, ledger persistence\n"
            "  - Configuration: YAML loading, validation, defaults\n"
            "  - Context: window management, pinning, entry lifecycle\n"
            "  - Memory: episodic recall, journal entries, embeddings\n"
            "  - File cache: LRU eviction, cache invalidation\n"
            "  - Digest: tree-sitter AST parsing for 8+ languages\n"
            "  - Plugins: loading, hooks, error isolation, auto-disable\n"
            "  - Licensing: tier gating, feature checks, BPoS passport\n"
            "  - AutoForge: smart auto-commit, edit tracking\n"
            "  - Shipwright: release management, version detection\n"
            "  - Event bus: pub/sub, priority ordering, async dispatch"
        ),
    },
}

_ST_PENDING = ("--", "gray")
_ST_RUNNING = (">>", "cyan")
_ST_PASSED  = ("OK", "green")
_ST_FAILED  = ("XX", "red")
_ST_SKIPPED = ("~~", "yellow")
_ST_ERROR   = ("!!", "red")

_RE_RESULT  = re.compile(
    r"^(tests[\\/]\S+\.py)::([\w]+)(?:::([\w]+))?\s+(PASSED|FAILED|SKIPPED|ERROR)"
)
_RE_SUMMARY = re.compile(r"^[=]+ (.+) [=]+$")

_MODULE_LEVEL = "(module)"


def _classify_file(fname: str) -> str:
    if fname.startswith("integration/"):
        return "INTEGRATION"
    lower = fname.replace("test_", "").lower()
    for name, _color, keywords in _CATEGORIES:
        if any(kw in lower for kw in keywords):
            return name
    return "SUITE"


def _humanize(name: str) -> str:
    s = name.replace("test_", "", 1).replace("_", " ").strip()
    return s[:1].upper() + s[1:] if s else name


# ── Disk cache ────────────────────────────────────────────────────────────────

def _load_cache() -> dict:
    try:
        if _CACHE_PATH.exists():
            data = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            if data.get("version") == _CACHE_VERSION:
                return data
    except Exception:
        pass
    return {"version": _CACHE_VERSION, "files": {}}


def _save_cache(cache: dict) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(
            json.dumps(cache, separators=(",", ":")),
            encoding="utf-8"
        )
    except Exception:
        pass


# ── AST discovery ─────────────────────────────────────────────────────────────

def _parse_file(tf: Path, source: str) -> dict:
    """Parse one test file → {cls_name: {cls_doc, methods:{name:{doc,src}}}}"""
    try:
        tree = ast.parse(source)
    except Exception:
        return {}

    src_lines = source.splitlines()
    result: dict = {}

    # Module-level standalone test functions
    standalone: dict = {}
    for node in tree.body:
        if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.startswith("test_")):
            doc = ast.get_docstring(node) or ""
            src = _extract_src(source, node)
            standalone[node.name] = {"doc": doc, "src": src}
    if standalone:
        result[_MODULE_LEVEL] = {"cls_doc": "", "methods": standalone}

    # Class-based tests
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name.startswith("Test")):
            continue
        cls_doc = ast.get_docstring(node) or ""
        methods: dict = {}
        for item in node.body:
            if (isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and item.name.startswith("test_")):
                doc = ast.get_docstring(item) or ""
                src = _extract_src(source, item)
                methods[item.name] = {"doc": doc, "src": src}
        if methods:
            result[node.name] = {"cls_doc": cls_doc, "methods": methods}

    return result


def _extract_src(source: str, node: ast.AST) -> str:
    """Extract dedented source of an AST node."""
    try:
        raw = ast.get_source_segment(source, node) or ""
        return textwrap.dedent(raw)
    except Exception:
        return ""


# ── Discovery (with cache) ────────────────────────────────────────────────────

def _discover(tests_dir: Path) -> tuple[dict, dict, dict]:
    """Return (tree_data, class_docs, file_cats).

    tree_data   = {fname: {cls_name: {method_name: {status, doc, src}}}}
    class_docs  = {(fname, cls_name): str}
    file_cats   = {fname: cat_name}
    """
    cache = _load_cache()
    cache_files: dict = cache.setdefault("files", {})
    cache_changed = False

    all_files: list[Path] = sorted(tests_dir.glob("test_*.py"))
    integ_dir = tests_dir / "integration"
    if integ_dir.is_dir():
        all_files += sorted(integ_dir.glob("test_*.py"))

    tree_data:  dict = {}
    class_docs: dict = {}
    file_cats:  dict = {}

    for tf in all_files:
        fname = (f"integration/{tf.name}"
                 if tf.parent.name == "integration" else tf.name)
        cat = _classify_file(fname)
        file_cats[fname] = cat

        mtime = tf.stat().st_mtime
        cached = cache_files.get(fname)

        if cached and cached.get("mtime") == mtime:
            parsed = cached["parsed"]
        else:
            try:
                source = tf.read_text(encoding="utf-8")
            except Exception:
                continue
            parsed = _parse_file(tf, source)
            cache_files[fname] = {"mtime": mtime, "parsed": parsed}
            cache_changed = True

        if not parsed:
            continue

        classes: dict = {}
        for cls_name, cls_data in parsed.items():
            class_docs[(fname, cls_name)] = cls_data.get("cls_doc", "")
            methods_raw = cls_data.get("methods", {})
            methods: dict = {}
            for m_name, m_data in methods_raw.items():
                methods[m_name] = {
                    "status": "pending",
                    "doc": m_data.get("doc", ""),
                    "src": m_data.get("src", ""),
                }
            if methods:
                classes[cls_name] = methods

        if classes:
            tree_data[fname] = classes

    if cache_changed:
        # Prune stale entries
        live = {f for f in tree_data}
        for k in list(cache_files.keys()):
            if k not in live:
                del cache_files[k]
        _save_cache(cache)

    return tree_data, class_docs, file_cats


class TestRunnerDialog:
    """Enterprise test suite runner — source-first detail pane, cached discovery."""

    def __init__(self, parent):
        if not HAS_CTK:
            return

        self._parent = parent
        self._proc: Optional[subprocess.Popen] = None
        self._running  = False
        self._stop_requested = False
        self._start_time = 0.0

        self._tree_data:   dict = {}
        self._class_docs:  dict = {}
        self._file_cats:   dict = {}
        self._tests_dir: Optional[Path] = None

        self._status_labels: dict = {}
        self._expanded: dict = {}
        self._selected_key: Optional[tuple] = None
        self._run_selection: set = set()
        self._selected_row_widget = None

        self._count_pass  = 0
        self._count_fail  = 0
        self._count_skip  = 0
        self._count_total = 0
        self._effects = None
        self._closed = False

        self._build_window()
        self._init_effects()

        # Discovery runs in background; window is already visible
        self._lbl_status.configure(
            text="  Discovering tests...", text_color=COLORS["cyan"])
        threading.Thread(target=self._bg_discover, daemon=True).start()

    # ── Background discovery ──────────────────────────────────────────────────

    def _bg_discover(self):
        tests_dir = Path.cwd() / "tests"
        if not tests_dir.is_dir():
            forge_root = Path(__file__).parent.parent.parent
            tests_dir = forge_root / "tests"
        if not tests_dir.is_dir():
            self._win.after(0, self._on_discovery_done)
            return

        self._tests_dir = tests_dir
        tree_data, class_docs, file_cats = _discover(tests_dir)
        self._tree_data  = tree_data
        self._class_docs = class_docs
        self._file_cats  = file_cats
        self._win.after(0, self._on_discovery_done)

    def _on_discovery_done(self):
        if self._closed:
            return
        self._build_tree()
        self._show_welcome()
        self._lbl_status.configure(
            text="  Ready — click a test or Run All  (Ctrl+R)",
            text_color=COLORS["gray"])

    # ── Window ────────────────────────────────────────────────────────────────

    def _build_window(self):
        self._win = ctk.CTkToplevel(self._parent)
        self._win.title("Forge  —  Test Intelligence Suite")
        self._win.minsize(820, 520)
        self._win.configure(fg_color=COLORS["bg_dark"])
        self._win.after(50, self._win.lift)
        self._win.after(50, self._win.focus_force)
        self._win.protocol("WM_DELETE_WINDOW", self._on_close)
        self._win.bind("<Control-r>", lambda e: self._run_all())
        _WG.restore("test_runner", self._win, "1100x700")
        _WG.track("test_runner", self._win)

        self._theme_cb = lambda cm: self._win.after(0, self._apply_theme, cm)
        add_theme_listener(self._theme_cb)

        # Top bar
        self._top_bar = ctk.CTkFrame(
            self._win, fg_color=COLORS["bg_panel"], height=52,
            corner_radius=0, border_width=1, border_color=COLORS["border"])
        self._top_bar.pack(fill="x")
        self._top_bar.pack_propagate(False)

        ctk.CTkLabel(
            self._top_bar, text="  Test Intelligence Suite",
            font=ctk.CTkFont(*FONT_TITLE), text_color=COLORS["cyan"]
        ).pack(side="left", padx=8, pady=10)

        ctk.CTkFrame(self._top_bar, fg_color=COLORS["border"],
                     width=1, corner_radius=0
                     ).pack(side="left", fill="y", padx=8, pady=8)

        btn_cfg = dict(height=32, font=ctk.CTkFont(*FONT_MONO_BOLD))
        self._btn_run_all = ctk.CTkButton(
            self._top_bar, text="Run All", width=90,
            fg_color=COLORS["cyan_dim"], hover_color=COLORS["cyan"],
            text_color=COLORS["bg_dark"], command=self._run_all, **btn_cfg)
        self._btn_run_all.pack(side="left", padx=(0, 4), pady=10)

        self._btn_run_sel = ctk.CTkButton(
            self._top_bar, text="Run Selected", width=120,
            fg_color=COLORS["bg_card"], hover_color=COLORS["border"],
            text_color=COLORS["white"], command=self._run_selected, **btn_cfg)
        self._btn_run_sel.pack(side="left", padx=(0, 4), pady=10)

        self._btn_stop = ctk.CTkButton(
            self._top_bar, text="Stop", width=70,
            fg_color=COLORS["bg_card"], hover_color=COLORS["red"],
            text_color=COLORS["gray"], command=self._stop_run,
            state="disabled", **btn_cfg)
        self._btn_stop.pack(side="left", pady=10)

        self._progress = ctk.CTkProgressBar(
            self._top_bar, width=160, height=10,
            fg_color=COLORS["bg_card"], progress_color=COLORS["cyan_dim"],
            corner_radius=3)
        self._progress.pack(side="right", padx=12, pady=18)
        self._progress.set(0)

        for attr, label, color in [
            ("_lbl_skip", "SKIP", "yellow"),
            ("_lbl_fail", "FAIL", "red"),
            ("_lbl_pass", "PASS", "green"),
        ]:
            sub = ctk.CTkFrame(self._top_bar, fg_color="transparent")
            sub.pack(side="right", padx=6, pady=8)
            val = ctk.CTkLabel(sub, text="0",
                               font=ctk.CTkFont(*FONT_MONO_BOLD),
                               text_color=COLORS[color], width=32)
            val.pack()
            ctk.CTkLabel(sub, text=label,
                         font=ctk.CTkFont(*FONT_MONO_XS),
                         text_color=COLORS["gray"]).pack()
            setattr(self, attr, val)

        self._top_sep = ctk.CTkFrame(
            self._win, fg_color=COLORS["border"], height=1, corner_radius=0)
        self._top_sep.pack(fill="x")

        body = ctk.CTkFrame(self._win, fg_color=COLORS["bg_dark"], corner_radius=0)
        body.pack(fill="both", expand=True)

        # Left tree panel
        self._left_panel = ctk.CTkFrame(
            body, fg_color=COLORS["bg_panel"], width=320,
            corner_radius=0, border_color=COLORS["border"], border_width=1)
        self._left_panel.pack(side="left", fill="y")
        self._left_panel.pack_propagate(False)

        tree_hdr = ctk.CTkFrame(
            self._left_panel, fg_color=COLORS["bg_card"],
            corner_radius=0, height=30)
        tree_hdr.pack(fill="x")
        tree_hdr.pack_propagate(False)

        ctk.CTkLabel(
            tree_hdr, text="  TEST CATEGORIES",
            font=ctk.CTkFont(*FONT_MONO_SM), text_color=COLORS["gray"],
            anchor="w").pack(side="left", padx=4, pady=5)

        self._lbl_total = ctk.CTkLabel(
            tree_hdr, text="",
            font=ctk.CTkFont(*FONT_MONO_XS), text_color=COLORS["gray"])
        self._lbl_total.pack(side="right", padx=8)

        self._tree_scroll = ctk.CTkScrollableFrame(
            self._left_panel, fg_color=COLORS["bg_panel"],
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["cyan_dim"])
        self._tree_scroll.pack(fill="both", expand=True)

        # Right panel
        right = ctk.CTkFrame(body, fg_color=COLORS["bg_dark"], corner_radius=0)
        right.pack(side="left", fill="both", expand=True)

        self._detail_frame = ctk.CTkFrame(
            right, fg_color=COLORS["bg_panel"], corner_radius=0,
            border_width=1, border_color=COLORS["border"])
        self._detail_frame.pack(fill="x")
        self._build_detail_pane()

        ctk.CTkFrame(right, fg_color=COLORS["border"],
                     height=1, corner_radius=0).pack(fill="x")

        con_hdr = ctk.CTkFrame(
            right, fg_color=COLORS["bg_card"], height=24,
            corner_radius=0, border_width=1, border_color=COLORS["border"])
        con_hdr.pack(fill="x")
        con_hdr.pack_propagate(False)

        ctk.CTkLabel(
            con_hdr, text="  OUTPUT CONSOLE",
            font=ctk.CTkFont(*FONT_MONO_XS), text_color=COLORS["gray"],
            anchor="w").pack(side="left", padx=4, pady=4)

        self._output = ctk.CTkTextbox(
            right, fg_color=COLORS["bg_card"],
            text_color=COLORS["white"],
            font=ctk.CTkFont(*FONT_MONO_SM),
            corner_radius=0, border_width=0,
            state="disabled", wrap="none",
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["cyan_dim"])
        self._output.pack(fill="both", expand=True)

        self._status_bar = ctk.CTkFrame(
            self._win, fg_color=COLORS["bg_panel"], height=28,
            corner_radius=0, border_width=1, border_color=COLORS["border"])
        self._status_bar.pack(fill="x")
        self._status_bar.pack_propagate(False)

        self._lbl_status = ctk.CTkLabel(
            self._status_bar, text="",
            font=ctk.CTkFont(*FONT_MONO_XS), text_color=COLORS["gray"],
            anchor="w")
        self._lbl_status.pack(side="left", fill="x", expand=True, padx=4)

        self._lbl_time = ctk.CTkLabel(
            self._status_bar, text="",
            font=ctk.CTkFont(*FONT_MONO_XS), text_color=COLORS["gray"])
        self._lbl_time.pack(side="right", padx=8)

    def _build_detail_pane(self):
        df = self._detail_frame

        top_row = ctk.CTkFrame(df, fg_color="transparent")
        top_row.pack(fill="x", padx=12, pady=(10, 0))

        self._detail_cat_badge = ctk.CTkLabel(
            top_row, text="",
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            corner_radius=4, height=22,
            fg_color=COLORS["bg_card"], text_color=COLORS["gray"])
        self._detail_cat_badge.pack(side="left", padx=(0, 10))

        self._detail_path = ctk.CTkLabel(
            top_row, text="",
            font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["gray"], anchor="w")
        self._detail_path.pack(side="left", fill="x", expand=True)

        self._detail_name = ctk.CTkLabel(
            df, text="",
            font=ctk.CTkFont(FONT_MONO_BOLD[0], FONT_MONO_BOLD[1] + 2, "bold"),
            text_color=COLORS["white"], anchor="w")
        self._detail_name.pack(fill="x", padx=12, pady=(3, 0))

        # Content textbox: description for categories/classes, source code for tests
        self._detail_content = ctk.CTkTextbox(
            df, fg_color=COLORS["bg_card"],
            text_color=COLORS["text_dim"],
            font=ctk.CTkFont(*FONT_MONO_SM),
            height=130, corner_radius=4, border_width=0,
            state="disabled", wrap="word",
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["cyan_dim"])
        self._detail_content.pack(fill="x", padx=8, pady=(4, 0))

        bot_row = ctk.CTkFrame(df, fg_color="transparent")
        bot_row.pack(fill="x", padx=12, pady=(4, 10))

        self._detail_subtitle = ctk.CTkLabel(
            bot_row, text="",
            font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["gray"], anchor="w")
        self._detail_subtitle.pack(side="left", fill="x", expand=True, pady=4)

        self._btn_run_this = ctk.CTkButton(
            bot_row, text="Run This Test", width=130, height=28,
            fg_color=COLORS["bg_card"], hover_color=COLORS["cyan_dim"],
            text_color=COLORS["gray"],
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            command=self._run_this_test, state="disabled")
        self._btn_run_this.pack(side="right")

    def _set_content(self, text: str, wrap: str = "word"):
        self._detail_content.configure(state="normal", wrap=wrap)
        self._detail_content.delete("1.0", "end")
        self._detail_content.insert("1.0", text)
        self._detail_content.configure(state="disabled")

    # ── Effects ───────────────────────────────────────────────────────────────

    def _init_effects(self):
        try:
            from forge.config import ForgeConfig
            from forge.ui.effects import EffectsEngine, WidgetGlow
            fx = ForgeConfig().get("effects_enabled", True)
            self._effects = EffectsEngine(self._win, enabled=fx)
            self._effects.register_card(self._top_bar, self._top_sep)
            self._effects.register_card(self._left_panel)
            self._effects.register_card(self._status_bar)
            self._effects.register_card(self._detail_frame)
            self._effects.register_window_edge_glow(self._win)
            self._effects.register_window_border_color(self._win)
            self._effects.register_widget(self._progress, WidgetGlow.PROGRESS)
            self._effects.start()
        except Exception:
            pass

    # ── Tree ──────────────────────────────────────────────────────────────────

    def _build_tree(self):
        for w in self._tree_scroll.winfo_children():
            w.destroy()
        self._status_labels.clear()

        total = sum(len(m) for cls in self._tree_data.values()
                    for m in cls.values())
        self._lbl_total.configure(text=f"{total} tests")

        for cat_name, cat_color, _ in _CATEGORIES:
            files_in_cat = [
                f for f, c in self._file_cats.items()
                if c == cat_name and f in self._tree_data
            ]
            if not files_in_cat:
                continue
            cat_count = sum(
                len(m) for f in files_in_cat
                for m in self._tree_data[f].values()
            )
            self._build_cat_section(cat_name, cat_color, cat_count, files_in_cat)

    def _build_cat_section(self, cat_name, cat_color, count, files):
        hdr = ctk.CTkFrame(
            self._tree_scroll, fg_color=COLORS["bg_card"],
            corner_radius=6, height=36, cursor="hand2")
        hdr.pack(fill="x", padx=4, pady=(8, 2))
        hdr.pack_propagate(False)

        stripe = ctk.CTkFrame(hdr, fg_color=cat_color, width=4, corner_radius=2)
        stripe.pack(side="left", fill="y", padx=(6, 8), pady=6)

        ctk.CTkLabel(
            hdr, text=cat_name,
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            text_color=COLORS["white"], anchor="w"
        ).pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            hdr, text=str(count),
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            text_color=cat_color, width=44, anchor="e"
        ).pack(side="right", padx=12)

        def on_cat_click(e, cn=cat_name):
            self._show_category_detail(cn)
        for w in (hdr, stripe):
            w.bind("<Button-1>", on_cat_click)

        for fname in files:
            self._build_file_row(fname)

    def _build_file_row(self, fname: str):
        classes = self._tree_data.get(fname, {})
        total = sum(len(m) for m in classes.values())
        base = (fname.replace("integration/", "")
                     .replace("test_", "").replace(".py", ""))
        display = base.replace("_", " ").title()

        hdr = ctk.CTkFrame(
            self._tree_scroll, fg_color=COLORS["bg_panel"],
            corner_radius=4, height=26, cursor="hand2")
        hdr.pack(fill="x", padx=(16, 4), pady=(1, 0))
        hdr.pack_propagate(False)

        arrow = ctk.CTkLabel(
            hdr, text=">",
            font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["cyan_dim"], width=14)
        arrow.pack(side="left", padx=(6, 2))

        ctk.CTkLabel(
            hdr, text=display,
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["text_dim"], anchor="w"
        ).pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            hdr, text=str(total),
            font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["gray"], width=24
        ).pack(side="right", padx=4)

        file_st = ctk.CTkLabel(
            hdr, text="", font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["gray"], width=20)
        file_st.pack(side="right")
        self._status_labels[(fname, None, None)] = file_st

        container = ctk.CTkFrame(self._tree_scroll, fg_color="transparent")
        container.pack(fill="x", padx=0, pady=0, after=hdr)
        container.pack_forget()

        def toggle(e=None, f=fname, c=container, a=arrow, h=hdr):
            if self._expanded.get(f, False):
                c.pack_forget()
                self._expanded[f] = False
                a.configure(text=">")
            else:
                c.pack(fill="x", padx=0, pady=0, after=h)
                self._expanded[f] = True
                a.configure(text="v")

        for w in (hdr, arrow):
            w.bind("<Button-1>", toggle)

        for cls_name, methods in classes.items():
            self._build_class_section(container, fname, cls_name, methods)

    def _build_class_section(self, parent, fname, cls_name, methods):
        if cls_name == _MODULE_LEVEL:
            cls_display = "module-level tests"
        else:
            cls_display = re.sub(
                r"(?<!^)(?=[A-Z])", " ",
                cls_name.replace("Test", "")
            ).strip()

        cls_row = ctk.CTkFrame(parent, fg_color="transparent",
                               height=20, cursor="hand2")
        cls_row.pack(fill="x", padx=(12, 2), pady=(3, 0))
        cls_row.pack_propagate(False)

        cls_lbl = ctk.CTkLabel(
            cls_row, text=f"  {cls_display}",
            font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["cyan_dim"], anchor="w")
        cls_lbl.pack(side="left", fill="x", expand=True)

        def on_cls(e, f=fname, c=cls_name):
            self._show_class_detail(f, c)
        for w in (cls_row, cls_lbl):
            w.bind("<Button-1>", on_cls)

        for method_name in methods:
            self._build_test_row(parent, fname, cls_name, method_name)

    def _build_test_row(self, parent, fname, cls_name, method_name):
        row = ctk.CTkFrame(parent, fg_color="transparent",
                           height=20, cursor="hand2")
        row.pack(fill="x", padx=(24, 2), pady=0)
        row.pack_propagate(False)

        st_txt, st_key = _ST_PENDING
        status_lbl = ctk.CTkLabel(
            row, text=st_txt,
            font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS[st_key], width=20)
        status_lbl.pack(side="left", padx=(0, 4))

        name_lbl = ctk.CTkLabel(
            row, text=_humanize(method_name),
            font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["text_dim"], anchor="w")
        name_lbl.pack(side="left", fill="x", expand=True)

        self._status_labels[(fname, cls_name, method_name)] = status_lbl

        def on_click(e, f=fname, c=cls_name, m=method_name, r=row):
            self._select_test(f, c, m, r)
        def on_enter(e, nl=name_lbl):
            nl.configure(text_color=COLORS["white"])
        def on_leave(e, nl=name_lbl):
            nl.configure(text_color=COLORS["text_dim"])

        for w in (row, name_lbl, status_lbl):
            w.bind("<Button-1>", on_click)
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)

    # ── Detail pane content ───────────────────────────────────────────────────

    def _select_test(self, fname, cls_name, method_name, row_widget):
        if self._selected_row_widget:
            try:
                self._selected_row_widget.configure(fg_color="transparent")
            except Exception:
                pass
        row_widget.configure(fg_color=COLORS["border"])
        self._selected_row_widget = row_widget
        self._selected_key = (fname, cls_name, method_name)
        self._run_selection = {(fname, cls_name, method_name)}
        self._show_test_detail(fname, cls_name, method_name)

    def _show_welcome(self):
        total = sum(len(m) for cls in self._tree_data.values()
                    for m in cls.values())
        n_cats = len(set(self._file_cats.values()))
        self._update_header(
            badge="FORGE", badge_color=COLORS["cyan"],
            name=f"{total} tests across {n_cats} categories",
            path="Click a test to see its source  ·  Ctrl+R runs all",
            subtitle="Select a test or category  ·  Ctrl+R to run all",
            run_enabled=False,
        )
        self._set_content(
            "FORGE BREAK tests verify AI reliability and response quality.\n"
            "CRUCIBLE tests verify security scanning catches real threats.\n"
            "INTEGRATION tests verify Forge survives chaos and crashes.\n"
            "SUITE tests verify every subsystem works correctly.\n\n"
            "Click any category header to see exactly what it protects.\n"
            "Click any test to see its source code and run it individually.\n\n"
            "Individual test runs capture full output — assertions, values, "
            "and error details are shown in the console below."
        )

    def _show_category_detail(self, cat_name: str):
        meta = _CATEGORY_META.get(cat_name, {})
        _, cat_color, _ = next(
            (c for c in _CATEGORIES if c[0] == cat_name),
            (cat_name, COLORS["gray"], [])
        )
        files_in_cat = [f for f, c in self._file_cats.items() if c == cat_name]
        count = sum(
            len(m) for f in files_in_cat
            for m in self._tree_data.get(f, {}).values()
        )
        self._selected_key = None
        self._run_selection.clear()
        self._update_header(
            badge=cat_name, badge_color=cat_color,
            name=f"{count} tests",
            path=f"{len(files_in_cat)} test files",
            subtitle=meta.get("subtitle", ""),
            run_enabled=False,
        )
        self._set_content(meta.get("description", ""))

    def _show_class_detail(self, fname: str, cls_name: str):
        cat_name = self._file_cats.get(fname, "SUITE")
        _, cat_color, _ = next(
            (c for c in _CATEGORIES if c[0] == cat_name),
            (cat_name, COLORS["gray"], [])
        )
        cls_doc = self._class_docs.get((fname, cls_name), "")
        methods = self._tree_data.get(fname, {}).get(cls_name, {})

        if cls_name == _MODULE_LEVEL:
            cls_display = "Module-level tests"
        else:
            cls_display = re.sub(
                r"(?<!^)(?=[A-Z])", " ",
                cls_name.replace("Test", "")
            ).strip()

        self._selected_key = (fname, cls_name, None)
        self._run_selection = {(fname, cls_name, m) for m in methods}
        self._update_header(
            badge=cat_name, badge_color=cat_color,
            name=cls_display,
            path=f"tests/{fname}  ·  {cls_name}",
            subtitle=f"{len(methods)} tests in this group",
            run_enabled=True,
        )
        desc = cls_doc if cls_doc else f"{len(methods)} tests in {cls_display}."
        self._set_content(desc)

    def _show_test_detail(self, fname: str, cls_name: str, method_name: str):
        cat_name = self._file_cats.get(fname, "SUITE")
        _, cat_color, _ = next(
            (c for c in _CATEGORIES if c[0] == cat_name),
            (cat_name, COLORS["gray"], [])
        )
        info = (self._tree_data.get(fname, {})
                               .get(cls_name, {})
                               .get(method_name, {}))
        method_doc = info.get("doc", "") if isinstance(info, dict) else ""
        src         = info.get("src", "") if isinstance(info, dict) else ""

        self._update_header(
            badge=cat_name, badge_color=cat_color,
            name=_humanize(method_name),
            path=f"tests/{fname}  ·  {cls_name}",
            subtitle=method_name,
            run_enabled=True,
        )

        # Content: docstring (if any) then source code
        parts: list[str] = []
        if method_doc:
            parts.append(f'"""{method_doc}"""\n\n')
        if src:
            parts.append(src)
        else:
            parts.append("(source not available)")

        self._detail_content.configure(wrap="none")
        self._set_content("".join(parts), wrap="none")

    def _update_header(self, badge, badge_color, name, path,
                       subtitle, run_enabled):
        dark = badge_color not in (COLORS.get("gray", ""), "#606060")
        self._detail_cat_badge.configure(
            text=f"  {badge}  ",
            fg_color=badge_color,
            text_color=COLORS["bg_dark"] if dark else COLORS["white"])
        self._detail_path.configure(text=path)
        self._detail_name.configure(text=name)
        self._detail_subtitle.configure(text=subtitle)
        self._btn_run_this.configure(
            state="normal" if run_enabled else "disabled",
            fg_color=COLORS["cyan_dim"] if run_enabled else COLORS["bg_card"],
            text_color=COLORS["bg_dark"] if run_enabled else COLORS["gray"],
        )

    # ── Run controls ──────────────────────────────────────────────────────────

    def _project_root(self) -> Path:
        if self._tests_dir:
            return self._tests_dir.parent
        return Path.cwd()

    def _run_all(self):
        if self._running:
            return
        self._reset_counters()
        self._clear_output()
        self._append_output("Running all tests...\n\n")
        cmd = [sys.executable, "-m", "pytest", "tests/",
               "-v", "--tb=short", "--no-header", "-p", "no:warnings",
               "--color=no"]
        total = sum(len(m) for cls in self._tree_data.values()
                    for m in cls.values())
        self._launch(cmd, total_hint=total)

    def _run_selected(self):
        if self._running or not self._run_selection:
            return
        self._reset_counters()
        self._clear_output()
        node_ids = self._selection_to_node_ids(self._run_selection)
        if not node_ids:
            return
        n = len(node_ids)
        self._append_output(f"Running {n} test{'s' if n != 1 else ''}...\n\n")
        cmd = [sys.executable, "-m", "pytest"] + node_ids + [
            "-v", "-s", "--tb=short", "--no-header",
            "-p", "no:warnings", "--color=no"]
        self._launch(cmd, total_hint=n)

    def _run_this_test(self):
        if self._running or not self._selected_key:
            return
        fname, cls_name, method_name = self._selected_key
        self._reset_counters()
        self._clear_output()

        if method_name is None:
            self._run_selection = {
                (fname, cls_name, m)
                for m in self._tree_data.get(fname, {}).get(cls_name, {})
            }
            self._run_selected()
            return

        node_id = self._make_node_id(fname, cls_name, method_name)
        self._append_output(f"Running: {node_id}\n\n")
        cmd = [sys.executable, "-m", "pytest", node_id,
               "-v", "-s", "--tb=long", "--no-header",
               "-p", "no:warnings", "--color=no"]
        self._launch(cmd, total_hint=1)

    def _make_node_id(self, fname, cls_name, method_name) -> str:
        base = f"tests/{fname}"
        if cls_name == _MODULE_LEVEL:
            return f"{base}::{method_name}"
        return f"{base}::{cls_name}::{method_name}"

    def _selection_to_node_ids(self, selection: set) -> list[str]:
        return sorted(
            self._make_node_id(f, c, m) for f, c, m in selection
        )

    def _stop_run(self):
        self._stop_requested = True
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass

    def _launch(self, cmd: list, total_hint: int = 1):
        self._running = True
        self._stop_requested = False
        self._start_time = time.monotonic()
        self._count_total = max(total_hint, 1)
        self._btn_run_all.configure(state="disabled")
        self._btn_run_sel.configure(state="disabled")
        self._btn_stop.configure(state="normal", text_color=COLORS["white"])
        self._lbl_status.configure(
            text="  Running...", text_color=COLORS["cyan"])
        self._progress.set(0)

        def worker():
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=str(self._project_root()),
                    **_SP_FLAGS,
                )
                self._proc = proc
                for line in proc.stdout:
                    if self._stop_requested:
                        break
                    if not self._closed:
                        self._win.after(0, self._process_line, line)
                proc.wait()
            except Exception as exc:
                if not self._closed:
                    self._win.after(0, self._append_output, f"\nError: {exc}\n")
            finally:
                if not self._closed:
                    self._win.after(0, self._on_run_complete)

        threading.Thread(target=worker, daemon=True).start()

    def _process_line(self, line: str):
        self._append_output(line)

        m = _RE_RESULT.match(line)
        if m:
            raw_fname, cls_or_method, maybe_method, result = m.groups()
            fname = raw_fname.replace("\\", "/").replace("tests/", "", 1)
            cls_name    = cls_or_method if maybe_method else _MODULE_LEVEL
            method_name = maybe_method or cls_or_method

            status_map = {
                "PASSED":  (_ST_PASSED,  "pass"),
                "FAILED":  (_ST_FAILED,  "fail"),
                "SKIPPED": (_ST_SKIPPED, "skip"),
                "ERROR":   (_ST_ERROR,   "fail"),
            }
            st, counter = status_map.get(result, (_ST_PENDING, ""))
            if counter == "pass":   self._count_pass += 1
            elif counter == "fail": self._count_fail += 1
            elif counter == "skip": self._count_skip += 1

            lbl = self._status_labels.get((fname, cls_name, method_name))
            if lbl:
                try:
                    lbl.configure(text=st[0], text_color=COLORS[st[1]])
                except Exception:
                    pass

            done = self._count_pass + self._count_fail + self._count_skip
            self._progress.set(min(done / self._count_total, 1.0))
            self._lbl_pass.configure(text=str(self._count_pass))
            self._lbl_fail.configure(text=str(self._count_fail))
            self._lbl_skip.configure(text=str(self._count_skip))

        m2 = _RE_SUMMARY.match(line.strip())
        if m2:
            self._lbl_status.configure(text=f"  {m2.group(1)}")

    def _on_run_complete(self):
        self._running = False
        self._proc = None
        elapsed = time.monotonic() - self._start_time
        self._lbl_time.configure(text=f"{elapsed:.1f}s")
        self._btn_run_all.configure(state="normal")
        self._btn_run_sel.configure(state="normal")
        self._btn_stop.configure(state="disabled", text_color=COLORS["gray"])
        self._progress.set(1.0)

        if self._count_fail > 0:
            self._lbl_status.configure(
                text=f"  {self._count_fail} failed  ·  {self._count_pass} passed",
                text_color=COLORS["red"])
        else:
            self._lbl_status.configure(
                text=f"  All {self._count_pass} tests passed",
                text_color=COLORS["green"])

    def _reset_counters(self):
        self._count_pass = self._count_fail = self._count_skip = 0
        self._lbl_pass.configure(text="0")
        self._lbl_fail.configure(text="0")
        self._lbl_skip.configure(text="0")
        self._progress.set(0)

    # ── Output console ────────────────────────────────────────────────────────

    def _clear_output(self):
        self._output.configure(state="normal")
        self._output.delete("1.0", "end")
        self._output.configure(state="disabled")

    def _append_output(self, text: str):
        self._output.configure(state="normal")
        self._output.insert("end", text)
        self._output.see("end")
        self._output.configure(state="disabled")

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _apply_theme(self, _=None):
        global COLORS
        COLORS = get_colors()
        try:
            recolor_widget_tree(self._win, COLORS)
        except Exception:
            pass

    # ── Close ─────────────────────────────────────────────────────────────────

    def _on_close(self):
        self._closed = True
        # Withdraw immediately — visually instant
        try:
            self._win.withdraw()
        except Exception:
            pass

        self._stop_requested = True
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass

        try:
            remove_theme_listener(self._theme_cb)
        except Exception:
            pass

        if self._effects:
            try:
                self._effects.stop()
            except Exception:
                pass

        try:
            self._win.destroy()
        except Exception:
            pass
