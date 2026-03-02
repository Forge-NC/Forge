"""Forge Charts — PIL-based chart rendering for dashboard and terminal.

Renders theme-aware charts using PIL ImageDraw. No external charting
libraries required. All chart functions are pure: (data, colors, config)
-> PIL.Image. Charts are optional — callers must wrap in try/except.

Chart types:
  - Line chart:  time-series trends (tokens, latency, continuity)
  - Bar chart:   categorical comparisons (tool usage, threats)
  - Donut chart: proportional breakdown (cost, resource usage)
  - Sparkline:   compact inline mini-chart for dashboard cards

Terminal fallbacks:
  - ASCII sparkline using block characters
  - ASCII horizontal bar chart

Anti-aliasing: renders at 2x resolution, then downscales with LANCZOS.
"""

import hashlib
import logging
import math
from dataclasses import dataclass, field
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

# ── Data classes ──


@dataclass
class ChartDataPoint:
    """A single data point for bar/donut charts."""
    value: float
    label: str = ""
    color: str = ""    # hex override; empty = use theme cycle


@dataclass
class ChartSeries:
    """A named series of data points for line charts."""
    name: str
    points: list[float]
    color: str = ""    # hex override


@dataclass
class ChartConfig:
    """Shared configuration for all chart types."""
    width: int = 300
    height: int = 150
    padding: tuple = (30, 10, 20, 40)  # top, right, bottom, left
    show_grid: bool = True
    show_labels: bool = True
    show_legend: bool = False
    title: str = ""
    x_labels: list = field(default_factory=list)
    y_label: str = ""


# ── Accent color cycle ──

_ACCENT_CYCLE = [
    "#00d4ff",  # cyan
    "#00ff88",  # green
    "#ff66aa",  # magenta
    "#4488ff",  # blue
    "#ffaa00",  # yellow
    "#ff6644",  # orange
    "#aa66ff",  # purple
    "#44ffdd",  # teal
]


# ── Font cache ──

_FONT_CACHE: dict[int, ImageFont.FreeTypeFont] = {}


def _get_font(size: int = 11) -> ImageFont.FreeTypeFont:
    """Load a monospace font with fallback chain. Cached."""
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    for name in ["consola.ttf", "Consolas.ttf",
                  "DejaVuSansMono.ttf", "LiberationMono-Regular.ttf"]:
        try:
            font = ImageFont.truetype(name, size)
            _FONT_CACHE[size] = font
            return font
        except OSError:
            continue
    font = ImageFont.load_default()
    _FONT_CACHE[size] = font
    return font


def _hex_to_rgba(hex_color: str, alpha: int = 255) -> tuple:
    """Convert '#rrggbb' to (r, g, b, a)."""
    h = hex_color.lstrip("#")
    if len(h) < 6:
        h = h.ljust(6, "0")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (r, g, b, alpha)


# ── ChartRenderer ──


class ChartRenderer:
    """Pure-function chart renderer. Receives theme colors in constructor."""

    def __init__(self, theme_colors: dict):
        self._colors = theme_colors
        self._font = _get_font(11)
        self._font_sm = _get_font(9)
        self._cache: dict[str, Image.Image] = {}

    def _bg(self) -> str:
        return self._colors.get("card_bg", self._colors.get("bg", "#1a1a2e"))

    def _fg(self) -> str:
        return self._colors.get("text", self._colors.get("fg", "#c8d6e5"))

    def _grid(self) -> str:
        return self._colors.get("card_border", self._colors.get("border", "#2a2a4a"))

    def _accent(self, idx: int = 0) -> str:
        return _ACCENT_CYCLE[idx % len(_ACCENT_CYCLE)]

    # ── Line Chart ──

    def line_chart(self, series: list[ChartSeries],
                   config: ChartConfig = None) -> Image.Image:
        """Render a line chart with filled area under each line.

        Returns an RGBA PIL Image at config.width x config.height.
        """
        cfg = config or ChartConfig()
        w, h = cfg.width, cfg.height
        # 2x supersampling
        W, H = w * 2, h * 2
        pt, pr, pb, pl = (v * 2 for v in cfg.padding)

        img = Image.new("RGBA", (W, H), _hex_to_rgba(self._bg()))
        draw = ImageDraw.Draw(img)

        if not series or not any(s.points for s in series):
            return img.resize((w, h), Image.LANCZOS)

        # Compute Y range across all series
        all_vals = [v for s in series for v in s.points]
        y_min = min(all_vals)
        y_max = max(all_vals)
        if y_max == y_min:
            y_max = y_min + 1

        chart_w = W - pl - pr
        chart_h = H - pt - pb

        # Grid lines (4 horizontal)
        if cfg.show_grid:
            grid_rgba = _hex_to_rgba(self._grid(), 100)
            for i in range(5):
                y = pt + int(chart_h * i / 4)
                draw.line([(pl, y), (W - pr, y)], fill=grid_rgba, width=1)

        # Draw each series
        for si, s in enumerate(series):
            if len(s.points) < 2:
                continue
            color_hex = s.color or self._accent(si)
            line_rgba = _hex_to_rgba(color_hex)
            fill_rgba = _hex_to_rgba(color_hex, 40)

            n = len(s.points)
            coords = []
            for i, val in enumerate(s.points):
                x = pl + int(chart_w * i / max(1, n - 1))
                y_norm = (val - y_min) / (y_max - y_min)
                y = pt + int(chart_h * (1 - y_norm))
                coords.append((x, y))

            # Filled area
            poly = list(coords) + [(coords[-1][0], H - pb), (coords[0][0], H - pb)]
            draw.polygon(poly, fill=fill_rgba)

            # Line
            draw.line(coords, fill=line_rgba, width=3)

            # Endpoints
            draw.ellipse([coords[0][0] - 3, coords[0][1] - 3,
                         coords[0][0] + 3, coords[0][1] + 3], fill=line_rgba)
            draw.ellipse([coords[-1][0] - 3, coords[-1][1] - 3,
                         coords[-1][0] + 3, coords[-1][1] + 3], fill=line_rgba)

        # Y-axis labels
        if cfg.show_labels:
            text_rgba = _hex_to_rgba(self._fg(), 180)
            font2x = _get_font(18)
            for i in range(5):
                val = y_max - (y_max - y_min) * i / 4
                y = pt + int(chart_h * i / 4) - 9
                label = f"{val:.0f}" if val == int(val) else f"{val:.1f}"
                draw.text((4, y), label, fill=text_rgba, font=font2x)

        # Title
        if cfg.title:
            title_rgba = _hex_to_rgba(self._fg())
            font_title = _get_font(20)
            draw.text((pl, 4), cfg.title, fill=title_rgba, font=font_title)

        return img.resize((w, h), Image.LANCZOS)

    # ── Bar Chart ──

    def bar_chart(self, data: list[ChartDataPoint],
                  config: ChartConfig = None) -> Image.Image:
        """Render a vertical bar chart with value labels."""
        cfg = config or ChartConfig()
        w, h = cfg.width, cfg.height
        W, H = w * 2, h * 2
        pt, pr, pb, pl = (v * 2 for v in cfg.padding)

        img = Image.new("RGBA", (W, H), _hex_to_rgba(self._bg()))
        draw = ImageDraw.Draw(img)

        if not data:
            return img.resize((w, h), Image.LANCZOS)

        values = [d.value for d in data]
        v_max = max(values) if values else 1
        if v_max == 0:
            v_max = 1

        chart_w = W - pl - pr
        chart_h = H - pt - pb
        n = len(data)
        gap = max(4, chart_w // (n * 6))
        bar_w = max(8, (chart_w - gap * (n + 1)) // n)

        # Grid
        if cfg.show_grid:
            grid_rgba = _hex_to_rgba(self._grid(), 100)
            for i in range(5):
                y = pt + int(chart_h * i / 4)
                draw.line([(pl, y), (W - pr, y)], fill=grid_rgba, width=1)

        # Bars
        font2x = _get_font(16)
        text_rgba = _hex_to_rgba(self._fg(), 200)
        for i, dp in enumerate(data):
            color_hex = dp.color or self._accent(i)
            bar_rgba = _hex_to_rgba(color_hex)

            bar_h = int(chart_h * dp.value / v_max) if v_max else 0
            x0 = pl + gap + i * (bar_w + gap)
            y0 = pt + chart_h - bar_h
            x1 = x0 + bar_w
            y1 = pt + chart_h

            draw.rectangle([x0, y0, x1, y1], fill=bar_rgba)

            # Value label above bar
            val_str = f"{dp.value:.0f}" if dp.value == int(dp.value) else f"{dp.value:.1f}"
            bbox = draw.textbbox((0, 0), val_str, font=font2x)
            tw = bbox[2] - bbox[0]
            draw.text((x0 + (bar_w - tw) // 2, y0 - 22),
                      val_str, fill=text_rgba, font=font2x)

            # Category label below bar
            if cfg.show_labels and dp.label:
                label = dp.label[:6]
                bbox = draw.textbbox((0, 0), label, font=font2x)
                tw = bbox[2] - bbox[0]
                draw.text((x0 + (bar_w - tw) // 2, y1 + 4),
                          label, fill=text_rgba, font=font2x)

        # Title
        if cfg.title:
            font_title = _get_font(20)
            draw.text((pl, 4), cfg.title, fill=_hex_to_rgba(self._fg()),
                      font=font_title)

        return img.resize((w, h), Image.LANCZOS)

    # ── Donut Chart ──

    def donut_chart(self, data: list[ChartDataPoint],
                    config: ChartConfig = None) -> Image.Image:
        """Render a donut (ring) chart with center label."""
        cfg = config or ChartConfig(width=200, height=200)
        w, h = cfg.width, cfg.height
        W, H = w * 2, h * 2

        img = Image.new("RGBA", (W, H), _hex_to_rgba(self._bg()))
        draw = ImageDraw.Draw(img)

        if not data:
            return img.resize((w, h), Image.LANCZOS)

        total = sum(d.value for d in data)
        if total == 0:
            return img.resize((w, h), Image.LANCZOS)

        cx, cy = W // 2, H // 2
        r_outer = min(cx, cy) - 20
        r_inner = int(r_outer * 0.55)

        # Draw segments
        start_angle = -90
        for i, dp in enumerate(data):
            sweep = dp.value / total * 360
            color_hex = dp.color or self._accent(i)
            color_rgba = _hex_to_rgba(color_hex)

            bbox = [cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer]
            draw.pieslice(bbox, start_angle, start_angle + sweep, fill=color_rgba)
            start_angle += sweep

        # Punch out center
        bg_rgba = _hex_to_rgba(self._bg())
        draw.ellipse([cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner],
                     fill=bg_rgba)

        # Center text
        font_center = _get_font(28)
        center_text = f"{total:.0f}" if total == int(total) else f"{total:.1f}"
        bbox = draw.textbbox((0, 0), center_text, font=font_center)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text((cx - tw // 2, cy - th // 2), center_text,
                  fill=_hex_to_rgba(self._fg()), font=font_center)

        return img.resize((w, h), Image.LANCZOS)

    # ── Sparkline ──

    def sparkline(self, values: list[float],
                  width: int = 120, height: int = 24,
                  color: str = "") -> Optional[Image.Image]:
        """Render a compact sparkline (no axes, no labels).

        Returns None if insufficient data.
        """
        if not values or len(values) < 2:
            return None

        W, H = width * 2, height * 2
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        v_min = min(values)
        v_max = max(values)
        if v_max == v_min:
            v_max = v_min + 1

        n = len(values)
        line_color = color or self._accent(0)
        line_rgba = _hex_to_rgba(line_color)
        fill_rgba = _hex_to_rgba(line_color, 30)

        pad = 4
        coords = []
        for i, v in enumerate(values):
            x = pad + int((W - 2 * pad) * i / max(1, n - 1))
            y_norm = (v - v_min) / (v_max - v_min)
            y = pad + int((H - 2 * pad) * (1 - y_norm))
            coords.append((x, y))

        # Fill
        poly = list(coords) + [(coords[-1][0], H - pad), (coords[0][0], H - pad)]
        draw.polygon(poly, fill=fill_rgba)

        # Line
        draw.line(coords, fill=line_rgba, width=3)

        return img.resize((width, height), Image.LANCZOS)

    # ── ASCII Sparkline (terminal fallback) ──

    @staticmethod
    def ascii_sparkline(values: list[float], width: int = 20) -> str:
        """Render an ASCII sparkline using block characters.

        Maps values to 8 levels: ' \\u2581\\u2582\\u2583\\u2584\\u2585\\u2586\\u2587\\u2588'
        """
        if not values:
            return ""

        mn, mx = min(values), max(values)
        rng = mx - mn if mx != mn else 1.0
        blocks = " \u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"

        # Resample to fit width
        if len(values) > width:
            step = len(values) / width
            sampled = [values[int(i * step)] for i in range(width)]
        else:
            sampled = values

        return "".join(
            blocks[min(8, int((v - mn) / rng * 8))] for v in sampled
        )

    # ── ASCII Bar Chart (terminal fallback) ──

    @staticmethod
    def ascii_bar_chart(data: dict, width: int = 25) -> str:
        """Render a horizontal ASCII bar chart.

        Args:
            data: {label: value} dict
            width: max bar width in characters
        """
        if not data:
            return ""

        max_val = max(data.values()) if data.values() else 1
        if max_val == 0:
            max_val = 1

        max_label = max(len(str(k)) for k in data.keys()) if data else 0
        lines = []
        for label, val in data.items():
            bar_len = int(val / max_val * width)
            bar = "\u2588" * bar_len
            lines.append(f"  {str(label):<{max_label}} {bar} {val}")

        return "\n".join(lines)
