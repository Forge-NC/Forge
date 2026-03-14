"""Forge Model Manager — enterprise-grade Ollama model management dialog.

Dual-pane CTkToplevel: installed models (left) + live registry catalog (right).
Supports pull with real progress bars, delete with confirmation, set-as-primary/
router quick actions, category filtering, and search.

Data sources:
  - Local: localhost /api/tags (installed), /api/ps (loaded)
  - Registry: ollama.com/api/tags (available models)
  - Search: ollama.com/search?q=... (HTML parsed for results)
  - Pull: localhost /api/pull (streaming JSON)
  - Delete: localhost /api/delete
"""

import json
import logging
import re
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

try:
    import customtkinter as ctk
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from forge.config import ForgeConfig
from forge.hardware import detect_gpu

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

# ── Category auto-detection from model names ──

_CAT_PATTERNS = [
    ("Coding",    re.compile(r"code|coder|starcoder|deepcoder|codellama|devstral", re.I)),
    ("Embedding", re.compile(r"embed|nomic|minilm|mxbai|bge", re.I)),
    ("Vision",    re.compile(r"vision|vl\b|ocr|llava|bakllava", re.I)),
    ("Reasoning", re.compile(r"r1|qwq|thinking|reason", re.I)),
]

# Models with confirmed native Ollama tool-calling support.
# Used to show a "Tools" badge in the catalog UI.
_TOOL_CALLING_MODELS = {
    "qwen3", "qwen3.5", "qwen3-coder", "qwen3-coder-next",
    "devstral", "devstral-small-2",
    "ministral-3",
    "granite4",
    "nemotron-3-nano",
    "lfm2",
    "functiongemma",
    "glm-4.7-flash",
}

# Descriptions for well-known models
_MODEL_DESCS = {
    "llama3.1":           "Meta's strong general-purpose model",
    "llama3.2":           "Meta's compact, efficient model",
    "llama3.3":           "Meta's latest 70B powerhouse",
    "llama3":             "Meta's capable open LLM",
    "qwen2.5":            "Alibaba's pretrained model (NO tool calling)",
    "qwen2.5-coder":      "Alibaba's coding specialist (NO tool calling)",
    "qwen3":              "Latest Qwen — native tool calling, thinking mode",
    "qwen3.5":            "Newest Qwen generation — tools + thinking",
    "qwen3-coder":        "Qwen 3 coding agent — native tool calling",
    "qwen3-coder-next":   "Qwen 3 next-gen agentic coding — native tools",
    "deepseek-r1":        "DeepSeek reasoning model family",
    "deepseek-coder":     "DeepSeek code specialist",
    "deepseek-coder-v2":  "DeepSeek v2 coding model",
    "gemma2":             "Google's high-performing model",
    "gemma3":             "Google's most capable single-GPU model",
    "mistral":            "Mistral AI's fast 7B model",
    "phi3":               "Microsoft's efficient small model",
    "phi4":               "Microsoft's latest small model",
    "codellama":          "Meta's code-specific Llama variant",
    "starcoder2":         "BigCode project code model",
    "nomic-embed-text":   "Best embedding model for code search",
    "mxbai-embed-large":  "High-quality large embeddings",
    "all-minilm":         "Tiny fast sentence embeddings",
    "granite4":           "IBM's enterprise model — native tool calling",
    "devstral":           "Mistral's agentic coding model — native tools",
    "devstral-small-2":   "Mistral's compact agentic coder — native tools",
    "ministral-3":        "Mistral's small model — native tool calling",
    "nemotron-3-nano":    "NVIDIA 30B reasoning + tool calling",
    "lfm2":               "Liquid Foundation Model — tool calling",
    "qwen3-vl":           "Qwen 3 vision + tool calling",
    "llava":              "Multimodal vision + language",
    "yi-coder":           "01.AI's fast coding model",
    "stable-code":        "Stability AI code model",
    "dolphin-mixtral":    "Uncensored Mixtral finetune",
    "wizard-coder":       "WizardLM coding finetune",
}

# ── Curated model catalog ──
# Popular models the live registry often omits. Format matches Ollama API.
# (name, size_gb_approx, parameter_size, category_hint)
_CURATED_MODELS = [
    # Coding — models with native tool calling (recommended for Forge)
    ("qwen3-coder:30b-a3b", 19.0,  "30B MoE", "Coding"),  # 3B active, fast
    ("devstral-small-2:24b", 14.0,  "24B",   "Coding"),  # Mistral agentic coder
    ("devstral:24b",         14.0,  "24B",   "Coding"),
    # Coding — legacy (NO native tool calling)
    ("qwen2.5-coder:1.5b",   1.0,  "1.5B",  "Coding"),
    ("qwen2.5-coder:3b",     2.0,  "3B",    "Coding"),
    ("qwen2.5-coder:7b",     4.7,  "7B",    "Coding"),
    ("qwen2.5-coder:14b",    9.0,  "14B",   "Coding"),
    ("qwen2.5-coder:32b",   19.0,  "32B",   "Coding"),
    ("codellama:7b",          3.8,  "7B",    "Coding"),
    ("codellama:13b",         7.4,  "13B",   "Coding"),
    ("codellama:34b",        19.0,  "34B",   "Coding"),
    ("codellama:70b",        39.0,  "70B",   "Coding"),
    ("deepseek-coder:1.3b",  0.8,  "1.3B",  "Coding"),
    ("deepseek-coder:6.7b",  3.8,  "6.7B",  "Coding"),
    ("deepseek-coder:33b",  19.0,  "33B",   "Coding"),
    ("deepseek-coder-v2:16b", 8.9, "16B",   "Coding"),
    ("deepseek-coder-v2:236b", 133.0, "236B", "Coding"),
    ("starcoder2:3b",         1.7,  "3B",    "Coding"),
    ("starcoder2:7b",         4.0,  "7B",    "Coding"),
    ("starcoder2:15b",        9.0,  "15B",   "Coding"),
    ("yi-coder:1.5b",         0.9,  "1.5B",  "Coding"),
    ("yi-coder:9b",           5.0,  "9B",    "Coding"),
    ("stable-code:3b",        1.6,  "3B",    "Coding"),
    # General — models with native tool calling (recommended for Forge)
    ("qwen3:0.6b",            0.5,  "0.6B",  "General"),
    ("qwen3:1.7b",            1.2,  "1.7B",  "General"),
    ("qwen3:4b",              2.6,  "4B",    "General"),
    ("qwen3:8b",              5.2,  "8B",    "General"),
    ("qwen3:14b",             9.0,  "14B",   "General"),
    ("qwen3:32b",            20.0,  "32B",   "General"),
    ("qwen3.5:0.8b",          0.6,  "0.8B",  "General"),
    ("qwen3.5:3b",            2.0,  "3B",    "General"),
    ("qwen3.5:7b",            4.7,  "7B",    "General"),
    ("qwen3.5:14b",           9.0,  "14B",   "General"),
    ("qwen3.5:32b",          20.0,  "32B",   "General"),
    ("ministral-3:3b",        2.0,  "3B",    "General"),
    ("ministral-3:8b",        5.0,  "8B",    "General"),
    ("ministral-3:14b",       9.0,  "14B",   "General"),
    ("granite4:2b",           1.5,  "2B",    "General"),
    ("granite4:8b",           4.9,  "8B",    "General"),
    ("nemotron-3-nano:30b",  19.0,  "30B",   "General"),
    # General — other
    ("llama3.2:1b",           0.7,  "1B",    "General"),
    ("llama3.2:3b",           2.0,  "3B",    "General"),
    ("llama3.1:8b",           4.7,  "8B",    "General"),
    ("llama3.1:70b",         40.0,  "70B",   "General"),
    ("llama3.3:70b",         43.0,  "70B",   "General"),
    ("gemma2:2b",             1.6,  "2B",    "General"),
    ("gemma2:9b",             5.4,  "9B",    "General"),
    ("gemma2:27b",           16.0,  "27B",   "General"),
    ("gemma3:1b",             0.8,  "1B",    "General"),
    ("mistral:7b",            4.1,  "7B",    "General"),
    ("phi3:3.8b",             2.2,  "3.8B",  "General"),
    ("phi3:14b",              7.9,  "14B",   "General"),
    ("phi4:14b",              8.4,  "14B",   "General"),
    # Reasoning
    ("deepseek-r1:1.5b",      1.1,  "1.5B",  "Reasoning"),
    ("deepseek-r1:7b",        4.7,  "7B",    "Reasoning"),
    ("deepseek-r1:8b",        4.9,  "8B",    "Reasoning"),
    ("deepseek-r1:14b",       9.0,  "14B",   "Reasoning"),
    ("deepseek-r1:32b",      20.0,  "32B",   "Reasoning"),
    ("deepseek-r1:70b",      43.0,  "70B",   "Reasoning"),
    ("deepseek-r1:671b",    404.0,  "671B",  "Reasoning"),
    ("qwq:32b",              20.0,  "32B",   "Reasoning"),
    # Vision
    ("llava:7b",              4.7,  "7B",    "Vision"),
    ("llava:13b",             8.0,  "13B",   "Vision"),
    ("llava:34b",            20.0,  "34B",   "Vision"),
    ("bakllava:7b",           4.7,  "7B",    "Vision"),
    ("qwen3-vl:3b",           2.4,  "3B",    "Vision"),
    ("qwen3-vl:8b",           5.5,  "8B",    "Vision"),
    # Embedding
    ("nomic-embed-text",      0.3,  "137M",  "Embedding"),
    ("mxbai-embed-large",     0.7,  "335M",  "Embedding"),
    ("all-minilm",            0.05, "23M",   "Embedding"),
    ("snowflake-arctic-embed:335m", 0.7, "335M", "Embedding"),
]

# Search result HTML parser
_RE_SEARCH_MODEL = re.compile(
    r'href="/library/([^"]+)"[^>]*>.*?'
    r'(?:class="[^"]*truncate[^"]*"[^>]*>([^<]*)</)',
    re.DOTALL,
)
_RE_SEARCH_ITEM = re.compile(
    r'<span[^>]*x-test-search-response-title[^>]*>([^<]+)</span>',
)


def _human_size(size_bytes: int) -> str:
    """Convert bytes to human-readable string."""
    if size_bytes >= 1_000_000_000:
        return f"{size_bytes / 1_000_000_000:.1f} GB"
    if size_bytes >= 1_000_000:
        return f"{size_bytes / 1_000_000:.0f} MB"
    if size_bytes >= 1_000:
        return f"{size_bytes / 1_000:.0f} KB"
    return f"{size_bytes} B"


def _categorize(name: str) -> str:
    """Auto-detect category from model name."""
    for cat, pattern in _CAT_PATTERNS:
        if pattern.search(name):
            return cat
    return "General"


def _get_desc(name: str) -> str:
    """Get description for a model, checking base name variants."""
    if name in _MODEL_DESCS:
        return _MODEL_DESCS[name]
    base = name.split(":")[0]
    if base in _MODEL_DESCS:
        return _MODEL_DESCS[base]
    return ""


def _http_get(url: str, timeout: int = 8) -> Optional[bytes]:
    """GET request, returns raw bytes or None."""
    try:
        req = urllib.request.Request(url, method="GET",
                                     headers={"User-Agent": "Forge/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


def _http_json(url: str, timeout: int = 8) -> dict:
    """GET request, returns parsed JSON or empty dict."""
    raw = _http_get(url, timeout)
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            pass
    return {}


def _estimate_vram_gb(size_bytes: int = 0, param_str: str = "") -> float:
    """Estimate VRAM needed from download size or parameter count.

    For GGUF models, download size closely matches VRAM needed for weights.
    Falls back to parameter count * 0.6 GB (Q4_K_M approximation).
    """
    if size_bytes > 0:
        return size_bytes / 1_000_000_000
    if param_str:
        m = re.match(r"([\d.]+)\s*[Bb]", param_str)
        if m:
            return float(m.group(1)) * 0.6
    return 0.0


def _classify_fit(vram_needed: float, vram_available: float) -> str:
    """Classify how well a model fits the user's GPU.

    Returns: "good", "ok", "tight", "too_large", or "unknown".
    """
    if vram_available <= 0 or vram_needed <= 0:
        return "unknown"
    ratio = vram_needed / vram_available
    if ratio <= 0.55:
        return "good"       # Plenty of room for context + KV cache
    elif ratio <= 0.80:
        return "ok"          # Fits, context may be somewhat limited
    elif ratio <= 1.0:
        return "tight"       # Very tight — reduced context, possible swapping
    else:
        return "too_large"   # Won't fit — CPU offload, very slow


# Fit level → (border_color, badge_text, badge_fg, name_color)
_FIT_STYLES = {
    "good":      (None,             " GOOD FIT ",  "#0a0e17", "#00ff88"),
    "ok":        (None,             " OK FIT ",    "#0a0e17", "#00d4ff"),
    "tight":     ("#ffaa00",        " HEAVY ",     "#0a0e17", "#ffaa00"),
    "too_large": ("#ff3344",        " TOO LARGE ", "#ffffff", "#ff3344"),
    "unknown":   (None,             None,          None,      "#e0e8f0"),
}

# ── Quantization VRAM estimation ──

# Bytes per parameter for common GGUF quantization levels
_QUANT_BPP: dict[str, float] = {
    "fp16":    2.00,
    "q8_0":    1.00,
    "q6_k":    0.82,
    "q5_k_m":  0.68,
    "q5_k_s":  0.65,
    "q5_0":    0.63,
    "q4_k_m":  0.55,
    "q4_k_s":  0.52,
    "q4_0":    0.50,
    "q3_k_m":  0.44,
    "q3_k_l":  0.47,
    "q3_k_s":  0.40,
    "q2_k":    0.34,
    "iq4_xs":  0.48,
    "iq3_xxs": 0.36,
    "iq2_xxs": 0.28,
}

# Human-readable quant descriptions
_QUANT_LABELS: dict[str, str] = {
    "fp16":    "FP16 \u2014 Full precision, best quality",
    "q8_0":    "Q8_0 \u2014 Near-lossless 8-bit",
    "q6_k":    "Q6_K \u2014 High quality 6-bit",
    "q5_k_m":  "Q5_K_M \u2014 Balanced quality/size",
    "q5_k_s":  "Q5_K_S \u2014 Balanced (small variant)",
    "q5_0":    "Q5_0 \u2014 Standard 5-bit",
    "q4_k_m":  "Q4_K_M \u2014 Good quality, popular default",
    "q4_k_s":  "Q4_K_S \u2014 Good quality (small variant)",
    "q4_0":    "Q4_0 \u2014 Basic 4-bit",
    "q3_k_m":  "Q3_K_M \u2014 Lower quality, saves VRAM",
    "q3_k_l":  "Q3_K_L \u2014 Lower quality (large variant)",
    "q3_k_s":  "Q3_K_S \u2014 Lower quality (small variant)",
    "q2_k":    "Q2_K \u2014 Minimum viable quality",
    "iq4_xs":  "IQ4_XS \u2014 Importance quant 4-bit",
    "iq3_xxs": "IQ3_XXS \u2014 Importance quant 3-bit",
    "iq2_xxs": "IQ2_XXS \u2014 Importance quant 2-bit",
}

# Standard quant variants most Ollama models offer
_COMMON_QUANTS = ["q2_K", "q3_K_M", "q4_K_M", "q5_K_M", "q6_K", "q8_0", "fp16"]


def _extract_params_b(s: str) -> float:
    """Extract parameter count in billions. '14B' -> 14.0, '137M' -> 0.137."""
    m = re.match(r"([\d.]+)\s*[Bb]", s)
    if m:
        return float(m.group(1))
    m = re.match(r"([\d.]+)\s*[Mm]", s)
    if m:
        return float(m.group(1)) / 1000
    return 0.0


def _estimate_quant_vram(params_b: float, quant: str) -> float:
    """Estimate VRAM (GB) for a model with given params and quantization."""
    if params_b <= 0:
        return 0.0
    key = quant.lower().strip().replace("-", "_")
    bpp = _QUANT_BPP.get(key, 0.55)
    return params_b * bpp + 0.5  # +0.5 GB overhead for KV cache


def _quant_from_tag(tag: str, param_prefix: str) -> str:
    """Extract quantization key from an Ollama tag.

    '14b' with prefix '14b' -> 'q4_k_m' (default)
    '14b-q8_0' with prefix '14b' -> 'q8_0'
    'latest' with prefix '' -> 'q4_k_m'
    """
    if param_prefix and tag == param_prefix:
        return "q4_k_m"

    if param_prefix and tag.startswith(param_prefix + "-"):
        suffix = tag[len(param_prefix) + 1:]
    elif not param_prefix:
        suffix = tag
    else:
        return "q4_k_m"

    key = suffix.lower().replace("-", "_")
    if key in _QUANT_BPP:
        return key
    return "q4_k_m"


class ModelManagerDialog:
    """Enterprise-grade model management dialog."""

    def __init__(self, parent, config: ForgeConfig):
        if not HAS_CTK:
            return

        self._config = config
        self._parent = parent
        self._base_url = str(
            config.get("ollama_url", "http://localhost:11434")).rstrip("/")

        # State
        self._installed: list[dict] = []
        self._running: set = set()
        self._registry: list[dict] = []
        self._pulling = False
        self._pull_queue: list = []
        self._search_after_id = None
        self._vram_gb: float = 0.0  # Detected GPU VRAM (0 = CPU only)

        self._effects = None
        self._build_window()
        self._init_effects()
        self._detect_vram()
        self._refresh_all()

    # ──────────────────────────────────────────────────────────
    # Window layout
    # ──────────────────────────────────────────────────────────

    def _build_window(self):
        from forge.ui.window_geo import WindowGeo as _WG
        self._win = ctk.CTkToplevel(self._parent)
        self._win.title("Forge — Model Manager")
        self._win.minsize(720, 520)
        self._win.configure(fg_color=COLORS["bg_dark"])
        _WG.restore("model_manager", self._win, "820x660")
        _WG.track("model_manager", self._win)
        self._win.after(50, self._win.lift)
        self._win.after(50, self._win.focus_force)
        self._win.protocol("WM_DELETE_WINDOW", self._on_close)

        # Register for live theme hot-swap
        self._theme_cb = lambda cm: self._win.after(
            0, self._apply_theme, cm)
        add_theme_listener(self._theme_cb)

        try:
            ico = Path(__file__).parent / "assets" / "forge.ico"
            if ico.exists():
                self._win.iconbitmap(str(ico))
        except Exception:
            pass

        # ── Top bar ──
        top = ctk.CTkFrame(self._win, fg_color=COLORS["bg_panel"],
                           height=46, corner_radius=0,
                           border_width=1, border_color=COLORS["border"])
        top.pack(fill="x")
        top.pack_propagate(False)
        self._top_bar = top

        ctk.CTkLabel(top, text="  Model Manager",
                     font=ctk.CTkFont(*FONT_TITLE),
                     text_color=COLORS["cyan"]).pack(side="left", padx=10)

        # Right side: status + count
        right_frame = ctk.CTkFrame(top, fg_color="transparent")
        right_frame.pack(side="right", padx=10)

        self._lbl_count = ctk.CTkLabel(
            right_frame, text="",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["gray"])
        self._lbl_count.pack(side="right", padx=(8, 0))

        self._lbl_status_dot = ctk.CTkLabel(
            right_frame, text="*",
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            text_color=COLORS["gray"])
        self._lbl_status_dot.pack(side="right")

        self._lbl_online = ctk.CTkLabel(
            right_frame, text="checking...",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["gray"])
        self._lbl_online.pack(side="right", padx=(0, 4))

        # VRAM chip (filled by _detect_vram)
        self._lbl_vram = ctk.CTkLabel(
            right_frame, text="",
            font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["gray"])
        self._lbl_vram.pack(side="right", padx=(0, 12))

        self._separator = ctk.CTkFrame(self._win, fg_color=COLORS["border"],
                                       height=1, corner_radius=0)
        self._separator.pack(fill="x")

        # ── Body ──
        body = ctk.CTkFrame(self._win, fg_color=COLORS["bg_dark"],
                            corner_radius=0)
        body.pack(fill="both", expand=True)

        self._build_installed_pane(body)
        self._build_catalog_pane(body)

        # ── Bottom status bar ──
        bar = ctk.CTkFrame(self._win, fg_color=COLORS["bg_panel"],
                           height=36, corner_radius=0,
                           border_width=1, border_color=COLORS["border"])
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self._bottom_bar = bar

        self._pull_bar = ctk.CTkProgressBar(
            bar, width=200, height=10,
            fg_color=COLORS["bg_card"],
            progress_color=COLORS["cyan_dim"],
            corner_radius=3)
        self._pull_bar.set(0)
        # Hidden initially — shown during pulls
        self._pull_bar_visible = False

        self._lbl_pull = ctk.CTkLabel(
            bar, text="",
            font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["gray"])
        self._lbl_pull.pack(side="left", padx=10)

        self._lbl_refresh = ctk.CTkLabel(
            bar, text="",
            font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["text_dim"])
        self._lbl_refresh.pack(side="right", padx=10)

    def _init_effects(self):
        """Set up visual effects for the model manager window."""
        try:
            from forge.ui.effects import EffectsEngine, WidgetGlow
            fx_enabled = self._config.get("effects_enabled", True)
            self._effects = EffectsEngine(self._win, enabled=fx_enabled)
            # Register top bar with separator (border glow + hover + pulse)
            self._effects.register_card(self._top_bar, self._separator)
            # Register left pane (border glow + hover)
            self._effects.register_card(self._left_pane)
            # Register bottom bar (border glow + hover)
            self._effects.register_card(self._bottom_bar)
            # Crackling edge glow on window
            self._effects.register_window_edge_glow(self._win)
            # OS-level window border color animation
            self._effects.register_window_border_color(self._win)
            # Pull progress bar glow
            self._effects.register_widget(
                self._pull_bar, WidgetGlow.PROGRESS)
            self._effects.start()
        except Exception:
            pass

    # ── Left pane: Installed ──

    def _build_installed_pane(self, parent):
        left = ctk.CTkFrame(parent, fg_color=COLORS["bg_panel"], width=360,
                            corner_radius=0, border_color=COLORS["border"],
                            border_width=1)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self._left_pane = left

        hdr = ctk.CTkFrame(left, fg_color="transparent")
        hdr.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkLabel(hdr, text="  INSTALLED",
                     font=ctk.CTkFont(*FONT_MONO_SM),
                     text_color=COLORS["gray"]).pack(side="left")

        ctk.CTkButton(hdr, text="Refresh", width=70, height=24,
                      fg_color=COLORS["bg_card"],
                      hover_color=COLORS["cyan_dim"],
                      text_color=COLORS["white"],
                      font=ctk.CTkFont(*FONT_MONO_XS),
                      command=self._refresh_all).pack(side="right")

        self._installed_scroll = ctk.CTkScrollableFrame(
            left, fg_color=COLORS["bg_panel"],
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["cyan_dim"])
        self._installed_scroll.pack(fill="both", expand=True, padx=4, pady=4)

    # ── Right pane: Available (registry + search) ──

    def _build_catalog_pane(self, parent):
        right = ctk.CTkFrame(parent, fg_color=COLORS["bg_dark"],
                             corner_radius=0)
        right.pack(side="right", fill="both", expand=True)

        # Header with search + category filter
        hdr = ctk.CTkFrame(right, fg_color="transparent")
        hdr.pack(fill="x", padx=8, pady=(8, 2))

        ctk.CTkLabel(hdr, text="  AVAILABLE",
                     font=ctk.CTkFont(*FONT_MONO_SM),
                     text_color=COLORS["gray"]).pack(side="left")

        self._search_entry = ctk.CTkEntry(
            hdr, width=140, height=26,
            placeholder_text="Search models...",
            font=ctk.CTkFont(*FONT_MONO_XS),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["white"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=4)
        self._search_entry.pack(side="right", padx=(4, 0))
        self._search_entry.bind("<KeyRelease>", self._on_search_key)

        # Category filter
        cat_row = ctk.CTkFrame(right, fg_color="transparent")
        cat_row.pack(fill="x", padx=8, pady=(2, 4))

        self._cat_var = ctk.StringVar(value="All")
        self._cat_seg = ctk.CTkSegmentedButton(
            cat_row,
            values=["All", "Coding", "General", "Reasoning",
                    "Embedding", "Vision"],
            variable=self._cat_var,
            font=ctk.CTkFont(*FONT_MONO_XS),
            fg_color=COLORS["bg_card"],
            selected_color=COLORS["cyan_dim"],
            selected_hover_color=COLORS["cyan"],
            unselected_color=COLORS["bg_panel"],
            unselected_hover_color=COLORS["bg_card"],
            text_color=COLORS["white"],
            command=lambda v: self._render_catalog())
        self._cat_seg.pack(fill="x")

        # Scrollable catalog
        self._catalog_scroll = ctk.CTkScrollableFrame(
            right, fg_color=COLORS["bg_dark"],
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["cyan_dim"])
        self._catalog_scroll.pack(fill="both", expand=True, padx=4, pady=4)

    # ──────────────────────────────────────────────────────────
    # Data loading (background threads)
    # ──────────────────────────────────────────────────────────

    def _detect_vram(self):
        """Detect GPU VRAM in background thread."""
        def _bg():
            gpu = detect_gpu()
            if gpu:
                total = round(gpu["vram_total_mb"] / 1024, 1)
                free = round(gpu["vram_free_mb"] / 1024, 1)
                self._win.after(0, lambda: self._apply_vram(
                    total, free, gpu.get("name", "")))
            else:
                self._win.after(0, lambda: self._apply_vram(0, 0, ""))

        threading.Thread(target=_bg, daemon=True,
                         name="ModelMgrVRAM").start()

    def _apply_vram(self, total: float, free: float, gpu_name: str):
        """Apply detected VRAM to state and UI.

        Always use total VRAM for fit calculations — Ollama unloads the
        current model before loading a new one, so the full capacity is
        available for any model the user picks.
        """
        self._vram_gb = total
        if total > 0:
            short_name = gpu_name.replace("NVIDIA GeForce ", "")
            in_use = round(total - free, 1)
            suffix = f"  ({in_use:.0f}GB in use)" if in_use >= 1.0 else ""
            self._lbl_vram.configure(
                text=f"{short_name}  {total:.0f}GB{suffix}",
                text_color=COLORS["cyan"])
        else:
            self._lbl_vram.configure(
                text="CPU Only",
                text_color=COLORS["yellow"])
        # Re-render with fit colors now that we know VRAM
        if self._installed or self._registry:
            self._render_installed()
            self._render_catalog()

    @staticmethod
    def _merge_curated(registry: list[dict]) -> list[dict]:
        """Merge curated popular models with live registry data.

        Registry models take priority (they have real sizes). Curated
        models fill in the gaps — popular models the feed omits.
        """
        seen = {m.get("name", "").split(":")[0] + ":" +
                (m.get("name", "").split(":")[1] if ":" in m.get("name", "")
                 else "latest")
                for m in registry}
        # Also track base names so we don't dupe "codellama" if registry
        # already has "codellama:70b"
        seen_bases = {m.get("name", "").split(":")[0] for m in registry}

        merged = list(registry)
        for name, size_gb, param_str, cat_hint in _CURATED_MODELS:
            base = name.split(":")[0]
            # Add if this exact variant isn't already in registry
            if name not in seen:
                merged.append({
                    "name": name,
                    "size": int(size_gb * 1_000_000_000),
                    "details": {"parameter_size": param_str},
                    "_curated": True,
                    "_cat_hint": cat_hint,
                })
                seen.add(name)
        return merged

    def _refresh_all(self):
        """Fetch installed + registry models in background."""
        def _bg():
            # Local models
            local_data = _http_json(f"{self._base_url}/api/tags")
            ps_data = _http_json(f"{self._base_url}/api/ps")
            online = bool(local_data)

            installed = local_data.get("models", [])
            running = {m.get("name", "") for m in ps_data.get("models", [])}

            # Registry models (from ollama.com)
            registry_data = _http_json("https://ollama.com/api/tags")
            registry = registry_data.get("models", [])

            self._win.after(0, lambda: self._apply_data(
                installed, running, registry, online))

        threading.Thread(target=_bg, daemon=True,
                         name="ModelMgrRefresh").start()

    def _apply_data(self, installed, running, registry, online):
        """Apply fetched data to UI (main thread)."""
        self._installed = installed
        self._running = running
        self._registry = self._merge_curated(registry)

        # Status indicators
        if online:
            self._lbl_status_dot.configure(text_color=COLORS["green"])
            self._lbl_online.configure(text="Online",
                                       text_color=COLORS["green"])
        else:
            self._lbl_status_dot.configure(text_color=COLORS["red"])
            self._lbl_online.configure(text="Offline",
                                       text_color=COLORS["red"])

        self._lbl_count.configure(text=f"{len(installed)} installed")
        self._lbl_refresh.configure(
            text=f"Last refresh: {time.strftime('%H:%M:%S')}")

        self._render_installed()
        self._render_catalog()

    # ──────────────────────────────────────────────────────────
    # Installed pane rendering
    # ──────────────────────────────────────────────────────────

    def _render_installed(self):
        """Rebuild the installed models list."""
        for w in self._installed_scroll.winfo_children():
            w.destroy()

        if not self._installed:
            ctk.CTkLabel(
                self._installed_scroll,
                text="No models installed.\n\nBrowse available models\non the right and click Pull.",
                font=ctk.CTkFont(*FONT_MONO_SM),
                text_color=COLORS["text_dim"],
                justify="center").pack(pady=40)
            return

        current_primary = str(self._config.get("default_model", ""))
        current_router = str(self._config.get("small_model", ""))

        _FIT_ORDER = {"good": 0, "ok": 1, "tight": 2,
                      "unknown": 3, "too_large": 4}

        def _inst_sort(m):
            sz = m.get("size", 0)
            ps = m.get("details", {}).get("parameter_size", "")
            est = _estimate_vram_gb(sz, ps)
            fit = _classify_fit(est, self._vram_gb)
            return (_FIT_ORDER.get(fit, 3), est)

        for model in sorted(self._installed, key=_inst_sort):
            self._build_installed_card(model, current_primary, current_router)

    def _build_installed_card(self, model, primary, router):
        name = model.get("name", "?")
        size_bytes = model.get("size", 0)
        details = model.get("details", {})
        family = details.get("family", "")
        params = details.get("parameter_size", "")
        quant = details.get("quantization_level", "")
        loaded = name in self._running

        # VRAM fit classification
        est_vram = _estimate_vram_gb(size_bytes, params)
        fit = _classify_fit(est_vram, self._vram_gb)
        style = _FIT_STYLES.get(fit, _FIT_STYLES["unknown"])
        _, _, _, name_color = style

        # Determine border highlight (role takes priority over fit)
        border_color = COLORS["border"]
        if name == primary:
            border_color = COLORS["cyan"]
        elif name == router:
            border_color = COLORS["green"]
        elif fit == "too_large":
            border_color = COLORS["red"]
        elif fit == "tight":
            border_color = COLORS["yellow"]

        card = ctk.CTkFrame(self._installed_scroll, fg_color=COLORS["bg_card"],
                            corner_radius=6, border_color=border_color,
                            border_width=1)
        card.pack(fill="x", padx=2, pady=2)

        # Top row: name + badges
        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=8, pady=(6, 0))

        ctk.CTkLabel(top_row, text=name,
                     font=ctk.CTkFont(*FONT_MONO_BOLD),
                     text_color=name_color,
                     anchor="w").pack(side="left")

        if loaded:
            ctk.CTkLabel(top_row, text=" LOADED ",
                         font=ctk.CTkFont(*FONT_MONO_XS),
                         text_color=COLORS["bg_dark"],
                         fg_color=COLORS["green"],
                         corner_radius=3).pack(side="right", padx=2)

        if name == primary:
            ctk.CTkLabel(top_row, text=" PRIMARY ",
                         font=ctk.CTkFont(*FONT_MONO_XS),
                         text_color=COLORS["bg_dark"],
                         fg_color=COLORS["cyan"],
                         corner_radius=3).pack(side="right", padx=2)
        elif name == router:
            ctk.CTkLabel(top_row, text=" ROUTER ",
                         font=ctk.CTkFont(*FONT_MONO_XS),
                         text_color=COLORS["bg_dark"],
                         fg_color=COLORS["green"],
                         corner_radius=3).pack(side="right", padx=2)

        # Fit badge for installed models that are problematic
        if fit == "too_large":
            ctk.CTkLabel(top_row, text=" TOO LARGE ",
                         font=ctk.CTkFont(*FONT_MONO_XS),
                         text_color="#ffffff",
                         fg_color=COLORS["red"],
                         corner_radius=3).pack(side="right", padx=2)
        elif fit == "tight":
            ctk.CTkLabel(top_row, text=" HEAVY ",
                         font=ctk.CTkFont(*FONT_MONO_XS),
                         text_color=COLORS["bg_dark"],
                         fg_color=COLORS["yellow"],
                         corner_radius=3).pack(side="right", padx=2)

        # Info row with VRAM estimate
        parts = []
        if size_bytes:
            parts.append(_human_size(size_bytes))
        if params:
            parts.append(params)
        if quant:
            parts.append(quant)
        if family:
            parts.append(family)
        if est_vram > 0 and self._vram_gb > 0:
            parts.append(f"~{est_vram:.1f}/{self._vram_gb:.0f}GB")
        info_text = "  |  ".join(parts) if parts else "No details"

        ctk.CTkLabel(card, text=f"  {info_text}",
                     font=ctk.CTkFont(*FONT_MONO_XS),
                     text_color=COLORS["gray"],
                     anchor="w").pack(fill="x", padx=8, pady=(1, 2))

        # Action buttons
        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(fill="x", padx=6, pady=(0, 6))

        # Embedding models can't be used as primary or router chat models
        is_embed = _categorize(name) == "Embedding"

        if not is_embed and name != primary:
            ctk.CTkButton(
                btns, text="Set Primary", width=90, height=24,
                fg_color=COLORS["bg_panel"],
                hover_color=COLORS["cyan_dim"],
                text_color=COLORS["white"],
                font=ctk.CTkFont(*FONT_MONO_XS),
                command=lambda n=name: self._set_primary(n)
            ).pack(side="left", padx=2)

        if not is_embed and name != router:
            ctk.CTkButton(
                btns, text="Set Router", width=80, height=24,
                fg_color=COLORS["bg_panel"],
                hover_color=COLORS["cyan_dim"],
                text_color=COLORS["white"],
                font=ctk.CTkFont(*FONT_MONO_XS),
                command=lambda n=name: self._set_router(n)
            ).pack(side="left", padx=2)

        ctk.CTkButton(
            btns, text="Delete", width=60, height=24,
            fg_color=COLORS["bg_panel"],
            hover_color=COLORS["red"],
            text_color=COLORS["gray"],
            font=ctk.CTkFont(*FONT_MONO_XS),
            command=lambda n=name: self._confirm_delete(n)
        ).pack(side="right", padx=2)

    # ──────────────────────────────────────────────────────────
    # Catalog pane rendering
    # ──────────────────────────────────────────────────────────

    def _render_catalog(self):
        """Rebuild the catalog from registry data."""
        for w in self._catalog_scroll.winfo_children():
            w.destroy()

        installed_names = {m.get("name", "") for m in self._installed}
        installed_bases = {m.get("name", "").split(":")[0]
                          for m in self._installed}
        cat_filter = self._cat_var.get()
        search_q = self._search_entry.get().strip().lower()

        if not self._registry:
            ctk.CTkLabel(
                self._catalog_scroll,
                text="Loading models from Ollama registry...\n\n"
                     "If this persists, check your\ninternet connection.",
                font=ctk.CTkFont(*FONT_MONO_SM),
                text_color=COLORS["text_dim"],
                justify="center").pack(pady=40)
            return

        # Fit tier sort order: good fits first, too-large last
        _FIT_ORDER = {"good": 0, "ok": 1, "tight": 2,
                      "unknown": 3, "too_large": 4}

        def _sort_key(model):
            """Sort by fit tier, then by estimated VRAM ascending."""
            size_bytes = model.get("size", 0)
            params = model.get("details", {}).get("parameter_size", "")
            est = _estimate_vram_gb(size_bytes, params)
            fit = _classify_fit(est, self._vram_gb)
            return (_FIT_ORDER.get(fit, 3), est)

        # Group by category
        by_cat: dict[str, list] = {}
        for model in self._registry:
            name = model.get("name", "")
            if not name:
                continue

            # Use category hint from curated data, fall back to regex
            cat = model.get("_cat_hint") or _categorize(name)

            # Apply filters
            if cat_filter != "All" and cat != cat_filter:
                continue
            if search_q and search_q not in name.lower():
                continue

            by_cat.setdefault(cat, []).append(model)

        if not by_cat:
            ctk.CTkLabel(
                self._catalog_scroll,
                text="No models match the current filter.",
                font=ctk.CTkFont(*FONT_MONO_SM),
                text_color=COLORS["text_dim"]).pack(pady=40)
            return

        # Render categories in order
        cat_order = ["Coding", "General", "Reasoning",
                     "Embedding", "Vision", "Other"]
        for cat in cat_order:
            models = by_cat.get(cat)
            if not models:
                continue

            # Category header
            ctk.CTkLabel(
                self._catalog_scroll,
                text=f"  {cat.upper()}",
                font=ctk.CTkFont(*FONT_MONO_SM),
                text_color=COLORS["cyan_dim"],
                anchor="w").pack(fill="x", padx=4, pady=(8, 2))

            for model in sorted(models, key=_sort_key):
                self._build_catalog_card(
                    model, installed_names, installed_bases)

    def _build_catalog_card(self, model, installed_names, installed_bases):
        name = model.get("name", "?")
        size_bytes = model.get("size", 0)
        details = model.get("details", {})
        params = details.get("parameter_size", "")
        quant = details.get("quantization_level", "")
        desc = _get_desc(name)
        cat = model.get("_cat_hint") or _categorize(name)

        # Exact name match, or base-name match only for untagged models
        # (e.g. "nomic-embed-text" matches "nomic-embed-text:latest").
        # Tagged models like "qwen3:4b" must NOT match "qwen3:14b".
        is_installed = (name in installed_names or
                        (":" not in name and
                         name.split(":")[0] in installed_bases))

        # ── VRAM fit classification ──
        est_vram = _estimate_vram_gb(size_bytes, params)
        fit = _classify_fit(est_vram, self._vram_gb)
        style = _FIT_STYLES.get(fit, _FIT_STYLES["unknown"])
        border_override, badge_text, badge_fg, name_color = style

        border_color = border_override or COLORS["border"]

        card = ctk.CTkFrame(self._catalog_scroll,
                            fg_color=COLORS["bg_card"],
                            corner_radius=6,
                            border_color=border_color,
                            border_width=1)
        card.pack(fill="x", padx=2, pady=2)

        # Top row: name + fit badge + category pill
        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=8, pady=(6, 0))

        ctk.CTkLabel(top_row, text=name,
                     font=ctk.CTkFont(*FONT_MONO_BOLD),
                     text_color=name_color,
                     anchor="w").pack(side="left")

        # Category color pill
        cat_colors = {
            "Coding": COLORS["cyan_dim"],
            "General": COLORS["gray"],
            "Embedding": COLORS["green"],
            "Reasoning": COLORS["yellow"],
            "Vision": "#cc44ff",
        }
        ctk.CTkLabel(top_row, text=f" {cat} ",
                     font=ctk.CTkFont(*FONT_MONO_XS),
                     text_color=COLORS["bg_dark"],
                     fg_color=cat_colors.get(cat, COLORS["gray"]),
                     corner_radius=3).pack(side="right")

        # Tool-calling badge — show for models with native tool support
        base_name = name.split(":")[0]
        if base_name in _TOOL_CALLING_MODELS:
            ctk.CTkLabel(top_row, text=" Tools ",
                         font=ctk.CTkFont(*FONT_MONO_XS),
                         text_color=COLORS["bg_dark"],
                         fg_color=COLORS["green"],
                         corner_radius=3).pack(side="right", padx=(0, 4))

        # Fit badge (only for tight/too_large — green/cyan shown via name color)
        if badge_text and fit in ("tight", "too_large"):
            badge_bg = COLORS["yellow"] if fit == "tight" else COLORS["red"]
            ctk.CTkLabel(top_row, text=badge_text,
                         font=ctk.CTkFont(*FONT_MONO_XS),
                         text_color=badge_fg,
                         fg_color=badge_bg,
                         corner_radius=3).pack(side="right", padx=(0, 4))

        # Description (if we have one)
        if desc:
            ctk.CTkLabel(card, text=f"  {desc}",
                         font=ctk.CTkFont(*FONT_MONO_XS),
                         text_color=COLORS["text_dim"],
                         anchor="w").pack(fill="x", padx=8, pady=(0, 1))

        # Info row with VRAM estimate
        parts = []
        if size_bytes:
            parts.append(_human_size(size_bytes))
        if params:
            parts.append(params)
        if quant:
            parts.append(quant)
        # VRAM estimate
        if est_vram > 0 and self._vram_gb > 0:
            vram_str = f"~{est_vram:.1f}GB VRAM"
            parts.append(vram_str)
        if parts:
            ctk.CTkLabel(card, text=f"  {'  |  '.join(parts)}",
                         font=ctk.CTkFont(*FONT_MONO_XS),
                         text_color=COLORS["gray"],
                         anchor="w").pack(fill="x", padx=8, pady=(0, 2))

        # Action: Pull or Installed
        action_row = ctk.CTkFrame(card, fg_color="transparent")
        action_row.pack(fill="x", padx=8, pady=(0, 6))

        if is_installed:
            ctk.CTkLabel(action_row, text="Installed",
                         font=ctk.CTkFont(*FONT_MONO_XS),
                         text_color=COLORS["green"]).pack(side="left")
        elif fit == "too_large":
            # Still allow pull but with warning color
            ctk.CTkButton(
                action_row, text="Pull Anyway", width=90, height=24,
                fg_color=COLORS["bg_panel"],
                hover_color=COLORS["red"],
                text_color=COLORS["yellow"],
                font=ctk.CTkFont(*FONT_MONO_XS),
                command=lambda n=name, p=params: self._show_quant_picker(n, p)
            ).pack(side="left")
            if est_vram > 0:
                over = est_vram - self._vram_gb
                ctk.CTkLabel(
                    action_row,
                    text=f"  {over:.1f}GB over your VRAM",
                    font=ctk.CTkFont(*FONT_MONO_XS),
                    text_color=COLORS["red"]).pack(side="left")
        else:
            ctk.CTkButton(
                action_row, text="Pull", width=60, height=24,
                fg_color=COLORS["cyan_dim"],
                hover_color=COLORS["cyan"],
                text_color=COLORS["bg_dark"],
                font=ctk.CTkFont(*FONT_MONO_BOLD),
                command=lambda n=name, p=params: self._show_quant_picker(n, p)
            ).pack(side="left")

            if size_bytes:
                ctk.CTkLabel(
                    action_row,
                    text=f"  ~{_human_size(size_bytes)} download",
                    font=ctk.CTkFont(*FONT_MONO_XS),
                    text_color=COLORS["text_dim"]).pack(side="left")

    # ──────────────────────────────────────────────────────────
    # Search (debounced)
    # ──────────────────────────────────────────────────────────

    def _on_search_key(self, event=None):
        """Debounce search: wait 300ms after last keystroke."""
        if self._search_after_id:
            self._win.after_cancel(self._search_after_id)
        self._search_after_id = self._win.after(300, self._do_search)

    def _do_search(self):
        """Execute search — filter existing registry + optionally fetch."""
        query = self._search_entry.get().strip()
        if not query:
            self._render_catalog()
            return

        # First: filter existing registry data locally
        self._render_catalog()

        # Also search ollama.com for models not in registry
        def _bg():
            try:
                url = f"https://ollama.com/search?q={urllib.request.quote(query)}"
                raw = _http_get(url, timeout=5)
                if not raw:
                    return
                html = raw.decode("utf-8", errors="replace")

                # Parse model names from search results
                found = set()
                for m in _RE_SEARCH_ITEM.finditer(html):
                    found.add(m.group(1).strip())

                # Also try simpler pattern
                for m in re.finditer(
                        r'/library/([a-z0-9._-]+)"', html):
                    found.add(m.group(1).strip())

                if not found:
                    return

                # Add any models not already in registry
                existing = {m.get("name", "").split(":")[0]
                            for m in self._registry}
                new_models = []
                for name in found:
                    if name not in existing:
                        new_models.append({
                            "name": name,
                            "size": 0,
                            "details": {},
                        })

                if new_models:
                    self._registry.extend(new_models)
                    self._win.after(0, self._render_catalog)
            except Exception:
                pass

        threading.Thread(target=_bg, daemon=True,
                         name="ModelMgrSearch").start()

    # ──────────────────────────────────────────────────────────
    # Actions: Set Primary / Router
    # ──────────────────────────────────────────────────────────

    def _set_primary(self, name: str):
        self._config.set("default_model", name)
        self._config.save()
        self._trigger_config_reload()
        self._flash(f"Primary model: {name}", COLORS["green"])
        self._render_installed()

    def _set_router(self, name: str):
        self._config.set("small_model", name)
        self._config.save()
        self._trigger_config_reload()
        self._flash(f"Router model: {name}", COLORS["green"])
        self._render_installed()

    def _trigger_config_reload(self):
        """Signal the engine to reload config."""
        try:
            trigger = Path.home() / ".forge" / "config_changed.txt"
            trigger.write_text("reload", encoding="utf-8")
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────
    # Actions: Delete with confirmation
    # ──────────────────────────────────────────────────────────

    def _confirm_delete(self, name: str):
        dlg = ctk.CTkToplevel(self._win)
        dlg.title("Confirm Delete")
        dlg.geometry("380x170")
        dlg.configure(fg_color=COLORS["bg_dark"])
        dlg.transient(self._win)
        dlg.grab_set()
        dlg.resizable(False, False)

        dlg.update_idletasks()
        x = self._win.winfo_x() + (self._win.winfo_width() - 380) // 2
        y = self._win.winfo_y() + (self._win.winfo_height() - 170) // 2
        dlg.geometry(f"+{max(0, x)}+{max(0, y)}")

        ctk.CTkLabel(dlg, text="Delete Model",
                     font=ctk.CTkFont(*FONT_TITLE),
                     text_color=COLORS["red"]).pack(pady=(18, 4))
        ctk.CTkLabel(dlg, text=f"Permanently delete {name}?",
                     font=ctk.CTkFont(*FONT_MONO),
                     text_color=COLORS["white"]).pack(pady=(0, 2))
        ctk.CTkLabel(dlg, text="This cannot be undone.",
                     font=ctk.CTkFont(*FONT_MONO_XS),
                     text_color=COLORS["gray"]).pack(pady=(0, 14))

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(fill="x", padx=24)

        ctk.CTkButton(btn_row, text="Cancel", width=130, height=34,
                      fg_color=COLORS["bg_card"],
                      hover_color=COLORS["bg_panel"],
                      text_color=COLORS["white"],
                      font=ctk.CTkFont(*FONT_MONO),
                      command=dlg.destroy).pack(side="left")

        ctk.CTkButton(btn_row, text="Delete", width=130, height=34,
                      fg_color=COLORS["red"],
                      hover_color="#ff5566",
                      text_color=COLORS["white"],
                      font=ctk.CTkFont(*FONT_MONO_BOLD),
                      command=lambda: self._do_delete(name, dlg)
                      ).pack(side="right")

    def _do_delete(self, name, dlg):
        dlg.destroy()
        self._flash(f"Deleting {name}...", COLORS["yellow"])

        def _bg():
            try:
                data = json.dumps({"name": name}).encode()
                req = urllib.request.Request(
                    f"{self._base_url}/api/delete", data=data,
                    headers={"Content-Type": "application/json"},
                    method="DELETE")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    if resp.status == 200:
                        self._win.after(0, lambda: self._flash(
                            f"{name} deleted", COLORS["green"]))
                        self._win.after(300, self._refresh_all)
                        return
            except Exception as e:
                self._win.after(0, lambda: self._flash(
                    f"Delete failed: {e}", COLORS["red"]))
                return
            self._win.after(0, lambda: self._flash(
                f"Delete failed", COLORS["red"]))

        threading.Thread(target=_bg, daemon=True,
                         name="ModelMgrDelete").start()

    # ──────────────────────────────────────────────────────────
    # Actions: Quantization variant picker
    # ──────────────────────────────────────────────────────────

    def _show_quant_picker(self, catalog_name: str, params_str: str):
        """Open a dialog showing available quantization variants."""
        if ":" in catalog_name:
            base, param_tag = catalog_name.split(":", 1)
        else:
            base, param_tag = catalog_name, ""

        params_b = _extract_params_b(params_str)

        # ── Build dialog ──
        dlg = ctk.CTkToplevel(self._win)
        dlg.title(f"Select Variant \u2014 {catalog_name}")
        dlg.geometry("560x520")
        dlg.configure(fg_color=COLORS["bg_dark"])
        dlg.transient(self._win)
        dlg.grab_set()
        dlg.resizable(True, True)
        dlg.minsize(440, 320)

        dlg.update_idletasks()
        x = self._win.winfo_x() + (self._win.winfo_width() - 560) // 2
        y = self._win.winfo_y() + (self._win.winfo_height() - 520) // 2
        dlg.geometry(f"+{max(0, x)}+{max(0, y)}")

        # Header
        hdr = ctk.CTkFrame(dlg, fg_color=COLORS["bg_panel"], height=50,
                           corner_radius=0, border_width=1,
                           border_color=COLORS["border"])
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        ctk.CTkLabel(hdr, text=f"  {catalog_name}",
                     font=ctk.CTkFont(*FONT_TITLE),
                     text_color=COLORS["cyan"]).pack(side="left", padx=10)

        if self._vram_gb > 0:
            ctk.CTkLabel(
                hdr, text=f"GPU: {self._vram_gb:.0f}GB VRAM  ",
                font=ctk.CTkFont(*FONT_MONO_XS),
                text_color=COLORS["green"]).pack(side="right", padx=10)

        ctk.CTkLabel(
            dlg, text="  Choose a quantization variant to pull:",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["text_dim"],
            anchor="w").pack(fill="x", padx=8, pady=(8, 4))

        # Scrollable variant list
        scroll = ctk.CTkScrollableFrame(
            dlg, fg_color=COLORS["bg_dark"],
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["cyan_dim"])
        scroll.pack(fill="both", expand=True, padx=8, pady=(0, 0))

        loading_lbl = ctk.CTkLabel(
            scroll, text="Fetching available variants...",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["text_dim"])
        loading_lbl.pack(pady=40)

        # Bottom bar
        bottom = ctk.CTkFrame(dlg, fg_color=COLORS["bg_panel"], height=46,
                              corner_radius=0, border_width=1,
                              border_color=COLORS["border"])
        bottom.pack(fill="x", side="bottom")
        bottom.pack_propagate(False)

        ctk.CTkButton(
            bottom, text="Cancel", width=80, height=30,
            fg_color=COLORS["bg_card"],
            hover_color=COLORS["bg_panel"],
            text_color=COLORS["white"],
            font=ctk.CTkFont(*FONT_MONO),
            command=dlg.destroy
        ).pack(side="right", padx=10, pady=8)

        # Fetch tags in background
        def _bg():
            tags = self._fetch_model_tags(base)
            try:
                dlg.after(0, lambda: self._render_quant_variants(
                    dlg, scroll, loading_lbl, base, param_tag,
                    params_b, tags))
            except Exception:
                pass  # Dialog closed while loading

        threading.Thread(target=_bg, daemon=True,
                         name="ModelMgrTags").start()

    def _fetch_model_tags(self, base: str) -> list[str]:
        """Fetch available tags from Ollama registry.

        Tries the Docker v2 registry API, falls back to empty list.
        """
        url = f"https://registry.ollama.ai/v2/library/{base}/tags/list"
        try:
            req = urllib.request.Request(
                url, method="GET",
                headers={"User-Agent": "Forge/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                tags = data.get("tags", [])
                if isinstance(tags, list):
                    return [t for t in tags if isinstance(t, str)]
        except Exception:
            log.debug("Registry tag fetch failed for %s, using fallback", base)
        return []

    def _render_quant_variants(self, dlg, scroll, loading_lbl,
                               base: str, param_tag: str,
                               params_b: float, tags: list[str]):
        """Render variant cards in the quant picker (main thread)."""
        loading_lbl.destroy()

        # If no tags fetched, generate standard quant variants as fallback
        if not tags and param_tag and params_b > 0:
            tags = [param_tag] + [
                f"{param_tag}-{q.lower()}" for q in _COMMON_QUANTS]

        if not tags:
            # Can't determine variants — offer direct pull
            default_name = f"{base}:{param_tag}" if param_tag else base
            ctk.CTkLabel(
                scroll,
                text="Could not fetch variant list.\n\n"
                     "Click below to pull the default variant.",
                font=ctk.CTkFont(*FONT_MONO_SM),
                text_color=COLORS["text_dim"],
                justify="center").pack(pady=20)
            ctk.CTkButton(
                scroll, text=f"Pull {default_name}",
                width=200, height=34,
                fg_color=COLORS["cyan_dim"],
                hover_color=COLORS["cyan"],
                text_color=COLORS["bg_dark"],
                font=ctk.CTkFont(*FONT_MONO_BOLD),
                command=lambda: (
                    dlg.destroy(), self._enqueue_pull(default_name))
            ).pack(pady=8)
            return

        # Filter tags matching our parameter tag
        if param_tag:
            matching = [t for t in tags
                        if t == param_tag or t.startswith(param_tag + "-")]
        else:
            matching = tags

        # Build variant data: (tag, full_name, quant_key, vram_est, fit)
        variants = []
        seen = set()
        for tag in matching:
            full_name = f"{base}:{tag}"
            if full_name in seen:
                continue
            seen.add(full_name)
            quant_key = _quant_from_tag(tag, param_tag)
            vram = _estimate_quant_vram(params_b, quant_key)
            fit = _classify_fit(vram, self._vram_gb) if vram > 0 else "unknown"
            variants.append((tag, full_name, quant_key, vram, fit))

        # Sort by VRAM ascending (smallest/most-compressed first)
        variants.sort(key=lambda v: (v[3] if v[3] > 0 else 999, v[0]))

        if not variants:
            default_name = f"{base}:{param_tag}" if param_tag else base
            ctk.CTkLabel(
                scroll,
                text=f"No variants found for '{param_tag or base}'.",
                font=ctk.CTkFont(*FONT_MONO_SM),
                text_color=COLORS["text_dim"],
                justify="center").pack(pady=20)
            ctk.CTkButton(
                scroll, text=f"Pull {default_name}",
                width=200, height=34,
                fg_color=COLORS["cyan_dim"],
                hover_color=COLORS["cyan"],
                text_color=COLORS["bg_dark"],
                font=ctk.CTkFont(*FONT_MONO_BOLD),
                command=lambda: (
                    dlg.destroy(), self._enqueue_pull(default_name))
            ).pack(pady=8)
            return

        # Check installed models
        installed_names = {m.get("name", "") for m in self._installed}

        for tag, full_name, quant_key, vram, fit in variants:
            self._build_variant_card(
                scroll, dlg, tag, full_name, quant_key, vram, fit,
                full_name in installed_names)

    def _build_variant_card(self, parent, dlg, tag: str, full_name: str,
                            quant_key: str, vram: float, fit: str,
                            is_installed: bool):
        """Build a single variant card in the quant picker."""
        style = _FIT_STYLES.get(fit, _FIT_STYLES["unknown"])
        _, badge_text, badge_fg, name_color = style

        border_color = COLORS["border"]
        if fit == "too_large":
            border_color = COLORS["red"]
        elif fit == "tight":
            border_color = COLORS["yellow"]

        card = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"],
                            corner_radius=6, border_color=border_color,
                            border_width=1)
        card.pack(fill="x", padx=2, pady=2)

        # Top row: full name + fit badge
        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=8, pady=(6, 0))

        ctk.CTkLabel(top_row, text=full_name,
                     font=ctk.CTkFont(*FONT_MONO_BOLD),
                     text_color=name_color,
                     anchor="w").pack(side="left")

        # Fit badge — show for all fit levels
        if fit == "good":
            ctk.CTkLabel(top_row, text=" GOOD FIT ",
                         font=ctk.CTkFont(*FONT_MONO_XS),
                         text_color=COLORS["bg_dark"],
                         fg_color=COLORS["green"],
                         corner_radius=3).pack(side="right", padx=2)
        elif fit == "ok":
            ctk.CTkLabel(top_row, text=" OK FIT ",
                         font=ctk.CTkFont(*FONT_MONO_XS),
                         text_color=COLORS["bg_dark"],
                         fg_color=COLORS["cyan"],
                         corner_radius=3).pack(side="right", padx=2)
        elif fit == "tight":
            ctk.CTkLabel(top_row, text=" HEAVY ",
                         font=ctk.CTkFont(*FONT_MONO_XS),
                         text_color=badge_fg,
                         fg_color=COLORS["yellow"],
                         corner_radius=3).pack(side="right", padx=2)
        elif fit == "too_large":
            ctk.CTkLabel(top_row, text=" TOO LARGE ",
                         font=ctk.CTkFont(*FONT_MONO_XS),
                         text_color=badge_fg,
                         fg_color=COLORS["red"],
                         corner_radius=3).pack(side="right", padx=2)

        # Info row: quant description + VRAM
        quant_label = _QUANT_LABELS.get(quant_key, quant_key.upper())
        parts = [quant_label]
        if vram > 0:
            vram_str = f"~{vram:.1f}GB VRAM"
            if self._vram_gb > 0:
                vram_str += f" of {self._vram_gb:.0f}GB"
            parts.append(vram_str)
        info = "  |  ".join(parts)

        ctk.CTkLabel(card, text=f"  {info}",
                     font=ctk.CTkFont(*FONT_MONO_XS),
                     text_color=COLORS["gray"],
                     anchor="w").pack(fill="x", padx=8, pady=(1, 2))

        # Action row
        action_row = ctk.CTkFrame(card, fg_color="transparent")
        action_row.pack(fill="x", padx=8, pady=(0, 6))

        if is_installed:
            ctk.CTkLabel(action_row, text="Installed",
                         font=ctk.CTkFont(*FONT_MONO_XS),
                         text_color=COLORS["green"]).pack(side="left")
        elif fit == "too_large":
            ctk.CTkButton(
                action_row, text="Pull Anyway", width=100, height=24,
                fg_color=COLORS["bg_panel"],
                hover_color=COLORS["red"],
                text_color=COLORS["yellow"],
                font=ctk.CTkFont(*FONT_MONO_XS),
                command=lambda n=full_name: (
                    dlg.destroy(), self._enqueue_pull(n))
            ).pack(side="left")
            if vram > 0 and self._vram_gb > 0:
                over = vram - self._vram_gb
                ctk.CTkLabel(
                    action_row,
                    text=f"  {over:.1f}GB over your VRAM",
                    font=ctk.CTkFont(*FONT_MONO_XS),
                    text_color=COLORS["red"]).pack(side="left")
        else:
            ctk.CTkButton(
                action_row, text="Pull", width=60, height=24,
                fg_color=COLORS["cyan_dim"],
                hover_color=COLORS["cyan"],
                text_color=COLORS["bg_dark"],
                font=ctk.CTkFont(*FONT_MONO_BOLD),
                command=lambda n=full_name: (
                    dlg.destroy(), self._enqueue_pull(n))
            ).pack(side="left")

    # ──────────────────────────────────────────────────────────
    # Actions: Pull with progress bar queue
    # ──────────────────────────────────────────────────────────

    def _enqueue_pull(self, name: str):
        if name in self._pull_queue:
            return
        self._pull_queue.append(name)
        if not self._pulling:
            self._process_queue()

    def _process_queue(self):
        if not self._pull_queue:
            self._pulling = False
            self._hide_pull_bar()
            self._lbl_pull.configure(text="")
            return

        self._pulling = True
        name = self._pull_queue.pop(0)
        self._show_pull_bar()
        self._pull_bar.set(0)
        self._pull_bar.configure(progress_color=COLORS["cyan_dim"])
        self._lbl_pull.configure(text=f"  Pulling {name}...",
                                 text_color=COLORS["cyan"])

        def _bg():
            try:
                data = json.dumps({"name": name, "stream": True}).encode()
                req = urllib.request.Request(
                    f"{self._base_url}/api/pull", data=data,
                    headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=600) as resp:
                    for line in resp:
                        try:
                            info = json.loads(line)
                            status = info.get("status", "")
                            total = info.get("total", 0)
                            completed = info.get("completed", 0)
                            if total and completed:
                                pct = completed / total
                                self._win.after(0, self._update_pull,
                                                name, status, pct)
                            else:
                                self._win.after(0, self._update_pull,
                                                name, status, -1)
                        except Exception:
                            pass

                self._win.after(0, lambda: (
                    self._pull_bar.set(1.0),
                    self._pull_bar.configure(
                        progress_color=COLORS["green"]),
                    self._flash(f"{name} pulled!", COLORS["green"]),
                ))
                self._win.after(500, self._refresh_all)
            except Exception as e:
                self._win.after(0, lambda: self._flash(
                    f"Pull failed: {e}", COLORS["red"]))
            finally:
                self._win.after(100, self._process_queue)

        threading.Thread(target=_bg, daemon=True,
                         name="ModelMgrPull").start()

    def _update_pull(self, name, status, pct):
        """Update pull progress bar and label (main thread)."""
        if pct >= 0:
            self._pull_bar.set(min(pct, 1.0))
            self._lbl_pull.configure(
                text=f"  {name}: {status} ({pct:.0%})",
                text_color=COLORS["cyan"])
        else:
            self._lbl_pull.configure(
                text=f"  {name}: {status}",
                text_color=COLORS["cyan"])

    def _show_pull_bar(self):
        if not self._pull_bar_visible:
            self._pull_bar.pack(side="left", padx=(10, 6), pady=8,
                                before=self._lbl_pull)
            self._pull_bar_visible = True

    def _hide_pull_bar(self):
        if self._pull_bar_visible:
            self._pull_bar.pack_forget()
            self._pull_bar_visible = False

    # ──────────────────────────────────────────────────────────
    # Utility
    # ──────────────────────────────────────────────────────────

    def _flash(self, text: str, color: str, duration_ms: int = 2500):
        """Show a brief status message, then clear."""
        self._lbl_pull.configure(text=f"  {text}", text_color=color)
        self._win.after(duration_ms, lambda: self._lbl_pull.configure(
            text="", text_color=COLORS["gray"]))

    def _apply_theme(self, color_map: dict):
        """Hot-swap theme colours on the model manager."""
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
        try:
            self._win.destroy()
        except Exception:
            pass
