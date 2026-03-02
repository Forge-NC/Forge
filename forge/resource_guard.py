"""Cross-platform process scanner and resource guard for stress tests.

Checks system resources (RAM, VRAM) and identifies heavy processes
before running stress tests. Can optionally close non-essential
processes to free resources.

Does NOT require psutil -- falls back to system commands when unavailable.
"""

import logging
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional

log = logging.getLogger(__name__)

# Prevent subprocess console windows on Windows
_SUBPROCESS_FLAGS = {}
if os.name == "nt":
    _SUBPROCESS_FLAGS["creationflags"] = subprocess.CREATE_NO_WINDOW

# ---------------------------------------------------------------------------
# Platform-specific process sets
# ---------------------------------------------------------------------------

_IS_WINDOWS = sys.platform == "win32"

_HEAVY_WINDOWS = {
    "chrome.exe", "firefox.exe", "msedge.exe", "discord.exe",
    "slack.exe", "teams.exe", "steam.exe", "steamwebhelper.exe",
    "epicgameslauncher.exe", "obs64.exe", "blender.exe",
    "spotify.exe", "brave.exe", "opera.exe", "vivaldi.exe",
    "code.exe",
}

_HEAVY_LINUX = {
    "chrome", "firefox", "discord", "steam", "blender",
    "obs", "spotify", "brave", "opera", "vivaldi", "code",
    "slack", "teams", "steamwebhelper", "epicgameslauncher",
}

DEFAULT_HEAVY_PROCESSES = _HEAVY_WINDOWS if _IS_WINDOWS else _HEAVY_LINUX

# These are NEVER closeable -- hardcoded, not user-configurable.
_PROTECTED_WINDOWS = {
    "svchost.exe", "explorer.exe", "csrss.exe", "winlogon.exe",
    "services.exe", "lsass.exe", "smss.exe", "system", "wininit.exe",
}

_PROTECTED_LINUX = {
    "systemd", "init", "xorg", "dbus-daemon",
}

_PROTECTED_ALWAYS = {
    "ollama", "ollama.exe", "ollama_llama_server",
    "python", "python.exe", "pythonw.exe",
}

PROTECTED_PROCESSES = (
    (_PROTECTED_WINDOWS if _IS_WINDOWS else _PROTECTED_LINUX) | _PROTECTED_ALWAYS
)

# Thresholds
_MIN_VRAM_MB = 4096   # 4 GB
_MIN_RAM_MB = 4096    # 4 GB

# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class ResourceReport:
    total_ram_mb: int = 0
    available_ram_mb: int = 0
    vram_total_mb: int = 0
    vram_free_mb: int = 0
    heavy_processes: List[dict] = field(default_factory=list)
    safe_to_test: bool = False
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_available_ram_mb() -> Optional[int]:
    """Return available (free + cached) system RAM in MB."""
    # Try psutil first
    try:
        import psutil
        mem = psutil.virtual_memory()
        return int(mem.available / (1024 * 1024))
    except Exception:
        pass

    # Fallback: platform-specific commands
    try:
        if _IS_WINDOWS:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory"],
                capture_output=True, text=True, timeout=10,
                **_SUBPROCESS_FLAGS,
            )
            val = result.stdout.strip()
            if val.isdigit():
                return int(val) // 1024  # FreePhysicalMemory is in KB
        else:
            with open("/proc/meminfo") as f:
                available = None
                free = None
                buffers = 0
                cached = 0
                for line in f:
                    if line.startswith("MemAvailable:"):
                        available = int(line.split()[1])  # KB
                    elif line.startswith("MemFree:"):
                        free = int(line.split()[1])
                    elif line.startswith("Buffers:"):
                        buffers = int(line.split()[1])
                    elif line.startswith("Cached:"):
                        cached = int(line.split()[1])
                if available is not None:
                    return available // 1024
                if free is not None:
                    return (free + buffers + cached) // 1024
    except Exception as exc:
        log.debug("Available RAM detection failed: %s", exc)
    return None


def _scan_processes_psutil(heavy_names: set) -> List[dict]:
    """Scan running processes via psutil."""
    import psutil  # caller already verified importability
    results = []
    for proc in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            info = proc.info
            name = (info["name"] or "").lower()
            if name in heavy_names:
                ram_mb = (info["memory_info"].rss // (1024 * 1024)) if info["memory_info"] else 0
                results.append({
                    "name": info["name"],
                    "pid": info["pid"],
                    "ram_mb": ram_mb,
                    "vram_mb": 0,
                    "category": "heavy",
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return results


def _scan_processes_fallback(heavy_names: set) -> List[dict]:
    """Scan running processes via system commands (no psutil)."""
    results = []
    try:
        if _IS_WINDOWS:
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=15,
                **_SUBPROCESS_FLAGS,
            )
            for line in result.stdout.strip().splitlines():
                # Format: "name.exe","PID","Session Name","Session#","Mem Usage"
                parts = [p.strip('"') for p in line.split('","')]
                if len(parts) < 5:
                    continue
                name = parts[0]
                if name.lower() not in heavy_names:
                    continue
                try:
                    pid = int(parts[1])
                except ValueError:
                    continue
                # Memory value like "123,456 K"
                mem_str = parts[4].replace(",", "").replace(" K", "").replace(" k", "").strip()
                try:
                    ram_kb = int(mem_str)
                    ram_mb = ram_kb // 1024
                except ValueError:
                    ram_mb = 0
                results.append({
                    "name": name,
                    "pid": pid,
                    "ram_mb": ram_mb,
                    "vram_mb": 0,
                    "category": "heavy",
                })
        else:
            result = subprocess.run(
                ["ps", "aux", "--sort=-%mem"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.strip().splitlines()[1:]:
                cols = line.split(None, 10)
                if len(cols) < 11:
                    continue
                pid_str = cols[1]
                rss_kb = cols[5]  # RSS in KB
                cmd = cols[10]
                proc_name = os.path.basename(cmd.split()[0]) if cmd else ""
                if proc_name.lower() not in heavy_names:
                    continue
                try:
                    pid = int(pid_str)
                    ram_mb = int(rss_kb) // 1024
                except ValueError:
                    continue
                results.append({
                    "name": proc_name,
                    "pid": pid,
                    "ram_mb": ram_mb,
                    "vram_mb": 0,
                    "category": "heavy",
                })
    except Exception as exc:
        log.debug("Process scan fallback failed: %s", exc)
    return results


def _scan_vram_usage() -> dict:
    """Return {pid: (process_name, vram_mb)} from nvidia-smi."""
    mapping = {}
    try:
        result = subprocess.run(
            ["nvidia-smi",
             "--query-compute-apps=pid,process_name,used_gpu_memory",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
            **_SUBPROCESS_FLAGS,
        )
        if result.returncode != 0:
            return mapping
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                continue
            try:
                pid = int(parts[0])
                name = os.path.basename(parts[1])
                vram = int(float(parts[2]))
                mapping[pid] = (name, vram)
            except (ValueError, IndexError):
                continue
    except FileNotFoundError:
        pass
    except Exception as exc:
        log.debug("VRAM scan failed: %s", exc)
    return mapping


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_resources(
    heavy_names: Optional[set] = None,
) -> ResourceReport:
    """Scan system resources and identify heavy processes.

    Args:
        heavy_names: Process names to flag. Defaults to DEFAULT_HEAVY_PROCESSES.

    Returns:
        ResourceReport with system state and safety assessment.
    """
    if heavy_names is None:
        heavy_names = DEFAULT_HEAVY_PROCESSES

    # Normalise to lowercase for matching
    heavy_lower = {n.lower() for n in heavy_names}

    report = ResourceReport()

    # --- GPU info via forge.hardware ---
    try:
        from forge.hardware import detect_gpu, detect_system_ram
        gpu = detect_gpu()
        if gpu:
            report.vram_total_mb = gpu["vram_total_mb"]
            report.vram_free_mb = gpu["vram_free_mb"]

        total_ram = detect_system_ram()
        if total_ram is not None:
            report.total_ram_mb = total_ram
    except Exception as exc:
        log.debug("forge.hardware import/call failed: %s", exc)

    # --- Available RAM ---
    avail = _get_available_ram_mb()
    if avail is not None:
        report.available_ram_mb = avail

    # --- Process scan ---
    try:
        import psutil  # noqa: F811
        procs = _scan_processes_psutil(heavy_lower)
    except ImportError:
        procs = _scan_processes_fallback(heavy_lower)

    # --- Attach VRAM usage ---
    vram_map = _scan_vram_usage()
    for p in procs:
        if p["pid"] in vram_map:
            p["vram_mb"] = vram_map[p["pid"]][1]
    # Add GPU-only heavy processes not found in CPU scan
    seen_pids = {p["pid"] for p in procs}
    for pid, (name, vram_mb) in vram_map.items():
        if pid not in seen_pids and name.lower() in heavy_lower:
            procs.append({
                "name": name,
                "pid": pid,
                "ram_mb": 0,
                "vram_mb": vram_mb,
                "category": "heavy",
            })

    report.heavy_processes = sorted(procs, key=lambda p: p["ram_mb"] + p["vram_mb"], reverse=True)

    # --- Warnings ---
    if report.vram_free_mb > 0 and report.vram_free_mb < _MIN_VRAM_MB:
        report.warnings.append(
            f"Low VRAM: {report.vram_free_mb}MB free (need {_MIN_VRAM_MB}MB)"
        )
    elif report.vram_total_mb == 0:
        report.warnings.append("No NVIDIA GPU detected")

    if report.available_ram_mb > 0 and report.available_ram_mb < _MIN_RAM_MB:
        report.warnings.append(
            f"Low RAM: {report.available_ram_mb}MB available (need {_MIN_RAM_MB}MB)"
        )
    elif report.available_ram_mb == 0 and report.total_ram_mb == 0:
        report.warnings.append("Could not detect system RAM")

    total_heavy_ram = sum(p["ram_mb"] for p in report.heavy_processes)
    total_heavy_vram = sum(p["vram_mb"] for p in report.heavy_processes)
    if total_heavy_ram > 1024:
        report.warnings.append(
            f"{len(report.heavy_processes)} heavy processes using "
            f"{total_heavy_ram}MB RAM, {total_heavy_vram}MB VRAM"
        )

    # --- Safety verdict ---
    vram_ok = report.vram_free_mb >= _MIN_VRAM_MB or report.vram_total_mb == 0
    ram_ok = report.available_ram_mb >= _MIN_RAM_MB or report.available_ram_mb == 0
    report.safe_to_test = vram_ok and ram_ok

    return report


def close_processes(
    processes: List[dict],
    force: bool = False,
) -> List[dict]:
    """Attempt to close the given processes.

    Args:
        processes: List of dicts with at least 'name' and 'pid' keys.
        force: If True, escalate to SIGKILL / taskkill /F after 10 seconds.

    Returns:
        List of {name, pid, closed: bool} result dicts.
    """
    results = []
    protected_lower = {n.lower() for n in PROTECTED_PROCESSES}

    for proc in processes:
        name = proc.get("name", "")
        pid = proc.get("pid", 0)

        # Never touch protected processes
        if name.lower() in protected_lower:
            log.warning("Refusing to close protected process: %s (PID %d)", name, pid)
            results.append({"name": name, "pid": pid, "closed": False})
            continue

        closed = False
        try:
            if _IS_WINDOWS:
                # Graceful close
                subprocess.run(
                    ["taskkill", "/PID", str(pid)],
                    capture_output=True, timeout=5,
                    **_SUBPROCESS_FLAGS,
                )
                # Check if process is gone
                time.sleep(1)
                check = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True, text=True, timeout=5,
                    **_SUBPROCESS_FLAGS,
                )
                if str(pid) not in check.stdout:
                    closed = True
                elif force:
                    time.sleep(9)  # total ~10s wait
                    subprocess.run(
                        ["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True, timeout=5,
                        **_SUBPROCESS_FLAGS,
                    )
                    time.sleep(1)
                    check2 = subprocess.run(
                        ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                        capture_output=True, text=True, timeout=5,
                        **_SUBPROCESS_FLAGS,
                    )
                    closed = str(pid) not in check2.stdout
            else:
                # Linux: SIGTERM
                os.kill(pid, signal.SIGTERM)
                time.sleep(1)
                try:
                    os.kill(pid, 0)  # probe: raises OSError if dead
                    if force:
                        time.sleep(9)
                        os.kill(pid, signal.SIGKILL)
                        time.sleep(1)
                        try:
                            os.kill(pid, 0)
                        except OSError:
                            closed = True
                    # Still alive and not forcing
                except OSError:
                    closed = True

        except ProcessLookupError:
            closed = True  # already gone
        except Exception as exc:
            log.debug("Failed to close %s (PID %d): %s", name, pid, exc)

        results.append({"name": name, "pid": pid, "closed": closed})

    return results


def format_report(report: ResourceReport) -> str:
    """Format a ResourceReport as a human-readable string."""
    lines = []
    lines.append("=== Resource Guard Report ===")
    lines.append("")

    # System memory
    if report.total_ram_mb:
        used_ram = report.total_ram_mb - report.available_ram_mb
        pct = (used_ram / report.total_ram_mb * 100) if report.total_ram_mb else 0
        indicator = "[OK]" if report.available_ram_mb >= _MIN_RAM_MB else "[!!]"
        lines.append(f"  RAM:   {indicator} {report.available_ram_mb}MB free "
                     f"/ {report.total_ram_mb}MB total ({pct:.0f}% used)")
    else:
        lines.append("  RAM:   [??] Could not detect")

    # VRAM
    if report.vram_total_mb:
        used_vram = report.vram_total_mb - report.vram_free_mb
        pct = (used_vram / report.vram_total_mb * 100) if report.vram_total_mb else 0
        indicator = "[OK]" if report.vram_free_mb >= _MIN_VRAM_MB else "[!!]"
        lines.append(f"  VRAM:  {indicator} {report.vram_free_mb}MB free "
                     f"/ {report.vram_total_mb}MB total ({pct:.0f}% used)")
    else:
        lines.append("  VRAM:  [--] No NVIDIA GPU detected")

    # Heavy processes
    lines.append("")
    if report.heavy_processes:
        lines.append(f"  Heavy processes ({len(report.heavy_processes)}):")
        lines.append(f"    {'Name':<28} {'PID':>7}  {'RAM':>7}  {'VRAM':>7}")
        lines.append("    " + "-" * 55)
        for p in report.heavy_processes:
            vram_str = f"{p['vram_mb']}MB" if p["vram_mb"] else "  -"
            lines.append(
                f"    {p['name']:<28} {p['pid']:>7}  "
                f"{p['ram_mb']:>5}MB  {vram_str:>7}"
            )
    else:
        lines.append("  Heavy processes: none detected")

    # Warnings
    if report.warnings:
        lines.append("")
        lines.append("  Warnings:")
        for w in report.warnings:
            lines.append(f"    [!] {w}")

    # Verdict
    lines.append("")
    if report.safe_to_test:
        lines.append("  Verdict: [OK] Safe to run stress tests")
    else:
        lines.append("  Verdict: [!!] Resources too low for stress tests")

    return "\n".join(lines)
