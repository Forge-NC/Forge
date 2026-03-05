"""Forge Settings Dialog — modal settings panel for the Neural Cortex dashboard.

CTkToplevel with tabbed categories covering all config.yaml settings.
Saves directly to config.yaml and signals the engine to reload.
"""

import json
import logging
import threading
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

try:
    import customtkinter as ctk
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from forge.config import DEFAULTS, ForgeConfig
from forge.ui.themes import (
    get_colors, get_fonts, get_theme, set_theme, list_themes, THEME_LABELS,
    add_theme_listener, remove_theme_listener, recolor_widget_tree,
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

_SAFETY_LABELS = ["Unleashed", "Smart Guard", "Confirm Writes", "Locked Down"]
_SAFETY_DESCS = [
    "No restrictions. Full file system and shell access.",
    "Blocks dangerous shell patterns (rm -rf, etc). Recommended.",
    "Prompts for confirmation before any file write or shell command.",
    "Read-only mode. No file writes, no shell commands.",
]


class ForgeSettingsDialog:
    """Modal settings dialog for the Forge Neural Cortex dashboard."""

    def __init__(self, parent: "ctk.CTk", config: ForgeConfig):
        if not HAS_CTK:
            return

        self._config = config
        self._widgets: dict[str, tuple] = {}
        self._parent = parent
        self._original_theme = get_theme()  # for Cancel revert
        self._original_effects = bool(config.get("effects_enabled", True))
        self._effects = None

        # ── Window ──
        self._win = ctk.CTkToplevel(parent)
        self._win.title("Forge Settings")
        self._win.geometry("540x600")
        self._win.minsize(480, 500)
        self._win.configure(fg_color=COLORS["bg_dark"])
        self._win.transient(parent)
        self._win.grab_set()
        self._win.resizable(True, True)
        self._win.protocol("WM_DELETE_WINDOW", self._close)

        # Register for live theme hot-swap
        self._theme_cb = lambda cm: self._win.after(
            0, self._apply_theme, cm)
        add_theme_listener(self._theme_cb)

        # Center on parent
        self._win.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width() - 540) // 2
        py = parent.winfo_y() + (parent.winfo_height() - 600) // 2
        self._win.geometry(f"+{max(0, px)}+{max(0, py)}")

        try:
            ico = Path(__file__).parent / "assets" / "forge.ico"
            if ico.exists():
                self._win.iconbitmap(str(ico))
        except Exception:
            pass

        # ── Header ──
        header = ctk.CTkFrame(self._win, fg_color=COLORS["bg_panel"],
                              corner_radius=0, height=40,
                              border_width=1, border_color=COLORS["border"])
        header.pack(fill="x")
        header.pack_propagate(False)
        self._header = header
        ctk.CTkLabel(header, text="  Settings",
                     font=ctk.CTkFont(*FONT_TITLE),
                     text_color=COLORS["cyan"]).pack(side="left", padx=8, pady=6)

        self._header_divider = ctk.CTkFrame(
            self._win, fg_color=COLORS["border"],
            height=1, corner_radius=0)
        self._header_divider.pack(fill="x")

        # ── Tabs ──
        self._tabs = ctk.CTkTabview(
            self._win, fg_color=COLORS["bg_dark"],
            segmented_button_fg_color=COLORS["bg_panel"],
            segmented_button_selected_color=COLORS["cyan_dim"],
            segmented_button_selected_hover_color=COLORS["cyan"],
            segmented_button_unselected_color=COLORS["bg_card"],
            segmented_button_unselected_hover_color=COLORS["bg_panel"],
            text_color=COLORS["white"],
            corner_radius=6)
        self._tabs.pack(fill="both", expand=True, padx=8, pady=(4, 0))

        for name in ["Safety", "Models", "Context", "Agent", "Voice", "UI", "Forge", "License", "Nightly", "Telemetry"]:
            self._tabs.add(name)

        self._build_safety_tab()
        self._build_models_tab()
        self._build_context_tab()
        self._build_agent_tab()
        self._build_voice_tab()
        self._build_ui_tab()
        self._build_forge_tab()
        self._build_license_tab()
        self._build_nightly_tab()
        self._build_telemetry_tab()

        # ── Button row ──
        btn_frame = ctk.CTkFrame(self._win, fg_color=COLORS["bg_dark"],
                                 height=50)
        btn_frame.pack(fill="x", padx=8, pady=(4, 8))

        ctk.CTkButton(btn_frame, text="Reset Defaults", width=120,
                      fg_color=COLORS["bg_card"],
                      hover_color=COLORS["bg_panel"],
                      text_color=COLORS["gray"],
                      command=self._on_reset).pack(side="left", padx=4)

        ctk.CTkButton(btn_frame, text="Save", width=90,
                      fg_color=COLORS["cyan_dim"],
                      hover_color=COLORS["cyan"],
                      text_color=COLORS["bg_dark"],
                      font=ctk.CTkFont(*FONT_MONO_BOLD),
                      command=self._on_save).pack(side="right", padx=4)

        ctk.CTkButton(btn_frame, text="Cancel", width=90,
                      fg_color=COLORS["bg_card"],
                      hover_color=COLORS["bg_panel"],
                      text_color=COLORS["white"],
                      command=self._close).pack(side="right", padx=4)

        self._init_effects()

    def _init_effects(self):
        """Set up visual effects for the settings window."""
        try:
            from forge.ui.effects import EffectsEngine, WidgetGlow
            fx_enabled = self._config.get("effects_enabled", True)
            self._effects = EffectsEngine(self._win, enabled=fx_enabled)
            # Register header with divider (border glow + hover + pulse)
            self._effects.register_card(self._header, self._header_divider)
            # Crackling edge glow on window
            self._effects.register_window_edge_glow(self._win)
            # OS-level window border color animation
            self._effects.register_window_border_color(self._win)
            # Register all sliders for widget glow
            for key, (wtype, widget) in self._widgets.items():
                if wtype == "slider":
                    self._effects.register_widget(
                        widget, WidgetGlow.SLIDER)
            self._effects.start()
        except Exception:
            pass

    # ── Tab builders ──────────────────────────────────────────────

    def _scrollable_tab(self, name: str) -> "ctk.CTkScrollableFrame":
        """Wrap a tab's content area in a scrollable frame."""
        tab = self._tabs.tab(name)
        tab.configure(fg_color=COLORS["bg_dark"])
        scroll = ctk.CTkScrollableFrame(
            tab, fg_color=COLORS["bg_dark"],
            scrollbar_button_color=COLORS["bg_panel"],
            scrollbar_button_hover_color=COLORS["cyan_dim"],
            corner_radius=0)
        scroll.pack(fill="both", expand=True)
        return scroll

    def _build_safety_tab(self):
        tab = self._scrollable_tab("Safety")

        # Safety level segmented button
        row = self._add_row(tab, "Safety Level")
        current = int(self._config.get("safety_level", 1))
        seg_var = ctk.StringVar(value=str(current))
        seg = ctk.CTkSegmentedButton(
            row, values=["0", "1", "2", "3"],
            variable=seg_var,
            font=ctk.CTkFont(*FONT_MONO_SM),
            fg_color=COLORS["bg_card"],
            selected_color=COLORS["cyan_dim"],
            selected_hover_color=COLORS["cyan"],
            unselected_color=COLORS["bg_panel"],
            unselected_hover_color=COLORS["bg_card"],
            text_color=COLORS["white"],
            width=240)
        seg.pack(side="right")
        self._widgets["safety_level"] = ("segmented", seg_var)

        # Description label that updates with selection
        desc_label = ctk.CTkLabel(tab, text="",
                                  font=ctk.CTkFont(*FONT_MONO_SM),
                                  text_color=COLORS["gray"],
                                  wraplength=460, justify="left")
        desc_label.pack(fill="x", padx=16, pady=(0, 4))

        def _update_desc(val):
            idx = int(val)
            desc_label.configure(
                text=f"  {_SAFETY_LABELS[idx]}: {_SAFETY_DESCS[idx]}")
        seg.configure(command=_update_desc)
        _update_desc(str(current))

        self._add_switch(tab, "sandbox_enabled", "Filesystem Sandbox")

        # Sandbox roots
        row2 = self._add_row(tab, "Sandbox Paths")
        roots = self._config.get("sandbox_roots", [])
        self._sandbox_paths = list(roots) if isinstance(roots, list) else []

        path_frame = ctk.CTkFrame(tab, fg_color=COLORS["bg_dark"])
        path_frame.pack(fill="x", padx=16, pady=(0, 4))

        self._paths_text = ctk.CTkTextbox(
            path_frame, height=80,
            font=ctk.CTkFont(*FONT_MONO_SM),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["white"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=4,
            state="disabled")
        self._paths_text.pack(fill="x", side="top")
        self._refresh_paths_display()

        path_btns = ctk.CTkFrame(path_frame, fg_color="transparent")
        path_btns.pack(fill="x", pady=(2, 0))
        ctk.CTkButton(path_btns, text="Add Directory...", width=120,
                      fg_color=COLORS["bg_card"],
                      hover_color=COLORS["cyan_dim"],
                      text_color=COLORS["white"],
                      font=ctk.CTkFont(*FONT_MONO_SM),
                      command=self._add_sandbox_path).pack(side="left")
        ctk.CTkButton(path_btns, text="Remove Last", width=100,
                      fg_color=COLORS["bg_card"],
                      hover_color=COLORS["red"],
                      text_color=COLORS["white"],
                      font=ctk.CTkFont(*FONT_MONO_SM),
                      command=self._remove_sandbox_path).pack(side="left", padx=4)

        self._widgets["sandbox_roots"] = ("pathlist", self._sandbox_paths)

        # ── Output & Data Security ──
        ctk.CTkFrame(tab, fg_color=COLORS["border"], height=1
                     ).pack(fill="x", padx=16, pady=(10, 6))
        ctk.CTkLabel(tab, text="Output & Data Security",
                     font=ctk.CTkFont(*FONT_MONO_BOLD),
                     text_color=COLORS["cyan"]
                     ).pack(anchor="w", padx=16, pady=(4, 2))

        self._add_switch(tab, "output_scanning", "Scan LLM Output")
        self._add_desc(tab,
            "Detect secrets and threats in model responses "
            "(respects safety level)")
        self._add_switch(tab, "rag_scanning", "Scan RAG Retrievals")
        self._add_desc(tab,
            "Check recalled code for threats before context injection "
            "(respects safety level)")
        self._add_switch(tab, "rate_limiting", "Tool Rate Limiting")
        self._add_desc(tab,
            "Circuit breaker for runaway tool call loops "
            "(limits scale with safety level)")
        self._add_slider(tab, "data_retention_days", "Data Retention",
                         0, 365, 365, fmt="{:.0f} days")
        self._add_desc(tab,
            "Auto-prune old forensics/exports on boot (0 = keep forever)")

        # ── Threat Intelligence ──
        ctk.CTkFrame(tab, fg_color=COLORS["border"], height=1
                     ).pack(fill="x", padx=16, pady=(10, 6))
        ctk.CTkLabel(tab, text="Threat Intelligence",
                     font=ctk.CTkFont(*FONT_MONO_BOLD),
                     text_color=COLORS["cyan"]
                     ).pack(anchor="w", padx=16, pady=(4, 2))

        self._add_switch(tab, "threat_signatures_enabled",
                         "External Signatures")
        self._add_desc(tab,
            "Load updateable threat patterns (extends hardcoded patterns)")
        self._add_switch(tab, "threat_auto_update",
                         "Auto-Update Signatures")
        self._add_desc(tab,
            "Check for new signatures on startup "
            "(interval scales with safety level)")

    def _build_models_tab(self):
        tab = self._scrollable_tab("Models")

        current_model = str(self._config.get("default_model", ""))
        current_small = str(self._config.get("small_model", ""))

        self._model_menu = self._add_dropdown(
            tab, "default_model", "Primary Model",
            [current_model] if current_model else ["(select)"])
        self._small_menu = self._add_dropdown(
            tab, "small_model", "Small Model (Router)",
            [current_small if current_small else "(none)"])

        self._add_switch(tab, "router_enabled", "Enable Model Router")
        self._add_desc(tab, "Routes simple tasks to the smaller model to save time")
        self._add_entry(tab, "embedding_model", "Embedding Model")
        self._add_desc(tab,
            "Model for semantic code search (/index, /recall). "
            "Pull with: ollama pull nomic-embed-text")
        self._add_entry(tab, "ollama_url", "Ollama URL")

        # Refresh models button
        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(8, 0))
        ctk.CTkButton(btn_row, text="Refresh Models", width=130,
                      fg_color=COLORS["bg_card"],
                      hover_color=COLORS["cyan_dim"],
                      text_color=COLORS["white"],
                      font=ctk.CTkFont(*FONT_MONO_SM),
                      command=self._fetch_models).pack(side="right")

        # ── Manage Models button ──
        ctk.CTkFrame(tab, fg_color=COLORS["border"], height=1
                     ).pack(fill="x", padx=16, pady=(10, 6))

        ctk.CTkButton(tab, text="Manage Models...", height=34,
                      fg_color=COLORS["cyan_dim"],
                      hover_color=COLORS["cyan"],
                      text_color=COLORS["bg_dark"],
                      font=ctk.CTkFont(*FONT_MONO_BOLD),
                      command=self._open_model_manager
                      ).pack(fill="x", padx=16, pady=(2, 0))
        self._add_desc(tab,
            "Browse Ollama's model library, pull new models, "
            "delete unused, set primary/router")

        # Auto-fetch models on open
        self._fetch_models()

    def _build_context_tab(self):
        tab = self._scrollable_tab("Context")

        self._add_slider(tab, "context_safety_margin", "Safety Margin",
                         0.50, 1.00, 50, fmt="{:.0%}")
        self._add_desc(tab,
            "Fraction of model's context window to actually use "
            "(0.85 = use 85%, leaving headroom for safety)")
        self._add_slider(tab, "swap_threshold_pct", "Swap Threshold",
                         50, 100, 50, fmt="{:.0f}%")
        self._add_desc(tab,
            "When context fills past this %, older messages are swapped "
            "out and replaced with a summary")
        self._add_entry(tab, "swap_summary_target_tokens",
                        "Context Swap Summary")
        self._add_desc(tab,
            "Target token count for the auto-generated summary when "
            "context is swapped out (~500 is a good default)")

        # Continuity Grade settings
        ctk.CTkLabel(tab, text="  Continuity Grade",
                     font=ctk.CTkFont(*FONT_MONO_BOLD),
                     text_color=COLORS["cyan_dim"],
                     anchor="w").pack(fill="x", padx=16, pady=(8, 2))
        self._add_switch(tab, "continuity_enabled", "Continuity Grade")
        self._add_desc(tab,
            "Measure context quality across swaps (A-F grade) and "
            "auto-recover when quality drops")
        self._add_slider(tab, "continuity_threshold",
                         "Recovery Threshold", 0, 100, 100, fmt="{:.0f}")
        self._add_desc(tab,
            "Score below which mild recovery triggers (re-read files + "
            "semantic recalls)")
        self._add_slider(tab, "continuity_aggressive_threshold",
                         "Aggressive Threshold", 0, 100, 100, fmt="{:.0f}")
        self._add_desc(tab,
            "Score below which aggressive recovery triggers (full "
            "rebuild + subtask recalls)")

        # ── Adaptive Model Intelligence ──
        ctk.CTkFrame(tab, fg_color=COLORS["border"], height=1).pack(
            fill="x", padx=16, pady=(10, 6))
        ctk.CTkLabel(tab, text="  Model Intelligence",
                     font=ctk.CTkFont(*FONT_MONO_BOLD),
                     text_color=COLORS["cyan_dim"],
                     anchor="w").pack(fill="x", padx=16, pady=(4, 2))
        self._add_switch(tab, "ami_enabled", "Adaptive Model Intelligence")
        self._add_desc(tab,
            "Self-healing orchestration: detect failures, force "
            "compliance, auto-recover")
        self._add_switch(tab, "ami_constrained_fallback",
                         "Constrained Decoding Fallback")
        self._add_desc(tab,
            "Force tool-call JSON format when native tool calling fails")

    def _build_agent_tab(self):
        tab = self._scrollable_tab("Agent")

        self._add_entry(tab, "max_agent_iterations", "Max Iterations")
        self._add_desc(tab, "Maximum tool-use loops before the agent stops")
        self._add_entry(tab, "shell_timeout", "Shell Timeout (s)")
        self._add_entry(tab, "shell_max_output", "Shell Max Output")
        self._add_dropdown(tab, "plan_mode", "Plan Mode",
                           ["off", "manual", "auto", "always"])
        self._add_entry(tab, "plan_auto_threshold", "Auto-Plan Threshold")
        self._add_desc(tab,
            "Complexity score above which auto-plan triggers (1-10 scale)")
        self._add_switch(tab, "dedup_enabled", "Tool Deduplication")
        self._add_slider(tab, "dedup_threshold", "Dedup Threshold",
                         0.50, 1.00, 50, fmt="{:.2f}")
        self._add_desc(tab,
            "How similar two tool calls must be to suppress the duplicate "
            "(higher = stricter)")
        self._add_entry(tab, "dedup_window", "Dedup Window")
        self._add_desc(tab, "Number of recent tool calls to check for duplicates")
        self._add_switch(tab, "cache_enabled", "File Cache")

    def _build_voice_tab(self):
        tab = self._scrollable_tab("Voice")

        self._add_dropdown(tab, "tts_engine", "TTS Engine",
                           ["edge", "local"])
        self._add_desc(tab,
            "edge = Microsoft neural voices (high quality, requires internet). "
            "local = System voices via pyttsx3 (fully offline, lower quality).")
        self._add_dropdown(tab, "voice_model", "Whisper Model",
                           ["tiny", "base", "small", "medium"])
        self._add_desc(tab, "Larger models are more accurate but slower")
        self._add_slider(tab, "voice_vox_threshold", "VOX Threshold",
                         0.00, 0.10, 20, fmt="{:.3f}")
        self._add_desc(tab,
            "Audio level that triggers voice recording "
            "(lower = more sensitive, 0 = always listening)")
        self._add_slider(tab, "voice_silence_timeout", "Silence Timeout (s)",
                         0.5, 5.0, 45, fmt="{:.1f}s")
        self._add_desc(tab, "Seconds of silence before voice recording stops")

    def _build_ui_tab(self):
        tab = self._scrollable_tab("UI")

        theme_menu = self._add_dropdown(tab, "theme", "Theme", list_themes())
        theme_menu.configure(command=self._on_theme_preview)
        self._add_desc(tab,
            "Color theme for the dashboard and all UI windows. "
            "Changes preview instantly.")
        fx_switch = self._add_switch(tab, "effects_enabled", "Visual Effects")
        fx_switch.configure(command=self._on_effects_preview)
        self._add_desc(tab,
            "Animated glowing borders, particles, and energy pulses. "
            "Only active on supported themes (Plasma, Cyberpunk, Matrix).")
        self._add_dropdown(tab, "persona", "Persona",
                           ["professional", "casual", "mentor", "hacker"])
        self._add_switch(tab, "show_hardware_on_start", "Show Hardware on Start")
        self._add_switch(tab, "show_billing_on_start", "Show Billing on Start")
        self._add_switch(tab, "show_cache_on_start", "Show Cache on Start")
        self._add_entry(tab, "starting_balance", "Starting Balance ($)")

    # ── Nightly tab ──────────────────────────────────────────────

    def _build_nightly_tab(self):
        tab = self._scrollable_tab("Nightly")

        # ── Schedule section ──
        ctk.CTkLabel(tab, text="  Nightly Schedule",
                     font=ctk.CTkFont(*FONT_MONO_BOLD),
                     text_color=COLORS["cyan_dim"],
                     anchor="w").pack(fill="x", padx=16, pady=(8, 2))
        self._add_desc(tab, "Run automated stress tests on a daily schedule.")

        self._add_entry(tab, "nightly_schedule_time", "Schedule Time")
        self._add_desc(tab, "24-hour format (HH:MM)")

        btn_row = ctk.CTkFrame(tab, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=4)
        install_btn = ctk.CTkButton(
            btn_row, text="Install Schedule", width=140,
            fg_color=COLORS["cyan_dim"], hover_color=COLORS["cyan"],
            text_color=COLORS["bg_dark"], font=ctk.CTkFont(*FONT_MONO_SM),
            command=self._install_schedule)
        install_btn.pack(side="left", padx=(0, 8))
        remove_btn = ctk.CTkButton(
            btn_row, text="Remove Schedule", width=140,
            fg_color=COLORS["bg_card"], hover_color=COLORS["bg_panel"],
            text_color=COLORS["gray"], font=ctk.CTkFont(*FONT_MONO_SM),
            command=self._remove_schedule)
        remove_btn.pack(side="left")

        self._schedule_status = ctk.CTkLabel(
            tab, text="  Checking...",
            font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["gray"], anchor="w")
        self._schedule_status.pack(fill="x", padx=16, pady=(0, 4))
        self._win.after(100, self._update_schedule_status)

        self._add_desc(tab,
            "Creates a Windows Task Scheduler entry or Linux cron job")

        # Separator
        ctk.CTkFrame(tab, fg_color=COLORS["border"], height=1
                     ).pack(fill="x", padx=16, pady=(10, 6))

        # ── Test Settings section ──
        ctk.CTkLabel(tab, text="  Test Settings",
                     font=ctk.CTkFont(*FONT_MONO_BOLD),
                     text_color=COLORS["cyan_dim"],
                     anchor="w").pack(fill="x", padx=16, pady=(8, 2))

        self._add_slider(tab, "nightly_max_duration_m", "Max Duration (min)",
                         5, 240, 47, fmt="{:.0f}")
        self._add_switch(tab, "nightly_show_cortex", "Show Cortex Overlay")
        self._add_desc(tab,
            "Display animated Neural Cortex brain during nightly tests")
        self._add_dropdown(tab, "nightly_cortex_position", "Cortex Position",
                           ["top_right", "top_left", "bottom_right", "bottom_left"])
        self._add_slider(tab, "nightly_cortex_size", "Cortex Size",
                         100, 400, 30, fmt="{:.0f}")

        # Separator
        ctk.CTkFrame(tab, fg_color=COLORS["border"], height=1
                     ).pack(fill="x", padx=16, pady=(10, 6))

        # ── Resource Guard section ──
        ctk.CTkLabel(tab, text="  Resource Guard",
                     font=ctk.CTkFont(*FONT_MONO_BOLD),
                     text_color=COLORS["cyan_dim"],
                     anchor="w").pack(fill="x", padx=16, pady=(8, 2))
        self._add_desc(tab,
            "Detects heavy processes before tests to free GPU/RAM")

        self._add_switch(tab, "nightly_auto_close", "Auto-close Processes")
        self._add_desc(tab,
            "Automatically close listed processes before nightly tests")

        # Process list — special handling (list stored as list, displayed as CSV)
        row = self._add_row(tab, "Process List")
        current_list = self._config.get("nightly_auto_close_list", [])
        initial_str = ", ".join(current_list) if isinstance(current_list, list) else str(current_list)
        self._nightly_process_entry = ctk.CTkEntry(
            row, font=ctk.CTkFont(*FONT_MONO_SM),
            fg_color=COLORS["bg_card"], text_color=COLORS["white"],
            border_color=COLORS["border"], border_width=1, corner_radius=4,
            width=200, height=28)
        self._nightly_process_entry.insert(0, initial_str)
        self._nightly_process_entry.pack(side="right")
        self._add_desc(tab,
            "Comma-separated, e.g. chrome.exe, discord.exe, steam.exe")

        self._add_entry(tab, "nightly_resource_ram_threshold_mb", "RAM Threshold (MB)")
        self._add_entry(tab, "nightly_resource_vram_threshold_mb", "VRAM Threshold (MB)")
        self._add_switch(tab, "nightly_force_kill", "Force Kill")
        self._add_desc(tab,
            "Force-kill processes after 10s graceful timeout (dangerous)")

        # Separator
        ctk.CTkFrame(tab, fg_color=COLORS["border"], height=1
                     ).pack(fill="x", padx=16, pady=(10, 6))

        # ── Advanced section ──
        ctk.CTkLabel(tab, text="  Advanced",
                     font=ctk.CTkFont(*FONT_MONO_BOLD),
                     text_color=COLORS["cyan_dim"],
                     anchor="w").pack(fill="x", padx=16, pady=(8, 2))

        self._add_switch(tab, "nightly_auto_bisect", "Auto-bisect")
        self._add_desc(tab,
            "Automatically git-bisect when a previously passing test fails")
        self._add_switch(tab, "nightly_auto_ceiling", "Auto Ceiling")
        self._add_desc(tab,
            "Binary-search for max stable turn count per scenario")
        self._add_switch(tab, "adaptive_expand_limits", "Allow Server Expansion")
        self._add_desc(tab,
            "Let server manifest increase scope beyond local defaults "
            "(reduce-only when OFF)")

    # ── Nightly schedule helpers ──────────────────────────────────

    def _install_schedule(self):
        """Install nightly schedule via forge.scheduler."""
        try:
            from forge.scheduler import install_schedule
            time_str = self._widgets.get("nightly_schedule_time", ("entry", None))
            if time_str and time_str[0] == "entry":
                time_val = time_str[1].get().strip() or "03:00"
            else:
                time_val = "03:00"
            result = install_schedule(time_val)
            if result.get("success"):
                self._schedule_status.configure(
                    text=f"  Scheduled daily at {time_val}",
                    text_color=COLORS["green"])
            else:
                self._schedule_status.configure(
                    text=f"  Error: {result.get('error', 'Unknown')}",
                    text_color=COLORS.get("red", "#f85149"))
        except Exception as e:
            self._schedule_status.configure(
                text=f"  Error: {e}",
                text_color=COLORS.get("red", "#f85149"))

    def _remove_schedule(self):
        """Remove nightly schedule."""
        try:
            from forge.scheduler import remove_schedule
            result = remove_schedule()
            if result.get("success"):
                self._schedule_status.configure(
                    text="  Not scheduled", text_color=COLORS["gray"])
            else:
                self._schedule_status.configure(
                    text=f"  Error: {result.get('error', 'Unknown')}",
                    text_color=COLORS.get("red", "#f85149"))
        except Exception as e:
            self._schedule_status.configure(
                text=f"  Error: {e}",
                text_color=COLORS.get("red", "#f85149"))

    def _update_schedule_status(self):
        """Check current schedule status and update label."""
        try:
            from forge.scheduler import get_schedule_info
            info = get_schedule_info()
            if info.get("scheduled"):
                time_str = info.get("time", "?")
                next_run = info.get("next_run", "")
                text = f"  Scheduled daily at {time_str}"
                if next_run:
                    text += f" (next: {next_run})"
                self._schedule_status.configure(
                    text=text, text_color=COLORS["green"])
            else:
                self._schedule_status.configure(
                    text="  Not scheduled", text_color=COLORS["gray"])
        except Exception:
            self._schedule_status.configure(
                text="  Status unknown", text_color=COLORS["gray"])

    # ── Telemetry tab ─────────────────────────────────────────────

    def _build_telemetry_tab(self):
        tab = self._scrollable_tab("Telemetry")

        ctk.CTkLabel(tab, text="  Anonymous Usage Data",
                     font=ctk.CTkFont(*FONT_MONO_BOLD),
                     text_color=COLORS["cyan_dim"],
                     anchor="w").pack(fill="x", padx=16, pady=(8, 2))

        self._add_desc(tab,
            "When enabled, Forge sends a redacted audit summary at the end "
            "of each session. This helps improve Forge. No user prompts or "
            "AI responses are included unless you disable redaction below.")

        self._add_switch(tab, "telemetry_enabled", "Enable Telemetry")
        self._add_desc(tab,
            "Opt-in: sends session metadata (model, tokens, duration, "
            "threat counts) to the Forge team. Disabled by default.")

        self._add_switch(tab, "telemetry_redact", "Redact Sensitive Data")
        self._add_desc(tab,
            "When ON (default), strips all user prompts, AI responses, "
            "file contents, and shell commands. Only metadata is sent.")

        self._add_entry(tab, "telemetry_url", "Custom Endpoint")
        self._add_desc(tab,
            "Leave blank to use the default Forge telemetry server. "
            "Enterprise users can point this to their own receiver.")

        # Separator
        ctk.CTkFrame(tab, fg_color=COLORS["border"], height=1
                     ).pack(fill="x", padx=16, pady=(10, 6))

        ctk.CTkLabel(tab, text="  What gets sent (with redaction ON):",
                     font=ctk.CTkFont(*FONT_MONO_BOLD),
                     text_color=COLORS["white"],
                     anchor="w").pack(fill="x", padx=16, pady=(4, 2))

        for item in [
            "Session duration, turn count, model name",
            "Token counts (input/output/cached)",
            "Threat detection counts (not content)",
            "Continuity grade, plan verification pass/fail",
            "Platform, Forge version, machine ID (hashed hostname)",
        ]:
            ctk.CTkLabel(tab, text=f"    * {item}",
                         font=ctk.CTkFont(*FONT_MONO_XS),
                         text_color=COLORS["gray"],
                         anchor="w").pack(fill="x", padx=16, pady=0)

        self._add_desc(tab,
            "Machine ID is a one-way hash. "
            "Your hostname cannot be recovered from it.")

    # ── Forge tab (AutoForge + Shipwright) ──

    def _build_forge_tab(self):
        tab = self._scrollable_tab("Forge")

        # Section: AutoForge
        ctk.CTkLabel(tab, text="AutoForge",
                     font=ctk.CTkFont(*FONT_MONO_BOLD),
                     text_color=COLORS["cyan"]
                     ).pack(anchor="w", padx=16, pady=(8, 2))

        self._add_switch(tab, "auto_commit", "Auto-Commit")
        self._add_desc(tab,
            "Automatically commit file edits at each turn boundary. "
            "Operates on the current project's git repo, not Forge itself.")

        # Separator
        ctk.CTkFrame(tab, fg_color=COLORS["border"], height=1
                     ).pack(fill="x", padx=16, pady=(10, 6))

        # Section: Shipwright
        ctk.CTkLabel(tab, text="Shipwright",
                     font=ctk.CTkFont(*FONT_MONO_BOLD),
                     text_color=COLORS["cyan"]
                     ).pack(anchor="w", padx=16, pady=(4, 2))

        self._add_switch(tab, "shipwright_llm_classify",
                         "LLM Commit Classification")
        self._add_desc(tab,
            "Use the AI model to classify ambiguous commit messages "
            "into categories (feature, fix, refactor, etc) for smarter "
            "version bumping.")

    # ── License tab (BPoS / Passport) ──

    def _build_license_tab(self):
        tab = self._scrollable_tab("License")

        # Section header
        ctk.CTkLabel(tab, text="License Tier",
                     font=ctk.CTkFont(*FONT_MONO_BOLD),
                     text_color=COLORS["cyan"]
                     ).pack(anchor="w", padx=16, pady=(8, 2))

        # Tier display
        tier_row = ctk.CTkFrame(tab, fg_color="transparent")
        tier_row.pack(fill="x", padx=16, pady=4)
        self._lic_tier_label = ctk.CTkLabel(
            tier_row, text="Community (Free)",
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            text_color=COLORS["green"])
        self._lic_tier_label.pack(side="left")

        # Activation count
        self._lic_act_label = ctk.CTkLabel(
            tab, text="  Activations: 1/1",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["gray"])
        self._lic_act_label.pack(anchor="w", padx=16, pady=2)

        # Genome maturity bar
        mat_frame = ctk.CTkFrame(tab, fg_color="transparent")
        mat_frame.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(mat_frame, text="Genome Maturity",
                     font=ctk.CTkFont(*FONT_MONO_SM),
                     text_color=COLORS["gray"],
                     width=140, anchor="w").pack(side="left")
        self._lic_maturity_bar = ctk.CTkProgressBar(
            mat_frame, height=10, corner_radius=3,
            fg_color=COLORS["bg_dark"],
            progress_color=COLORS["cyan"])
        self._lic_maturity_bar.pack(
            side="left", fill="x", expand=True, padx=(6, 0))
        self._lic_maturity_bar.set(0.0)
        self._lic_maturity_pct = ctk.CTkLabel(
            mat_frame, text="0%",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["white"], width=40)
        self._lic_maturity_pct.pack(side="right")

        # Action buttons
        btn_frame = ctk.CTkFrame(tab, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(8, 4))
        ctk.CTkButton(
            btn_frame, text="Activate Passport...", width=160,
            fg_color=COLORS["cyan_dim"],
            hover_color=COLORS["cyan"],
            text_color=COLORS["bg_dark"],
            font=ctk.CTkFont(*FONT_MONO_SM),
            command=self._activate_passport).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            btn_frame, text="Deactivate", width=100,
            fg_color=COLORS["bg_card"],
            hover_color=COLORS["red"],
            text_color=COLORS["white"],
            font=ctk.CTkFont(*FONT_MONO_SM),
            command=self._deactivate_passport).pack(side="left")

        # Separator
        ctk.CTkFrame(tab, fg_color=COLORS["border"], height=1
                     ).pack(fill="x", padx=16, pady=(10, 6))

        # Tier comparison table
        ctk.CTkLabel(tab, text="Tier Comparison",
                     font=ctk.CTkFont(*FONT_MONO_BOLD),
                     text_color=COLORS["cyan"]
                     ).pack(anchor="w", padx=16, pady=(4, 4))
        self._build_tier_table(tab)

        # Populate current state
        self._refresh_license_display()

    def _build_tier_table(self, parent):
        """Build a 4-column tier comparison table."""
        from forge.passport import get_tiers

        tiers = get_tiers()
        features = [
            ("genome_persistence", "Genome Persistence"),
            ("seats", "Seats"),
            ("auto_commit", "AutoForge"),
            ("shipwright", "Shipwright"),
            ("enterprise_mode", "Enterprise Mode"),
            ("fleet_analytics", "Fleet Analytics"),
        ]

        # Header row
        hdr = ctk.CTkFrame(parent, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(0, 2))
        ctk.CTkLabel(hdr, text="Feature", width=140, anchor="w",
                     font=ctk.CTkFont(*FONT_MONO_XS),
                     text_color=COLORS["gray"]).pack(side="left")
        for tier_key in ("community", "pro", "power"):
            cfg = tiers.get(tier_key, {})
            label = cfg.get("label", tier_key.title())
            ctk.CTkLabel(hdr, text=label, width=90, anchor="center",
                         font=ctk.CTkFont(*FONT_MONO_XS),
                         text_color=COLORS["white"]).pack(side="left")

        # Feature rows
        for feat_key, feat_label in features:
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=1)
            ctk.CTkLabel(row, text=feat_label, width=140, anchor="w",
                         font=ctk.CTkFont(*FONT_MONO_XS),
                         text_color=COLORS["text_dim"]).pack(side="left")
            for tier_key in ("community", "pro", "power"):
                cfg = tiers.get(tier_key, {})
                val = cfg.get(feat_key, False)
                if isinstance(val, bool):
                    display = "yes" if val else "--"
                    color = COLORS["green"] if val else COLORS["border"]
                else:
                    display = str(val)
                    color = COLORS["white"]
                ctk.CTkLabel(row, text=display, width=90, anchor="center",
                             font=ctk.CTkFont(*FONT_MONO_XS),
                             text_color=color).pack(side="left")

    def _refresh_license_display(self):
        """Populate license tab from BPoS state."""
        try:
            from forge.passport import BPoS
            from forge.machine_id import get_machine_id
            config_dir = Path.home() / ".forge"
            bpos = BPoS(data_dir=config_dir, machine_id=get_machine_id())

            tier = bpos.tier
            tc = bpos.tier_config
            tier_colors = {
                "community": COLORS["green"],
                "pro": COLORS["cyan"],
                "power": COLORS["magenta"],
            }
            color = tier_colors.get(tier, COLORS["white"])
            price = tc.get("price_display", tc.get("price", "Free"))
            self._lic_tier_label.configure(
                text=f"{tc.get('label', tier)} ({price})", text_color=color)

            passport = bpos._passport
            acts = len(passport.activations) if passport else 1
            seats = tc.get("seats", 1)
            self._lic_act_label.configure(
                text=f"  Seats: {acts}/{seats}")

            maturity = bpos.get_genome_maturity()
            self._lic_maturity_bar.set(maturity)
            self._lic_maturity_pct.configure(
                text=f"{int(maturity * 100)}%")
        except Exception as e:
            log.debug("License display: %s", e)

    def _activate_passport(self):
        """Open file dialog to activate a passport JSON."""
        import tkinter.filedialog as fd
        import json as _json
        path = fd.askopenfilename(
            parent=self._win,
            title="Select Passport File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            from forge.passport import BPoS
            from forge.machine_id import get_machine_id
            config_dir = Path.home() / ".forge"
            bpos = BPoS(data_dir=config_dir, machine_id=get_machine_id())
            data = _json.loads(Path(path).read_text())
            ok, msg = bpos.activate(data)
            self._refresh_license_display()
            if ok:
                self._show_msg("Passport activated", COLORS["green"])
            else:
                self._show_msg(f"Failed: {msg}", COLORS["red"])
        except Exception as e:
            self._show_msg(f"Error: {e}", COLORS["red"])

    def _deactivate_passport(self):
        """Deactivate the current passport."""
        try:
            from forge.passport import BPoS
            from forge.machine_id import get_machine_id
            config_dir = Path.home() / ".forge"
            bpos = BPoS(data_dir=config_dir, machine_id=get_machine_id())
            ok, msg = bpos.deactivate()
            self._refresh_license_display()
            if ok:
                self._show_msg("Passport deactivated", COLORS["green"])
            else:
                self._show_msg(f"Failed: {msg}", COLORS["red"])
        except Exception as e:
            self._show_msg(f"Error: {e}", COLORS["red"])

    def _show_msg(self, text: str, color: str):
        """Brief flash message near the bottom of the window."""
        lbl = ctk.CTkLabel(self._win, text=text,
                           font=ctk.CTkFont(*FONT_MONO_SM),
                           text_color=color)
        lbl.place(relx=0.5, rely=0.95, anchor="center")
        self._win.after(3000, lbl.destroy)

    # ── Widget helpers ────────────────────────────────────────────

    def _add_row(self, parent, label_text) -> ctk.CTkFrame:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(row, text=label_text,
                     font=ctk.CTkFont(*FONT_MONO),
                     text_color=COLORS["gray"],
                     width=170, anchor="w").pack(side="left")
        return row

    def _add_switch(self, parent, key: str, label: str):
        row = self._add_row(parent, label)
        var = ctk.BooleanVar(value=bool(self._config.get(key, False)))
        sw = ctk.CTkSwitch(row, variable=var, text="",
                           fg_color=COLORS["bg_card"],
                           progress_color=COLORS["cyan"],
                           button_color=COLORS["white"],
                           button_hover_color=COLORS["cyan_glow"],
                           width=44)
        sw.pack(side="right")
        self._widgets[key] = ("switch", var)
        return sw

    def _add_dropdown(self, parent, key: str, label: str,
                      choices: list[str]) -> ctk.CTkOptionMenu:
        row = self._add_row(parent, label)
        current = str(self._config.get(key, choices[0] if choices else ""))
        if current not in choices:
            choices = [current] + choices
        var = ctk.StringVar(value=current)
        menu = ctk.CTkOptionMenu(
            row, variable=var, values=choices,
            fg_color=COLORS["bg_card"],
            button_color=COLORS["cyan_dim"],
            button_hover_color=COLORS["cyan"],
            dropdown_fg_color=COLORS["bg_card"],
            dropdown_hover_color=COLORS["cyan_dim"],
            text_color=COLORS["white"],
            font=ctk.CTkFont(*FONT_MONO_SM),
            dropdown_font=ctk.CTkFont(*FONT_MONO_SM),
            width=200)
        menu.pack(side="right")
        self._widgets[key] = ("dropdown", var, menu)
        return menu

    def _add_slider(self, parent, key: str, label: str,
                    from_: float, to_: float, steps: int,
                    fmt: str = "{:.2f}"):
        row = self._add_row(parent, label)
        current = float(self._config.get(key, from_))
        val_label = ctk.CTkLabel(row, text=fmt.format(current),
                                 font=ctk.CTkFont(*FONT_MONO),
                                 text_color=COLORS["white"], width=60)
        val_label.pack(side="right")
        slider = ctk.CTkSlider(
            row, from_=from_, to=to_,
            number_of_steps=steps,
            fg_color=COLORS["bg_card"],
            progress_color=COLORS["cyan_dim"],
            button_color=COLORS["cyan"],
            button_hover_color=COLORS["cyan_glow"],
            width=160,
            command=lambda v: val_label.configure(text=fmt.format(v)))
        slider.set(current)
        slider.pack(side="right", padx=(0, 6))
        self._widgets[key] = ("slider", slider)

    def _add_entry(self, parent, key: str, label: str):
        row = self._add_row(parent, label)
        current = self._config.get(key, "")
        entry = ctk.CTkEntry(
            row, font=ctk.CTkFont(*FONT_MONO_SM),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["white"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=4,
            width=200, height=28)
        entry.insert(0, str(current))
        entry.pack(side="right")
        self._widgets[key] = ("entry", entry)

    def _add_desc(self, parent, text: str):
        """Add a small description label below a setting for context."""
        ctk.CTkLabel(parent, text=f"  {text}",
                     font=ctk.CTkFont(*FONT_MONO_XS),
                     text_color=COLORS["text_dim"],
                     wraplength=480, justify="left", anchor="w"
                     ).pack(fill="x", padx=16, pady=(0, 2))

    # ── Sandbox path management ───────────────────────────────────

    def _refresh_paths_display(self):
        self._paths_text.configure(state="normal")
        self._paths_text.delete("1.0", "end")
        if self._sandbox_paths:
            self._paths_text.insert("1.0", "\n".join(self._sandbox_paths))
        else:
            self._paths_text.insert("1.0", "(no paths configured)")
        self._paths_text.configure(state="disabled")

    def _add_sandbox_path(self):
        import tkinter.filedialog as fd
        path = fd.askdirectory(parent=self._win, title="Select sandbox directory")
        if path:
            if path not in self._sandbox_paths:
                self._sandbox_paths.append(path)
                self._refresh_paths_display()

    def _remove_sandbox_path(self):
        if self._sandbox_paths:
            self._sandbox_paths.pop()
            self._refresh_paths_display()

    # ── Ollama model fetch ────────────────────────────────────────

    def _fetch_models(self):
        def _do_fetch():
            try:
                url = self._config.get("ollama_url", "http://localhost:11434")
                # Try reading from the entry widget if it exists
                if "ollama_url" in self._widgets:
                    info = self._widgets["ollama_url"]
                    if info[0] == "entry":
                        url = info[1].get().strip() or url
                req = urllib.request.Request(f"{url}/api/tags", method="GET")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = json.loads(resp.read())
                models = [m["name"] for m in data.get("models", [])]
                if models:
                    self._win.after(0, lambda: self._populate_model_menus(models))
            except Exception:
                pass  # Ollama not available — keep current values

        threading.Thread(target=_do_fetch, daemon=True).start()

    def _populate_model_menus(self, models: list[str]):
        # Update primary model dropdown
        if "default_model" in self._widgets:
            _, var, menu = self._widgets["default_model"]
            current = var.get()
            if current not in models:
                models = [current] + models
            menu.configure(values=models)

        # Update small model dropdown
        if "small_model" in self._widgets:
            _, var, menu = self._widgets["small_model"]
            current = var.get()
            small_list = ["(none)"] + models
            if current and current != "(none)" and current not in small_list:
                small_list = ["(none)", current] + models
            menu.configure(values=small_list)

    # ── Pull model from Ollama ─────────────────────────────────────

    def _open_model_manager(self):
        """Open the enterprise Model Manager dialog."""
        from forge.ui.model_manager import ModelManagerDialog
        # Release grab so Model Manager can take focus
        self._win.grab_release()
        ModelManagerDialog(self._win, self._config)
        # Refresh dropdowns when model manager closes
        self._win.after(500, self._fetch_models)
        self._win.after(600, self._win.grab_set)

    # ── Save / Reset ──────────────────────────────────────────────

    def _on_save(self):
        for key, widget_info in self._widgets.items():
            kind = widget_info[0]
            default = DEFAULTS.get(key)

            if kind == "switch":
                value = widget_info[1].get()
            elif kind == "segmented":
                value = int(widget_info[1].get())
            elif kind == "dropdown":
                value = widget_info[1].get()
                if value == "(none)":
                    value = ""
            elif kind == "slider":
                value = widget_info[1].get()
                if isinstance(default, int):
                    value = int(round(value))
            elif kind == "entry":
                raw = widget_info[1].get().strip()
                if isinstance(default, int):
                    try:
                        value = int(raw)
                    except ValueError:
                        value = default
                elif isinstance(default, float):
                    try:
                        value = float(raw)
                    except ValueError:
                        value = default
                else:
                    value = raw
            elif kind == "pathlist":
                value = list(widget_info[1])
            else:
                continue

            self._config.set(key, value)

        # Handle process list (stored as list, displayed as comma-separated string)
        if hasattr(self, "_nightly_process_entry"):
            raw = self._nightly_process_entry.get().strip()
            items = [s.strip() for s in raw.split(",") if s.strip()]
            self._config.set("nightly_auto_close_list", items)

        self._config.save()

        # Apply saved theme + effects state. force=True ensures all
        # engines re-read config even if the theme name didn't change.
        saved_theme = self._config.get("theme", "midnight")
        set_theme(saved_theme, force=True)
        self._saved = True

        # Signal engine to reload config
        try:
            trigger = Path.home() / ".forge" / "config_changed.txt"
            trigger.write_text("reload", encoding="utf-8")
        except Exception:
            pass

        # Green flash "Saved!" then close
        flash = ctk.CTkLabel(
            self._win, text="  Saved!  ",
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            text_color=COLORS["green"],
            fg_color=COLORS["bg_card"],
            corner_radius=6, height=32)
        flash.place(relx=0.5, rely=0.5, anchor="center")
        self._win.after(600, self._close)

    def _on_reset(self):
        for key, widget_info in self._widgets.items():
            kind = widget_info[0]
            default = DEFAULTS.get(key)
            if default is None:
                continue

            if kind == "switch":
                widget_info[1].set(bool(default))
            elif kind == "segmented":
                widget_info[1].set(str(default))
            elif kind == "dropdown":
                val = str(default) if default else "(none)"
                widget_info[1].set(val)
            elif kind == "slider":
                widget_info[1].set(float(default))
            elif kind == "entry":
                entry = widget_info[1]
                entry.delete(0, "end")
                entry.insert(0, str(default))
            elif kind == "pathlist":
                widget_info[1].clear()
                self._refresh_paths_display()

    def _on_theme_preview(self, choice: str):
        """Live-preview the selected theme across all open windows."""
        set_theme(choice)

    def _on_effects_preview(self):
        """Live-preview effects toggle across all open windows instantly.

        Uses the global engine registry to directly call set_enabled()
        on every active EffectsEngine — no event-loop round-trip needed.
        """
        from forge.ui.effects import toggle_all_effects
        enabled = bool(self._widgets["effects_enabled"][1].get())
        toggle_all_effects(enabled)

    def _apply_theme(self, color_map: dict):
        """Hot-swap theme colours on the settings dialog."""
        if self._win:
            recolor_widget_tree(self._win, color_map)

    def _close(self):
        """Clean up effects, theme listener, and destroy the window.

        If the user didn't Save, revert to the original theme and
        effects state.
        """
        if self._effects:
            try:
                self._effects.shutdown()
            except Exception:
                pass
            self._effects = None
        if hasattr(self, "_theme_cb"):
            remove_theme_listener(self._theme_cb)
        # Revert theme + effects if user cancelled (didn't save)
        if not getattr(self, "_saved", False):
            # Restore original effects state on all remaining engines
            from forge.ui.effects import toggle_all_effects
            toggle_all_effects(self._original_effects)
            set_theme(self._original_theme, force=True)
        try:
            self._win.destroy()
        except Exception:
            pass
