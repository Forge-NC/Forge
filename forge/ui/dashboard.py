"""Forge Neural Cortex — enterprise GUI with depth-aware animation.

Single-window architecture:
  1. Boot phase: brain animation + status log
  2. After boot: swaps to dashboard cards + launch terminal button
  3. Polls ~/.forge/dashboard_state.json for live updates from engine

The brain's neural pathways are extracted with a depth map. RGB waves
propagate using multiplicative glow — internal structures stay visible.

Eight animation states (BOOT, IDLE, THINKING, TOOL_EXEC, INDEXING,
SWAPPING, ERROR, THREAT) with smooth cubic ease-in-out transitions.
THREAT mode: angry red rapid flash triggered by Crucible detections.

MIT-licensed dependencies only: customtkinter + Pillow + numpy.
"""

import enum
import json
import os
import subprocess
import sys
import threading
import time
import logging
import math
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Callable

try:
    import customtkinter as ctk
    from PIL import Image, ImageEnhance
    import numpy as np
    HAS_GUI_DEPS = True
except ImportError:
    HAS_GUI_DEPS = False

from forge.persona import get_persona, Persona, PERSONALITIES
from forge.audio.commands import parse_voice_command
from forge.ui.themes import (
    get_colors, get_fonts, add_theme_listener, remove_theme_listener,
    recolor_widget_tree,
)
from forge.ui.effects import EffectsEngine

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────
# Color palette & fonts — loaded from central theme system
# ──────────────────────────────────────────────────────────────────

COLORS = get_colors()

BRAIN_IMAGE_PATH = Path(__file__).parent / "assets" / "brain.png"
BRAIN_SIZE = (220, 220)
STATE_FILE = Path.home() / ".forge" / "dashboard_state.json"

_F = get_fonts()
FONT_MONO = _F["mono"]
FONT_MONO_BOLD = _F["mono_bold"]
FONT_MONO_SM = _F["mono_sm"]
FONT_MONO_XS = _F["mono_xs"]
FONT_TITLE = _F["title"]
FONT_TITLE_SM = _F["title_sm"]

# ──────────────────────────────────────────────────────────────────
# Animation State Machine
# ──────────────────────────────────────────────────────────────────

class AnimState(enum.Enum):
    BOOT = "boot"
    IDLE = "idle"
    THINKING = "thinking"
    TOOL_EXEC = "tool_exec"
    INDEXING = "indexing"
    SWAPPING = "swapping"
    ERROR = "error"
    THREAT = "threat"
    PASS = "pass"


@dataclass
class StateConfig:
    wave_count: int = 1
    speed: float = 0.4
    sigma: float = 0.18
    hue_center: float = 0.52
    hue_range: float = 0.05
    base_brightness: float = 0.55
    intensity: float = 0.5
    fps: int = 10
    saturation: float = 0.7
    render_mode: str = "radial"


STATE_CONFIGS = {
    AnimState.BOOT: StateConfig(
        wave_count=1, speed=0.3, sigma=0.20,
        hue_center=0.52, hue_range=0.08,
        base_brightness=0.35, intensity=0.7, fps=12,
        saturation=0.6, render_mode="spiral",
    ),
    AnimState.IDLE: StateConfig(
        wave_count=1, speed=0.4, sigma=0.18,
        hue_center=0.52, hue_range=0.05,
        base_brightness=0.55, intensity=0.4, fps=8,
        saturation=0.7, render_mode="radial",
    ),
    AnimState.THINKING: StateConfig(
        wave_count=3, speed=1.2, sigma=0.12,
        hue_center=0.0, hue_range=0.5,
        base_brightness=0.50, intensity=0.8, fps=14,
        saturation=0.85, render_mode="radial",
    ),
    AnimState.TOOL_EXEC: StateConfig(
        wave_count=2, speed=1.5, sigma=0.10,
        hue_center=0.42, hue_range=0.10,
        base_brightness=0.50, intensity=0.7, fps=14,
        saturation=0.8, render_mode="sweep",
    ),
    AnimState.INDEXING: StateConfig(
        wave_count=4, speed=0.8, sigma=0.08,
        hue_center=0.78, hue_range=0.08,
        base_brightness=0.45, intensity=0.6, fps=12,
        saturation=0.75, render_mode="radial",
    ),
    AnimState.SWAPPING: StateConfig(
        wave_count=1, speed=2.0, sigma=0.15,
        hue_center=0.52, hue_range=0.02,
        base_brightness=0.45, intensity=1.2, fps=16,
        saturation=0.3, render_mode="flash",
    ),
    AnimState.ERROR: StateConfig(
        wave_count=1, speed=0.6, sigma=0.25,
        hue_center=0.0, hue_range=0.02,
        base_brightness=0.50, intensity=0.9, fps=12,
        saturation=0.9, render_mode="pulse",
    ),
    AnimState.THREAT: StateConfig(
        wave_count=5, speed=3.0, sigma=0.06,
        hue_center=0.0, hue_range=0.04,
        base_brightness=0.70, intensity=1.5, fps=20,
        saturation=1.0, render_mode="flash",
    ),
    AnimState.PASS: StateConfig(
        wave_count=1, speed=0.3, sigma=0.35,
        hue_center=0.33, hue_range=0.05,
        base_brightness=0.70, intensity=0.9, fps=10,
        saturation=0.85, render_mode="radial",
    ),
}

TRANSITION_DURATION = 0.5


class AnimationEngine:
    """Drives brain animation with state-aware depth-modulated rendering."""

    def __init__(self, pathway_mask, wave_dist, depth_map,
                 brain_base_rgb, brain_alpha, sweep_x):
        self.pathway_mask = pathway_mask
        self.wave_dist = wave_dist
        self.depth_map = depth_map
        self.brain_base_rgb = brain_base_rgb
        self.brain_alpha = brain_alpha
        self.sweep_x = sweep_x

        self._state = AnimState.BOOT
        self._config = STATE_CONFIGS[AnimState.BOOT]
        self._phase: float = 0.0

        self._transitioning = False
        self._trans_start: float = 0.0
        self._trans_from: StateConfig = self._config
        self._trans_to: StateConfig = self._config

        self._flash_start: float = 0.0

        self._depth_delay = depth_map * 0.3
        self._depth_atten = 1.0 - depth_map * 0.5

    @property
    def state(self) -> AnimState:
        return self._state

    @property
    def fps(self) -> int:
        return self._get_config().fps

    def set_state(self, new_state: AnimState):
        if new_state == self._state and not self._transitioning:
            return
        self._trans_from = self._get_config()
        self._trans_to = STATE_CONFIGS[new_state]
        self._trans_start = time.monotonic()
        self._transitioning = True
        self._state = new_state
        if new_state in (AnimState.SWAPPING, AnimState.ERROR):
            self._flash_start = time.monotonic()

    def _get_config(self) -> StateConfig:
        if not self._transitioning:
            return self._config
        elapsed = time.monotonic() - self._trans_start
        t = min(elapsed / TRANSITION_DURATION, 1.0)
        if t >= 1.0:
            self._transitioning = False
            self._config = self._trans_to
            return self._config
        t = t * t * (3.0 - 2.0 * t)
        self._config = StateConfig(
            wave_count=round(_lerp(self._trans_from.wave_count,
                                    self._trans_to.wave_count, t)),
            speed=_lerp(self._trans_from.speed, self._trans_to.speed, t),
            sigma=_lerp(self._trans_from.sigma, self._trans_to.sigma, t),
            hue_center=_lerp(self._trans_from.hue_center,
                              self._trans_to.hue_center, t),
            hue_range=_lerp(self._trans_from.hue_range,
                             self._trans_to.hue_range, t),
            base_brightness=_lerp(self._trans_from.base_brightness,
                                   self._trans_to.base_brightness, t),
            intensity=_lerp(self._trans_from.intensity,
                             self._trans_to.intensity, t),
            fps=round(_lerp(self._trans_from.fps, self._trans_to.fps, t)),
            saturation=_lerp(self._trans_from.saturation,
                              self._trans_to.saturation, t),
            render_mode=self._trans_to.render_mode,
        )
        return self._config

    def advance(self, dt: float):
        self._phase += dt

    def render_frame(self):
        cfg = self._get_config()
        mode = cfg.render_mode
        if mode == "spiral":
            wave_total, color_rgb = self._calc_spiral(cfg)
        elif mode == "sweep":
            wave_total, color_rgb = self._calc_sweep(cfg)
        elif mode == "flash":
            wave_total, color_rgb = self._calc_flash(cfg)
        elif mode == "pulse":
            wave_total, color_rgb = self._calc_pulse(cfg)
        else:
            wave_total, color_rgb = self._calc_radial(cfg)

        glow_factor = 1.0 + wave_total[..., np.newaxis] * color_rgb * 2.0
        out_rgb = self.brain_base_rgb * cfg.base_brightness * glow_factor
        out_rgb = np.clip(out_rgb, 0, 255)

        h, w = self.pathway_mask.shape
        bg = np.full((h, w, 4), [10, 14, 23, 255], dtype=np.uint8)
        af = self.brain_alpha[..., np.newaxis]
        bg_f = bg[:, :, :3].astype(np.float32)
        blended = (out_rgb * af + bg_f * (1.0 - af)).astype(np.uint8)
        bg[:, :, :3] = blended
        return bg

    def _calc_radial(self, cfg):
        h, w = self.pathway_mask.shape
        wave_total = np.zeros((h, w), dtype=np.float32)
        hue_accum = np.zeros((h, w), dtype=np.float32)
        for i in range(cfg.wave_count):
            offset = i * (1.0 / max(cfg.wave_count, 1))
            wp = (self._phase * cfg.speed + offset) % 1.3
            adj = self.wave_dist + self._depth_delay
            wave = np.exp(-((adj - wp) ** 2) / (2 * cfg.sigma ** 2))
            wave = wave * self.pathway_mask * self._depth_atten * cfg.intensity
            wave_total += wave
            hue = (cfg.hue_center + cfg.hue_range *
                   math.sin(self._phase * 0.3 + i * 2.09)) % 1.0
            hue_accum += wave * hue
        safe = np.where(wave_total > 0.001, wave_total, 1.0)
        avg_hue = np.clip((hue_accum / safe) % 1.0, 0, 1)
        wave_total = np.clip(wave_total, 0, 1.5)
        r, g, b = _hsv_to_rgb(avg_hue, cfg.saturation, np.ones_like(avg_hue))
        return wave_total, np.stack([r, g, b], axis=-1)

    def _calc_spiral(self, cfg):
        h, w = self.pathway_mask.shape
        cy, cx = h / 2.0, w / 2.0
        yy = np.arange(h, dtype=np.float32).reshape(-1, 1)
        xx = np.arange(w, dtype=np.float32).reshape(1, -1)
        angle = np.arctan2(yy - cy, xx - cx) / (2 * np.pi) + 0.5
        sp = (self._phase * cfg.speed) % 1.5
        sd = (self.wave_dist + angle * 0.3) % 1.5
        wave = np.exp(-((sd - sp) ** 2) / (2 * cfg.sigma ** 2))
        wave = wave * self.pathway_mask * self._depth_atten * cfg.intensity
        wave = np.clip(wave, 0, 1.5)
        hue = np.full((h, w), cfg.hue_center, dtype=np.float32)
        boot_p = min(self._phase * cfg.speed / 3.0, 1.0)
        sat = np.full((h, w), cfg.saturation * (1 - boot_p * 0.5),
                       dtype=np.float32)
        r, g, b = _hsv_to_rgb(hue, sat, np.ones_like(hue))
        return wave, np.stack([r, g, b], axis=-1)

    def _calc_sweep(self, cfg):
        h, w = self.pathway_mask.shape
        wave_total = np.zeros((h, w), dtype=np.float32)
        for i in range(cfg.wave_count):
            offset = i * (1.0 / max(cfg.wave_count, 1))
            sp = (self._phase * cfg.speed + offset) % 1.4
            wave = np.exp(-((self.sweep_x - sp) ** 2) /
                           (2 * cfg.sigma ** 2))
            wave = wave * self.pathway_mask * self._depth_atten * cfg.intensity
            wave_total += wave
        wave_total = np.clip(wave_total, 0, 1.5)
        hue = np.full((h, w), cfg.hue_center, dtype=np.float32)
        r, g, b = _hsv_to_rgb(hue, cfg.saturation, np.ones_like(hue))
        return wave_total, np.stack([r, g, b], axis=-1)

    def _calc_flash(self, cfg):
        h, w = self.pathway_mask.shape
        elapsed = time.monotonic() - self._flash_start
        if elapsed < 0.3:
            intensity = cfg.intensity * (1.0 - (elapsed / 0.3) * 0.3)
            wave = self.pathway_mask * self._depth_atten * intensity
            return np.clip(wave, 0, 1.5), np.ones((h, w, 3), dtype=np.float32)
        fade = min((elapsed - 0.3) / 1.0, 1.0)
        mc = StateConfig(
            wave_count=1, speed=cfg.speed, sigma=cfg.sigma * (2 - fade),
            hue_center=0.52, hue_range=0.02,
            base_brightness=cfg.base_brightness,
            intensity=cfg.intensity * fade, fps=cfg.fps,
            saturation=0.6 + 0.2 * fade, render_mode="radial")
        return self._calc_radial(mc)

    def _calc_pulse(self, cfg):
        h, w = self.pathway_mask.shape
        elapsed = time.monotonic() - self._flash_start
        decay = max(0, 1.0 - elapsed / 1.5)
        wp = min(elapsed * 0.8, 1.2)
        wave = np.exp(-((self.wave_dist - wp) ** 2) /
                       (2 * cfg.sigma ** 2))
        wave = wave * self.pathway_mask * self._depth_atten * cfg.intensity * decay
        wave = np.clip(wave, 0, 1.5)
        hue = np.full((h, w), cfg.hue_center, dtype=np.float32)
        r, g, b = _hsv_to_rgb(hue, cfg.saturation, np.ones_like(hue))
        return wave, np.stack([r, g, b], axis=-1)


def _lerp(a, b, t):
    return a + (b - a) * t


def _hsv_to_rgb(h, s, v):
    h6 = (h * 6.0) % 6.0
    i = np.floor(h6).astype(np.int32) % 6
    f = h6 - np.floor(h6)
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    conds = [i == 0, i == 1, i == 2, i == 3, i == 4, i == 5]
    r = np.select(conds, [v, q, p, p, t, v], default=v)
    g = np.select(conds, [t, v, v, q, p, p], default=p)
    b = np.select(conds, [p, p, t, v, v, q], default=v)
    return (np.clip(r, 0, 1).astype(np.float32),
            np.clip(g, 0, 1).astype(np.float32),
            np.clip(b, 0, 1).astype(np.float32))


def _build_anim_engine_from_image(brain_path: Path):
    """Load brain PNG, extract pathways + depth, return AnimationEngine."""
    img = Image.open(str(brain_path)).convert("RGBA")
    img = img.resize(BRAIN_SIZE, Image.LANCZOS)
    arr = np.array(img, dtype=np.float32)
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3] / 255.0
    brightness = np.max(rgb, axis=2) / 255.0
    pathway_mask = np.clip((brightness * alpha) ** 0.7, 0, 1)
    depth_map = 1.0 - np.clip((brightness * alpha) ** 0.5, 0, 1)
    h, w = BRAIN_SIZE[1], BRAIN_SIZE[0]
    cy, cx = h / 2.0, w / 2.0
    yy = np.arange(h, dtype=np.float32).reshape(-1, 1)
    xx = np.arange(w, dtype=np.float32).reshape(1, -1)
    dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    wave_dist = dist / np.sqrt(cy ** 2 + cx ** 2)
    sweep_x = np.broadcast_to(xx / float(w), (h, w)).copy()
    return AnimationEngine(pathway_mask, wave_dist, depth_map,
                           rgb, alpha, sweep_x)


# ──────────────────────────────────────────────────────────────────
# Dashboard Card Management — drag, collapse, hide, persist
# ──────────────────────────────────────────────────────────────────

_LAYOUT_FILE = Path.home() / ".forge" / "dashboard_layout.json"

CARD_IDS = ["launch", "voice", "chat", "context", "continuity",
            "reliability", "performance", "session", "memory",
            "autoforge", "shipwright", "license"]


@dataclass
class CardDescriptor:
    """Tracks a single dashboard card's widgets and state."""
    card_id: str
    title: str
    frame: object           # CTkFrame — outer card
    header: object          # CTkFrame — header row
    divider: object         # CTkFrame — 1px line
    body: object            # CTkFrame — content area
    collapse_btn: object    # CTkLabel — toggle
    collapsed: bool = False
    hidden: bool = False
    order: int = 0


class CardManager:
    """Manages card order, collapse, hide, and drag-and-drop."""

    def __init__(self, parent_frame, effects=None):
        self._parent = parent_frame
        self._effects = effects
        self._cards: dict = {}
        self._order: list = list(CARD_IDS)
        self._collapsed: set = set()
        self._hidden: set = set()
        self._drag_state = None
        self._drop_indicator = None
        self._load_state()

    def register(self, desc: CardDescriptor):
        """Register a card descriptor."""
        self._cards[desc.card_id] = desc
        if desc.card_id in self._collapsed:
            desc.collapsed = True
        if desc.card_id in self._hidden:
            desc.hidden = True
        if desc.card_id in self._order:
            desc.order = self._order.index(desc.card_id)
        else:
            desc.order = len(self._order)
            self._order.append(desc.card_id)

    def apply_initial_state(self):
        """Apply saved collapse/hide state and repack in saved order."""
        for cid, desc in self._cards.items():
            if desc.collapsed:
                self._do_collapse(desc)
            if desc.hidden:
                self._do_hide(desc)
        self.repack_all()

    def repack_all(self):
        """Repack all visible cards in order."""
        canvas = None
        scroll_pos = None
        try:
            canvas = self._parent._parent_canvas
            scroll_pos = canvas.yview()
        except Exception:
            pass

        for cid in self._order:
            if cid in self._cards:
                try:
                    self._cards[cid].frame.pack_forget()
                except Exception:
                    pass

        for cid in self._order:
            if cid in self._cards and not self._cards[cid].hidden:
                self._cards[cid].frame.pack(fill="x", padx=8, pady=1)

        if canvas and scroll_pos:
            try:
                self._parent.after(
                    10, lambda: canvas.yview_moveto(scroll_pos[0]))
            except Exception:
                pass

    def collapse(self, card_id: str):
        desc = self._cards.get(card_id)
        if not desc or desc.collapsed:
            return
        self._do_collapse(desc)
        self._collapsed.add(card_id)
        self.save_state()

    def uncollapse(self, card_id: str):
        desc = self._cards.get(card_id)
        if not desc or not desc.collapsed:
            return
        self._do_uncollapse(desc)
        self._collapsed.discard(card_id)
        self.save_state()

    def toggle_collapse(self, card_id: str):
        desc = self._cards.get(card_id)
        if not desc:
            return
        if desc.collapsed:
            self.uncollapse(card_id)
        else:
            self.collapse(card_id)

    def hide(self, card_id: str):
        desc = self._cards.get(card_id)
        if not desc or desc.hidden:
            return
        self._do_hide(desc)
        self._hidden.add(card_id)
        self.repack_all()
        self.save_state()

    def unhide(self, card_id: str):
        desc = self._cards.get(card_id)
        if not desc or not desc.hidden:
            return
        desc.hidden = False
        self._hidden.discard(card_id)
        self.repack_all()
        self.save_state()

    def get_hidden_ids(self) -> list:
        return [cid for cid in self._order if cid in self._hidden]

    def bind_drag(self, card_id: str, *handles):
        for w in handles:
            w.bind("<ButtonPress-1>",
                   lambda e, cid=card_id: self._drag_start(e, cid))
            w.bind("<B1-Motion>", self._drag_motion)
            w.bind("<ButtonRelease-1>", self._drag_end)

    # ── Drag internals ──

    def _drag_start(self, event, card_id):
        desc = self._cards.get(card_id)
        if not desc or desc.hidden:
            return
        self._drag_state = {
            "card_id": card_id,
            "start_y": event.y_root,
            "orig_border": desc.frame.cget("border_color"),
        }
        try:
            desc.frame.configure(border_color=COLORS["cyan"])
        except Exception:
            pass

    def _drag_motion(self, event):
        if not self._drag_state:
            return
        visible = [cid for cid in self._order
                   if cid in self._cards and not self._cards[cid].hidden]
        target_idx = None
        drag_y = event.y_root

        for i, cid in enumerate(visible):
            desc = self._cards[cid]
            try:
                wy = desc.frame.winfo_rooty()
                wh = desc.frame.winfo_height()
                mid = wy + wh // 2
                if drag_y < mid:
                    target_idx = i
                    break
            except Exception:
                continue
        if target_idx is None:
            target_idx = len(visible)

        self._show_drop_indicator(visible, target_idx)

    def _drag_end(self, event):
        if not self._drag_state:
            return
        card_id = self._drag_state["card_id"]
        orig_border = self._drag_state["orig_border"]
        self._drag_state = None

        desc = self._cards.get(card_id)
        if desc:
            try:
                desc.frame.configure(border_color=orig_border)
            except Exception:
                pass

        visible = [cid for cid in self._order
                   if cid in self._cards and not self._cards[cid].hidden]
        drag_y = event.y_root
        target_idx = None
        for i, cid in enumerate(visible):
            d = self._cards[cid]
            try:
                wy = d.frame.winfo_rooty()
                wh = d.frame.winfo_height()
                mid = wy + wh // 2
                if drag_y < mid:
                    target_idx = i
                    break
            except Exception:
                continue
        if target_idx is None:
            target_idx = len(visible)

        self._hide_drop_indicator()

        if card_id in visible:
            old_idx = visible.index(card_id)
            if old_idx == target_idx or old_idx + 1 == target_idx:
                return
            visible.remove(card_id)
            if target_idx > old_idx:
                target_idx -= 1
            visible.insert(target_idx, card_id)

        new_order = list(visible)
        for cid in self._order:
            if cid not in new_order:
                new_order.append(cid)
        self._order = new_order

        self.repack_all()
        self.save_state()

    def _show_drop_indicator(self, visible, target_idx):
        self._hide_drop_indicator()
        try:
            indicator = ctk.CTkFrame(
                self._parent, fg_color=COLORS["cyan"],
                height=3, corner_radius=0)
            if target_idx < len(visible):
                target_frame = self._cards[visible[target_idx]].frame
                indicator.pack(fill="x", padx=12, pady=0,
                               before=target_frame)
            else:
                indicator.pack(fill="x", padx=12, pady=0)
            self._drop_indicator = indicator
        except Exception:
            pass

    def _hide_drop_indicator(self):
        if self._drop_indicator:
            try:
                self._drop_indicator.destroy()
            except Exception:
                pass
            self._drop_indicator = None

    # ── Collapse/hide internals ──

    def _do_collapse(self, desc: CardDescriptor):
        desc.collapsed = True
        try:
            desc.divider.pack_forget()
            desc.body.pack_forget()
            desc.collapse_btn.configure(text="\u25bc")
        except Exception:
            pass

    def _do_uncollapse(self, desc: CardDescriptor):
        desc.collapsed = False
        try:
            desc.divider.pack(fill="x", padx=10, pady=(0, 1),
                              after=desc.header)
            desc.body.pack(fill="both", expand=True,
                           after=desc.divider)
            desc.collapse_btn.configure(text="\u25b2")
        except Exception:
            pass

    def _do_hide(self, desc: CardDescriptor):
        desc.hidden = True

    # ── Persistence ──

    def save_state(self):
        data = {
            "card_order": self._order,
            "collapsed": list(self._collapsed),
            "hidden": list(self._hidden),
        }
        try:
            _LAYOUT_FILE.parent.mkdir(parents=True, exist_ok=True)
            _LAYOUT_FILE.write_text(
                json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            log.debug("Failed to save dashboard layout", exc_info=True)

    def _load_state(self):
        try:
            if _LAYOUT_FILE.exists():
                data = json.loads(
                    _LAYOUT_FILE.read_text(encoding="utf-8"))
                saved_order = data.get("card_order", [])
                merged = [c for c in saved_order if c in CARD_IDS]
                for c in CARD_IDS:
                    if c not in merged:
                        merged.append(c)
                self._order = merged
                self._collapsed = set(data.get("collapsed", []))
                self._hidden = set(data.get("hidden", []))
        except Exception:
            log.debug("Failed to load dashboard layout", exc_info=True)


# ──────────────────────────────────────────────────────────────────
# ForgeLauncher — single-window: boot → dashboard → terminal
# ──────────────────────────────────────────────────────────────────

class ForgeLauncher:
    """Primary Forge GUI. Boots, then becomes the live dashboard."""

    _instance_alive = False
    _instance_lock = threading.Lock()

    def __init__(self):
        if not HAS_GUI_DEPS:
            raise ImportError(
                "GUI requires: pip install customtkinter Pillow numpy")

        self._root: Optional[ctk.CTk] = None
        self._running = False
        self._terminal_proc: Optional[subprocess.Popen] = None
        self._status_texts: list[str] = []
        self._boot_complete = False

        # Widget refs
        self._brain_label = None
        self._state_label = None
        self._activity_dot = None
        self._content_frame = None     # holds boot OR dashboard content
        self._boot_frame = None        # status log during boot
        self._dash_frame = None        # dashboard cards after boot
        self._launch_btn = None
        self._footer_label = None
        self._ctx_bar = None
        self._ctx_label = None
        self._stat_labels: dict[str, ctk.CTkLabel] = {}
        self._voice_status_label = None
        self._voice_mode_var = None
        self._chat_display = None
        self._chat_input = None

        # Card management (drag, collapse, hide)
        self._card_mgr: Optional[CardManager] = None
        self._restore_btn = None

        # Voice input (runs in dashboard directly)
        self._voice = None
        self._voice_busy = False

        # Animation
        self._anim_engine: Optional[AnimationEngine] = None
        self._brain_ctk_img = None

        # Visual effects engine
        self._effects: Optional[EffectsEngine] = None

        # Sound
        self._sound = None
        self._last_sound_state: Optional[str] = None
        try:
            from forge.audio.sounds import SoundManager
            self._sound = SoundManager()
        except Exception:
            pass

    def run(self):
        with ForgeLauncher._instance_lock:
            if ForgeLauncher._instance_alive:
                return
            ForgeLauncher._instance_alive = True
        try:
            self._build_and_run()
        finally:
            with ForgeLauncher._instance_lock:
                ForgeLauncher._instance_alive = False

    # ── Build window ──

    def _build_and_run(self):
        # Apply saved theme BEFORE building any widgets so COLORS dict
        # reflects the user's chosen theme (and effects activate correctly)
        from forge.config import ForgeConfig
        from forge.ui.themes import set_theme
        self._config = ForgeConfig()
        _saved_theme = self._config.get("theme", "midnight")
        set_theme(_saved_theme)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self._root = ctk.CTk()
        self._root.title("Forge Neural Cortex")
        self._root.geometry("400x700")
        self._root.minsize(380, 600)
        self._root.configure(fg_color=COLORS["bg_dark"])
        self._root.resizable(True, True)
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        ico_path = Path(__file__).parent / "assets" / "forge.ico"
        if ico_path.exists():
            try:
                self._root.iconbitmap(str(ico_path))
            except Exception:
                pass

        # ── Keyboard shortcuts (no native menu bar) ──
        self._root.bind("<Control-comma>",
                        lambda e: self._open_settings())
        self._hud_overlay = None

        # ── Header ──
        header = ctk.CTkFrame(
            self._root, fg_color=COLORS["bg_panel"],
            corner_radius=0, height=44)
        header.pack(fill="x")
        header.pack_propagate(False)

        self._forge_label = ctk.CTkLabel(
            header, text="  F O R G E",
            font=ctk.CTkFont(*FONT_TITLE),
            text_color=COLORS["cyan"],
            cursor="hand2")
        self._forge_label.pack(side="left", padx=10, pady=6)
        self._forge_label.bind("<Button-1>",
                               lambda e: self._toggle_hud_menu())
        self._forge_label.bind(
            "<Enter>",
            lambda e: self._forge_label.configure(
                text_color=COLORS["cyan_glow"]))
        self._forge_label.bind(
            "<Leave>",
            lambda e: self._forge_label.configure(
                text_color=COLORS["cyan"]))

        self._subtitle_label = ctk.CTkLabel(
            header, text="Neural Cortex",
            font=ctk.CTkFont(*FONT_MONO),
            text_color=COLORS["gray"])
        self._subtitle_label.pack(side="left", pady=6)

        self._activity_dot = ctk.CTkLabel(
            header, text="  \u25cf",
            font=ctk.CTkFont(size=14),
            text_color=COLORS["cyan"])
        self._activity_dot.pack(side="right", padx=10, pady=6)

        # ── Brain section ──
        brain_frame = ctk.CTkFrame(
            self._root, fg_color=COLORS["bg_dark"], corner_radius=0)
        brain_frame.pack(fill="x", padx=10, pady=(2, 0))

        self._brain_label = ctk.CTkLabel(brain_frame, text="")
        self._brain_label.pack(pady=1)

        self._state_label = ctk.CTkLabel(
            brain_frame, text="BOOTING",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["cyan_dim"])
        self._state_label.pack(pady=(0, 1))

        self._load_brain()

        # ── Content area (boot status → dashboard cards) ──
        self._content_frame = ctk.CTkFrame(
            self._root, fg_color=COLORS["bg_dark"], corner_radius=0)
        self._content_frame.pack(fill="both", expand=True, padx=0, pady=0)

        self._build_boot_content()

        # ── Footer ──
        footer = ctk.CTkFrame(
            self._root, fg_color=COLORS["bg_panel"],
            corner_radius=0, height=28)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)

        self._footer_label = ctk.CTkLabel(
            footer, text="  Forge v0.1.0 | 100% Local | $0.00 forever",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["text_dim"])
        self._footer_label.pack(side="left", padx=5, pady=2)

        # Register for live theme hot-swap
        self._theme_cb = lambda cm: self._root.after(
            0, self._apply_theme, cm)
        add_theme_listener(self._theme_cb)

        self._running = True
        self._schedule_animation()

        # Start boot checks in background
        threading.Thread(target=self._boot_sequence, daemon=True).start()

        self._root.mainloop()

    # ── Boot phase content ──

    def _build_boot_content(self):
        """Build the boot status log in the content area."""
        self._boot_frame = ctk.CTkFrame(
            self._content_frame, fg_color=COLORS["bg_card"],
            corner_radius=6, border_color=COLORS["border"], border_width=1)
        self._boot_frame.pack(fill="x", padx=10, pady=4)

        ctk.CTkLabel(
            self._boot_frame, text="  System Status",
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            text_color=COLORS["cyan_dim"], anchor="w"
        ).pack(fill="x", padx=4, pady=(4, 1))

        ctk.CTkFrame(
            self._boot_frame, fg_color=COLORS["border"], height=1
        ).pack(fill="x", padx=10, pady=(0, 2))

        self._status_label = ctk.CTkLabel(
            self._boot_frame, text="Initializing...",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["gray"],
            anchor="w", justify="left", wraplength=340)
        self._status_label.pack(fill="x", padx=10, pady=(0, 6))

    # ── Dashboard phase content ──

    def _swap_to_dashboard(self):
        """Replace boot content with dashboard cards + launch button."""
        # Destroy boot content
        if self._boot_frame:
            self._boot_frame.destroy()
            self._boot_frame = None

        # Build scrollable dashboard in content area
        self._dash_scroll = ctk.CTkScrollableFrame(
            self._content_frame, fg_color=COLORS["bg_dark"],
            corner_radius=0,
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["cyan_dim"])
        self._dash_scroll.pack(fill="both", expand=True, padx=0, pady=0)
        self._dash_frame = self._dash_scroll

        # Initialize effects engine (before cards so _make_card can register)
        from forge.config import ForgeConfig
        fx_enabled = ForgeConfig().get("effects_enabled", True)
        self._effects = EffectsEngine(self._root, enabled=fx_enabled)

        # Initialize card manager (loads saved order/collapse/hide state)
        self._card_mgr = CardManager(self._dash_frame, self._effects)

        # Build all cards — _make_card returns (frame, body)
        # Each builder is guarded so one failure can't block the rest.
        for _builder in [
            self._build_launch_card,
            self._build_voice_card,
            self._build_chat_area,
            self._build_context_card,
            self._build_continuity_card,
            self._build_reliability_card,
            self._build_performance_card,
            self._build_session_card,
            self._build_memory_card,
            self._build_autoforge_card,
            self._build_shipwright_card,
            self._build_license_card,
        ]:
            try:
                _builder()
            except Exception:
                log.error("Card build failed: %s", _builder.__name__,
                          exc_info=True)

        # Update notification card (only if behind)
        if getattr(self, "_update_behind", 0) > 0:
            self._build_update_card()

        # Register edge glow + border color + widget glow on the dashboard.
        # Wrapped in try/except so a failure here can't kill card management,
        # voice init, or state polling below.
        try:
            from forge.ui.effects import WidgetGlow
            self._effects.register_window_edge_glow(self._root)
            self._effects.register_window_border_color(self._root)
            if self._ctx_bar:
                self._effects.register_widget(
                    self._ctx_bar, WidgetGlow.PROGRESS)
            if self._cg_bar:
                self._effects.register_widget(
                    self._cg_bar, WidgetGlow.PROGRESS)
        except Exception:
            log.debug("Effects registration failed", exc_info=True)

        # Ensure effects animation loop is running now that all
        # cards, edge glow, and widgets are registered.
        self._effects.start()

        # Apply saved layout (reorder, collapse, hide)
        self._card_mgr.apply_initial_state()

        # Force scroll region update — CTkScrollableFrame's canvas must
        # know the full content height or the last cards get clipped.
        def _fix_scroll():
            try:
                self._dash_scroll.update_idletasks()
                canvas = self._dash_scroll._parent_canvas
                canvas.configure(scrollregion=canvas.bbox("all"))
            except Exception:
                pass
        _fix_scroll()
        # Schedule a second pass after the event loop settles
        self._root.after(300, _fix_scroll)

        # Show restore button if any cards hidden
        self._update_restore_btn()

        # Initialize voice input
        self._init_dashboard_voice()

        # Start polling state file
        self._schedule_state_poll()

    def _build_launch_card(self):
        """Launch Terminal wrapped in a manageable card."""
        card, body = self._make_card(
            self._dash_frame, "launch", "Launch Terminal")

        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(1, 4))

        self._launch_btn = ctk.CTkButton(
            btn_row, text="Console",
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            fg_color=COLORS["cyan_dim"],
            hover_color=COLORS["cyan"],
            text_color=COLORS["bg_dark"],
            corner_radius=6, height=28,
            command=self._launch_terminal)
        self._launch_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self._gui_terminal = None
        gui_btn = ctk.CTkButton(
            btn_row, text="GUI Terminal",
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            fg_color=COLORS["magenta"],
            hover_color=COLORS["purple"],
            text_color=COLORS["white"],
            corner_radius=6, height=28,
            command=self._launch_gui_terminal)
        gui_btn.pack(side="left", fill="x", expand=True, padx=(4, 0))

    def _build_voice_card(self):
        """Voice mode toggle — PTT / VOX switch."""
        card, body = self._make_card(
            self._dash_frame, "voice", "Voice Input")

        toggle_frame = ctk.CTkFrame(body, fg_color="transparent")
        toggle_frame.pack(fill="x", padx=10, pady=(1, 3))

        # Load saved voice mode (default to ptt)
        saved_mode = "ptt"
        voice_file = Path.home() / ".forge" / "voice_mode.txt"
        try:
            if voice_file.exists():
                saved = voice_file.read_text(encoding="utf-8").strip()
                if saved in ("ptt", "vox"):
                    saved_mode = saved
        except Exception:
            pass
        self._voice_mode_var = ctk.StringVar(value=saved_mode)

        ptt_btn = ctk.CTkRadioButton(
            toggle_frame, text="Push-to-Talk",
            variable=self._voice_mode_var, value="ptt",
            font=ctk.CTkFont(*FONT_MONO),
            text_color=COLORS["white"],
            fg_color=COLORS["cyan"],
            border_color=COLORS["cyan_dim"],
            hover_color=COLORS["cyan_dim"],
            command=self._on_voice_mode_change)
        ptt_btn.pack(side="left", padx=(0, 15))

        vox_btn = ctk.CTkRadioButton(
            toggle_frame, text="VOX (Auto)",
            variable=self._voice_mode_var, value="vox",
            font=ctk.CTkFont(*FONT_MONO),
            text_color=COLORS["white"],
            fg_color=COLORS["magenta"],
            border_color=COLORS["purple"],
            hover_color=COLORS["purple"],
            command=self._on_voice_mode_change)
        vox_btn.pack(side="left", padx=(0, 15))

        self._voice_status_label = ctk.CTkLabel(
            toggle_frame, text="initializing...",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["gray"])
        self._voice_status_label.pack(side="right")

    def _on_voice_mode_change(self):
        """Handle voice mode toggle from GUI."""
        mode = self._voice_mode_var.get()
        # Write to state file so terminal engine picks it up too
        voice_file = Path.home() / ".forge" / "voice_mode.txt"
        try:
            voice_file.write_text(mode, encoding="utf-8")
        except Exception:
            pass
        # Switch dashboard voice mode
        if self._voice:
            self._voice.mode = mode
        if mode == "ptt":
            self._voice_status_label.configure(text="hold ` to speak")
        else:
            self._voice_status_label.configure(text="listening...")

    def _build_chat_area(self):
        """Chat display for voice interactions."""
        card, body = self._make_card(
            self._dash_frame, "chat", "Chat")

        self._chat_display = ctk.CTkTextbox(
            body, height=90,
            font=ctk.CTkFont(*FONT_MONO_SM),
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["white"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=4,
            wrap="word", state="disabled")
        self._chat_display.pack(fill="x", padx=8, pady=(1, 3))

        # Text input for typing (alternative to voice)
        input_frame = ctk.CTkFrame(body, fg_color="transparent")
        input_frame.pack(fill="x", padx=8, pady=(0, 4))

        self._chat_input = ctk.CTkEntry(
            input_frame,
            font=ctk.CTkFont(*FONT_MONO),
            fg_color=COLORS["bg_dark"],
            text_color=COLORS["white"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=6,
            placeholder_text="Type or speak...")
        self._chat_input.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self._chat_input.bind("<Return>", self._on_chat_submit)

        send_btn = ctk.CTkButton(
            input_frame, text="Send", width=50,
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            fg_color=COLORS["cyan_dim"],
            hover_color=COLORS["cyan"],
            text_color=COLORS["bg_dark"],
            corner_radius=4, height=26,
            command=lambda: self._on_chat_submit(None))
        send_btn.pack(side="right")

    def _on_chat_submit(self, event):
        """Handle typed chat input."""
        if not self._chat_input:
            return
        text = self._chat_input.get().strip()
        if not text or self._voice_busy:
            return
        self._chat_input.delete(0, "end")
        self._handle_chat_message(text)

    def _init_dashboard_voice(self):
        """Initialize voice input directly in the dashboard."""
        try:
            from forge.audio.stt import VoiceInput, check_voice_deps
        except ImportError:
            self._update_voice_label("no voice deps")
            return

        deps = check_voice_deps()
        if not deps["ready"]:
            missing = ", ".join(deps["missing"])
            self._update_voice_label(f"missing: {missing}")
            return

        def on_transcription(text):
            if self._root and self._running:
                self._root.after(0, lambda: self._handle_chat_message(text))

        def on_state_change(state):
            if not self._root or not self._running:
                return
            labels = {
                "recording": ("recording...", COLORS["red"]),
                "transcribing": ("transcribing...", COLORS["yellow"]),
                "ready": (None, None),
            }
            if state in labels:
                txt, color = labels[state]
                if txt:
                    self._root.after(0, lambda t=txt, c=color:
                        self._update_voice_label(t, c))
                else:
                    mode = self._voice_mode_var.get() if self._voice_mode_var else "ptt"
                    lbl = "hold ` to speak" if mode == "ptt" else "listening..."
                    self._root.after(0, lambda l=lbl:
                        self._update_voice_label(l))

        mode = self._voice_mode_var.get() if self._voice_mode_var else "ptt"
        self._voice = VoiceInput(
            model_size="tiny",
            hotkey="`",
            mode=mode,
            on_transcription=on_transcription,
            on_state_change=on_state_change,
        )

        if self._voice.initialize():
            self._voice.start_hotkey()
            lbl = "hold ` to speak" if mode == "ptt" else "listening..."
            self._update_voice_label(lbl)
        else:
            self._update_voice_label("init failed")
            self._voice = None

    def _update_voice_label(self, text: str, color: str = None):
        if self._voice_status_label:
            self._voice_status_label.configure(
                text=text,
                text_color=color or COLORS["gray"])

    def _handle_chat_message(self, text: str):
        """Process a chat message (from voice or typed input).

        First checks for voice commands (launch terminal, switch mode, etc).
        If no command detected, sends to Ollama as chat.
        """
        if self._voice_busy:
            return

        persona = get_persona()

        # Check for voice commands first
        cmd, remainder = parse_voice_command(text, persona.name)
        if cmd:
            self._execute_voice_command(cmd, remainder)
            return

        self._voice_busy = True
        self._chat_append(f"You: {text}\n", COLORS["cyan"])
        self._chat_append(f"{persona.name}: ", COLORS["green"])

        # Mute VOX while AI is responding (prevent feedback)
        if self._voice:
            self._voice._vox_muted = True

        threading.Thread(
            target=self._ollama_chat, args=(text,),
            daemon=True, name="DashChat").start()

    def _execute_voice_command(self, cmd: str, extra: str):
        """Execute a recognized voice command."""
        persona = get_persona()
        if cmd == "launch_terminal":
            self._chat_append(f"[{persona.name}: launching terminal]\n",
                              COLORS["cyan_dim"])
            self._launch_terminal()
        elif cmd == "switch_ptt":
            if self._voice_mode_var:
                self._voice_mode_var.set("ptt")
            self._on_voice_mode_change()
            self._chat_append(f"[{persona.name}: switched to push-to-talk]\n",
                              COLORS["cyan_dim"])
        elif cmd == "switch_vox":
            if self._voice_mode_var:
                self._voice_mode_var.set("vox")
            self._on_voice_mode_change()
            self._chat_append(f"[{persona.name}: switched to VOX mode]\n",
                              COLORS["cyan_dim"])
        elif cmd == "voice_off":
            if self._voice:
                self._voice.stop()
                self._voice = None
            self._update_voice_label("voice disabled")
            self._chat_append(f"[{persona.name}: voice disabled]\n",
                              COLORS["cyan_dim"])
        elif cmd == "show_stats":
            self._chat_append(f"[{persona.name}: stats on dashboard]\n",
                              COLORS["cyan_dim"])
        elif cmd == "show_help":
            self._chat_append(
                f"[{persona.name}] Commands: launch terminal, "
                "push to talk, vox mode, voice off, show stats, "
                "plan mode, plan mode off, help\n",
                COLORS["cyan_dim"])
        elif cmd == "plan_mode":
            # Write plan mode activation to shared state
            self._chat_append(
                f"[{persona.name}: plan mode activated]\n",
                COLORS["cyan_dim"])
            try:
                state_path = Path.home() / ".forge" / "plan_mode_voice.txt"
                state_path.write_text("on", encoding="utf-8")
            except Exception:
                pass
        elif cmd == "plan_off":
            self._chat_append(
                f"[{persona.name}: plan mode disabled]\n",
                COLORS["cyan_dim"])
            try:
                state_path = Path.home() / ".forge" / "plan_mode_voice.txt"
                state_path.write_text("off", encoding="utf-8")
            except Exception:
                pass
        elif cmd == "synapse_check":
            self._chat_append(
                f"[{persona.name}: running synapse check]\n",
                COLORS["cyan_dim"])
            self._run_synapse_check()

    def _run_synapse_check(self):
        """Cycle through all Neural Cortex thought modes.

        Switches to each AnimState, plays its sound, and TTS-announces
        the mode name.  Runs in a background thread so the GUI stays
        responsive.
        """
        import threading

        SEQUENCE = [
            (AnimState.BOOT,      "Boot"),
            (AnimState.IDLE,      "Idle"),
            (AnimState.THINKING,  "Thinking"),
            (AnimState.TOOL_EXEC, "Executing"),
            (AnimState.INDEXING,  "Indexing"),
            (AnimState.SWAPPING,  "Swapping"),
            (AnimState.ERROR,     "Error"),
            (AnimState.THREAT,    "Threat"),
        ]
        DWELL = 2.5  # seconds per mode

        def _cycle():
            # Create a TTS instance for announcements
            tts = None
            try:
                from forge.audio.tts import TextToSpeech
                from forge.config import load_config
                cfg = load_config()
                tts = TextToSpeech(engine=cfg.get("tts_engine", "edge"))
            except Exception:
                pass

            self._chat_append("Synapse check: cycling all thought modes...\n",
                              COLORS["cyan_dim"])

            for state, label in SEQUENCE:
                # Switch animation state
                if self._anim_engine:
                    self._root.after(0, self._anim_engine.set_state, state)

                # Play associated sound
                if self._sound:
                    self._sound.on_state_change(state.value)

                # TTS announce
                if tts:
                    tts.speak(label)

                # Show in chat
                self._chat_append(f"  [{label}]\n", COLORS["cyan"])

                time.sleep(DWELL)

            # Return to idle
            if self._anim_engine:
                self._root.after(0, self._anim_engine.set_state, AnimState.IDLE)
            if self._sound:
                self._sound.on_state_change("idle")
            if tts:
                tts.speak("Complete")
                time.sleep(1.0)
                tts.stop()

            self._chat_append("Synapse check complete.\n", COLORS["green"])

        threading.Thread(target=_cycle, daemon=True,
                         name="ForgeSynapseCheck").start()

    def _ollama_chat(self, prompt: str):
        """Send prompt to Ollama and stream response into chat display."""
        import requests

        persona = get_persona()
        sys_content = (
            f"{persona.system_prompt_prefix} "
            "You are a local AI coding assistant. "
            "Keep responses concise — 2-3 sentences max. "
            "You're answering via voice/chat in the dashboard GUI. "
            "You do NOT have access to tools here. If the user asks you to "
            "read, write, edit, or search files, or run commands, tell them "
            "to use the terminal (say 'launch terminal' or click the button) "
            "where you have full tool access."
        )
        messages = [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": prompt},
        ]
        payload = {
            "model": "qwen2.5-coder:14b",
            "messages": messages,
            "stream": True,
            "options": {"temperature": 0.1, "num_predict": 512},
        }

        try:
            r = requests.post(
                "http://localhost:11434/api/chat",
                json=payload, stream=True, timeout=60)
            if r.status_code != 200:
                self._root.after(0, lambda:
                    self._chat_append(f"[Error: Ollama {r.status_code}]\n",
                                      COLORS["red"]))
                return

            for line in r.iter_lines():
                if not line or not self._running:
                    break
                import json as _json
                data = _json.loads(line)
                content = data.get("message", {}).get("content", "")
                if content:
                    self._root.after(0, lambda c=content:
                        self._chat_append(c))
                if data.get("done"):
                    self._root.after(0, lambda:
                        self._chat_append("\n\n"))
                    break
        except requests.exceptions.ConnectionError:
            self._root.after(0, lambda:
                self._chat_append("[Ollama not running]\n", COLORS["red"]))
        except Exception as e:
            self._root.after(0, lambda:
                self._chat_append(f"[Error: {e}]\n", COLORS["red"]))
        finally:
            self._voice_busy = False
            if self._voice:
                self._voice._vox_muted = False

    def _chat_append(self, text: str, color: str = None):
        """Append text to the chat display (thread-safe via after())."""
        if not self._chat_display:
            return
        self._chat_display.configure(state="normal")
        self._chat_display.insert("end", text)
        self._chat_display.see("end")
        self._chat_display.configure(state="disabled")

    def _build_context_card(self):
        card, body = self._make_card(
            self._dash_frame, "context", "Context Window")

        bar_frame = ctk.CTkFrame(body, fg_color="transparent")
        bar_frame.pack(fill="x", padx=10, pady=(0, 1))

        self._ctx_bar = ctk.CTkProgressBar(
            bar_frame, height=10, corner_radius=3,
            fg_color=COLORS["bg_dark"],
            progress_color=COLORS["cyan"],
            border_color=COLORS["border"], border_width=1)
        self._ctx_bar.pack(fill="x")
        self._ctx_bar.set(0)

        self._ctx_label = ctk.CTkLabel(
            body, text="0% | 0 / 0 tokens",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["gray"])
        self._ctx_label.pack(padx=10, anchor="w")

        self._stat_labels["partitions"] = ctk.CTkLabel(
            body, text="core: 0 | working: 0 | ref: 0 | recall: 0",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["text_dim"])
        self._stat_labels["partitions"].pack(padx=10, anchor="w", pady=(0, 2))

    def _build_continuity_card(self):
        card, body = self._make_card(
            self._dash_frame, "continuity", "Continuity Grade")

        # Grade + progress bar row
        grade_frame = ctk.CTkFrame(body, fg_color="transparent")
        grade_frame.pack(fill="x", padx=10, pady=(0, 1))

        self._cg_grade_label = ctk.CTkLabel(
            grade_frame, text="A",
            font=ctk.CTkFont(*FONT_TITLE),
            text_color=COLORS["green"], width=36)
        self._cg_grade_label.pack(side="left")

        self._cg_bar = ctk.CTkProgressBar(
            grade_frame, height=10, corner_radius=3,
            fg_color=COLORS["bg_dark"],
            progress_color=COLORS["green"],
            border_color=COLORS["border"], border_width=1)
        self._cg_bar.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self._cg_bar.set(1.0)

        self._cg_score_label = ctk.CTkLabel(
            body, text="100/100 | 0 swaps",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["gray"])
        self._cg_score_label.pack(padx=10, anchor="w", pady=(0, 2))

        # Sparkline placeholder for continuity trend
        self._cg_sparkline_label = ctk.CTkLabel(
            body, text="", height=24)
        self._cg_sparkline_label.pack(fill="x", padx=10, pady=(2, 4))
        self._cg_sparkline_img = None
        self._cg_sparkline_hash = ""

    def _build_reliability_card(self):
        card, body = self._make_card(
            self._dash_frame, "reliability", "Reliability")

        # Score + progress bar row
        score_frame = ctk.CTkFrame(body, fg_color="transparent")
        score_frame.pack(fill="x", padx=10, pady=(0, 1))

        self._rel_score_label = ctk.CTkLabel(
            score_frame, text="--",
            font=ctk.CTkFont(*FONT_TITLE),
            text_color=COLORS["green"], width=36)
        self._rel_score_label.pack(side="left")

        self._rel_bar = ctk.CTkProgressBar(
            score_frame, height=10, corner_radius=3,
            fg_color=COLORS["bg_dark"],
            progress_color=COLORS["green"],
            border_color=COLORS["border"], border_width=1)
        self._rel_bar.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self._rel_bar.set(1.0)

        for key, label, default in [
            ("rel_verify", "Verification", "--%"),
            ("rel_continuity", "Continuity", "--"),
            ("rel_tools", "Tool Success", "--%"),
            ("rel_trend", "30-Session", "--"),
        ]:
            self._add_stat_row(body, key, label, default)

        # Sparkline placeholder
        self._rel_sparkline_label = ctk.CTkLabel(
            body, text="", height=24)
        self._rel_sparkline_label.pack(fill="x", padx=10, pady=(2, 4))
        self._rel_sparkline_img = None
        self._rel_sparkline_hash = ""

    def _build_performance_card(self):
        card, body = self._make_card(
            self._dash_frame, "performance", "Performance")
        for key, label, default in [
            ("tok_s", "Throughput", "-- tok/s"),
            ("trend", "Trend", "--"),
            ("cache", "Cache Hit", "--%"),
            ("swaps", "Auto-Swaps", "0"),
        ]:
            self._add_stat_row(body, key, label, default)

        # Sparkline placeholder for throughput trend
        self._perf_sparkline_label = ctk.CTkLabel(
            body, text="", height=24)
        self._perf_sparkline_label.pack(fill="x", padx=10, pady=(2, 4))
        self._perf_sparkline_img = None
        self._perf_sparkline_hash = ""

    def _build_session_card(self):
        card, body = self._make_card(
            self._dash_frame, "session", "Session")
        for key, label, default in [
            ("turns", "Turns", "0"),
            ("duration", "Duration", "0m"),
            ("tokens", "Tokens", "0"),
            ("cost_saved", "Saved vs Opus", "$0.00"),
        ]:
            self._add_stat_row(body, key, label, default)

    def _build_memory_card(self):
        card, body = self._make_card(
            self._dash_frame, "memory", "Memory")
        for key, label, default in [
            ("journal", "Journal", "0 entries"),
            ("index", "Sem. Index", "not loaded"),
            ("mem_status", "Status", "Ready"),
        ]:
            self._add_stat_row(body, key, label, default,
                               val_color=COLORS["cyan_dim"])

    def _build_autoforge_card(self):
        card, body = self._make_card(
            self._dash_frame, "autoforge", "AutoForge")
        for key, label, default in [
            ("af_status", "Status", "disabled"),
            ("af_pending", "Pending", "0"),
            ("af_commits", "Commits", "0"),
        ]:
            self._add_stat_row(body, key, label, default)
        # Recent commits mini-list
        self._af_recent = ctk.CTkLabel(
            body, text="", font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["text_dim"], anchor="w", justify="left",
            wraplength=280)
        self._af_recent.pack(fill="x", padx=10, pady=(2, 4))

    def _build_shipwright_card(self):
        card, body = self._make_card(
            self._dash_frame, "shipwright", "Shipwright")
        for key, label, default in [
            ("sw_version", "Version", "0.0.0"),
            ("sw_unreleased", "Unreleased", "0 commits"),
            ("sw_bump", "Suggested", "--"),
            ("sw_last", "Last Release", "--"),
        ]:
            self._add_stat_row(body, key, label, default)

    def _build_license_card(self):
        card, body = self._make_card(
            self._dash_frame, "license", "License")
        # Tier badge
        tier_row = ctk.CTkFrame(body, fg_color="transparent", height=24)
        tier_row.pack(fill="x", padx=10, pady=(2, 1))
        tier_row.pack_propagate(False)
        self._lic_card_tier = ctk.CTkLabel(
            tier_row, text="Community",
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            text_color=COLORS["green"])
        self._lic_card_tier.pack(side="left")
        # Maturity bar
        self._lic_card_bar = ctk.CTkProgressBar(
            tier_row, height=8, corner_radius=3,
            fg_color=COLORS["bg_dark"],
            progress_color=COLORS["cyan"])
        self._lic_card_bar.pack(
            side="right", fill="x", expand=True, padx=(10, 0))
        self._lic_card_bar.set(0.0)
        for key, label, default in [
            ("lic_maturity", "Maturity", "0%"),
            ("lic_acts", "Activations", "1/1"),
            ("lic_genome", "Genome", "resets"),
        ]:
            self._add_stat_row(body, key, label, default)

    def _make_card(self, parent, card_id: str, title: str):
        """Create a dashboard card with drag handle, collapse/hide buttons.

        Returns (frame, body) — callers pack content into body.
        """
        frame = ctk.CTkFrame(
            parent, fg_color=COLORS["bg_card"],
            corner_radius=6,
            border_color=COLORS["border"], border_width=1)
        frame.pack(fill="x", padx=8, pady=1)

        # Header row
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=4, pady=(2, 0))

        # Drag handle
        drag_handle = ctk.CTkLabel(
            header, text="\u2261", font=ctk.CTkFont(*FONT_MONO_BOLD),
            text_color=COLORS["gray"], width=18, cursor="fleur")
        drag_handle.pack(side="left", padx=(2, 0))

        # Title
        title_lbl = ctk.CTkLabel(
            header, text=f" {title}",
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            text_color=COLORS["cyan_dim"], anchor="w")
        title_lbl.pack(side="left", fill="x", expand=True)

        # Hide button
        hide_btn = ctk.CTkLabel(
            header, text="\u00d7", font=ctk.CTkFont(*FONT_MONO_BOLD),
            text_color=COLORS["gray"], width=18, cursor="hand2")
        hide_btn.pack(side="right", padx=(0, 4))
        hide_btn.bind(
            "<Enter>",
            lambda e: hide_btn.configure(text_color=COLORS["red"]))
        hide_btn.bind(
            "<Leave>",
            lambda e: hide_btn.configure(text_color=COLORS["gray"]))
        hide_btn.bind(
            "<Button-1>",
            lambda e, cid=card_id: self._on_card_hide(cid))

        # Collapse button
        collapse_btn = ctk.CTkLabel(
            header, text="\u25b2", font=ctk.CTkFont(*FONT_MONO),
            text_color=COLORS["gray"], width=18, cursor="hand2")
        collapse_btn.pack(side="right", padx=(0, 2))
        collapse_btn.bind(
            "<Enter>",
            lambda e: collapse_btn.configure(text_color=COLORS["cyan"]))
        collapse_btn.bind(
            "<Leave>",
            lambda e: collapse_btn.configure(text_color=COLORS["gray"]))
        collapse_btn.bind(
            "<Button-1>",
            lambda e, cid=card_id: self._on_card_collapse(cid))

        # Divider
        divider = ctk.CTkFrame(frame, fg_color=COLORS["border"], height=1)
        divider.pack(fill="x", padx=10, pady=(0, 1))

        # Body — content goes here
        body = ctk.CTkFrame(frame, fg_color="transparent")
        body.pack(fill="both", expand=True)

        # Register with effects engine
        if self._effects:
            self._effects.register_card(frame, divider)

        # Register with card manager
        desc = CardDescriptor(
            card_id=card_id, title=title,
            frame=frame, header=header,
            divider=divider, body=body,
            collapse_btn=collapse_btn)
        self._card_mgr.register(desc)
        self._card_mgr.bind_drag(card_id, drag_handle, title_lbl)

        return frame, body

    def _on_card_collapse(self, card_id: str):
        """Toggle collapse on a card."""
        if self._card_mgr:
            self._card_mgr.toggle_collapse(card_id)

    def _on_card_hide(self, card_id: str):
        """Hide a card and show restore button."""
        if self._card_mgr:
            self._card_mgr.hide(card_id)
            self._update_restore_btn()

    def _update_restore_btn(self):
        """Show or hide the 'Restore Cards' button based on hidden cards."""
        if not self._card_mgr:
            return
        hidden = self._card_mgr.get_hidden_ids()

        if hidden and not self._restore_btn:
            self._restore_btn = ctk.CTkButton(
                self._dash_frame, text="Restore Hidden Cards",
                font=ctk.CTkFont(*FONT_MONO),
                fg_color=COLORS["border"],
                hover_color=COLORS["cyan_dim"],
                text_color=COLORS["gray"],
                corner_radius=4, height=24,
                command=self._show_restore_popup)
            self._restore_btn.pack(fill="x", padx=15, pady=(4, 2))
        elif not hidden and self._restore_btn:
            self._restore_btn.destroy()
            self._restore_btn = None

    def _show_restore_popup(self):
        """Popup listing hidden cards with restore buttons."""
        if not self._card_mgr:
            return
        hidden = self._card_mgr.get_hidden_ids()
        if not hidden:
            return

        popup = ctk.CTkToplevel(self._root)
        popup.title("Restore Cards")
        popup.geometry("260x300")
        popup.configure(fg_color=COLORS["bg_dark"])
        popup.transient(self._root)
        popup.grab_set()
        popup.resizable(False, False)

        popup.update_idletasks()
        x = self._root.winfo_x() + (self._root.winfo_width() - 260) // 2
        y = self._root.winfo_y() + (self._root.winfo_height() - 300) // 2
        popup.geometry(f"+{max(0, x)}+{max(0, y)}")

        ctk.CTkLabel(
            popup, text="Hidden Cards",
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            text_color=COLORS["cyan"]
        ).pack(pady=(12, 8))

        for cid in hidden:
            desc = self._card_mgr._cards.get(cid)
            title = desc.title if desc else cid

            row = ctk.CTkFrame(popup, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=2)

            ctk.CTkLabel(
                row, text=title,
                font=ctk.CTkFont(*FONT_MONO),
                text_color=COLORS["white"], anchor="w"
            ).pack(side="left", fill="x", expand=True)

            ctk.CTkButton(
                row, text="Show", width=60, height=24,
                font=ctk.CTkFont(*FONT_MONO_SM),
                fg_color=COLORS["cyan_dim"],
                hover_color=COLORS["cyan"],
                text_color=COLORS["bg_dark"],
                corner_radius=4,
                command=lambda c=cid, p=popup: (
                    self._card_mgr.unhide(c),
                    self._update_restore_btn(),
                    p.destroy())
            ).pack(side="right")

        ctk.CTkButton(
            popup, text="Restore All", width=120, height=28,
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            fg_color=COLORS["cyan_dim"],
            hover_color=COLORS["cyan"],
            text_color=COLORS["bg_dark"],
            corner_radius=4,
            command=lambda: (
                [self._card_mgr.unhide(c) for c in hidden],
                self._update_restore_btn(),
                popup.destroy())
        ).pack(pady=(12, 8))

    def _add_stat_row(self, parent, key, label, default,
                      val_color=None):
        row = ctk.CTkFrame(parent, fg_color="transparent", height=20)
        row.pack(fill="x", padx=10, pady=(0, 1))
        row.pack_propagate(False)
        ctk.CTkLabel(
            row, text=label,
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["gray"], width=100, anchor="w"
        ).pack(side="left")
        val = ctk.CTkLabel(
            row, text=default,
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=val_color or COLORS["white"], anchor="e")
        val.pack(side="right")
        self._stat_labels[key] = val

    # ── Brain image + animation engine ──

    def _load_brain(self):
        if not BRAIN_IMAGE_PATH.exists():
            self._brain_label.configure(
                text="[brain.png not found]",
                text_color=COLORS["gray"])
            return
        try:
            self._anim_engine = _build_anim_engine_from_image(BRAIN_IMAGE_PATH)
            frame_arr = self._anim_engine.render_frame()
            frame_pil = Image.fromarray(frame_arr, "RGBA")
            ctk_img = ctk.CTkImage(
                light_image=frame_pil, dark_image=frame_pil,
                size=BRAIN_SIZE)
            self._brain_label.configure(image=ctk_img, text="")
            self._brain_ctk_img = ctk_img
        except Exception as e:
            log.warning("Brain load failed: %s", e)
            self._brain_label.configure(
                text="[image error]", text_color=COLORS["red"])

    def _schedule_animation(self):
        if not self._running or not self._anim_engine:
            return

        fps = self._anim_engine.fps
        interval_ms = max(30, int(1000 / fps))
        self._anim_engine.advance(1.0 / fps)

        try:
            frame_arr = self._anim_engine.render_frame()
            frame_pil = Image.fromarray(frame_arr, "RGBA")
            ctk_img = ctk.CTkImage(
                light_image=frame_pil, dark_image=frame_pil,
                size=BRAIN_SIZE)
            self._brain_label.configure(image=ctk_img)
            self._brain_ctk_img = ctk_img
        except Exception:
            pass

        # Update activity dot + state label
        if self._activity_dot and self._anim_engine:
            state = self._anim_engine.state
            state_colors = {
                AnimState.BOOT: COLORS["cyan"],
                AnimState.IDLE: COLORS["gray"],
                AnimState.THINKING: COLORS["cyan_glow"],
                AnimState.TOOL_EXEC: COLORS["green"],
                AnimState.INDEXING: COLORS["magenta"],
                AnimState.SWAPPING: COLORS["yellow"],
                AnimState.ERROR: COLORS["red"],
            }
            dot_color = state_colors.get(state, COLORS["gray"])
            if state != AnimState.IDLE:
                pulse = 0.5 + 0.5 * math.sin(self._anim_engine._phase * 6)
                if pulse < 0.4:
                    dot_color = COLORS["gray"]
            self._activity_dot.configure(text_color=dot_color)

        if self._state_label and self._anim_engine:
            names = {
                AnimState.BOOT: "BOOTING", AnimState.IDLE: "IDLE",
                AnimState.THINKING: "THINKING",
                AnimState.TOOL_EXEC: "EXECUTING",
                AnimState.INDEXING: "INDEXING",
                AnimState.SWAPPING: "SWAPPING",
                AnimState.ERROR: "ERROR",
            }
            self._state_label.configure(
                text=names.get(self._anim_engine.state, ""))

        if self._root and self._running:
            self._root.after(interval_ms, self._schedule_animation)

    # ── Boot sequence ──

    def _add_status(self, text: str):
        self._status_texts.append(text)
        if len(self._status_texts) > 8:
            self._status_texts = self._status_texts[-8:]
        display = "\n".join(self._status_texts)
        if self._root and self._running and self._status_label:
            self._root.after(0, lambda d=display:
                             self._status_label.configure(text=d))

    def _show_persona_setup(self):
        """First-run dialog: let user name their AI and pick personality."""
        persona = get_persona()
        if persona.configured:
            return  # already set up

        dialog = ctk.CTkToplevel(self._root)
        dialog.title("Name Your AI")
        dialog.geometry("340x380")
        dialog.configure(fg_color=COLORS["bg_dark"])
        dialog.transient(self._root)
        dialog.grab_set()
        dialog.resizable(False, False)

        # Center on parent
        dialog.update_idletasks()
        x = self._root.winfo_x() + (self._root.winfo_width() - 340) // 2
        y = self._root.winfo_y() + (self._root.winfo_height() - 380) // 2
        dialog.geometry(f"+{x}+{y}")

        ctk.CTkLabel(
            dialog, text="Name Your AI",
            font=ctk.CTkFont(*FONT_TITLE),
            text_color=COLORS["cyan"]
        ).pack(pady=(18, 4))

        ctk.CTkLabel(
            dialog, text="Give your Forge a name it'll respond to",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["gray"]
        ).pack(pady=(0, 10))

        name_entry = ctk.CTkEntry(
            dialog, font=ctk.CTkFont(*FONT_MONO),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["white"],
            border_color=COLORS["cyan_dim"],
            border_width=1, corner_radius=6,
            placeholder_text="e.g. Jerry, Nova, Atlas...",
            width=260, height=36)
        name_entry.pack(pady=(0, 12))
        name_entry.focus()

        ctk.CTkLabel(
            dialog, text="Personality",
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            text_color=COLORS["cyan_dim"]
        ).pack(anchor="w", padx=40, pady=(0, 4))

        personality_var = ctk.StringVar(value="professional")
        for key, info in PERSONALITIES.items():
            ctk.CTkRadioButton(
                dialog, text=f"{key.title()} — {info['desc']}",
                variable=personality_var, value=key,
                font=ctk.CTkFont(*FONT_MONO_SM),
                text_color=COLORS["white"],
                fg_color=COLORS["cyan"],
                border_color=COLORS["cyan_dim"],
                hover_color=COLORS["cyan_dim"],
            ).pack(anchor="w", padx=44, pady=2)

        result = {"done": False}

        def on_save():
            name = name_entry.get().strip()
            if not name:
                name = "Forge"
            persona.name = name
            persona.personality = personality_var.get()
            persona.save()
            result["done"] = True
            dialog.destroy()

        def on_skip():
            result["done"] = True
            dialog.destroy()

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=(14, 0))

        ctk.CTkButton(
            btn_frame, text="Save", width=120, height=32,
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            fg_color=COLORS["cyan_dim"],
            hover_color=COLORS["cyan"],
            text_color=COLORS["bg_dark"],
            corner_radius=6, command=on_save
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame, text="Skip", width=80, height=32,
            font=ctk.CTkFont(*FONT_MONO),
            fg_color=COLORS["border"],
            hover_color=COLORS["bg_card"],
            text_color=COLORS["gray"],
            corner_radius=6, command=on_skip
        ).pack(side="left", padx=5)

        name_entry.bind("<Return>", lambda e: on_save())
        dialog.wait_window()

    def _show_telemetry_setup(self):
        """Show first-run telemetry quick-setup dialog."""
        self._telemetry_setup_done = False

        dialog = ctk.CTkToplevel(self._root)
        dialog.title("Quick Setup")
        dialog.geometry("400x280")
        dialog.transient(self._root)
        dialog.grab_set()
        dialog.configure(fg_color=COLORS["bg_dark"])
        dialog.resizable(False, False)

        # Center
        dialog.update_idletasks()
        px = self._root.winfo_x() + (self._root.winfo_width() - 400) // 2
        py = self._root.winfo_y() + (self._root.winfo_height() - 280) // 2
        dialog.geometry(f"+{max(0, px)}+{max(0, py)}")

        ctk.CTkLabel(
            dialog, text="Telemetry Setup",
            font=ctk.CTkFont(*FONT_TITLE_SM),
            text_color=COLORS["cyan"],
        ).pack(pady=(16, 4))

        ctk.CTkLabel(
            dialog,
            text="Paste the telemetry token from your admin.\nLeave blank to skip.",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["gray"],
        ).pack(pady=(0, 12))

        ctk.CTkLabel(
            dialog, text="Token:",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["white"], anchor="w",
        ).pack(fill="x", padx=40)

        token_entry = ctk.CTkEntry(
            dialog,
            font=ctk.CTkFont(*FONT_MONO_SM),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["white"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=4,
            width=320, height=30,
            placeholder_text="64-char hex token",
        )
        token_entry.pack(padx=40, pady=(2, 8))

        ctk.CTkLabel(
            dialog, text="Label:",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["white"], anchor="w",
        ).pack(fill="x", padx=40)

        # Auto-generate label from hostname + GPU
        auto_label = ""
        try:
            import socket
            hostname = socket.gethostname().split(".")[0].lower()
            auto_label = hostname
            try:
                from forge.hardware import detect_gpu
                gpu = detect_gpu()
                gpu_name = gpu.get("name", "")
                if gpu_name:
                    short = gpu_name.split()[-1].lower()
                    auto_label = f"{hostname}-{short}"
            except Exception:
                pass
        except Exception:
            pass

        label_entry = ctk.CTkEntry(
            dialog,
            font=ctk.CTkFont(*FONT_MONO_SM),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["white"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=4,
            width=320, height=30,
        )
        label_entry.pack(padx=40, pady=(2, 12))
        if auto_label:
            label_entry.insert(0, auto_label)

        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=40, pady=(0, 16))

        def on_skip():
            # Mark as prompted so dialog doesn't nag on every boot
            self._config.set("telemetry_prompted", True)
            self._config.save()
            self._telemetry_setup_done = True
            dialog.destroy()

        def on_save():
            tok = token_entry.get().strip()
            lbl = label_entry.get().strip()
            if tok:
                self._config.set("telemetry_enabled", True)
                self._config.set("telemetry_token", tok)
                if lbl:
                    self._config.set("telemetry_label", lbl)
                self._config.save()
            self._telemetry_setup_done = True
            dialog.destroy()

        ctk.CTkButton(
            btn_row, text="Save", width=130,
            fg_color=COLORS["cyan_dim"],
            hover_color=COLORS["cyan"],
            text_color=COLORS["bg_dark"],
            font=ctk.CTkFont(*FONT_MONO_SM),
            height=32,
            command=on_save,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="Skip", width=130,
            fg_color=COLORS["bg_card"],
            hover_color=COLORS["bg_panel"],
            text_color=COLORS["gray"],
            font=ctk.CTkFont(*FONT_MONO_SM),
            height=32,
            command=on_skip,
        ).pack(side="left")

        dialog.protocol("WM_DELETE_WINDOW", on_skip)

    def _boot_sequence(self):
        try:
            self._boot_sequence_inner()
        except Exception as e:
            self._add_status(f"[!!] Boot error: {e}")
            # Still swap to dashboard so user isn't permanently stuck
            self._boot_complete = True
            if self._root and self._running:
                self._root.after(1000, self._swap_to_dashboard)

    def _boot_sequence_inner(self):
        # Set Ollama env vars (needed when launched via pythonw without .bat)
        os.environ.setdefault("OLLAMA_FLASH_ATTENTION", "1")
        os.environ.setdefault("OLLAMA_KV_CACHE_TYPE", "q8_0")
        os.environ.setdefault("OLLAMA_MAX_LOADED_MODELS", "2")

        # First-run: persona name setup
        persona = get_persona()
        if not persona.configured:
            self._root.after(0, self._show_persona_setup)
            # Wait for dialog to finish before continuing boot
            import time as _time
            for _ in range(300):  # up to 30s
                _time.sleep(0.1)
                if persona.configured or not self._running:
                    break
            # Reload persona after setup
            persona = get_persona()

        # First-run telemetry setup (only once — skip if already prompted)
        _telem_token = self._config.get("telemetry_token", "")
        _telem_on = self._config.get("telemetry_enabled", False)
        _telem_prompted = self._config.get("telemetry_prompted", False)
        if not _telem_token and not _telem_on and not _telem_prompted:
            self._root.after(0, self._show_telemetry_setup)
            import time as _time2
            for _ in range(300):  # up to 30s
                _time2.sleep(0.1)
                if getattr(self, "_telemetry_setup_done", False) or not self._running:
                    break

        # Update subtitle with persona name
        if persona.name != "Forge":
            self._root.after(0, lambda: self._subtitle_label.configure(
                text=f'"{persona.name}" — Neural Cortex'))

        # Play boot sound
        if self._sound:
            self._sound.play("boot")

        time.sleep(0.5)
        self._add_status("[..] Checking Ollama...")

        import requests
        ollama_ok = False
        try:
            resp = requests.get("http://localhost:11434/api/tags", timeout=3)
            if resp.status_code == 200:
                ollama_ok = True
        except Exception:
            pass

        if not ollama_ok:
            # Auto-start Ollama
            self._add_status("[..] Starting Ollama...")
            try:
                startflags = 0
                if os.name == "nt":
                    startflags = subprocess.CREATE_NO_WINDOW
                subprocess.Popen(
                    ["ollama", "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=startflags,
                )
                # Wait for it to come up
                for attempt in range(15):
                    time.sleep(1)
                    try:
                        resp = requests.get(
                            "http://localhost:11434/api/tags", timeout=2)
                        if resp.status_code == 200:
                            ollama_ok = True
                            break
                    except Exception:
                        pass
                    self._add_status(
                        f"[..] Waiting for Ollama ({attempt + 1}s)...")
            except FileNotFoundError:
                self._add_status("[!!] Ollama not installed")
                self._add_status("     Install: https://ollama.com")
            except Exception as e:
                self._add_status(f"[!!] Ollama start failed: {e}")

        if ollama_ok:
            self._add_status("[OK] Ollama running")
            try:
                resp = requests.get(
                    "http://localhost:11434/api/tags", timeout=3)
                data = resp.json()
                models = [m["name"] for m in data.get("models", [])]
                if models:
                    self._add_status(
                        f"[OK] Models: {', '.join(models[:3])}")
                else:
                    self._add_status("[!!] No models pulled")
            except Exception:
                pass
        else:
            self._add_status("[!!] Ollama failed to start")

        time.sleep(0.3)
        self._add_status("[..] Detecting hardware...")
        try:
            from forge.hardware import get_hardware_summary
            hw = get_hardware_summary()
            gpu = hw.get("gpu")
            ram = hw.get("ram_gb", 0)
            vram = hw.get("vram_gb", 0)
            if gpu:
                self._add_status(
                    f"[OK] {gpu['name']} ({vram}GB VRAM)")
            elif ram:
                self._add_status(f"[OK] CPU mode ({ram:.0f}GB RAM)")
            else:
                self._add_status("[OK] Hardware detected")
        except Exception as e:
            self._add_status(f"[!!] Hardware: {e}")
            hw = {}

        time.sleep(0.3)
        try:
            vram_gb = hw.get("vram_gb", 0) if hw else 0
            if vram_gb > 0:
                from forge.hardware import calculate_max_context
                ctx_info = calculate_max_context(vram_gb, "qwen2.5-coder:14b")
                rec_ctx = ctx_info.get("recommended_context", 0)
                rec_mode = ctx_info.get("recommended_mode", "?")
                if rec_ctx > 0:
                    self._add_status(
                        f"[OK] Context: ~{rec_ctx:,} tokens "
                        f"(KV: {rec_mode.upper()})")
        except Exception:
            pass

        # Auto-update check (silent on failure)
        self._update_behind = 0
        self._update_version = ""
        self._update_changelog = []
        try:
            import subprocess as _sp
            _forge_root = str(Path(__file__).parent.parent.parent)
            _flags = {}
            if os.name == "nt":
                _flags["creationflags"] = _sp.CREATE_NO_WINDOW
            _sp.run(
                ["git", "fetch", "origin"],
                cwd=_forge_root,
                capture_output=True, timeout=10, **_flags,
            )
            result = _sp.run(
                ["git", "rev-list", "--count", "HEAD..origin/master"],
                cwd=_forge_root,
                capture_output=True, text=True, timeout=5, **_flags,
            )
            if result.returncode == 0:
                count = int(result.stdout.strip())
                self._update_behind = count
                if count > 0:
                    # Get remote version from pyproject.toml
                    ver_result = _sp.run(
                        ["git", "show", "origin/master:pyproject.toml"],
                        cwd=_forge_root,
                        capture_output=True, text=True, timeout=5, **_flags,
                    )
                    if ver_result.returncode == 0:
                        import re as _re
                        m = _re.search(
                            r'version\s*=\s*"([^"]+)"', ver_result.stdout)
                        if m:
                            self._update_version = m.group(1)
                    # Get changelog (recent commits)
                    log_result = _sp.run(
                        ["git", "log", "--oneline",
                         f"HEAD..origin/master"],
                        cwd=_forge_root,
                        capture_output=True, text=True, timeout=5, **_flags,
                    )
                    if log_result.returncode == 0:
                        self._update_changelog = [
                            l.strip() for l in
                            log_result.stdout.strip().split("\n")[:8]
                            if l.strip()
                        ]
                    ver_str = (f" (v{self._update_version})"
                               if self._update_version else "")
                    self._add_status(
                        f"[!!] Update available{ver_str}: "
                        f"{count} new commit{'s' if count != 1 else ''}")
                else:
                    self._add_status("[OK] Forge is up to date")
        except Exception:
            pass  # Silent failure -- no network, no git, etc.

        time.sleep(0.2)
        persona = get_persona()
        self._add_status(f"[OK] {persona.name} is ready")

        # Play ready sound
        if self._sound:
            self._sound.stop()
            self._sound.play("ready")

        if self._anim_engine:
            self._anim_engine.set_state(AnimState.IDLE)

        self._boot_complete = True
        if self._root and self._running:
            self._root.after(500, self._swap_to_dashboard)

    # ── Update notification card ──

    def _build_update_card(self):
        """Build an update notification card at the top of the dashboard."""
        n = getattr(self, "_update_behind", 0)
        if n <= 0:
            return

        ver = getattr(self, "_update_version", "")
        changelog = getattr(self, "_update_changelog", [])

        card = ctk.CTkFrame(
            self._dash_frame, fg_color=COLORS["bg_card"],
            corner_radius=8, border_width=1, border_color=COLORS["yellow"],
        )
        card.pack(fill="x", padx=12, pady=(8, 4))
        self._update_card = card

        # Header row
        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(8, 0))

        title = f"Update to v{ver}" if ver else "Update Available"
        subtitle = f"{n} new commit{'s' if n != 1 else ''}"
        ctk.CTkLabel(
            header,
            text=f"{title}  --  {subtitle}",
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            text_color=COLORS["yellow"], anchor="w",
        ).pack(side="left")

        # Changelog preview
        if changelog:
            cl_frame = ctk.CTkFrame(card, fg_color="transparent")
            cl_frame.pack(fill="x", padx=16, pady=(4, 0))
            for line in changelog[:5]:
                # Strip commit hash prefix for cleaner display
                parts = line.split(" ", 1)
                msg = parts[1] if len(parts) > 1 else line
                ctk.CTkLabel(
                    cl_frame,
                    text=f"  {msg}",
                    font=ctk.CTkFont(*FONT_MONO_SM),
                    text_color=COLORS["gray"], anchor="w",
                ).pack(fill="x")
            if len(changelog) > 5:
                ctk.CTkLabel(
                    cl_frame,
                    text=f"  ... and {n - 5} more",
                    font=ctk.CTkFont(*FONT_MONO_SM),
                    text_color=COLORS["text_dim"], anchor="w",
                ).pack(fill="x")

        # Button row
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(6, 8))

        ctk.CTkButton(
            btn_row, text="Skip", width=130,
            fg_color=COLORS["bg_panel"],
            hover_color=COLORS["bg_card"],
            text_color=COLORS["gray"],
            font=ctk.CTkFont(*FONT_MONO_SM),
            height=32, command=lambda: self._update_card.pack_forget(),
        ).pack(side="right", padx=(4, 0))

        ctk.CTkButton(
            btn_row,
            text=f"Update to v{ver}" if ver else "Update Now",
            width=160, fg_color=COLORS["cyan_dim"],
            hover_color=COLORS["cyan"],
            text_color=COLORS["bg_dark"],
            font=ctk.CTkFont(*FONT_MONO_SM),
            height=32, command=self._apply_update_from_card,
        ).pack(side="right", padx=(4, 0))

    def _apply_update_from_card(self):
        """Pull updates and reinstall deps directly from the dashboard card."""
        import threading as _th

        card = getattr(self, "_update_card", None)
        if not card:
            return

        # Replace card content with progress
        for w in card.winfo_children():
            w.destroy()

        status_lbl = ctk.CTkLabel(
            card, text="  Pulling updates...",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["yellow"], anchor="w",
        )
        status_lbl.pack(fill="x", padx=12, pady=8)

        def _do_update():
            forge_root = str(Path(__file__).parent.parent.parent)
            flags = {}
            if os.name == "nt":
                flags["creationflags"] = subprocess.CREATE_NO_WINDOW

            # Pull
            try:
                pull = subprocess.run(
                    ["git", "pull", "--ff-only", "origin", "master"],
                    cwd=forge_root, capture_output=True, text=True,
                    timeout=30, **flags,
                )
                if pull.returncode != 0:
                    self._root.after(0, lambda: self._update_card_result(
                        status_lbl, False, f"Pull failed: {pull.stderr[:200]}"))
                    return
            except Exception as e:
                self._root.after(0, lambda: self._update_card_result(
                    status_lbl, False, f"Pull error: {e}"))
                return

            # Check if pyproject.toml changed (need pip reinstall)
            reinstalled = False
            try:
                diff = subprocess.run(
                    ["git", "diff", "--name-only",
                     f"HEAD~{self._update_behind}", "HEAD"],
                    cwd=forge_root, capture_output=True, text=True,
                    timeout=5, **flags,
                )
                changed = diff.stdout.strip().split("\n") if diff.stdout.strip() else []
                if "pyproject.toml" in changed:
                    self._root.after(0, lambda: status_lbl.configure(
                        text="  Reinstalling dependencies..."))
                    venv_py = Path(forge_root) / ".venv" / "Scripts" / "python.exe"
                    if not venv_py.exists():
                        venv_py = Path(forge_root) / ".venv" / "bin" / "python"
                    if venv_py.exists():
                        subprocess.run(
                            [str(venv_py), "-m", "pip", "install", "-e",
                             forge_root, "--quiet"],
                            capture_output=True, timeout=120, **flags,
                        )
                        reinstalled = True
            except Exception:
                pass

            ver = getattr(self, "_update_version", "")
            ver_msg = f" to v{ver}" if ver else ""
            extra = " + dependencies reinstalled" if reinstalled else ""
            msg = f"Updated{ver_msg}{extra}. Restart Forge for full effect."
            self._root.after(0, lambda: self._update_card_result(
                status_lbl, True, msg))

        _th.Thread(target=_do_update, daemon=True).start()

    def _update_card_result(self, label, success, message):
        """Show update result in the card."""
        color = COLORS["green"] if success else COLORS["red"]
        label.configure(text=f"  {message}", text_color=color)

    # ── Terminal launch ──

    def _launch_terminal(self):
        if self._terminal_proc and self._terminal_proc.poll() is None:
            return  # already running

        project_dir = Path(__file__).parent.parent.parent
        # Use venv python — sys.executable points to it when launched via venv
        python_exe = sys.executable
        # On Windows, pythonw.exe can't spawn console apps properly
        if sys.platform == "win32" and python_exe.lower().endswith("pythonw.exe"):
            python_exe = python_exe[:-5] + ".exe"  # pythonw.exe -> python.exe

        # Play terminal launch sound
        if self._sound:
            self._sound.play("terminal")

        try:
            if os.name == "nt":
                self._terminal_proc = subprocess.Popen(
                    [python_exe, "-m", "forge"],
                    cwd=str(project_dir),
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                )
            else:
                self._terminal_proc = subprocess.Popen(
                    [python_exe, "-m", "forge"],
                    cwd=str(project_dir),
                    start_new_session=True,
                )

            # Update button
            if self._launch_btn:
                self._launch_btn.configure(
                    text=f"Terminal Running (PID {self._terminal_proc.pid})",
                    fg_color=COLORS["border"],
                    hover_color=COLORS["border"],
                    text_color=COLORS["gray"])

            # Hand off voice to terminal and start focus monitoring
            self._pause_dashboard_voice()

            # Give the terminal window focus after a short delay
            if os.name == "nt":
                self._root.after(800, self._focus_terminal)

            # Start monitoring window focus to swap voice
            self._start_focus_monitor()
        except Exception as e:
            log.warning("Terminal launch failed: %s", e)

    def _launch_gui_terminal(self):
        """Launch the in-process GUI terminal window."""
        if self._gui_terminal is not None:
            return  # already open

        if self._sound:
            self._sound.play("terminal")

        try:
            from forge.ui.gui_terminal import (
                ForgeTerminalWindow, GuiTerminalIO, HAS_CTK)
            if not HAS_CTK:
                log.warning("GUI Terminal requires customtkinter")
                return

            # Create a toplevel window (shares mainloop with dashboard)
            top = ctk.CTkToplevel(self._root)

            def on_gui_close():
                self._gui_terminal = None
                try:
                    top.destroy()
                except Exception:
                    pass

            win = ForgeTerminalWindow(top, on_close=on_gui_close)
            gui_io = GuiTerminalIO(top, win)
            self._gui_terminal = top

            def _run_engine():
                # Redirect stdout/stderr so direct print() calls show in GUI
                old_stdout = sys.stdout
                old_stderr = sys.stderr
                sys.stdout = gui_io._stdout_redirect
                sys.stderr = gui_io._stdout_redirect
                # Re-point logging handlers to the new stderr so log
                # messages don't crash with "NoneType has no .write"
                for handler in logging.root.handlers:
                    if isinstance(handler, logging.StreamHandler):
                        handler.stream = gui_io._stdout_redirect
                try:
                    from forge.engine import ForgeEngine
                    engine = ForgeEngine(
                        cwd=os.getcwd(),
                        terminal_io=gui_io)
                    engine.run()
                except Exception as e:
                    import traceback
                    tb = traceback.format_exc()
                    log.warning("GUI terminal engine error: %s", e)
                    try:
                        top.after(0, win.append_text,
                                  f"\n[Engine Error]\n{tb}\n", "error")
                    except Exception:
                        pass
                finally:
                    sys.stdout = old_stdout
                    sys.stderr = old_stderr
                    # Restore logging handlers to original stderr
                    for handler in logging.root.handlers:
                        if isinstance(handler, logging.StreamHandler):
                            handler.stream = old_stderr or sys.__stderr__
                    gui_io.shutdown()

            threading.Thread(
                target=_run_engine, daemon=True,
                name="ForgeGUIEngine").start()
        except Exception as e:
            log.warning("GUI terminal launch failed: %s", e)

    def _focus_terminal(self):
        """Bring the terminal console window to the foreground (Windows only)."""
        if sys.platform != "win32":
            return
        if not self._terminal_proc or self._terminal_proc.poll() is not None:
            return
        try:
            import ctypes
            import ctypes.wintypes
            # EnumWindows to find the console owned by our child process
            pid = self._terminal_proc.pid
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            WNDENUMPROC = ctypes.WINFUNCTYPE(
                ctypes.wintypes.BOOL,
                ctypes.wintypes.HWND,
                ctypes.wintypes.LPARAM)

            found_hwnd = [None]

            def enum_callback(hwnd, lparam):
                # Get the process ID for this window
                proc_id = ctypes.wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
                if proc_id.value == pid:
                    if user32.IsWindowVisible(hwnd):
                        found_hwnd[0] = hwnd
                        return False  # stop enumeration
                return True

            user32.EnumWindows(WNDENUMPROC(enum_callback), 0)

            if found_hwnd[0]:
                user32.SetForegroundWindow(found_hwnd[0])
                user32.BringWindowToTop(found_hwnd[0])
        except Exception:
            pass  # non-critical

    # ── Voice focus: swap voice between dashboard and terminal ──

    def _pause_dashboard_voice(self):
        """Stop dashboard voice input (terminal takes over mic)."""
        if self._voice:
            try:
                self._voice.stop()
            except Exception:
                pass
            self._voice = None
        self._update_voice_label("voice in terminal")
        # Tell terminal to enable its voice
        self._write_voice_focus("terminal")

    def _resume_dashboard_voice(self):
        """Re-init dashboard voice input (dashboard has focus)."""
        if self._voice:
            return  # already running
        # Tell terminal to disable its voice
        self._write_voice_focus("dashboard")
        self._init_dashboard_voice()

    def _write_voice_focus(self, target: str):
        """Write which window should own voice: 'dashboard' or 'terminal'."""
        try:
            focus_file = Path.home() / ".forge" / "voice_focus.txt"
            focus_file.write_text(target, encoding="utf-8")
        except Exception:
            pass

    def _start_focus_monitor(self):
        """Monitor window focus to swap voice between dashboard and terminal."""
        if not self._running or not self._terminal_proc:
            return
        self._root.bind("<FocusIn>", self._on_dashboard_focus_in)
        self._root.bind("<FocusOut>", self._on_dashboard_focus_out)

    def _on_dashboard_focus_in(self, event=None):
        """Dashboard window got focus — reclaim voice from terminal."""
        if self._terminal_proc and self._terminal_proc.poll() is None:
            self._resume_dashboard_voice()

    def _on_dashboard_focus_out(self, event=None):
        """Dashboard window lost focus — hand voice to terminal."""
        if self._terminal_proc and self._terminal_proc.poll() is None:
            self._pause_dashboard_voice()

    # ── State file polling (drives animation + card updates) ──

    def _schedule_state_poll(self):
        if not self._running:
            return

        state_data = _read_state_file()
        if state_data:
            # Ignore stale data (older than 5s = leftover from previous session)
            ts = state_data.get("timestamp", 0)
            if time.time() - ts > 5.0:
                state_data = None

        if state_data:
            # Update animation state
            state_str = state_data.get("state", "idle")

            if self._anim_engine:
                state_map = {
                    "idle": AnimState.IDLE,
                    "thinking": AnimState.THINKING,
                    "tool_exec": AnimState.TOOL_EXEC,
                    "indexing": AnimState.INDEXING,
                    "recovering": AnimState.INDEXING,
                    "swapping": AnimState.SWAPPING,
                    "error": AnimState.ERROR,
                    "threat": AnimState.THREAT,
                }
                ns = state_map.get(state_str, AnimState.IDLE)
                self._anim_engine.set_state(ns)

            # Trigger sound on state change
            if self._sound and state_str != self._last_sound_state:
                self._last_sound_state = state_str
                self._sound.on_state_change(state_str)

            # Update dashboard cards from state data
            self._apply_state_data(state_data)

        # Check for synapse check trigger from /synapse command
        try:
            trigger = Path.home() / ".forge" / "synapse_check.txt"
            if trigger.exists():
                trigger.unlink(missing_ok=True)
                self._run_synapse_check()
        except Exception:
            pass

        # Check terminal alive
        if self._terminal_proc and self._terminal_proc.poll() is not None:
            self._terminal_proc = None
            if self._anim_engine:
                self._anim_engine.set_state(AnimState.IDLE)
            if self._launch_btn:
                self._launch_btn.configure(
                    text="Launch Terminal",
                    fg_color=COLORS["cyan_dim"],
                    hover_color=COLORS["cyan"],
                    text_color=COLORS["bg_dark"])
            # Terminal closed — reclaim voice for dashboard
            try:
                self._root.unbind("<FocusIn>")
                self._root.unbind("<FocusOut>")
            except Exception:
                pass
            self._write_voice_focus("dashboard")
            if not self._voice:
                self._init_dashboard_voice()

        if self._root and self._running:
            self._root.after(500, self._schedule_state_poll)

    def _apply_state_data(self, data: dict):
        """Update dashboard card values from state file data."""
        ctx = data.get("context", {})
        pct = ctx.get("usage_pct", 0)
        total = ctx.get("total_tokens", 0)
        maximum = ctx.get("max_tokens", 1)

        if self._ctx_bar:
            self._ctx_bar.set(pct / 100.0)
            if pct > 90:
                self._ctx_bar.configure(progress_color=COLORS["red"])
            elif pct > 75:
                self._ctx_bar.configure(progress_color=COLORS["yellow"])
            else:
                self._ctx_bar.configure(progress_color=COLORS["cyan"])

        if self._ctx_label:
            self._ctx_label.configure(
                text=f"{pct:.0f}% | {total:,} / {maximum:,} tokens")

        parts = ctx.get("partitions", {})
        if parts and "partitions" in self._stat_labels:
            p_str = " | ".join(
                f"{k}: {v.get('tokens', 0):,}" for k, v in parts.items())
            self._stat_labels["partitions"].configure(text=p_str)

        perf = data.get("performance", {})
        if "tok_s" in self._stat_labels:
            tok_s = perf.get("avg_tok_s", 0)
            self._stat_labels["tok_s"].configure(
                text=f"{tok_s:.1f} tok/s",
                text_color=COLORS["green"] if tok_s > 10 else COLORS["white"])
        if "trend" in self._stat_labels:
            trend = perf.get("trend", "--")
            color = (COLORS["green"] if trend == "improving"
                     else COLORS["red"] if trend == "degrading"
                     else COLORS["white"])
            self._stat_labels["trend"].configure(text=trend, text_color=color)

        cache = data.get("cache", {})
        if "cache" in self._stat_labels:
            hit_rate = cache.get("hit_rate", 0)
            self._stat_labels["cache"].configure(
                text=f"{hit_rate:.0f}%",
                text_color=COLORS["green"] if hit_rate > 50
                else COLORS["white"])

        if "swaps" in self._stat_labels:
            self._stat_labels["swaps"].configure(
                text=str(data.get("swaps", 0)))

        session = data.get("session", {})
        if "turns" in self._stat_labels:
            self._stat_labels["turns"].configure(
                text=str(session.get("turns", 0)))
        if "duration" in self._stat_labels:
            self._stat_labels["duration"].configure(
                text=f"{session.get('duration_m', 0):.1f}m")
        if "tokens" in self._stat_labels:
            self._stat_labels["tokens"].configure(
                text=f"{session.get('tokens', 0):,}")
        if "cost_saved" in self._stat_labels:
            self._stat_labels["cost_saved"].configure(
                text=f"${session.get('cost_saved', 0):.4f}",
                text_color=COLORS["green"])

        memory = data.get("memory", {})
        if "journal" in self._stat_labels:
            self._stat_labels["journal"].configure(
                text=f"{memory.get('journal_entries', 0)} entries")
        if "index" in self._stat_labels:
            chunks = memory.get("index_chunks", 0)
            if chunks > 0:
                self._stat_labels["index"].configure(
                    text=f"{chunks} chunks",
                    text_color=COLORS["cyan_dim"])
            else:
                self._stat_labels["index"].configure(
                    text="not loaded", text_color=COLORS["text_dim"])
        if "mem_status" in self._stat_labels:
            status = memory.get("status", "Idle")
            color = (COLORS["cyan_glow"] if status == "Active"
                     else COLORS["green"] if status == "Ready"
                     else COLORS["gray"])
            self._stat_labels["mem_status"].configure(
                text=status, text_color=color)

        # Continuity Grade
        cg = data.get("continuity", {})
        if cg.get("enabled", False):
            score = cg.get("score", 100)
            grade = cg.get("grade", "A")
            swaps = cg.get("swaps", 0)

            grade_colors = {
                "A": COLORS["green"], "B": COLORS["cyan"],
                "C": COLORS["yellow"], "D": COLORS["yellow"],
                "F": COLORS["red"],
            }
            gc = grade_colors.get(grade, COLORS["white"])

            if hasattr(self, '_cg_grade_label') and self._cg_grade_label:
                self._cg_grade_label.configure(text=grade, text_color=gc)
            if hasattr(self, '_cg_bar') and self._cg_bar:
                self._cg_bar.set(score / 100.0)
                self._cg_bar.configure(progress_color=gc)
            if hasattr(self, '_cg_score_label') and self._cg_score_label:
                self._cg_score_label.configure(
                    text=f"{score:.0f}/100 | {swaps} "
                         f"swap{'s' if swaps != 1 else ''}")

        # ── Sparkline charts (optional — never crash if PIL fails) ──
        try:
            self._update_sparklines(data)
        except Exception:
            pass  # Charts are optional

        # ── Reliability card ──
        rel = data.get("reliability", {})
        if rel:
            score = rel.get("score", 100)
            if hasattr(self, "_rel_bar") and self._rel_bar:
                self._rel_bar.set(score / 100.0)
                color = (COLORS["green"] if score >= 80
                         else COLORS["yellow"] if score >= 60
                         else COLORS["red"])
                self._rel_bar.configure(progress_color=color)
                if hasattr(self, "_rel_score_label") and self._rel_score_label:
                    self._rel_score_label.configure(
                        text=f"{score:.0f}", text_color=color)

            current = rel.get("current", {})
            if "rel_verify" in self._stat_labels:
                vr = current.get("verification_pass_rate", 1)
                self._stat_labels["rel_verify"].configure(
                    text=f"{vr * 100:.0f}%")
            if "rel_continuity" in self._stat_labels:
                ca = current.get("continuity_grade_avg", 100)
                self._stat_labels["rel_continuity"].configure(
                    text=f"{ca:.0f}/100")
            if "rel_tools" in self._stat_labels:
                tr = current.get("tool_success_rate", 1)
                self._stat_labels["rel_tools"].configure(
                    text=f"{tr * 100:.0f}%")

            trend = rel.get("trend", {})
            if "rel_trend" in self._stat_labels:
                td = trend.get("direction", "--")
                tc = (COLORS["green"] if td == "improving"
                      else COLORS["red"] if td == "degrading"
                      else COLORS["white"])
                self._stat_labels["rel_trend"].configure(
                    text=td, text_color=tc)

        # ── AutoForge card ──
        af = data.get("autoforge", {})
        if af:
            if "af_status" in self._stat_labels:
                enabled = af.get("enabled", False)
                self._stat_labels["af_status"].configure(
                    text="enabled" if enabled else "disabled",
                    text_color=COLORS["green"] if enabled
                    else COLORS["gray"])
            if "af_pending" in self._stat_labels:
                pending = af.get("pending", 0)
                self._stat_labels["af_pending"].configure(
                    text=str(pending),
                    text_color=COLORS["yellow"] if pending > 0
                    else COLORS["white"])
            if "af_commits" in self._stat_labels:
                self._stat_labels["af_commits"].configure(
                    text=str(af.get("session_commits", 0)))
            if hasattr(self, "_af_recent") and self._af_recent:
                commits = af.get("recent_commits", [])
                if commits:
                    lines = [f"[{c['sha']}] {c['msg']}"
                             for c in commits[-3:]]
                    self._af_recent.configure(text="\n".join(lines))

        # ── Shipwright card ──
        sw = data.get("shipwright", {})
        if sw:
            if "sw_version" in self._stat_labels:
                self._stat_labels["sw_version"].configure(
                    text=sw.get("version", "0.0.0"))
            if "sw_unreleased" in self._stat_labels:
                count = sw.get("unreleased_count", 0)
                self._stat_labels["sw_unreleased"].configure(
                    text=f"{count} commits",
                    text_color=COLORS["cyan"] if count > 0
                    else COLORS["white"])
            if "sw_bump" in self._stat_labels:
                bump = sw.get("suggested_bump", "none")
                bc = {"major": COLORS["red"], "minor": COLORS["cyan"],
                      "patch": COLORS["green"]}.get(bump, COLORS["gray"])
                self._stat_labels["sw_bump"].configure(
                    text=bump, text_color=bc)
            if "sw_last" in self._stat_labels:
                self._stat_labels["sw_last"].configure(
                    text=sw.get("last_release_date", "--"))

        # ── License card ──
        lic = data.get("license", {})
        if lic:
            tier = lic.get("tier", "community")
            tc = {"community": COLORS["green"],
                  "pro": COLORS["cyan"],
                  "power": COLORS["magenta"]}.get(tier, COLORS["white"])
            if hasattr(self, "_lic_card_tier") and self._lic_card_tier:
                self._lic_card_tier.configure(
                    text=lic.get("tier_label", "Community"),
                    text_color=tc)
            if hasattr(self, "_lic_card_bar") and self._lic_card_bar:
                mat = lic.get("maturity_pct", 0) / 100.0
                self._lic_card_bar.set(mat)
            if "lic_maturity" in self._stat_labels:
                self._stat_labels["lic_maturity"].configure(
                    text=f"{lic.get('maturity_pct', 0)}%")
            if "lic_acts" in self._stat_labels:
                acts = lic.get("activations", 1)
                max_acts = lic.get("max_activations", 1)
                self._stat_labels["lic_acts"].configure(
                    text=f"{acts}/{max_acts}")
            if "lic_genome" in self._stat_labels:
                persist = lic.get("genome_persistence", False)
                self._stat_labels["lic_genome"].configure(
                    text="persists" if persist else "resets",
                    text_color=COLORS["green"] if persist
                    else COLORS["yellow"])

        model = data.get("model", "")
        if model and self._footer_label:
            self._footer_label.configure(
                text=f"  {model} | Local AI | $0.00 forever")

    def _update_sparklines(self, data: dict):
        """Render sparkline charts into card labels. Cached by data hash."""
        from forge.ui.charts import ChartRenderer

        renderer = ChartRenderer(COLORS)

        # Performance throughput sparkline
        perf = data.get("performance", {})
        tok_hist = perf.get("recent_5", [])
        if len(tok_hist) >= 3 and hasattr(self, "_perf_sparkline_label"):
            data_hash = str(tok_hist)
            if data_hash != getattr(self, "_perf_sparkline_hash", ""):
                img = renderer.sparkline(
                    tok_hist, width=280, height=24,
                    color=COLORS.get("cyan", "#00d4ff"))
                if img:
                    ctk_img = ctk.CTkImage(
                        light_image=img, dark_image=img, size=(280, 24))
                    self._perf_sparkline_label.configure(
                        image=ctk_img, text="")
                    self._perf_sparkline_img = ctk_img
                    self._perf_sparkline_hash = data_hash

        # Continuity score sparkline
        cg = data.get("continuity", {})
        score_hist = cg.get("score_history", [])
        if len(score_hist) >= 3 and hasattr(self, "_cg_sparkline_label"):
            data_hash = str(score_hist)
            if data_hash != getattr(self, "_cg_sparkline_hash", ""):
                img = renderer.sparkline(
                    score_hist, width=280, height=24,
                    color=COLORS.get("green", "#00ff88"))
                if img:
                    ctk_img = ctk.CTkImage(
                        light_image=img, dark_image=img, size=(280, 24))
                    self._cg_sparkline_label.configure(
                        image=ctk_img, text="")
                    self._cg_sparkline_img = ctk_img
                    self._cg_sparkline_hash = data_hash

        # Reliability trend sparkline
        rel = data.get("reliability", {})
        trend = rel.get("trend", {})
        rel_scores = trend.get("scores", [])
        if len(rel_scores) >= 3 and hasattr(self, "_rel_sparkline_label"):
            data_hash = str(rel_scores)
            if data_hash != getattr(self, "_rel_sparkline_hash", ""):
                img = renderer.sparkline(
                    rel_scores, width=280, height=24,
                    color=COLORS.get("magenta", "#ff66aa"))
                if img:
                    ctk_img = ctk.CTkImage(
                        light_image=img, dark_image=img, size=(280, 24))
                    self._rel_sparkline_label.configure(
                        image=ctk_img, text="")
                    self._rel_sparkline_img = ctk_img
                    self._rel_sparkline_hash = data_hash

    def _apply_theme(self, color_map: dict):
        """Hot-swap theme colours on the launcher window."""
        if self._root:
            recolor_widget_tree(self._root, color_map)

    def _on_close(self):
        self._running = False
        if self._card_mgr:
            self._card_mgr.save_state()
        if self._effects:
            self._effects.shutdown()
            self._effects = None
        if hasattr(self, "_theme_cb"):
            remove_theme_listener(self._theme_cb)
        if self._voice:
            try:
                self._voice.stop()
            except Exception:
                pass
            self._voice = None
        if self._sound:
            try:
                self._sound.stop()
            except Exception:
                pass
        try:
            self._root.destroy()
        except Exception:
            pass

    # ── File menu callbacks ───────────────────────────────────────

    def _open_settings(self):
        from forge.ui.settings_dialog import ForgeSettingsDialog
        from forge.config import ForgeConfig
        config = ForgeConfig()
        ForgeSettingsDialog(self._root, config)

    def _open_nightly_settings(self):
        """Open Settings dialog pre-selected to the Nightly tab."""
        from forge.ui.settings_dialog import ForgeSettingsDialog
        from forge.config import ForgeConfig
        config = ForgeConfig()
        dialog = ForgeSettingsDialog(self._root, config)
        try:
            dialog._tabs.set("Nightly")
        except Exception:
            pass

    def _show_about(self):
        from forge import __version__
        dlg = ctk.CTkToplevel(self._root)
        dlg.title("About Forge")
        dlg.geometry("320x240")
        dlg.configure(fg_color=COLORS["bg_dark"])
        dlg.transient(self._root)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.update_idletasks()
        x = self._root.winfo_x() + (self._root.winfo_width() - 320) // 2
        y = self._root.winfo_y() + (self._root.winfo_height() - 240) // 2
        dlg.geometry(f"+{max(0, x)}+{max(0, y)}")

        ctk.CTkLabel(dlg, text="F O R G E",
                     font=ctk.CTkFont(*FONT_TITLE),
                     text_color=COLORS["cyan"]).pack(pady=(28, 4))
        ctk.CTkLabel(dlg, text=f"v{__version__}",
                     font=ctk.CTkFont(*FONT_MONO),
                     text_color=COLORS["gray"]).pack()
        ctk.CTkLabel(dlg, text="Local AI Coding Assistant",
                     font=ctk.CTkFont(*FONT_MONO_SM),
                     text_color=COLORS["gray"]).pack(pady=(4, 0))
        ctk.CTkLabel(dlg, text="100% Local  |  $0.00 Forever",
                     font=ctk.CTkFont(*FONT_MONO_SM),
                     text_color=COLORS["cyan_dim"]).pack(pady=(8, 0))
        ctk.CTkLabel(dlg, text="No tokens. No compaction. No bullshit.",
                     font=ctk.CTkFont(*FONT_MONO_SM),
                     text_color=COLORS["text_dim"]).pack(pady=(4, 0))
        ctk.CTkButton(dlg, text="OK", width=80,
                      fg_color=COLORS["cyan_dim"],
                      hover_color=COLORS["cyan"],
                      text_color=COLORS["bg_dark"],
                      command=dlg.destroy).pack(pady=(16, 0))

    # ── HUD Menu (Iron Man style) ─────────────────────────────────

    def _toggle_hud_menu(self):
        """Toggle the HUD overlay menu."""
        if self._hud_overlay is not None:
            self._close_hud_menu()
        else:
            self._open_hud_menu()

    def _open_hud_menu(self):
        """Build and animate the Iron Man HUD menu overlay."""
        if self._hud_overlay is not None:
            return

        # Use a tkinter Canvas as the overlay — it supports transparency-like
        # behavior and avoids CTkFrame nested-place rendering issues.
        import tkinter as tk

        root_w = self._root.winfo_width()
        root_h = self._root.winfo_height()

        # Overlay: plain tk.Frame covers the whole window (no CTk nesting)
        overlay = tk.Frame(self._root, bg=COLORS["bg_dark"],
                           highlightthickness=0)
        overlay.place(x=0, y=0, width=root_w, height=root_h)
        overlay.lift()
        self._hud_overlay = overlay

        # Click overlay background to dismiss
        overlay.bind("<Button-1>", lambda e: self._close_hud_menu())

        # Menu panel (left side, 280px wide) — uses CTkFrame for styling
        panel = ctk.CTkFrame(
            overlay, fg_color=COLORS["bg_panel"],
            corner_radius=0, width=280,
            border_color=COLORS["cyan_dim"], border_width=1)
        panel.pack(side="left", fill="y")
        panel.pack_propagate(False)
        panel.configure(width=280)

        # Absorb clicks on panel so they don't close overlay
        def _absorb(e):
            return "break"
        panel.bind("<Button-1>", _absorb)

        # Panel header
        ctk.CTkLabel(
            panel, text="  F O R G E",
            font=ctk.CTkFont(*FONT_TITLE),
            text_color=COLORS["cyan"]
        ).pack(fill="x", padx=10, pady=(18, 2))
        ctk.CTkLabel(
            panel, text="  Neural Cortex",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["gray"]
        ).pack(fill="x", padx=10, pady=(0, 10))

        # Separator
        ctk.CTkFrame(
            panel, fg_color=COLORS["border"], height=1
        ).pack(fill="x", padx=12, pady=(0, 6))

        # Menu items (staggered entrance)
        items = [
            ("Settings", "Ctrl+,", self._open_settings),
            ("Model Manager", None, self._open_model_manager),
            ("Fleet Manager", None, self._open_puppet_manager),
            ("Test Suite", None, self._open_test_runner),
            ("Run All Tests", None, self._run_all_tests),
            ("Nightly Tests", None, self._open_nightly_settings),
            ("Check for Updates", None, self._check_for_updates),
            ("Admin Panel", None, self._open_admin_panel),
            None,
            ("About", None, self._show_about),
            ("Quit", None, self._on_close),
        ]

        self._hud_rows = []
        item_idx = 0
        for item in items:
            if item is None:
                ctk.CTkFrame(
                    panel, fg_color=COLORS["border"], height=1
                ).pack(fill="x", padx=16, pady=3)
                continue

            label_text, accel, cmd = item
            row = self._create_hud_item(panel, label_text, accel, cmd)
            row.pack(fill="x", padx=8, pady=2)

            # Stagger: start with row hidden (zero-height), reveal after delay
            row._target_height = 36
            row.configure(height=0)
            delay = 80 + item_idx * 60
            self._root.after(delay, self._reveal_hud_row, row)
            self._hud_rows.append(row)
            item_idx += 1

        # Scan line animation on the panel
        scan = ctk.CTkFrame(panel, fg_color=COLORS["cyan"], height=2)
        scan.place(relx=0, rely=0, relwidth=1)
        self._animate_scan_line(scan)

        # Play sound
        if self._sound:
            self._sound.play("ready")

        # Bind Escape to close
        self._root.bind("<Escape>", self._hud_escape)

    def _hud_escape(self, event=None):
        """Close HUD menu on Escape key."""
        self._close_hud_menu()
        self._root.unbind("<Escape>")

    def _reveal_hud_row(self, row):
        """Animate a HUD menu row appearing (stagger effect)."""
        try:
            row.configure(height=36)
        except Exception:
            pass

    def _create_hud_item(self, parent, label, accel, command):
        """Create a single HUD menu item row."""
        row = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"],
                           corner_radius=4, height=36, cursor="hand2")
        row.pack_propagate(False)

        # Left accent bar
        accent = ctk.CTkFrame(row, fg_color=COLORS["cyan_dim"],
                              width=3, corner_radius=0)
        accent.pack(side="left", fill="y")

        # Arrow
        arrow_lbl = ctk.CTkLabel(
            row, text=" >", font=ctk.CTkFont(*FONT_MONO),
            text_color=COLORS["cyan_dim"], width=20)
        arrow_lbl.pack(side="left")

        # Label
        name_lbl = ctk.CTkLabel(
            row, text=label, font=ctk.CTkFont(*FONT_MONO),
            text_color=COLORS["white"], anchor="w")
        name_lbl.pack(side="left", fill="x", expand=True, padx=4)

        # Accelerator
        accel_lbl = None
        if accel:
            accel_lbl = ctk.CTkLabel(
                row, text=accel, font=ctk.CTkFont(*FONT_MONO_SM),
                text_color=COLORS["gray"])
            accel_lbl.pack(side="right", padx=8)

        # Hover glow — only modify CTkLabels and the row/accent frames
        def _enter(e):
            row.configure(fg_color=COLORS["cyan_dim"])
            accent.configure(fg_color=COLORS["cyan"])
            arrow_lbl.configure(text_color=COLORS["cyan"])

        def _leave(e):
            row.configure(fg_color=COLORS["bg_card"])
            accent.configure(fg_color=COLORS["cyan_dim"])
            arrow_lbl.configure(text_color=COLORS["cyan_dim"])

        def _click(e):
            self._close_hud_menu()
            command()

        # Bind to each widget explicitly (safe — no configure on wrong type)
        clickables = [row, accent, arrow_lbl, name_lbl]
        if accel_lbl:
            clickables.append(accel_lbl)
        for w in clickables:
            w.bind("<Enter>", _enter)
            w.bind("<Leave>", _leave)
            w.bind("<Button-1>", _click)

        return row

    def _animate_scan_line(self, scan_widget, steps=20, duration=400):
        """Animate a scan line sweeping down the menu panel."""
        interval = duration // steps

        def _step(i):
            if i >= steps or self._hud_overlay is None:
                try:
                    scan_widget.place_forget()
                except Exception:
                    pass
                return
            frac = i / steps
            scan_widget.place(relx=0, rely=frac, relwidth=1)
            self._root.after(interval, _step, i + 1)

        _step(0)

    def _close_hud_menu(self):
        """Close and destroy the HUD overlay."""
        if self._hud_overlay is not None:
            try:
                self._root.unbind("<Escape>")
            except Exception:
                pass
            try:
                self._hud_overlay.destroy()
            except Exception:
                pass
            self._hud_overlay = None
            self._hud_rows = []

    def _open_model_manager(self):
        """Open the enterprise Model Manager dialog."""
        from forge.ui.model_manager import ModelManagerDialog
        from forge.config import ForgeConfig
        config = ForgeConfig()
        ModelManagerDialog(self._root, config)

    def _open_puppet_manager(self):
        """Open the Fleet Manager dialog."""
        from forge.ui.puppet_manager import PuppetManagerDialog
        from forge.config import ForgeConfig
        config = ForgeConfig()
        PuppetManagerDialog(self._root, config)

    def _open_test_runner(self):
        """Open the Test Suite Runner dialog."""
        from forge.ui.test_runner import TestRunnerDialog
        TestRunnerDialog(self._root)

    def _run_all_tests(self):
        """Open the Test Suite Runner and auto-start all tests."""
        from forge.ui.test_runner import TestRunnerDialog
        runner = TestRunnerDialog(self._root)
        self._root.after(300, runner._run_all)

    def _check_for_updates(self):
        """Open the update checker dialog."""
        from forge.ui.admin_panel import UpdateCheckDialog
        UpdateCheckDialog(self._root)

    def _open_admin_panel(self):
        """Open the admin panel for collaborator and token management."""
        from forge.ui.admin_panel import AdminPanelDialog
        from forge.config import ForgeConfig
        AdminPanelDialog(self._root, ForgeConfig())


# ──────────────────────────────────────────────────────────────────
# ForgeDashboard — for /dashboard command in engine.py (in-process)
# ──────────────────────────────────────────────────────────────────

class ForgeDashboard:
    """In-process dashboard launched from engine /dashboard command."""

    _instance_alive = False
    _instance_lock = threading.Lock()

    def __init__(self, get_data_fn: Optional[Callable] = None,
                 brain_path: Optional[str] = None):
        if not HAS_GUI_DEPS:
            raise ImportError(
                "GUI requires: pip install customtkinter Pillow numpy")
        self._get_data = get_data_fn
        self._brain_path = Path(brain_path) if brain_path else BRAIN_IMAGE_PATH
        self._running = False
        self._root: Optional[ctk.CTk] = None
        self._thread: Optional[threading.Thread] = None
        self._anim_engine: Optional[AnimationEngine] = None
        self._brain_label = None
        self._brain_ctk_img = None
        self._state_label = None
        self._activity_dot = None
        self._ctx_bar = None
        self._ctx_label = None
        self._stat_labels: dict[str, ctk.CTkLabel] = {}
        self._effects: Optional[EffectsEngine] = None

    @classmethod
    def is_alive(cls) -> bool:
        with cls._instance_lock:
            return cls._instance_alive

    def launch(self, blocking=False):
        with ForgeDashboard._instance_lock:
            if ForgeDashboard._instance_alive:
                return
            ForgeDashboard._instance_alive = True
        if blocking:
            self._build_and_run()
        else:
            self._thread = threading.Thread(
                target=self._build_and_run, daemon=True)
            self._thread.start()

    def close(self):
        self._running = False
        if self._root:
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass

    def set_state(self, state_name: str):
        if self._anim_engine:
            try:
                self._anim_engine.set_state(AnimState(state_name))
            except ValueError:
                pass

    def set_activity(self, active: bool):
        if self._anim_engine:
            self._anim_engine.set_state(
                AnimState.THINKING if active else AnimState.IDLE)

    def update_data(self, data: dict):
        if self._root and self._running:
            try:
                self._root.after(0, self._apply_data, data)
            except Exception:
                pass

    def _build_and_run(self):
        try:
            # Apply saved theme BEFORE building widgets
            from forge.config import ForgeConfig
            from forge.ui.themes import set_theme
            _cfg = ForgeConfig()
            _saved_theme = _cfg.get("theme", "midnight")
            set_theme(_saved_theme)

            ctk.set_appearance_mode("dark")
            ctk.set_default_color_theme("blue")
            self._root = ctk.CTk()
            self._root.title("Forge Neural Cortex")
            self._root.geometry("380x760")
            self._root.minsize(360, 680)
            self._root.configure(fg_color=COLORS["bg_dark"])
            self._root.protocol("WM_DELETE_WINDOW", self._on_close)

            ico_path = Path(__file__).parent / "assets" / "forge.ico"
            if ico_path.exists():
                try:
                    self._root.iconbitmap(str(ico_path))
                except Exception:
                    pass

            # Header
            header = ctk.CTkFrame(
                self._root, fg_color=COLORS["bg_panel"],
                corner_radius=0, height=40)
            header.pack(fill="x")
            header.pack_propagate(False)
            ctk.CTkLabel(
                header, text="  F O R G E",
                font=ctk.CTkFont(*FONT_TITLE),
                text_color=COLORS["cyan"]
            ).pack(side="left", padx=10, pady=5)
            ctk.CTkLabel(
                header, text="Neural Cortex",
                font=ctk.CTkFont(*FONT_MONO),
                text_color=COLORS["gray"]
            ).pack(side="left", pady=5)
            self._activity_dot = ctk.CTkLabel(
                header, text="  \u25cf", font=ctk.CTkFont(size=14),
                text_color=COLORS["gray"])
            self._activity_dot.pack(side="right", padx=10)

            # Brain
            bf = ctk.CTkFrame(
                self._root, fg_color=COLORS["bg_dark"], corner_radius=0)
            bf.pack(fill="x", padx=10, pady=(8, 0))
            self._brain_label = ctk.CTkLabel(bf, text="")
            self._brain_label.pack(pady=3)
            self._state_label = ctk.CTkLabel(
                bf, text="IDLE", font=ctk.CTkFont(*FONT_MONO_SM),
                text_color=COLORS["cyan_dim"])
            self._state_label.pack(pady=(0, 2))

            try:
                self._anim_engine = _build_anim_engine_from_image(
                    self._brain_path)
                self._anim_engine.set_state(AnimState.IDLE)
                f = self._anim_engine.render_frame()
                fp = Image.fromarray(f, "RGBA")
                ci = ctk.CTkImage(light_image=fp, dark_image=fp,
                                  size=BRAIN_SIZE)
                self._brain_label.configure(image=ci, text="")
                self._brain_ctk_img = ci
            except Exception as e:
                log.warning("Brain load: %s", e)
                self._brain_label.configure(
                    text="[image error]", text_color=COLORS["red"])

            # Cards
            self._build_cards()

            # Footer
            footer = ctk.CTkFrame(
                self._root, fg_color=COLORS["bg_panel"],
                corner_radius=0, height=28)
            footer.pack(fill="x", side="bottom")
            footer.pack_propagate(False)
            self._stat_labels["footer"] = ctk.CTkLabel(
                footer, text="  Forge v0.1.0 | Local AI | $0.00 forever",
                font=ctk.CTkFont(*FONT_MONO_SM),
                text_color=COLORS["text_dim"])
            self._stat_labels["footer"].pack(side="left", padx=5, pady=2)

            # Register for live theme hot-swap
            self._theme_cb = lambda cm: self._root.after(
                0, self._apply_theme, cm)
            add_theme_listener(self._theme_cb)

            self._running = True
            self._schedule_refresh()
            self._schedule_animation()
            self._root.mainloop()
        except Exception as e:
            log.warning("Dashboard error: %s", e)
        finally:
            self._running = False
            with ForgeDashboard._instance_lock:
                ForgeDashboard._instance_alive = False

    def _build_cards(self):
        # Initialize effects engine
        from forge.config import ForgeConfig
        fx_enabled = ForgeConfig().get("effects_enabled", True)
        self._effects = EffectsEngine(self._root, enabled=fx_enabled)

        # Context
        card = _make_card_widget(self._root, "Context Window", self._effects)
        bf = ctk.CTkFrame(card, fg_color="transparent")
        bf.pack(fill="x", padx=15, pady=(0, 3))
        self._ctx_bar = ctk.CTkProgressBar(
            bf, height=14, corner_radius=4,
            fg_color=COLORS["bg_dark"], progress_color=COLORS["cyan"],
            border_color=COLORS["border"], border_width=1)
        self._ctx_bar.pack(fill="x")
        self._ctx_bar.set(0)
        self._ctx_label = ctk.CTkLabel(
            card, text="0% | 0 / 0 tokens",
            font=ctk.CTkFont(*FONT_MONO), text_color=COLORS["gray"])
        self._ctx_label.pack(padx=15, anchor="w")
        self._stat_labels["partitions"] = ctk.CTkLabel(
            card, text="", font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["text_dim"])
        self._stat_labels["partitions"].pack(padx=15, anchor="w", pady=(0, 5))

        # Performance
        card = _make_card_widget(self._root, "Performance", self._effects)
        for k, l, d in [("tok_s", "Throughput", "-- tok/s"),
                         ("trend", "Trend", "--"),
                         ("cache", "Cache Hit", "--%"),
                         ("swaps", "Auto-Swaps", "0")]:
            _add_row(card, k, l, d, self._stat_labels)

        # Session
        card = _make_card_widget(self._root, "Session", self._effects)
        for k, l, d in [("turns", "Turns", "0"),
                         ("duration", "Duration", "0m"),
                         ("tokens", "Tokens", "0"),
                         ("cost_saved", "Saved vs Opus", "$0.00")]:
            _add_row(card, k, l, d, self._stat_labels)

        # Memory
        card = _make_card_widget(self._root, "Memory", self._effects)
        for k, l, d in [("journal", "Journal", "0 entries"),
                         ("index", "Sem. Index", "not loaded"),
                         ("mem_status", "Status", "Ready")]:
            _add_row(card, k, l, d, self._stat_labels,
                     val_color=COLORS["cyan_dim"])

        # Edge glow + border color + widget glow for the dashboard window
        try:
            from forge.ui.effects import WidgetGlow
            self._effects.register_window_edge_glow(self._root)
            self._effects.register_window_border_color(self._root)
            if self._ctx_bar:
                self._effects.register_widget(
                    self._ctx_bar, WidgetGlow.PROGRESS)
        except Exception:
            log.debug("Effects registration failed", exc_info=True)

        # Ensure effects animation loop is running
        self._effects.start()

    def _apply_theme(self, color_map: dict):
        """Hot-swap theme colours on every widget in the dashboard."""
        if self._root:
            recolor_widget_tree(self._root, color_map)

    def _on_close(self):
        self._running = False
        if self._effects:
            self._effects.shutdown()
            self._effects = None
        if hasattr(self, "_theme_cb"):
            remove_theme_listener(self._theme_cb)
        try:
            self._root.destroy()
        except Exception:
            pass
        with ForgeDashboard._instance_lock:
            ForgeDashboard._instance_alive = False

    def _schedule_refresh(self):
        if not self._running:
            return
        try:
            if self._get_data:
                self._apply_data(self._get_data())
        except Exception:
            pass
        if self._root and self._running:
            self._root.after(2000, self._schedule_refresh)

    def _schedule_animation(self):
        if not self._running or not self._anim_engine:
            return
        fps = self._anim_engine.fps
        interval_ms = max(30, int(1000 / fps))
        self._anim_engine.advance(1.0 / fps)
        try:
            f = self._anim_engine.render_frame()
            fp = Image.fromarray(f, "RGBA")
            ci = ctk.CTkImage(light_image=fp, dark_image=fp,
                              size=BRAIN_SIZE)
            self._brain_label.configure(image=ci)
            self._brain_ctk_img = ci
        except Exception:
            pass
        if self._activity_dot:
            state = self._anim_engine.state
            sc = {AnimState.IDLE: COLORS["gray"],
                  AnimState.THINKING: COLORS["cyan_glow"],
                  AnimState.TOOL_EXEC: COLORS["green"],
                  AnimState.INDEXING: COLORS["magenta"],
                  AnimState.SWAPPING: COLORS["yellow"],
                  AnimState.ERROR: COLORS["red"]}
            dc = sc.get(state, COLORS["gray"])
            if state != AnimState.IDLE:
                if 0.5 + 0.5 * math.sin(self._anim_engine._phase * 6) < 0.4:
                    dc = COLORS["gray"]
            self._activity_dot.configure(text_color=dc)
        if self._state_label:
            nm = {AnimState.IDLE: "IDLE", AnimState.THINKING: "THINKING",
                  AnimState.TOOL_EXEC: "EXECUTING",
                  AnimState.INDEXING: "INDEXING",
                  AnimState.SWAPPING: "SWAPPING",
                  AnimState.ERROR: "ERROR"}
            self._state_label.configure(
                text=nm.get(self._anim_engine.state, ""))
        if self._root and self._running:
            self._root.after(interval_ms, self._schedule_animation)

    def _apply_data(self, data):
        if not data:
            return
        anim_state = data.get("anim_state")
        if anim_state and self._anim_engine:
            try:
                self._anim_engine.set_state(AnimState(anim_state))
            except ValueError:
                pass
        if "is_active" in data and not anim_state:
            self.set_activity(data["is_active"])

        ctx = data.get("context", {})
        pct = ctx.get("usage_pct", 0)
        total = ctx.get("total_tokens", 0)
        maximum = ctx.get("max_tokens", 1)
        if self._ctx_bar:
            self._ctx_bar.set(pct / 100.0)
            c = COLORS["red"] if pct > 90 else (
                COLORS["yellow"] if pct > 75 else COLORS["cyan"])
            self._ctx_bar.configure(progress_color=c)
        if self._ctx_label:
            self._ctx_label.configure(
                text=f"{pct:.0f}% | {total:,} / {maximum:,} tokens")
        parts = ctx.get("partitions", {})
        if parts and "partitions" in self._stat_labels:
            self._stat_labels["partitions"].configure(
                text=" | ".join(f"{k}: {v.get('tokens', 0):,}"
                                for k, v in parts.items()))

        perf = data.get("performance", {})
        _set(self._stat_labels, "tok_s",
             f"{perf.get('avg_tok_s', 0):.1f} tok/s",
             COLORS["green"] if perf.get("avg_tok_s", 0) > 10
             else COLORS["white"])
        trend = perf.get("trend", "--")
        _set(self._stat_labels, "trend", trend,
             COLORS["green"] if trend == "improving"
             else COLORS["red"] if trend == "degrading"
             else COLORS["white"])
        _set(self._stat_labels, "cache",
             f"{data.get('cache', {}).get('hit_rate', 0):.0f}%")
        _set(self._stat_labels, "swaps", str(data.get("swaps", 0)))

        s = data.get("session", {})
        _set(self._stat_labels, "turns", str(s.get("turns", 0)))
        _set(self._stat_labels, "duration",
             f"{s.get('duration_m', 0):.1f}m")
        _set(self._stat_labels, "tokens", f"{s.get('tokens', 0):,}")
        _set(self._stat_labels, "cost_saved",
             f"${s.get('cost_saved', 0):.4f}", COLORS["green"])

        m = data.get("memory", {})
        _set(self._stat_labels, "journal",
             f"{m.get('journal_entries', 0)} entries")
        chunks = m.get("index_chunks", 0)
        _set(self._stat_labels, "index",
             f"{chunks} chunks" if chunks else "not loaded",
             COLORS["cyan_dim"] if chunks else COLORS["text_dim"])
        status = m.get("status", "Idle")
        _set(self._stat_labels, "mem_status", status,
             COLORS["cyan_glow"] if status == "Active"
             else COLORS["green"] if status == "Ready"
             else COLORS["gray"])

        model = data.get("model", "")
        if model:
            _set(self._stat_labels, "footer",
                 f"  {model} | Local AI | $0.00 forever")


# ──────────────────────────────────────────────────────────────────
# Shared widget helpers
# ──────────────────────────────────────────────────────────────────

def _make_card_widget(parent, title, effects=None):
    frame = ctk.CTkFrame(
        parent, fg_color=COLORS["bg_card"], corner_radius=8,
        border_color=COLORS["border"], border_width=1)
    frame.pack(fill="x", padx=10, pady=3)
    ctk.CTkLabel(
        frame, text=f"  {title}",
        font=ctk.CTkFont(*FONT_MONO_BOLD),
        text_color=COLORS["cyan_dim"], anchor="w"
    ).pack(fill="x", padx=5, pady=(4, 1))
    divider = ctk.CTkFrame(
        frame, fg_color=COLORS["border"], height=1)
    divider.pack(fill="x", padx=15, pady=(0, 2))
    if effects:
        effects.register_card(frame, divider)
    return frame


def _add_row(parent, key, label, default, labels_dict,
             val_color=None):
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=15, pady=1)
    ctk.CTkLabel(
        row, text=label, font=ctk.CTkFont(*FONT_MONO),
        text_color=COLORS["gray"], width=120, anchor="w"
    ).pack(side="left")
    val = ctk.CTkLabel(
        row, text=default, font=ctk.CTkFont(*FONT_MONO_BOLD),
        text_color=val_color or COLORS["white"], anchor="e")
    val.pack(side="right")
    labels_dict[key] = val


def _set(labels, key, text, color=None):
    if key in labels:
        if color:
            labels[key].configure(text=text, text_color=color)
        else:
            labels[key].configure(text=text)


def _read_state_file() -> Optional[dict]:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


# ──────────────────────────────────────────────────────────────────
# Entry points
# ──────────────────────────────────────────────────────────────────

def launch_launcher():
    """Launch ForgeLauncher (primary entry point)."""
    if not HAS_GUI_DEPS:
        print("GUI requires: pip install customtkinter Pillow numpy")
        return
    ForgeLauncher().run()


def launch_dashboard_standalone(brain_path=None):
    """Launch dashboard in demo mode cycling through all 7 states."""
    if not HAS_GUI_DEPS:
        print("GUI requires: pip install customtkinter Pillow numpy")
        return

    demo_phase = [0]
    state_cycle = [
        ("idle", 8), ("thinking", 8), ("tool_exec", 4),
        ("thinking", 4), ("indexing", 6), ("swapping", 2),
        ("idle", 4), ("error", 3),
    ]
    total_cycle = sum(d for _, d in state_cycle)

    def get_demo_data():
        demo_phase[0] += 1
        p = demo_phase[0]
        pct = 30 + 40 * abs(math.sin(p * 0.1))
        cycle_pos = (p * 2) % total_cycle
        elapsed = 0
        current_state = "idle"
        for sn, dur in state_cycle:
            elapsed += dur
            if cycle_pos < elapsed:
                current_state = sn
                break
        return {
            "anim_state": current_state,
            "context": {
                "usage_pct": pct, "total_tokens": int(pct * 320),
                "max_tokens": 32000,
                "partitions": {
                    "core": {"tokens": 800, "entries": 2},
                    "working": {"tokens": int(pct * 200), "entries": 8},
                    "reference": {"tokens": int(pct * 80), "entries": 3},
                    "recall": {"tokens": int(pct * 40), "entries": 1},
                },
            },
            "performance": {
                "avg_tok_s": 15.2 + 3 * math.sin(p * 0.2),
                "trend": "stable",
            },
            "cache": {"hit_rate": 72.5},
            "swaps": p // 20,
            "session": {
                "turns": p // 4, "duration_m": p * 0.1,
                "tokens": p * 312, "cost_saved": p * 0.003,
            },
            "memory": {
                "journal_entries": p // 4, "index_chunks": 234,
                "status": "Active" if current_state == "thinking"
                else "Ready",
            },
            "model": "qwen2.5-coder:14b",
        }

    path = brain_path or str(BRAIN_IMAGE_PATH)
    ForgeDashboard(get_data_fn=get_demo_data, brain_path=path).launch(
        blocking=True)


if __name__ == "__main__":
    import sys
    if "--launcher" in sys.argv:
        launch_launcher()
    else:
        brain = sys.argv[1] if len(sys.argv) > 1 else None
        launch_dashboard_standalone(brain)
