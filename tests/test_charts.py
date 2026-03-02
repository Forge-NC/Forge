"""Tests for the PIL-based chart rendering engine."""

import pytest
from PIL import Image

from forge.ui.charts import (
    ChartRenderer, ChartConfig, ChartDataPoint, ChartSeries,
)

# Minimal theme colors for testing
THEME = {
    "bg": "#1a1a2e",
    "fg": "#c8d6e5",
    "card_bg": "#1e1e3a",
    "card_border": "#2a2a4a",
    "text": "#c8d6e5",
    "accent": "#00d4ff",
}


@pytest.fixture
def renderer():
    return ChartRenderer(THEME)


# ── Line Chart ──

class TestLineChart:
    def test_returns_image(self, renderer):
        series = [ChartSeries("test", [1, 2, 3, 4, 5])]
        img = renderer.line_chart(series)
        assert isinstance(img, Image.Image)
        assert img.mode == "RGBA"

    def test_dimensions(self, renderer):
        cfg = ChartConfig(width=400, height=200)
        series = [ChartSeries("t", [10, 20, 30])]
        img = renderer.line_chart(series, cfg)
        assert img.size == (400, 200)

    def test_empty_series(self, renderer):
        img = renderer.line_chart([])
        assert isinstance(img, Image.Image)

    def test_single_point(self, renderer):
        series = [ChartSeries("t", [42])]
        img = renderer.line_chart(series)
        assert isinstance(img, Image.Image)

    def test_constant_values(self, renderer):
        series = [ChartSeries("t", [5, 5, 5, 5])]
        img = renderer.line_chart(series)
        assert isinstance(img, Image.Image)

    def test_multiple_series(self, renderer):
        s1 = ChartSeries("a", [1, 3, 2, 4])
        s2 = ChartSeries("b", [4, 2, 3, 1])
        img = renderer.line_chart([s1, s2])
        assert isinstance(img, Image.Image)


# ── Bar Chart ──

class TestBarChart:
    def test_returns_image(self, renderer):
        data = [ChartDataPoint(10, "A"), ChartDataPoint(20, "B")]
        img = renderer.bar_chart(data)
        assert isinstance(img, Image.Image)

    def test_dimensions(self, renderer):
        cfg = ChartConfig(width=350, height=180)
        data = [ChartDataPoint(5, "X")]
        img = renderer.bar_chart(data, cfg)
        assert img.size == (350, 180)

    def test_empty_data(self, renderer):
        img = renderer.bar_chart([])
        assert isinstance(img, Image.Image)

    def test_zero_values(self, renderer):
        data = [ChartDataPoint(0, "Z")]
        img = renderer.bar_chart(data)
        assert isinstance(img, Image.Image)


# ── Donut Chart ──

class TestDonutChart:
    def test_returns_image(self, renderer):
        data = [ChartDataPoint(30, "A"), ChartDataPoint(70, "B")]
        img = renderer.donut_chart(data)
        assert isinstance(img, Image.Image)

    def test_single_segment(self, renderer):
        data = [ChartDataPoint(100, "All")]
        img = renderer.donut_chart(data)
        assert isinstance(img, Image.Image)

    def test_empty_data(self, renderer):
        img = renderer.donut_chart([])
        assert isinstance(img, Image.Image)


# ── Sparkline ──

class TestSparkline:
    def test_returns_image(self, renderer):
        img = renderer.sparkline([1, 3, 2, 5, 4], width=100, height=20)
        assert isinstance(img, Image.Image)
        assert img.size == (100, 20)

    def test_insufficient_data(self, renderer):
        assert renderer.sparkline([]) is None
        assert renderer.sparkline([42]) is None

    def test_constant_values(self, renderer):
        img = renderer.sparkline([5, 5, 5, 5])
        assert isinstance(img, Image.Image)

    def test_custom_color(self, renderer):
        img = renderer.sparkline([1, 2, 3], color="#ff0000")
        assert isinstance(img, Image.Image)


# ── ASCII Sparkline ──

class TestAsciiSparkline:
    def test_basic(self):
        result = ChartRenderer.ascii_sparkline([0, 25, 50, 75, 100], width=5)
        assert len(result) == 5
        # First char should be space (min value)
        assert result[0] == " "
        # Last char should be full block (max value)
        assert result[-1] == "\u2588"

    def test_empty(self):
        assert ChartRenderer.ascii_sparkline([]) == ""

    def test_constant(self):
        result = ChartRenderer.ascii_sparkline([5, 5, 5], width=3)
        assert len(result) == 3

    def test_resampling(self):
        result = ChartRenderer.ascii_sparkline(list(range(100)), width=10)
        assert len(result) == 10


# ── ASCII Bar Chart ──

class TestAsciiBarChart:
    def test_basic(self):
        result = ChartRenderer.ascii_bar_chart({"A": 10, "B": 20}, width=20)
        assert "A" in result
        assert "B" in result
        assert "10" in result
        assert "20" in result

    def test_empty(self):
        assert ChartRenderer.ascii_bar_chart({}) == ""

    def test_zero_value(self):
        result = ChartRenderer.ascii_bar_chart({"X": 0, "Y": 5})
        assert "X" in result
