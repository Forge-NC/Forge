"""Hardware detection and model recommendation.

Detects GPU model, VRAM, system RAM, and recommends the best
coding model that fits entirely on GPU (no CPU offload penalty).

Also supports quick benchmarking after model load to give users
real tok/s numbers on their hardware.
"""

import os
import re
import subprocess
import logging
from typing import Optional

# On Windows, prevent subprocess from flashing console windows
_SUBPROCESS_FLAGS = {}
if os.name == "nt":
    _SUBPROCESS_FLAGS["creationflags"] = (
        subprocess.CREATE_NO_WINDOW  # 0x08000000
    )

log = logging.getLogger(__name__)

# Model VRAM requirements (approximate, Q4_K_M quantization)
# Format: (model_name, vram_gb_weights, min_vram_for_32k_ctx, description)
MODEL_SPECS = [
    ("qwen2.5-coder:32b",  20.0, 24.0, "Best quality, needs 24GB+ VRAM"),
    ("qwen2.5-coder:14b",   8.5, 12.0, "Great quality, fits 12-16GB VRAM"),
    ("deepseek-coder-v2:16b", 9.5, 14.0, "Strong alternative, needs 14GB+"),
    ("qwen2.5-coder:7b",    4.5,  7.0, "Good quality, fits 8GB+ VRAM"),
    ("codellama:13b",        7.5, 11.0, "Solid baseline, needs 12GB+"),
    ("codellama:7b",         4.0,  6.5, "Lightweight, fits 8GB VRAM"),
    ("qwen2.5-coder:3b",    2.0,  4.0, "Minimal, fits 4GB+ VRAM"),
    ("qwen2.5-coder:1.5b",  1.2,  2.5, "Tiny, fits almost any GPU"),
]


def detect_gpu() -> Optional[dict]:
    """Detect NVIDIA GPU via nvidia-smi.

    Returns dict with:
        name: str (e.g. "NVIDIA GeForce RTX 5070 Ti")
        vram_total_mb: int
        vram_free_mb: int
        vram_used_mb: int
        driver_version: str
        cuda_version: str
    Or None if no NVIDIA GPU / nvidia-smi not found.
    """
    try:
        result = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=name,memory.total,memory.free,memory.used,"
             "driver_version",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
            **_SUBPROCESS_FLAGS,
        )
        if result.returncode != 0:
            return None

        line = result.stdout.strip().split("\n")[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            return None

        info = {
            "name": parts[0],
            "vram_total_mb": int(float(parts[1])),
            "vram_free_mb": int(float(parts[2])),
            "vram_used_mb": int(float(parts[3])),
            "driver_version": parts[4],
        }

        # Parse CUDA version from nvidia-smi header
        header_result = subprocess.run(
            ["nvidia-smi"], capture_output=True, text=True, timeout=5,
            **_SUBPROCESS_FLAGS,
        )
        cuda_match = re.search(r"CUDA Version:\s*([\d.]+)",
                               header_result.stdout)
        if cuda_match:
            info["cuda_version"] = cuda_match.group(1)
        else:
            info["cuda_version"] = "unknown"

        return info

    except FileNotFoundError:
        log.debug("nvidia-smi not found")
        return None
    except Exception as e:
        log.debug("GPU detection failed: %s", e)
        return None


def detect_system_ram() -> Optional[int]:
    """Detect total system RAM in MB."""
    try:
        if os.name == "nt":
            # Try PowerShell first (wmic is deprecated on Win11)
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory"],
                capture_output=True, text=True, timeout=10,
                **_SUBPROCESS_FLAGS,
            )
            val = result.stdout.strip()
            if val.isdigit():
                return int(val) // (1024 * 1024)

            # Fallback: wmic
            result = subprocess.run(
                ["wmic", "computersystem", "get", "TotalPhysicalMemory",
                 "/value"],
                capture_output=True, text=True, timeout=10,
                **_SUBPROCESS_FLAGS,
            )
            match = re.search(r"TotalPhysicalMemory=(\d+)", result.stdout)
            if match:
                return int(match.group(1)) // (1024 * 1024)
        else:
            # Linux: read /proc/meminfo
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return kb // 1024
    except Exception as e:
        log.debug("RAM detection failed: %s", e)
    return None


def detect_cpu() -> Optional[str]:
    """Detect CPU model name."""
    try:
        if os.name == "nt":
            # Try PowerShell first
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_Processor).Name"],
                capture_output=True, text=True, timeout=10,
                **_SUBPROCESS_FLAGS,
            )
            name = result.stdout.strip()
            if name and "error" not in name.lower():
                return name

            # Fallback: wmic
            result = subprocess.run(
                ["wmic", "cpu", "get", "Name", "/value"],
                capture_output=True, text=True, timeout=10,
                **_SUBPROCESS_FLAGS,
            )
            match = re.search(r"Name=(.+)", result.stdout)
            if match:
                return match.group(1).strip()
        else:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        return line.split(":")[1].strip()
    except Exception:
        pass
    return None


def get_hardware_summary() -> dict:
    """Get a full hardware summary.

    Returns dict with gpu, ram_mb, cpu, and recommendation.
    """
    gpu = detect_gpu()
    ram_mb = detect_system_ram()
    cpu = detect_cpu()

    summary = {
        "gpu": gpu,
        "ram_mb": ram_mb,
        "cpu": cpu,
        "vram_gb": round(gpu["vram_total_mb"] / 1024, 1) if gpu else 0,
        "vram_free_gb": round(gpu["vram_free_mb"] / 1024, 1) if gpu else 0,
        "ram_gb": round(ram_mb / 1024, 1) if ram_mb else 0,
    }

    # Generate recommendation — always use total VRAM since Ollama unloads
    # the current model before loading a new one
    if gpu:
        vram_total = summary["vram_gb"]
        summary["usable_vram_gb"] = vram_total
        summary["recommendation"] = recommend_model(vram_total)
    else:
        summary["usable_vram_gb"] = 0
        summary["recommendation"] = {
            "model": "qwen2.5-coder:3b",
            "reason": "No NVIDIA GPU detected — using smallest model (CPU-only)",
            "fit": "cpu_only",
        }

    return summary


def recommend_model(available_vram_gb: float) -> dict:
    """Recommend the best model that fits entirely on GPU.

    Args:
        available_vram_gb: Usable VRAM in GB.

    Returns dict with:
        model: str — recommended model name
        reason: str — why this model
        fit: str — "full_gpu", "tight", "cpu_offload"
        alternatives: list[dict] — other options
    """
    best = None
    alternatives = []

    for name, weights_gb, full_ctx_gb, desc in MODEL_SPECS:
        if full_ctx_gb <= available_vram_gb:
            entry = {
                "model": name,
                "vram_needed": full_ctx_gb,
                "headroom_gb": round(available_vram_gb - full_ctx_gb, 1),
                "fit": "full_gpu",
                "desc": desc,
            }
            if best is None:
                best = entry
            else:
                alternatives.append(entry)
        elif weights_gb <= available_vram_gb:
            entry = {
                "model": name,
                "vram_needed": full_ctx_gb,
                "headroom_gb": round(available_vram_gb - weights_gb, 1),
                "fit": "tight",
                "desc": f"{desc} (reduced context to fit)",
            }
            if best is None:
                best = entry
            else:
                alternatives.append(entry)

    if best is None:
        # Nothing fits — recommend smallest
        return {
            "model": "qwen2.5-coder:1.5b",
            "reason": f"Only {available_vram_gb:.1f}GB VRAM available — using smallest model",
            "fit": "minimal",
            "alternatives": [],
        }

    fit_label = {
        "full_gpu": "Fits entirely on GPU with room for full context",
        "tight": "Fits on GPU but context window may be limited",
    }

    return {
        "model": best["model"],
        "reason": f"{fit_label[best['fit']]} "
                  f"({best['headroom_gb']}GB headroom on {available_vram_gb:.1f}GB VRAM)",
        "fit": best["fit"],
        "alternatives": alternatives[:3],
    }


def calculate_max_context(vram_gb: float, model_name: str) -> dict:
    """Calculate the maximum context window for a model given available VRAM.

    Takes into account KV cache quantization options:
    - FP16 (default): full precision KV cache
    - Q8_0: 8-bit quantized KV cache (~50% memory savings)
    - Q4_0: 4-bit quantized KV cache (~75% memory savings)

    Returns dict with context sizes for each KV cache mode and
    the recommended configuration.
    """
    # Model weight sizes (approximate, Q4_K_M)
    weight_sizes = {
        "qwen2.5-coder:32b":   20.0,
        "qwen2.5-coder:14b":    8.5,
        "qwen2.5-coder:7b":     4.5,
        "qwen2.5-coder:3b":     2.0,
        "qwen2.5-coder:1.5b":   1.2,
        "deepseek-coder-v2:16b": 9.5,
        "codellama:13b":         7.5,
        "codellama:7b":          4.0,
    }

    # KV cache bytes per token (FP16) — depends on model architecture
    # Formula: 2 (K+V) × layers × kv_heads × head_dim × 2 bytes (FP16)
    # These are pre-calculated for each model family
    kv_bytes_per_token = {
        "qwen2.5-coder:32b":   0.625,   # 64 layers, 8 kv_heads, 128 dim → ~0.625 MB/tok
        "qwen2.5-coder:14b":   0.375,   # 48 layers, 8 kv_heads, 128 dim → ~0.375 MB/tok
        "qwen2.5-coder:7b":    0.188,   # 28 layers, 4 kv_heads, 128 dim → ~0.188 MB/tok
        "qwen2.5-coder:3b":    0.110,   # 36 layers, 2 kv_heads, 128 dim → ~0.110 MB/tok
        "qwen2.5-coder:1.5b":  0.075,   # 28 layers, 2 kv_heads, 128 dim → ~0.075 MB/tok
        "deepseek-coder-v2:16b": 0.400, # Similar to 14b class
        "codellama:13b":        0.320,   # 40 layers, 8 kv_heads, 128 dim
        "codellama:7b":         0.188,   # 32 layers, 8 kv_heads, 128 dim
    }

    # Model architecture max context
    arch_max_ctx = {
        "qwen2.5-coder:32b":   131072,
        "qwen2.5-coder:14b":   131072,
        "qwen2.5-coder:7b":    131072,
        "qwen2.5-coder:3b":    32768,
        "qwen2.5-coder:1.5b":  32768,
        "deepseek-coder-v2:16b": 163840,
        "codellama:13b":        16384,
        "codellama:7b":         16384,
    }

    # Look up model specs (fuzzy match on base name)
    base = model_name.split(":")[0] + ":" + model_name.split(":")[-1] if ":" in model_name else model_name
    weights_gb = weight_sizes.get(base, 8.0)
    kv_mb_per_tok = kv_bytes_per_token.get(base, 0.375)
    max_arch_ctx = arch_max_ctx.get(base, 32768)

    # Available VRAM for KV cache (leave 0.5GB for overhead)
    available_for_kv = max(0, (vram_gb - weights_gb - 0.5))
    available_for_kv_mb = available_for_kv * 1024

    # Calculate context for each KV quantization mode
    modes = {}
    for mode_name, multiplier in [("fp16", 1.0), ("q8_0", 0.5), ("q4_0", 0.25)]:
        effective_kv_per_tok = kv_mb_per_tok * multiplier
        if effective_kv_per_tok > 0:
            max_tokens = int(available_for_kv_mb / effective_kv_per_tok)
        else:
            max_tokens = 0
        # Cap at architecture maximum
        max_tokens = min(max_tokens, max_arch_ctx)
        modes[mode_name] = max_tokens

    # Recommend the best mode
    # Q8_0 is the sweet spot: negligible quality loss, 2x context
    # Q4_0 has measurable quality degradation — only use when Q8 isn't enough
    # The Forge launcher sets OLLAMA_KV_CACHE_TYPE=q8_0 by default
    if modes["q8_0"] >= 16384:
        recommended_mode = "q8_0"
        recommended_ctx = min(modes["q8_0"], 131072)
        q4_ctx = min(modes["q4_0"], 131072)
        reason = (f"Q8 KV cache: {recommended_ctx:,} tokens with zero quality loss "
                  f"(Q4 available: {q4_ctx:,} tokens with slight quality trade-off)")
    elif modes["q4_0"] >= 16384:
        recommended_mode = "q4_0"
        recommended_ctx = min(modes["q4_0"], 131072)
        reason = "Q4 KV cache: needed for usable context on your VRAM"
    else:
        recommended_mode = "fp16"
        recommended_ctx = max(modes["fp16"], 2048)
        reason = "FP16 KV cache: very limited VRAM"

    return {
        "model": model_name,
        "weights_gb": weights_gb,
        "available_for_kv_gb": round(available_for_kv, 1),
        "arch_max_context": max_arch_ctx,
        "modes": {
            "fp16": {"context": modes["fp16"], "kv_gb": round(modes["fp16"] * kv_mb_per_tok / 1024, 1)},
            "q8_0": {"context": modes["q8_0"], "kv_gb": round(modes["q8_0"] * kv_mb_per_tok * 0.5 / 1024, 1)},
            "q4_0": {"context": modes["q4_0"], "kv_gb": round(modes["q4_0"] * kv_mb_per_tok * 0.25 / 1024, 1)},
        },
        "recommended_mode": recommended_mode,
        "recommended_context": recommended_ctx,
        "reason": reason,
    }


def format_context_report(ctx_info: dict) -> str:
    """Format context calculation as human-readable string."""
    lines = []
    lines.append(f"Context Window Analysis for {ctx_info['model']}:")
    lines.append(f"  Model weights:       {ctx_info['weights_gb']}GB")
    lines.append(f"  VRAM for KV cache:   {ctx_info['available_for_kv_gb']}GB")
    lines.append(f"  Architecture max:    {ctx_info['arch_max_context']:,} tokens")
    lines.append("")
    lines.append("  KV Cache Mode        Context Window   KV Memory")
    lines.append("  " + "-" * 55)
    for mode_name, label in [("fp16", "FP16 (default)"), ("q8_0", "Q8 quantized"), ("q4_0", "Q4 quantized")]:
        m = ctx_info["modes"][mode_name]
        marker = " <--" if mode_name == ctx_info["recommended_mode"] else ""
        lines.append(f"  {label:22} {m['context']:>8,} tokens   {m['kv_gb']:>5.1f}GB{marker}")
    lines.append("")
    lines.append(f"  Recommended: {ctx_info['recommended_mode'].upper()} "
                 f"= {ctx_info['recommended_context']:,} tokens")
    lines.append(f"  ({ctx_info['reason']})")
    return "\n".join(lines)


def format_hardware_report(summary: dict) -> str:
    """Format hardware summary as a human-readable string."""
    lines = []
    lines.append("Hardware Profile:")
    lines.append("")

    if summary["gpu"]:
        gpu = summary["gpu"]
        lines.append(f"  GPU:    {gpu['name']}")
        lines.append(f"  VRAM:   {summary['vram_gb']}GB total, "
                     f"{summary['vram_free_gb']}GB free")
        lines.append(f"  CUDA:   {gpu.get('cuda_version', 'N/A')}")
        lines.append(f"  Driver: {gpu.get('driver_version', 'N/A')}")
    else:
        lines.append("  GPU:    No NVIDIA GPU detected")

    if summary["cpu"]:
        lines.append(f"  CPU:    {summary['cpu']}")

    if summary["ram_gb"]:
        lines.append(f"  RAM:    {summary['ram_gb']}GB")

    rec = summary.get("recommendation", {})
    if rec:
        lines.append("")
        lines.append(f"  Recommended model: {rec['model']}")
        lines.append(f"  Reason: {rec['reason']}")

        alts = rec.get("alternatives", [])
        if alts:
            lines.append("")
            lines.append("  Alternatives:")
            for alt in alts:
                lines.append(f"    {alt['model']:30} {alt['desc']}")

    return "\n".join(lines)
