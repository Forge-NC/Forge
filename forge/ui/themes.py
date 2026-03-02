"""Forge Theme System — centralized colors and fonts for all UI modules.

Single source of truth. Every UI file imports from here instead of
defining its own COLORS dict. Themes are selected via config.yaml
and the /theme command.

Usage:
    from forge.ui.themes import get_colors, get_fonts
    COLORS = get_colors()
    FONTS  = get_fonts()
"""

import logging
import sys
from typing import Callable, Optional

log = logging.getLogger(__name__)

# ── Cross-platform font families ──
if sys.platform == "win32":
    _MONO_FAMILY = "Consolas"
    _BODY_FAMILY = "Segoe UI"
elif sys.platform == "darwin":
    _MONO_FAMILY = "Menlo"
    _BODY_FAMILY = "Helvetica Neue"
else:  # Linux / other
    _MONO_FAMILY = "DejaVu Sans Mono"
    _BODY_FAMILY = "DejaVu Sans"

# ── Theme change listeners ──
# Callbacks receive a color_map dict: {old_hex_lower: new_hex}
# so they can walk their widget trees and remap colors in-place.

_theme_listeners: list[Callable] = []


def add_theme_listener(callback: Callable[[dict], None]):
    """Register a callback for theme changes.

    ``callback(color_map)`` is called after ``set_theme()`` updates
    the live dicts.  *color_map* maps every changed colour's old hex
    value (lower-cased) to its new hex value.
    """
    if callback not in _theme_listeners:
        _theme_listeners.append(callback)


def remove_theme_listener(callback: Callable[[dict], None]):
    """Unregister a previously registered theme-change callback."""
    try:
        _theme_listeners.remove(callback)
    except ValueError:
        pass


def recolor_widget_tree(widget, color_map: dict[str, str]):
    """Recursively recolor *widget* and all descendants.

    For every CTk / tk property that holds a hex colour found as a key
    in *color_map*, the property is updated to the new value.
    """
    _recolor_widget(widget, color_map)
    try:
        for child in widget.winfo_children():
            recolor_widget_tree(child, color_map)
    except Exception:
        pass


def _recolor_widget(widget, color_map: dict[str, str]):
    """Recolor a single widget (CTk or plain tk)."""
    # ── customtkinter properties ──
    _CTK_PROPS = (
        "fg_color", "bg_color", "text_color", "border_color",
        "button_color", "button_hover_color", "hover_color",
        "progress_color", "placeholder_text_color",
        "scrollbar_button_color", "scrollbar_button_hover_color",
        "segmented_button_fg_color", "segmented_button_selected_color",
        "segmented_button_selected_hover_color",
        "segmented_button_unselected_color",
        "segmented_button_unselected_hover_color",
        "selected_color", "selected_hover_color",
        "unselected_color", "unselected_hover_color",
        "dropdown_fg_color", "dropdown_hover_color",
    )
    for prop in _CTK_PROPS:
        try:
            val = widget.cget(prop)
        except Exception:
            continue
        if isinstance(val, str):
            key = val.lower()
            if key in color_map:
                widget.configure(**{prop: color_map[key]})
        elif isinstance(val, (list, tuple)):
            new_vals = []
            changed = False
            for v in val:
                if isinstance(v, str) and v.lower() in color_map:
                    new_vals.append(color_map[v.lower()])
                    changed = True
                else:
                    new_vals.append(v)
            if changed:
                try:
                    widget.configure(**{prop: tuple(new_vals)})
                except Exception:
                    pass

    # ── plain tk properties ──
    _TK_PROPS = (
        "bg", "fg", "background", "foreground",
        "activebackground", "activeforeground",
        "highlightbackground", "highlightcolor",
        "insertbackground", "selectbackground",
        "troughcolor",
    )
    for prop in _TK_PROPS:
        try:
            val = widget.cget(prop)
        except Exception:
            continue
        if isinstance(val, str) and val.lower() in color_map:
            try:
                widget.configure(**{prop: color_map[val.lower()]})
            except Exception:
                pass

# ── Current theme state (module-level) ──

_current_theme: str = "midnight"


# ── Theme definitions ──
# Each theme defines 28 color keys covering all UI modules.
#
# Dashboard/settings/test_runner/model_manager keys:
#   bg_dark, bg_panel, bg_card, border, cyan, cyan_dim, cyan_glow,
#   blue, green, yellow, red, white, gray, text_dim, magenta, purple
#
# Docs window additions:
#   bg_sidebar, bg_content, bg_input, bg_hover, bg_selected,
#   fg, fg_dim, fg_muted, accent, accent_dim, accent_glow,
#   separator, highlight_bg

THEMES: dict[str, dict[str, str]] = {

    # ── Midnight (default — fixed readability) ──────────────────
    "midnight": {
        "bg_dark":       "#0a0e17",
        "bg_panel":      "#0f1520",
        "bg_card":       "#141c2b",
        "border":        "#1a2540",
        "cyan":          "#00d4ff",
        "cyan_dim":      "#0088aa",
        "cyan_glow":     "#00e5ff",
        "blue":          "#0066cc",
        "green":         "#00ff88",
        "yellow":        "#ffaa00",
        "red":           "#ff3344",
        "white":         "#e0e8f0",
        "gray":          "#8899aa",
        "text_dim":      "#8294ab",
        "magenta":       "#cc44ff",
        "purple":        "#8844cc",
        # Docs extras
        "bg_sidebar":    "#0f1520",
        "bg_content":    "#141c2b",
        "bg_input":      "#182238",
        "bg_hover":      "#1c2a42",
        "bg_selected":   "#1a2a40",
        "fg":            "#e0e8f0",
        "fg_dim":        "#9999bb",
        "fg_muted":      "#8888aa",
        "accent":        "#00d4ff",
        "accent_dim":    "#0088aa",
        "accent_glow":   "#00e5ff",
        "separator":     "#1e3050",
        "highlight_bg":  "#1a3a50",
    },

    # ── Obsidian — charcoal neutral ─────────────────────────────
    "obsidian": {
        "bg_dark":       "#1a1a1a",
        "bg_panel":      "#222222",
        "bg_card":       "#2a2a2a",
        "border":        "#3a3a3a",
        "cyan":          "#66ccff",
        "cyan_dim":      "#4499cc",
        "cyan_glow":     "#88ddff",
        "blue":          "#5599dd",
        "green":         "#66dd88",
        "yellow":        "#ddbb44",
        "red":           "#ee5555",
        "white":         "#e8e8e8",
        "gray":          "#999999",
        "text_dim":      "#909090",
        "magenta":       "#cc77dd",
        "purple":        "#9966cc",
        "bg_sidebar":    "#222222",
        "bg_content":    "#2a2a2a",
        "bg_input":      "#333333",
        "bg_hover":      "#383838",
        "bg_selected":   "#2e3e4e",
        "fg":            "#e8e8e8",
        "fg_dim":        "#aaaaaa",
        "fg_muted":      "#888888",
        "accent":        "#66ccff",
        "accent_dim":    "#4499cc",
        "accent_glow":   "#88ddff",
        "separator":     "#444444",
        "highlight_bg":  "#2a3a4a",
    },

    # ── Dracula — classic purple-tinted ─────────────────────────
    "dracula": {
        "bg_dark":       "#282a36",
        "bg_panel":      "#2d2f3d",
        "bg_card":       "#343746",
        "border":        "#44475a",
        "cyan":          "#8be9fd",
        "cyan_dim":      "#5bb8cc",
        "cyan_glow":     "#a4f0ff",
        "blue":          "#6272a4",
        "green":         "#50fa7b",
        "yellow":        "#f1fa8c",
        "red":           "#ff5555",
        "white":         "#f8f8f2",
        "gray":          "#9999bb",
        "text_dim":      "#9090b5",
        "magenta":       "#ff79c6",
        "purple":        "#bd93f9",
        "bg_sidebar":    "#21222c",
        "bg_content":    "#2d2f3d",
        "bg_input":      "#383a4c",
        "bg_hover":      "#3e4058",
        "bg_selected":   "#44475a",
        "fg":            "#f8f8f2",
        "fg_dim":        "#b0b0cc",
        "fg_muted":      "#9090aa",
        "accent":        "#bd93f9",
        "accent_dim":    "#9070cc",
        "accent_glow":   "#d4b0ff",
        "separator":     "#44475a",
        "highlight_bg":  "#383a50",
    },

    # ── Solarized Dark — warm, precise ──────────────────────────
    "solarized_dark": {
        "bg_dark":       "#002b36",
        "bg_panel":      "#003340",
        "bg_card":       "#073642",
        "border":        "#0a4858",
        "cyan":          "#2aa198",
        "cyan_dim":      "#1a7a73",
        "cyan_glow":     "#35c4ba",
        "blue":          "#268bd2",
        "green":         "#859900",
        "yellow":        "#b58900",
        "red":           "#dc322f",
        "white":         "#eee8d5",
        "gray":          "#93a1a1",
        "text_dim":      "#8d9e9e",
        "magenta":       "#d33682",
        "purple":        "#6c71c4",
        "bg_sidebar":    "#003340",
        "bg_content":    "#073642",
        "bg_input":      "#0a4050",
        "bg_hover":      "#0c4a5c",
        "bg_selected":   "#0e5060",
        "fg":            "#eee8d5",
        "fg_dim":        "#a0aaa0",
        "fg_muted":      "#839496",
        "accent":        "#268bd2",
        "accent_dim":    "#1a6a9c",
        "accent_glow":   "#38a0e8",
        "separator":     "#0a4858",
        "highlight_bg":  "#0a3e50",
    },

    # ── Nord — arctic, cool blue ────────────────────────────────
    "nord": {
        "bg_dark":       "#2e3440",
        "bg_panel":      "#343a48",
        "bg_card":       "#3b4252",
        "border":        "#4c566a",
        "cyan":          "#88c0d0",
        "cyan_dim":      "#6a9aaa",
        "cyan_glow":     "#a0d8e8",
        "blue":          "#5e81ac",
        "green":         "#a3be8c",
        "yellow":        "#ebcb8b",
        "red":           "#bf616a",
        "white":         "#eceff4",
        "gray":          "#a0aabb",
        "text_dim":      "#99a0ae",
        "magenta":       "#b48ead",
        "purple":        "#9478a8",
        "bg_sidebar":    "#2e3440",
        "bg_content":    "#3b4252",
        "bg_input":      "#434c5e",
        "bg_hover":      "#4c566a",
        "bg_selected":   "#3d5070",
        "fg":            "#eceff4",
        "fg_dim":        "#b0b8c8",
        "fg_muted":      "#909aaa",
        "accent":        "#88c0d0",
        "accent_dim":    "#6a9aaa",
        "accent_glow":   "#a0d8e8",
        "separator":     "#4c566a",
        "highlight_bg":  "#3a4860",
    },

    # ── Monokai — warm dark, bright accents ─────────────────────
    "monokai": {
        "bg_dark":       "#272822",
        "bg_panel":      "#2d2e27",
        "bg_card":       "#33342c",
        "border":        "#484940",
        "cyan":          "#66d9ef",
        "cyan_dim":      "#44a8bb",
        "cyan_glow":     "#88e8ff",
        "blue":          "#55aadd",
        "green":         "#a6e22e",
        "yellow":        "#e6db74",
        "red":           "#f92672",
        "white":         "#f8f8f2",
        "gray":          "#a0a090",
        "text_dim":      "#999988",
        "magenta":       "#fd5ff0",
        "purple":        "#ae81ff",
        "bg_sidebar":    "#23241e",
        "bg_content":    "#2d2e27",
        "bg_input":      "#383930",
        "bg_hover":      "#40413a",
        "bg_selected":   "#49483e",
        "fg":            "#f8f8f2",
        "fg_dim":        "#b0b0a0",
        "fg_muted":      "#908f80",
        "accent":        "#a6e22e",
        "accent_dim":    "#80b020",
        "accent_glow":   "#c0f840",
        "separator":     "#484940",
        "highlight_bg":  "#3e3d30",
    },

    # ── Cyberpunk — neon on black ───────────────────────────────
    "cyberpunk": {
        "bg_dark":       "#050508",
        "bg_panel":      "#0a0a12",
        "bg_card":       "#10101c",
        "border":        "#1a1a30",
        "cyan":          "#00ffff",
        "cyan_dim":      "#00aaaa",
        "cyan_glow":     "#44ffff",
        "blue":          "#0088ff",
        "green":         "#00ff88",
        "yellow":        "#ffff00",
        "red":           "#ff0044",
        "white":         "#f0f0ff",
        "gray":          "#8888aa",
        "text_dim":      "#8080a0",
        "magenta":       "#ff2d95",
        "purple":        "#cc44ff",
        "bg_sidebar":    "#08080f",
        "bg_content":    "#0e0e1a",
        "bg_input":      "#151528",
        "bg_hover":      "#1a1a35",
        "bg_selected":   "#20103a",
        "fg":            "#f0f0ff",
        "fg_dim":        "#9999bb",
        "fg_muted":      "#7777aa",
        "accent":        "#ff2d95",
        "accent_dim":    "#cc1070",
        "accent_glow":   "#ff55aa",
        "separator":     "#221133",
        "highlight_bg":  "#1a0a30",
    },

    # ── Matrix — green phosphor ─────────────────────────────────
    "matrix": {
        "bg_dark":       "#0a0f0a",
        "bg_panel":      "#0f150f",
        "bg_card":       "#141e14",
        "border":        "#1a2e1a",
        "cyan":          "#00ff41",
        "cyan_dim":      "#00aa2b",
        "cyan_glow":     "#44ff66",
        "blue":          "#00cc55",
        "green":         "#00ff41",
        "yellow":        "#88ff00",
        "red":           "#ff2200",
        "white":         "#ccffcc",
        "gray":          "#669966",
        "text_dim":      "#70a070",
        "magenta":       "#00ff88",
        "purple":        "#00dd66",
        "bg_sidebar":    "#0a100a",
        "bg_content":    "#0f180f",
        "bg_input":      "#152215",
        "bg_hover":      "#1a2c1a",
        "bg_selected":   "#1a3520",
        "fg":            "#ccffcc",
        "fg_dim":        "#88bb88",
        "fg_muted":      "#669966",
        "accent":        "#00ff41",
        "accent_dim":    "#00aa2b",
        "accent_glow":   "#55ff77",
        "separator":     "#1a3a1a",
        "highlight_bg":  "#0f2a15",
    },

    # ── Amber — retro terminal ──────────────────────────────────
    "amber": {
        "bg_dark":       "#1a1000",
        "bg_panel":      "#201500",
        "bg_card":       "#281c00",
        "border":        "#3a2800",
        "cyan":          "#ffb000",
        "cyan_dim":      "#cc8800",
        "cyan_glow":     "#ffcc33",
        "blue":          "#dd9900",
        "green":         "#ffcc00",
        "yellow":        "#ffb000",
        "red":           "#ff4400",
        "white":         "#ffe0aa",
        "gray":          "#aa8844",
        "text_dim":      "#a08050",
        "magenta":       "#ffcc55",
        "purple":        "#ddaa33",
        "bg_sidebar":    "#1a1000",
        "bg_content":    "#221800",
        "bg_input":      "#302000",
        "bg_hover":      "#3a2800",
        "bg_selected":   "#3a3010",
        "fg":            "#ffe0aa",
        "fg_dim":        "#cc9955",
        "fg_muted":      "#aa7733",
        "accent":        "#ffb000",
        "accent_dim":    "#cc8800",
        "accent_glow":   "#ffcc44",
        "separator":     "#3a2800",
        "highlight_bg":  "#2a2000",
    },

    # ── Phosphor — green CRT ────────────────────────────────────
    "phosphor": {
        "bg_dark":       "#0a120a",
        "bg_panel":      "#0f1a0f",
        "bg_card":       "#142214",
        "border":        "#1e3a1e",
        "cyan":          "#33ff33",
        "cyan_dim":      "#22aa22",
        "cyan_glow":     "#66ff66",
        "blue":          "#22dd44",
        "green":         "#33ff33",
        "yellow":        "#99ff33",
        "red":           "#ff3333",
        "white":         "#ccffcc",
        "gray":          "#77aa77",
        "text_dim":      "#70a070",
        "magenta":       "#66ff99",
        "purple":        "#44dd77",
        "bg_sidebar":    "#0a120a",
        "bg_content":    "#0f1c0f",
        "bg_input":      "#182818",
        "bg_hover":      "#1e3220",
        "bg_selected":   "#1e3a28",
        "fg":            "#ccffcc",
        "fg_dim":        "#88cc88",
        "fg_muted":      "#66aa66",
        "accent":        "#33ff33",
        "accent_dim":    "#22aa22",
        "accent_glow":   "#66ff66",
        "separator":     "#1e3a1e",
        "highlight_bg":  "#142e1a",
    },

    # ── Arctic — light theme ────────────────────────────────────
    "arctic": {
        "bg_dark":       "#f0f2f5",
        "bg_panel":      "#e8eaee",
        "bg_card":       "#ffffff",
        "border":        "#d0d4da",
        "cyan":          "#0077cc",
        "cyan_dim":      "#005599",
        "cyan_glow":     "#0099ee",
        "blue":          "#0066cc",
        "green":         "#22884a",
        "yellow":        "#bb7700",
        "red":           "#cc2233",
        "white":         "#1a1a2e",
        "gray":          "#667788",
        "text_dim":      "#9aacbb",
        "magenta":       "#9944bb",
        "purple":        "#6633aa",
        "bg_sidebar":    "#e4e6ea",
        "bg_content":    "#f5f6f8",
        "bg_input":      "#ffffff",
        "bg_hover":      "#dde0e5",
        "bg_selected":   "#d0e0f0",
        "fg":            "#1a1a2e",
        "fg_dim":        "#556070",
        "fg_muted":      "#778899",
        "accent":        "#0077cc",
        "accent_dim":    "#005599",
        "accent_glow":   "#0099ee",
        "separator":     "#d0d4da",
        "highlight_bg":  "#daeaf5",
    },

    # ── Sunset — warm coral ─────────────────────────────────────
    "sunset": {
        "bg_dark":       "#1a0f0a",
        "bg_panel":      "#221410",
        "bg_card":       "#2a1a14",
        "border":        "#3e2820",
        "cyan":          "#ff6b4a",
        "cyan_dim":      "#cc4a30",
        "cyan_glow":     "#ff8866",
        "blue":          "#ee6644",
        "green":         "#88cc55",
        "yellow":        "#ffcc44",
        "red":           "#ff3344",
        "white":         "#f0e0d8",
        "gray":          "#aa8878",
        "text_dim":      "#a08070",
        "magenta":       "#ee6688",
        "purple":        "#cc5577",
        "bg_sidebar":    "#1a0f0a",
        "bg_content":    "#221610",
        "bg_input":      "#2e1e18",
        "bg_hover":      "#382820",
        "bg_selected":   "#3a2a22",
        "fg":            "#f0e0d8",
        "fg_dim":        "#bb9988",
        "fg_muted":      "#997766",
        "accent":        "#ff6b4a",
        "accent_dim":    "#cc4a30",
        "accent_glow":   "#ff8866",
        "separator":     "#3e2820",
        "highlight_bg":  "#2e2018",
    },

    # ── OD Green — military olive drab ─────────────────────────────
    "od_green": {
        "bg_dark":       "#111408",
        "bg_panel":      "#1a1e10",
        "bg_card":       "#222816",
        "border":        "#3a4025",
        "cyan":          "#6b8e23",
        "cyan_dim":      "#4a6218",
        "cyan_glow":     "#8ab630",
        "blue":          "#5a7a28",
        "green":         "#7da830",
        "yellow":        "#c2a878",
        "red":           "#aa4433",
        "white":         "#d4c8a0",
        "gray":          "#8a8a6a",
        "text_dim":      "#909070",
        "magenta":       "#8a7a50",
        "purple":        "#6a6a40",
        "bg_sidebar":    "#141808",
        "bg_content":    "#1c2010",
        "bg_input":      "#282e1a",
        "bg_hover":      "#303822",
        "bg_selected":   "#384020",
        "fg":            "#d4c8a0",
        "fg_dim":        "#aaa880",
        "fg_muted":      "#888860",
        "accent":        "#6b8e23",
        "accent_dim":    "#4a6218",
        "accent_glow":   "#8ab630",
        "separator":     "#3a4025",
        "highlight_bg":  "#2a3018",
    },

    # ── Plasma — electric glow (effects-enabled) ──────────────────
    "plasma": {
        "bg_dark":       "#070010",
        "bg_panel":      "#0c0018",
        "bg_card":       "#120024",
        "border":        "#1e0040",
        "cyan":          "#00e5ff",
        "cyan_dim":      "#0099bb",
        "cyan_glow":     "#44ffff",
        "blue":          "#4400ff",
        "green":         "#00ff88",
        "yellow":        "#ffcc00",
        "red":           "#ff0055",
        "white":         "#e8e0ff",
        "gray":          "#8877aa",
        "text_dim":      "#9988bb",
        "magenta":       "#ff00cc",
        "purple":        "#aa00ff",
        "bg_sidebar":    "#0a0014",
        "bg_content":    "#10001e",
        "bg_input":      "#1a0030",
        "bg_hover":      "#22003e",
        "bg_selected":   "#280048",
        "fg":            "#e8e0ff",
        "fg_dim":        "#b0a0cc",
        "fg_muted":      "#9080aa",
        "accent":        "#00e5ff",
        "accent_dim":    "#0099bb",
        "accent_glow":   "#44ffff",
        "separator":     "#2a0050",
        "highlight_bg":  "#1a0038",
    },
}

# ── Human-readable theme names ──

THEME_LABELS = {
    "midnight":       "Midnight",
    "obsidian":       "Obsidian",
    "dracula":        "Dracula",
    "solarized_dark": "Solarized Dark",
    "nord":           "Nord",
    "monokai":        "Monokai",
    "cyberpunk":      "Cyberpunk",
    "matrix":         "Matrix",
    "amber":          "Amber",
    "phosphor":       "Phosphor",
    "arctic":         "Arctic",
    "sunset":         "Sunset",
    "od_green":       "OD Green",
    "plasma":         "Plasma",
}

# ── Font base sizes (after +2pt readability bump) ──

_FONT_SIZES = {
    "mono":          13,
    "mono_bold":     13,
    "mono_sm":       12,
    "mono_xs":       11,
    "title":         18,
    "title_sm":      16,
    # Docs window (Segoe UI)
    "body":          13,
    "body_bold":     13,
    "heading":       16,
    "subheading":    14,
    "sidebar":       13,
    "sidebar_bold":  13,
    "search":        14,
    "small":         11,
    "doc_title":     20,
}


# ── Live singleton dicts ──
# These are the SAME objects returned by get_colors() / get_docs_colors().
# set_theme() updates them in-place so every module that holds a reference
# sees the new colors immediately — no re-import needed.

_LIVE_COLORS: dict[str, str] = {}
_LIVE_DOCS_COLORS: dict[str, str] = {}


def _rebuild_live_dicts():
    """Repopulate the live color dicts from the current theme."""
    t = THEMES.get(_current_theme, THEMES["midnight"])

    _LIVE_COLORS.clear()
    _LIVE_COLORS.update(t)

    _LIVE_DOCS_COLORS.clear()
    _LIVE_DOCS_COLORS.update({
        "bg":           t["bg_dark"],
        "bg_sidebar":   t["bg_sidebar"],
        "bg_content":   t["bg_content"],
        "bg_card":      t["bg_card"],
        "bg_input":     t["bg_input"],
        "bg_hover":     t["bg_hover"],
        "bg_selected":  t["bg_selected"],
        "fg":           t["fg"],
        "fg_dim":       t["fg_dim"],
        "fg_muted":     t["fg_muted"],
        "accent":       t["accent"],
        "accent_dim":   t["accent_dim"],
        "accent_glow":  t["accent_glow"],
        "green":        t["green"],
        "yellow":       t["yellow"],
        "red":          t["red"],
        "magenta":      t["magenta"],
        "border":       t["border"],
        "separator":    t["separator"],
        "highlight_bg": t["highlight_bg"],
        "white":        t["white"],
    })


# Initialize on first import
_rebuild_live_dicts()


# ── Public API ──

def set_theme(name: str, force: bool = False):
    """Set the active theme by name.

    Updates the live color dicts in-place so all modules that hold
    a reference to COLORS (from get_colors()) see the new colors.
    Then notifies all registered listeners with an old-hex → new-hex
    mapping so open windows can hot-swap their widget colours.

    *force* — notify listeners even if the theme hasn't changed
    (used by settings save to refresh the effects engine).
    """
    global _current_theme
    if name not in THEMES:
        log.warning("Unknown theme '%s', keeping '%s'", name, _current_theme)
        return
    if name == _current_theme and not force:
        return

    # Snapshot old colours before rebuilding
    old_main = dict(_LIVE_COLORS)
    old_docs = dict(_LIVE_DOCS_COLORS)

    _current_theme = name
    _rebuild_live_dicts()

    # Build old_hex → new_hex mapping for every colour that changed
    color_map: dict[str, str] = {}
    for key, old_hex in old_main.items():
        new_hex = _LIVE_COLORS.get(key, old_hex)
        if old_hex != new_hex:
            color_map[old_hex.lower()] = new_hex
    for key, old_hex in old_docs.items():
        new_hex = _LIVE_DOCS_COLORS.get(key, old_hex)
        if old_hex != new_hex:
            color_map[old_hex.lower()] = new_hex

    # Notify listeners
    for cb in list(_theme_listeners):
        try:
            cb(color_map)
        except Exception:
            log.debug("Theme listener error", exc_info=True)


def get_theme() -> str:
    """Return the current theme name."""
    return _current_theme


def get_colors() -> dict[str, str]:
    """Return the live COLORS dict shared by all UI modules.

    This is a LIVE reference — set_theme() updates it in-place.
    Used by: dashboard.py, settings_dialog.py, test_runner.py, model_manager.py
    """
    return _LIVE_COLORS


def get_docs_colors() -> dict[str, str]:
    """Return the live docs-window color dict.

    This is a LIVE reference — set_theme() updates it in-place.
    Maps unified theme keys to the _C naming convention.
    """
    return _LIVE_DOCS_COLORS


def get_fonts() -> dict[str, tuple]:
    """Return font tuples for all UI components.

    Keys: mono, mono_bold, mono_sm, mono_xs, title, title_sm,
          body, body_bold, heading, subheading, sidebar, sidebar_bold,
          search, small, doc_title
    """
    s = _FONT_SIZES
    return {
        "mono":          (_MONO_FAMILY, s["mono"]),
        "mono_bold":     (_MONO_FAMILY, s["mono_bold"], "bold"),
        "mono_sm":       (_MONO_FAMILY, s["mono_sm"]),
        "mono_xs":       (_MONO_FAMILY, s["mono_xs"]),
        "title":         (_MONO_FAMILY, s["title"], "bold"),
        "title_sm":      (_MONO_FAMILY, s["title_sm"], "bold"),
        # Docs window fonts
        "body":          (_BODY_FAMILY, s["body"]),
        "body_bold":     (_BODY_FAMILY, s["body_bold"], "bold"),
        "heading":       (_BODY_FAMILY, s["heading"], "bold"),
        "subheading":    (_BODY_FAMILY, s["subheading"], "bold"),
        "sidebar":       (_BODY_FAMILY, s["sidebar"]),
        "sidebar_bold":  (_BODY_FAMILY, s["sidebar_bold"], "bold"),
        "search":        (_BODY_FAMILY, s["search"]),
        "small":         (_BODY_FAMILY, s["small"]),
        "doc_title":     (_BODY_FAMILY, s["doc_title"], "bold"),
    }


def list_themes() -> list[str]:
    """Return sorted list of available theme names."""
    return sorted(THEMES.keys())
