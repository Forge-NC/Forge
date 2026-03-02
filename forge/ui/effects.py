"""Forge Visual Effects Engine — animated borders, particles, energy pulses.

Theme-aware effect system.  Effects activate only for themes listed in
EFFECTS_CONFIG.  All animations use root.after() and clean up on theme
switch or window close.

Usage (inside dashboard.py):
    from forge.ui.effects import EffectsEngine
    fx = EffectsEngine(root)
    fx.register_card(card_frame, divider_frame)
    fx.register_particle_region(content_frame)
    # on close:
    fx.shutdown()
"""

import logging
import math
import random
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Global engine registry — direct toggle for all active effects engines
# ---------------------------------------------------------------------------
# Every EffectsEngine registers itself on creation and unregisters on
# shutdown.  This lets the settings dialog toggle ALL engines directly
# without relying on indirect theme-listener → after(0) → callback chains.

_active_engines: set["EffectsEngine"] = set()
_engines_lock = threading.Lock()


def toggle_all_effects(enabled: bool):
    """Directly enable or disable effects on every active EffectsEngine.

    Called by the settings dialog for instant live preview.  This is
    synchronous and immediate — no event-loop round-trip.
    """
    with _engines_lock:
        snapshot = list(_active_engines)
    for engine in snapshot:
        try:
            engine.set_enabled(enabled)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Effects configuration per theme
# ---------------------------------------------------------------------------
# Themes NOT listed here get zero effects and zero performance cost.

EFFECTS_CONFIG: dict[str, dict] = {
    "plasma": {
        "border_glow": True,
        "particles": True,
        "header_pulse": True,
        "hover_glow": True,
        "edge_glow": True,
        "edge_thickness": 3,
        "edge_crackle_rate": 0.10,
        "widget_glow": True,
        "palette": ["#00e5ff", "#4400ff", "#ff00cc", "#aa00ff", "#00e5ff"],
        "particle_colors": ["#00e5ff", "#ff00cc", "#aa00ff"],
        "pulse_color": "#ff00cc",
        "hover_boost": "#44ffff",
        "particle_count": 25,
        "glow_fps": 10,
    },
    "cyberpunk": {
        "border_glow": True,
        "particles": True,
        "header_pulse": True,
        "hover_glow": True,
        "edge_glow": True,
        "edge_thickness": 3,
        "edge_crackle_rate": 0.12,
        "widget_glow": True,
        "palette": ["#00ffff", "#0088ff", "#ff2d95", "#cc44ff", "#00ffff"],
        "particle_colors": ["#00ffff", "#ff2d95"],
        "pulse_color": "#ff2d95",
        "hover_boost": "#44ffff",
        "particle_count": 20,
        "glow_fps": 10,
    },
    "matrix": {
        "border_glow": True,
        "particles": True,
        "header_pulse": True,
        "hover_glow": True,
        "edge_glow": True,
        "edge_thickness": 3,
        "edge_crackle_rate": 0.08,
        "widget_glow": True,
        "palette": ["#00ff41", "#00dd66", "#00ff88", "#44ff66", "#00ff41"],
        "particle_colors": ["#00ff41", "#88ff00"],
        "pulse_color": "#00ff41",
        "hover_boost": "#66ff66",
        "particle_count": 20,
        "glow_fps": 8,
    },
}


# ---------------------------------------------------------------------------
# Color utilities
# ---------------------------------------------------------------------------

def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{max(0,min(255,r)):02x}{max(0,min(255,g)):02x}{max(0,min(255,b)):02x}"


def _lerp_color(c1: str, c2: str, t: float) -> str:
    """Linearly interpolate between two hex colors."""
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    return _rgb_to_hex(
        int(r1 + (r2 - r1) * t),
        int(g1 + (g2 - g1) * t),
        int(b1 + (b2 - b1) * t),
    )


# ---------------------------------------------------------------------------
# BorderGlowEffect
# ---------------------------------------------------------------------------

class BorderGlowEffect:
    """Cycles a CTkFrame's border_color through a smooth palette."""

    def __init__(self, card_frame, palette: list[str],
                 phase_offset: float = 0.0):
        self._card = card_frame
        self._palette = palette
        self._palette_rgb = [_hex_to_rgb(c) for c in palette]
        self._offset = phase_offset
        # Save the static border for restore
        try:
            self._original_border = card_frame.cget("border_color")
        except Exception:
            self._original_border = "#1a2540"
        self._original_width = 1

    def update(self, phase: float):
        """Compute and apply interpolated border color."""
        n = len(self._palette_rgb)
        if n < 2:
            return
        # Wrap phase through the palette loop
        p = (phase * 0.3 + self._offset) % (n - 1)
        idx = int(p)
        frac = p - idx
        # Smoothstep
        frac = frac * frac * (3.0 - 2.0 * frac)
        c1 = self._palette_rgb[idx]
        c2 = self._palette_rgb[min(idx + 1, n - 1)]
        r = int(c1[0] + (c2[0] - c1[0]) * frac)
        g = int(c1[1] + (c2[1] - c1[1]) * frac)
        b = int(c1[2] + (c2[2] - c1[2]) * frac)
        try:
            self._card.configure(border_color=_rgb_to_hex(r, g, b),
                                 border_width=2)
        except Exception:
            log.debug("BorderGlow configure failed", exc_info=True)

    def restore(self):
        """Reset to static theme border."""
        try:
            from forge.ui.themes import get_colors
            border = get_colors().get("border", self._original_border)
            self._card.configure(border_color=border,
                                 border_width=self._original_width)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# HoverGlowEffect
# ---------------------------------------------------------------------------

class HoverGlowEffect:
    """Brightens a card's border on mouse hover."""

    def __init__(self, card_frame, boost_color: str):
        self._card = card_frame
        self._boost = boost_color
        self._hovered = False
        self._bound = False

    @property
    def is_hovered(self) -> bool:
        return self._hovered

    def bind(self):
        if self._bound:
            return
        self._card.bind("<Enter>", self._on_enter, add="+")
        self._card.bind("<Leave>", self._on_leave, add="+")
        self._bound = True

    def unbind(self):
        if not self._bound:
            return
        try:
            self._card.unbind("<Enter>")
            self._card.unbind("<Leave>")
        except Exception:
            pass
        self._bound = False
        self._hovered = False

    def _on_enter(self, _event):
        self._hovered = True
        try:
            self._card.configure(border_color=self._boost, border_width=3)
        except Exception:
            pass

    def _on_leave(self, _event):
        self._hovered = False
        try:
            self._card.configure(border_width=2)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# HeaderPulseEffect
# ---------------------------------------------------------------------------

class HeaderPulseEffect:
    """Traveling bright spot along a card's header divider line."""

    def __init__(self, divider_frame, pulse_color: str, bg_color: str):
        self._divider = divider_frame
        self._pulse_color = pulse_color
        self._bg_color = bg_color
        self._canvas = None
        self._width = 0
        self._setup_pending = True

    def setup(self):
        """Create the canvas overlay on the divider."""
        try:
            import tkinter as tk
        except ImportError:
            return
        try:
            self._divider.update_idletasks()
            self._width = self._divider.winfo_width()
            if self._width < 20:
                return  # Not visible yet, retry later
            h = max(self._divider.winfo_height(), 2)
            self._canvas = tk.Canvas(
                self._divider.master,
                width=self._width, height=h,
                bg=self._bg_color, highlightthickness=0, bd=0)
            self._canvas.place(in_=self._divider, x=0, y=0,
                               relwidth=1.0, height=h)
            self._setup_pending = False
        except Exception:
            log.debug("HeaderPulse setup failed", exc_info=True)

    def update(self, phase: float):
        """Move the bright spot."""
        if self._setup_pending:
            self.setup()
        if not self._canvas:
            return
        try:
            w = self._canvas.winfo_width()
            if w < 20:
                return
            self._canvas.delete("pulse")
            # Position: sweep left to right
            pos = (phase * 0.4) % 1.0
            cx = int(pos * w)
            # Draw layered bright spot (3 lines for gradient effect)
            for i, alpha in enumerate([0.25, 0.55, 1.0]):
                spread = 30 - i * 10
                color = _lerp_color(self._bg_color, self._pulse_color, alpha)
                x0 = max(0, cx - spread)
                x1 = min(w, cx + spread)
                self._canvas.create_line(x0, 1, x1, 1, fill=color,
                                         width=2, tags="pulse")
        except Exception:
            pass

    def destroy(self):
        if self._canvas:
            try:
                self._canvas.destroy()
            except Exception:
                pass
            self._canvas = None
        self._setup_pending = True


# ---------------------------------------------------------------------------
# ParticleField
# ---------------------------------------------------------------------------

@dataclass
class _Particle:
    x: float
    y: float
    vx: float
    vy: float
    radius: float
    color: str
    brightness: float
    canvas_id: int = 0


class ParticleField:
    """Slowly drifting bright dots on a tk.Canvas background."""

    def __init__(self, parent, colors: list[str], count: int = 25,
                 bg_color: str = "#070010"):
        try:
            import tkinter as tk
        except ImportError:
            self._canvas = None
            return

        self._parent = parent
        self._colors = colors or ["#ffffff"]
        self._target_count = count
        self._bg = bg_color
        self._particles: list[_Particle] = []

        self._canvas = tk.Canvas(
            parent, bg=bg_color, highlightthickness=0, bd=0)
        self._canvas.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        # Canvas overrides lower() to mean tag_lower() (for canvas
        # items).  Use raw Tcl call to lower the WIDGET.
        try:
            self._canvas.tk.call('lower', self._canvas._w)
        except Exception:
            pass

        self._width = 0
        self._height = 0

    def spawn_particles(self):
        """Create initial batch at random positions."""
        if not self._canvas:
            return
        self._canvas.delete("all")
        self._particles.clear()
        try:
            self._canvas.update_idletasks()
            self._width = self._canvas.winfo_width()
            self._height = self._canvas.winfo_height()
        except Exception:
            return
        if self._width < 20 or self._height < 20:
            return
        for _ in range(self._target_count):
            self._spawn_one(random_y=True)

    def _spawn_one(self, random_y: bool = False):
        """Spawn a single particle."""
        if not self._canvas or self._width < 20:
            return
        x = random.uniform(10, self._width - 10)
        y = (random.uniform(10, self._height - 10) if random_y
             else self._height + random.uniform(5, 30))
        vx = random.uniform(-0.3, 0.3)
        vy = random.uniform(-0.8, -0.2)  # drift upward
        radius = random.uniform(1.0, 2.5)
        color = random.choice(self._colors)
        brightness = random.uniform(0.3, 1.0)

        # Dim the color by brightness
        r, g, b = _hex_to_rgb(color)
        r = int(r * brightness)
        g = int(g * brightness)
        b = int(b * brightness)
        fill = _rgb_to_hex(r, g, b)

        cid = self._canvas.create_oval(
            x - radius, y - radius, x + radius, y + radius,
            fill=fill, outline="", tags="particle")

        self._particles.append(_Particle(
            x=x, y=y, vx=vx, vy=vy, radius=radius,
            color=color, brightness=brightness, canvas_id=cid))

    def update(self, dt: float):
        """Advance all particles. Respawn dead ones."""
        if not self._canvas:
            return
        try:
            self._width = self._canvas.winfo_width()
            self._height = self._canvas.winfo_height()
        except Exception:
            return

        dead = []
        for p in self._particles:
            # Slight horizontal wobble
            p.vx += random.uniform(-0.02, 0.02)
            p.vx = max(-0.5, min(0.5, p.vx))
            p.x += p.vx * dt * 60
            p.y += p.vy * dt * 60

            # Fade brightness as it rises
            p.brightness *= 0.998

            if p.y < -10 or p.brightness < 0.05:
                dead.append(p)
                continue

            try:
                self._canvas.coords(
                    p.canvas_id,
                    p.x - p.radius, p.y - p.radius,
                    p.x + p.radius, p.y + p.radius)
                # Update color with faded brightness
                r, g, b = _hex_to_rgb(p.color)
                r = int(r * p.brightness)
                g = int(g * p.brightness)
                b = int(b * p.brightness)
                self._canvas.itemconfig(p.canvas_id, fill=_rgb_to_hex(r, g, b))
            except Exception:
                dead.append(p)

        # Remove dead particles and respawn
        for p in dead:
            try:
                self._canvas.delete(p.canvas_id)
            except Exception:
                pass
            self._particles.remove(p)
            if len(self._particles) < self._target_count:
                self._spawn_one(random_y=False)

    def destroy(self):
        """Remove canvas and clear all data."""
        self._particles.clear()
        if self._canvas:
            try:
                self._canvas.destroy()
            except Exception:
                pass
            self._canvas = None


# ---------------------------------------------------------------------------
# WindowBorderColor — OS-level window frame border animation
# ---------------------------------------------------------------------------

class WindowBorderColor:
    """Animate the actual OS window frame border color.

    On Windows 11+, uses DWM (Desktop Window Manager) to set the
    window border color.  On other platforms this is a no-op.
    """

    _DWMWA_BORDER_COLOR = 34
    _COLOR_DEFAULT = 0xFFFFFFFF

    def __init__(self, window, palette: list[str]):
        self._palette_rgb = [_hex_to_rgb(c) for c in palette]
        self._available = False
        self._dwm_set = None  # bound DwmSetWindowAttribute
        self._hwnd_val = 0    # raw integer HWND (avoids ctypes on every tick)

        if sys.platform != "win32":
            return

        try:
            import ctypes
            import ctypes.wintypes

            # Ensure the window is mapped so winfo_id() returns a real HWND
            window.update_idletasks()

            # winfo_id() returns the inner Tk frame HWND.  DWM needs
            # the actual top-level window handle.
            inner = window.winfo_id()

            user32 = ctypes.windll.user32
            # Declare proper types so 64-bit HWNDs aren't truncated
            user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            user32.GetAncestor.restype = ctypes.c_void_p
            top = user32.GetAncestor(inner, 2)  # GA_ROOT = 2
            self._hwnd_val = top if top else inner

            dwmapi = ctypes.windll.dwmapi
            dwmapi.DwmSetWindowAttribute.argtypes = [
                ctypes.c_void_p,       # HWND
                ctypes.wintypes.DWORD,  # dwAttribute
                ctypes.c_void_p,       # pvAttribute (pointer)
                ctypes.wintypes.DWORD,  # cbAttribute
            ]
            dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long  # HRESULT

            # Probe with COLOR_DEFAULT (no visible change)
            val = ctypes.wintypes.DWORD(self._COLOR_DEFAULT)
            hr = dwmapi.DwmSetWindowAttribute(
                self._hwnd_val, self._DWMWA_BORDER_COLOR,
                ctypes.byref(val), ctypes.sizeof(val))
            if hr == 0:
                self._available = True
                self._dwm_set = dwmapi.DwmSetWindowAttribute
                self._dword = ctypes.wintypes.DWORD  # cache class ref
                self._byref = ctypes.byref
            else:
                log.debug("DWM border color not supported (hr=0x%08x)", hr)
        except Exception:
            log.debug("WindowBorderColor init failed", exc_info=True)

    def _set_color(self, colorref: int):
        """Low-level DWM call with an integer COLORREF."""
        val = self._dword(colorref)
        self._dwm_set(
            self._hwnd_val, self._DWMWA_BORDER_COLOR,
            self._byref(val), 4)

    def update(self, phase: float):
        if not self._available:
            return
        n = len(self._palette_rgb)
        if n < 2:
            return
        try:
            p = (phase * 0.3) % (n - 1)
            idx = int(p)
            frac = p - idx
            frac = frac * frac * (3.0 - 2.0 * frac)
            c1 = self._palette_rgb[idx]
            c2 = self._palette_rgb[min(idx + 1, n - 1)]
            r = int(c1[0] + (c2[0] - c1[0]) * frac)
            g = int(c1[1] + (c2[1] - c1[1]) * frac)
            b = int(c1[2] + (c2[2] - c1[2]) * frac)
            # COLORREF is 0x00BBGGRR (BGR, not RGB)
            self._set_color(b << 16 | g << 8 | r)
        except Exception:
            pass

    def update_palette(self, palette: list[str]):
        self._palette_rgb = [_hex_to_rgb(c) for c in palette]

    def restore(self):
        """Reset to default (let Windows manage border color)."""
        if not self._available:
            return
        try:
            self._set_color(self._COLOR_DEFAULT)
        except Exception:
            pass

    def destroy(self):
        self.restore()
        self._available = False
        self._dwm_set = None


# ---------------------------------------------------------------------------
# WindowEdgeGlow — crackling energy border
# ---------------------------------------------------------------------------

@dataclass
class _EdgeSpark:
    """A bright spark traveling along a window edge."""
    position: float    # 0.0–1.0 along edge length
    brightness: float  # 0.0–1.0, decays each tick
    speed: float       # movement per tick (signed)
    color: tuple       # (r, g, b) base color


class WindowEdgeGlow:
    """Crackling energy glow along window edges.

    Creates 4 thin canvas strips placed at the window edges.
    Animates with palette-based color cycling plus random
    crackle/flicker and traveling spark particles.
    """

    def __init__(self, window, palette: list[str], bg_color: str,
                 thickness: int = 3, crackle_rate: float = 0.10):
        try:
            import tkinter as tk
        except ImportError:
            self._edges = {}
            return

        self._palette_rgb = [_hex_to_rgb(c) for c in palette]
        self._thickness = thickness
        self._crackle_rate = crackle_rate

        # 4 edge canvas strips
        self._edges: dict[str, "tk.Canvas"] = {}

        # Bail out if window is already destroyed (e.g. theme change
        # fires on a closed settings/model-manager dialog)
        try:
            if not window.winfo_exists():
                return
        except Exception:
            return

        for side in ("top", "bottom", "left", "right"):
            kw: dict = dict(bg=bg_color, highlightthickness=0, bd=0)
            if side in ("top", "bottom"):
                kw["height"] = thickness
            else:
                kw["width"] = thickness
            self._edges[side] = tk.Canvas(window, **kw)

        # Place at absolute window edges
        self._edges["top"].place(x=0, y=0, relwidth=1.0, height=thickness)
        self._edges["bottom"].place(
            x=0, rely=1.0, relwidth=1.0, height=thickness, anchor="sw")
        self._edges["left"].place(x=0, y=0, width=thickness, relheight=1.0)
        self._edges["right"].place(
            relx=1.0, y=0, width=thickness, relheight=1.0, anchor="ne")

        # Raise edge canvases above other widgets.  Canvas overrides
        # lift() to mean tag_raise() (for canvas items), so we must
        # use the raw Tcl call to raise the WIDGET in the stacking order.
        for c in self._edges.values():
            c.tk.call('raise', c._w)

        # Per-edge crackle intensity (decays each tick)
        self._crackle = {s: 0.0 for s in self._edges}
        self._sparks: dict[str, list[_EdgeSpark]] = {
            s: [] for s in self._edges}
        self._tick_count = 0

    def update(self, phase: float):
        """Update edge glow + spark particles."""
        n = len(self._palette_rgb)
        if n < 2 or not self._edges:
            return

        self._tick_count += 1
        # Re-raise periodically so edges stay on top
        if self._tick_count % 30 == 0:
            for c in self._edges.values():
                try:
                    c.tk.call('raise', c._w)
                except Exception:
                    pass

        # Base palette interpolation
        p = (phase * 0.3) % (n - 1)
        idx = int(p)
        frac = p - idx
        frac = frac * frac * (3.0 - 2.0 * frac)
        c1 = self._palette_rgb[idx]
        c2 = self._palette_rgb[min(idx + 1, n - 1)]
        base_r = c1[0] + (c2[0] - c1[0]) * frac
        base_g = c1[1] + (c2[1] - c1[1]) * frac
        base_b = c1[2] + (c2[2] - c1[2]) * frac

        for side, canvas in self._edges.items():
            try:
                cw = canvas.winfo_width()
                ch = canvas.winfo_height()
                if cw < 3 or ch < 3:
                    continue

                # Crackle: random brightness spikes with fast decay
                self._crackle[side] *= 0.82
                if random.random() < self._crackle_rate:
                    self._crackle[side] = random.uniform(0.5, 1.0)

                # Base brightness: slow sine + crackle
                bright = (0.25
                          + 0.25 * math.sin(
                              phase * 1.5 + hash(side) % 100 * 0.1)
                          + 0.5 * self._crackle[side])
                bright = max(0.0, min(1.0, bright))

                r = int(base_r * bright)
                g = int(base_g * bright)
                b = int(base_b * bright)
                canvas.configure(bg=_rgb_to_hex(r, g, b))
                canvas.delete("spark")

                # Spawn new sparks
                if random.random() < self._crackle_rate * 1.5:
                    sc = random.choice(self._palette_rgb)
                    self._sparks[side].append(_EdgeSpark(
                        position=random.random(),
                        brightness=random.uniform(0.7, 1.0),
                        speed=(random.choice([-1, 1])
                               * random.uniform(0.01, 0.06)),
                        color=sc))

                # Update + draw sparks
                length = cw if side in ("top", "bottom") else ch
                alive = []
                for spark in self._sparks[side]:
                    spark.position += spark.speed
                    spark.brightness *= 0.90
                    if (spark.brightness < 0.08
                            or spark.position < -0.05
                            or spark.position > 1.05):
                        continue
                    alive.append(spark)

                    # Bright spark color (boosted toward white)
                    sr = min(255, int(
                        spark.color[0] * spark.brightness
                        + 180 * spark.brightness))
                    sg = min(255, int(
                        spark.color[1] * spark.brightness
                        + 180 * spark.brightness))
                    sb = min(255, int(
                        spark.color[2] * spark.brightness
                        + 180 * spark.brightness))
                    spark_hex = _rgb_to_hex(sr, sg, sb)

                    spread = max(3, int(length * 0.04))
                    pos_px = int(spark.position * length)
                    p0 = max(0, pos_px - spread)
                    p1 = min(length, pos_px + spread)
                    t = self._thickness
                    if side in ("top", "bottom"):
                        canvas.create_line(
                            p0, t // 2, p1, t // 2,
                            fill=spark_hex, width=t, tags="spark")
                    else:
                        canvas.create_line(
                            t // 2, p0, t // 2, p1,
                            fill=spark_hex, width=t, tags="spark")

                self._sparks[side] = alive
                if len(alive) > 12:
                    self._sparks[side] = alive[-8:]
            except Exception:
                pass

    def update_palette(self, palette: list[str]):
        self._palette_rgb = [_hex_to_rgb(c) for c in palette]

    def destroy(self):
        self._sparks.clear()
        self._crackle.clear()
        for canvas in self._edges.values():
            try:
                canvas.destroy()
            except Exception:
                pass
        self._edges.clear()


# ---------------------------------------------------------------------------
# WidgetGlow — color-cycling sliders / progress bars / scrollbars
# ---------------------------------------------------------------------------

class WidgetGlow:
    """Animated color cycling on interactive CTk widgets."""

    SLIDER = "slider"
    PROGRESS = "progress"
    SCROLLBAR = "scrollbar"

    def __init__(self, widget, palette: list[str],
                 widget_type: str = "slider", phase_offset: float = 0.0):
        self._widget = widget
        self._palette_rgb = [_hex_to_rgb(c) for c in palette]
        self._type = widget_type
        self._offset = phase_offset

    def update(self, phase: float):
        n = len(self._palette_rgb)
        if n < 2:
            return
        # Slower cycle than border glow
        p = (phase * 0.15 + self._offset) % (n - 1)
        idx = int(p)
        frac = p - idx
        c1 = self._palette_rgb[idx]
        c2 = self._palette_rgb[min(idx + 1, n - 1)]
        r = int(c1[0] + (c2[0] - c1[0]) * frac)
        g = int(c1[1] + (c2[1] - c1[1]) * frac)
        b = int(c1[2] + (c2[2] - c1[2]) * frac)
        color = _rgb_to_hex(r, g, b)
        dim = _rgb_to_hex(r // 3, g // 3, b // 3)

        try:
            if self._type == self.SLIDER:
                self._widget.configure(
                    progress_color=color, button_color=color)
            elif self._type == self.PROGRESS:
                self._widget.configure(progress_color=color)
            elif self._type == self.SCROLLBAR:
                self._widget.configure(
                    button_color=dim, button_hover_color=color)
        except Exception:
            pass

    def update_palette(self, palette: list[str]):
        self._palette_rgb = [_hex_to_rgb(c) for c in palette]

    def restore(self):
        try:
            from forge.ui.themes import get_colors
            colors = get_colors()
            if self._type == self.SLIDER:
                self._widget.configure(
                    progress_color=colors.get("cyan_dim", "#006688"),
                    button_color=colors.get("cyan", "#00bcd4"))
            elif self._type == self.PROGRESS:
                self._widget.configure(
                    progress_color=colors.get("cyan_dim", "#006688"))
            elif self._type == self.SCROLLBAR:
                self._widget.configure(
                    button_color=colors.get("border", "#1a2540"),
                    button_hover_color=colors.get("cyan_dim", "#006688"))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# EffectsEngine — main coordinator
# ---------------------------------------------------------------------------

class EffectsEngine:
    """Central effects coordinator for a single Tk root window.

    Owns the animation after-loop, manages all registered effects,
    listens for theme changes, and provides clean shutdown.
    """

    def __init__(self, root, enabled: bool = True):
        self._root = root
        self._enabled = enabled
        self._running = False
        self._shutting_down = False
        self._after_id = None
        self._last_tick: float = 0.0
        self._phase: float = 0.0

        # Registered effects
        self._border_glows: list[BorderGlowEffect] = []
        self._hover_glows: list[HoverGlowEffect] = []
        self._hover_map: dict[int, HoverGlowEffect] = {}  # id(card) -> hover
        self._header_pulses: list[HeaderPulseEffect] = []
        self._particle_field: Optional[ParticleField] = None
        self._particle_parent = None

        # Edge glow (crackling window border)
        self._edge_glow: Optional[WindowEdgeGlow] = None
        self._edge_window = None  # stored for deactivate/reactivate

        # OS-level window border color animation (Windows 11+)
        self._border_color: Optional[WindowBorderColor] = None
        self._border_color_window = None

        # Widget glow (sliders / progress bars / scrollbars)
        self._widget_glows: list[WidgetGlow] = []
        self._widget_registrations: list[tuple] = []  # (widget, type)

        # Current effects config (None = disabled for current theme)
        self._config: Optional[dict] = None

        # Listen for theme changes — marshal to GUI thread via after()
        from forge.ui.themes import add_theme_listener, get_theme
        self._theme_cb = lambda _cm: self._root.after(0, self._on_theme_change)
        add_theme_listener(self._theme_cb)

        # Register in global engine registry for direct toggle
        with _engines_lock:
            _active_engines.add(self)

        # Check if current theme has effects
        if self._enabled:
            self._activate_for_theme(get_theme())

    # ── Registration ──

    def register_card(self, card_frame, divider_frame=None):
        """Register a card for border glow + hover glow.

        Call this for each card after it's packed/placed.
        *divider_frame* is the 1px separator inside the card header.
        """
        idx = len(self._border_glows)
        palette = (self._config or {}).get("palette", [])
        glow = BorderGlowEffect(card_frame, palette, phase_offset=idx * 0.7)
        self._border_glows.append(glow)

        boost = (self._config or {}).get("hover_boost", "#ffffff")
        hover = HoverGlowEffect(card_frame, boost)
        self._hover_glows.append(hover)
        self._hover_map[id(card_frame)] = hover

        if divider_frame is not None:
            from forge.ui.themes import get_colors
            bg = get_colors().get("border", "#1e0040")
            pulse_color = (self._config or {}).get("pulse_color", "#ff00cc")
            pulse = HeaderPulseEffect(divider_frame, pulse_color, bg)
            self._header_pulses.append(pulse)

        # If already running, activate the new effect immediately
        if self._running and self._config:
            if self._config.get("hover_glow"):
                hover.bind()
            log.debug("Registered card #%d for effects (running=%s)",
                      idx, self._running)

    def register_particle_region(self, parent_frame):
        """Create a particle field canvas behind cards in *parent_frame*.

        The parent_frame must NOT be covered by an opaque widget
        (e.g. don't use a frame that has a CTkScrollableFrame on top).
        """
        self._particle_parent = parent_frame
        if self._config and self._config.get("particles"):
            self._create_particles()

    def register_window_edge_glow(self, window):
        """Register a window for crackling edge glow effect.

        *window* is a CTk, CTkToplevel, or tk.Toplevel. Four thin
        canvas strips are placed along its inner edges when the
        current theme supports edge_glow.
        """
        self._edge_window = window
        if self._config and self._config.get("edge_glow"):
            self._create_edge_glow()

    def register_window_border_color(self, window):
        """Register a window for OS-level border color animation.

        On Windows 11+, this uses the DWM API to animate the actual
        window frame border color through the theme palette.  On other
        platforms this is a silent no-op.
        """
        self._border_color_window = window
        if self._config:
            self._create_border_color()

    def register_widget(self, widget, widget_type: str = "slider"):
        """Register a CTkSlider, CTkProgressBar, or CTkScrollbar for glow.

        *widget_type* is one of ``WidgetGlow.SLIDER``, ``PROGRESS``, or
        ``SCROLLBAR``.
        """
        self._widget_registrations.append((widget, widget_type))
        if self._config and self._config.get("widget_glow"):
            palette = self._config.get("palette", [])
            offset = len(self._widget_glows) * 0.5
            wg = WidgetGlow(widget, palette, widget_type, offset)
            self._widget_glows.append(wg)

    # ── Public control ──

    def set_enabled(self, enabled: bool):
        """Enable or disable effects at runtime.

        Always performs the full deactivate/activate cycle to guarantee
        effects come back reliably after being toggled off then on.
        """
        self._enabled = enabled
        if self._shutting_down:
            return
        # Always tear down first so we start from a clean state
        self._deactivate()
        if enabled:
            from forge.ui.themes import get_theme
            self._activate_for_theme(get_theme())
        log.debug("Effects engine set_enabled=%s running=%s",
                  enabled, self._running)

    # ── Lifecycle ──

    def start(self):
        """Begin the effects animation loop."""
        if self._running:
            return
        self._running = True
        self._last_tick = time.monotonic()
        log.debug("Effects engine started: %d glows, %d pulses, particles=%s",
                  len(self._border_glows), len(self._header_pulses),
                  self._particle_field is not None)

        # Bind hover effects
        if self._config and self._config.get("hover_glow"):
            for h in self._hover_glows:
                h.bind()

        self._tick()

    def stop(self):
        """Pause all effects (retains registrations)."""
        self._running = False
        if self._after_id:
            try:
                self._root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

        # Unbind hover
        for h in self._hover_glows:
            h.unbind()

        # Restore static borders
        for g in self._border_glows:
            g.restore()

    def shutdown(self):
        """Full cleanup — stop loops, unregister listener, destroy widgets."""
        self._shutting_down = True
        self.stop()
        with _engines_lock:
            _active_engines.discard(self)
        from forge.ui.themes import remove_theme_listener
        remove_theme_listener(self._theme_cb)

        for p in self._header_pulses:
            p.destroy()
        self._header_pulses.clear()

        if self._particle_field:
            self._particle_field.destroy()
            self._particle_field = None

        if self._edge_glow:
            self._edge_glow.destroy()
            self._edge_glow = None

        if self._border_color:
            self._border_color.destroy()
            self._border_color = None

        for wg in self._widget_glows:
            wg.restore()
        self._widget_glows.clear()
        self._widget_registrations.clear()

        self._border_glows.clear()
        self._hover_glows.clear()
        self._hover_map.clear()
        log.debug("Effects engine shut down")

    # ── Theme change ──

    def _on_theme_change(self):
        """Re-activate effects for the new theme.

        Called via root.after(0, ...) so it always runs on the GUI thread.
        Respects the current _enabled state set by toggle_all_effects() —
        does NOT re-read config from disk, which would override live
        preview toggles in the settings dialog.
        """
        if self._shutting_down:
            return
        # Guard against destroyed windows (settings dialog closed
        # but theme listener hasn't been removed yet)
        try:
            if not self._root.winfo_exists():
                self.shutdown()
                return
        except Exception:
            self.shutdown()
            return

        from forge.ui.themes import get_theme
        theme = get_theme()
        log.debug("Effects theme change: theme=%s enabled=%s", theme,
                  self._enabled)

        # Full teardown + rebuild for new theme palette
        self._deactivate()
        if self._enabled:
            self._activate_for_theme(theme)

    def _activate_for_theme(self, theme_name: str):
        cfg = EFFECTS_CONFIG.get(theme_name)
        if not cfg:
            self._config = None
            log.debug("No effects config for theme '%s'", theme_name)
            return
        self._config = cfg
        log.debug("Activating effects for '%s': %d registered cards",
                  theme_name, len(self._border_glows))

        # Update palettes on existing glows
        palette = cfg.get("palette", [])
        for i, glow in enumerate(self._border_glows):
            glow._palette = palette
            glow._palette_rgb = [_hex_to_rgb(c) for c in palette]
            glow._offset = i * 0.7

        # Update hover boost
        boost = cfg.get("hover_boost", "#ffffff")
        for h in self._hover_glows:
            h._boost = boost

        # Update pulse colors
        from forge.ui.themes import get_colors
        bg = get_colors().get("border", "#1e0040")
        pulse_c = cfg.get("pulse_color", "#ff00cc")
        for p in self._header_pulses:
            p._pulse_color = pulse_c
            p._bg_color = bg

        # Particles
        if cfg.get("particles") and self._particle_parent:
            self._create_particles()

        # Window edge glow
        if cfg.get("edge_glow") and self._edge_window:
            self._create_edge_glow()

        # OS-level window border color
        if self._border_color_window:
            self._create_border_color()

        # Widget glow — rebuild from registrations
        self._widget_glows.clear()
        if cfg.get("widget_glow"):
            palette = cfg.get("palette", [])
            for i, (widget, wtype) in enumerate(self._widget_registrations):
                wg = WidgetGlow(widget, palette, wtype, i * 0.5)
                self._widget_glows.append(wg)

        self.start()

    def _deactivate(self):
        self.stop()
        # Destroy pulse canvases (they'll be re-created on next activate)
        for p in self._header_pulses:
            p.destroy()
        # Destroy particle field
        if self._particle_field:
            self._particle_field.destroy()
            self._particle_field = None
        # Destroy edge glow
        if self._edge_glow:
            self._edge_glow.destroy()
            self._edge_glow = None
        # Destroy OS-level border color
        if self._border_color:
            self._border_color.destroy()
            self._border_color = None
        # Restore widgets to theme defaults
        for wg in self._widget_glows:
            wg.restore()
        self._widget_glows.clear()

    def _create_particles(self):
        """Create (or recreate) the particle field."""
        if self._particle_field:
            self._particle_field.destroy()
        if not self._particle_parent or not self._config:
            return
        from forge.ui.themes import get_colors
        bg = get_colors().get("bg_dark", "#070010")
        colors = self._config.get("particle_colors", ["#ffffff"])
        count = self._config.get("particle_count", 25)
        self._particle_field = ParticleField(
            self._particle_parent, colors, count, bg)
        # Defer spawn until canvas is visible
        self._root.after(200, self._deferred_spawn)

    def _deferred_spawn(self):
        if self._particle_field:
            self._particle_field.spawn_particles()

    def _create_edge_glow(self):
        """Create (or recreate) the window edge glow."""
        if self._edge_glow:
            self._edge_glow.destroy()
            self._edge_glow = None
        if not self._edge_window or not self._config:
            return
        try:
            if not self._edge_window.winfo_exists():
                return
        except Exception:
            return
        from forge.ui.themes import get_colors
        bg = get_colors().get("bg_dark", "#070010")
        palette = self._config.get("palette", [])
        thickness = self._config.get("edge_thickness", 3)
        crackle = self._config.get("edge_crackle_rate", 0.10)
        self._edge_glow = WindowEdgeGlow(
            self._edge_window, palette, bg, thickness, crackle)

    def _create_border_color(self):
        """Create (or recreate) the OS-level window border color effect."""
        if self._border_color:
            self._border_color.destroy()
            self._border_color = None
        if not self._border_color_window or not self._config:
            return
        try:
            if not self._border_color_window.winfo_exists():
                return
        except Exception:
            return
        palette = self._config.get("palette", [])
        self._border_color = WindowBorderColor(
            self._border_color_window, palette)

    # ── Animation tick ──

    def _tick(self):
        if not self._running or not self._config:
            return
        # Auto-shutdown if our window was destroyed
        try:
            if not self._root.winfo_exists():
                self.shutdown()
                return
        except Exception:
            self.shutdown()
            return
        try:
            self._tick_inner()
        except Exception:
            log.debug("Effects tick error", exc_info=True)
        # Always reschedule while running (don't let exceptions kill the loop)
        if self._running and self._config:
            fps = self._config.get("glow_fps", 10)
            interval = max(33, int(1000 / fps))
            self._after_id = self._root.after(interval, self._tick)

    def _tick_inner(self):
        now = time.monotonic()
        dt = now - self._last_tick
        self._last_tick = now
        self._phase += dt

        # Border glow
        if self._config.get("border_glow"):
            for glow in self._border_glows:
                # Skip hovered cards
                hover = self._hover_map.get(id(glow._card))
                if hover and hover.is_hovered:
                    continue
                glow.update(self._phase)

        # Header pulse
        if self._config.get("header_pulse"):
            for pulse in self._header_pulses:
                pulse.update(self._phase)

        # Particles
        if self._particle_field and self._config.get("particles"):
            self._particle_field.update(dt)

        # Edge glow (crackling window border)
        if self._edge_glow and self._config.get("edge_glow"):
            self._edge_glow.update(self._phase)

        # OS-level window border color
        if self._border_color:
            self._border_color.update(self._phase)

        # Widget glow (sliders / progress bars / scrollbars)
        if self._widget_glows and self._config.get("widget_glow"):
            for wg in self._widget_glows:
                wg.update(self._phase)
