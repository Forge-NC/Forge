"""Cross-platform nightly test scheduling module.

Provides functions to install, remove, query, and inspect scheduled tasks
for automated nightly stress tests. On Windows this uses the ``schtasks``
command-line tool; on Linux it manipulates the user crontab via
``crontab -l`` / ``crontab -``.

All public functions return plain dicts and never raise exceptions.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

TASK_NAME = "ForgeNightly"

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BAT_PATH = _REPO_ROOT / "scripts" / "nightly.bat"
_SH_PATH = _REPO_ROOT / "scripts" / "nightly.sh"
_IS_WINDOWS = sys.platform == "win32"

_CREATE_NO_WINDOW = 0x08000000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_time(time_str: str) -> tuple[int, int]:
    """Validate *time_str* as ``HH:MM`` and return ``(hour, minute)``.

    Raises ``ValueError`` on bad input.
    """
    m = re.fullmatch(r"(\d{2}):(\d{2})", time_str)
    if not m:
        raise ValueError(f"Invalid time format '{time_str}', expected HH:MM")
    hour, minute = int(m.group(1)), int(m.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"Time out of range: {time_str}")
    return hour, minute


def _run(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a subprocess with sensible defaults."""
    defaults: dict = dict(capture_output=True, text=True, timeout=10)
    if _IS_WINDOWS:
        defaults["creationflags"] = _CREATE_NO_WINDOW
    defaults.update(kwargs)
    return subprocess.run(args, **defaults)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def install_schedule(time_str: str = "03:00") -> dict:
    """Create a daily scheduled task to run nightly stress tests.

    Parameters
    ----------
    time_str : str
        Time in ``HH:MM`` (24-hour) format.  Defaults to ``"03:00"``.

    Returns
    -------
    dict
        ``{"success": True, "platform": ..., "time": ...}`` on success,
        ``{"success": False, "error": ...}`` on failure.
    """
    try:
        hour, minute = _parse_time(time_str)
    except ValueError as exc:
        return {"success": False, "error": str(exc)}

    canonical = f"{hour:02d}:{minute:02d}"

    if _IS_WINDOWS:
        script = str(_BAT_PATH)
        cmd = [
            "schtasks", "/create",
            "/tn", TASK_NAME,
            "/tr", script,
            "/sc", "daily",
            "/st", canonical,
            "/f",
        ]
    else:
        script = str(_SH_PATH)
        cron_line = f"{minute} {hour} * * * {script} >> ~/.forge/nightly_logs/cron.log 2>&1"
        # Read existing crontab, append new line, write back.
        try:
            existing = _run(["crontab", "-l"])
            lines = existing.stdout.splitlines() if existing.returncode == 0 else []
            # Remove any pre-existing nightly entry to avoid duplicates.
            lines = [ln for ln in lines if "nightly.sh" not in ln]
            lines.append(cron_line)
            new_crontab = "\n".join(lines) + "\n"
            result = _run(["crontab", "-"], input=new_crontab)
            if result.returncode != 0:
                msg = result.stderr.strip() or "crontab write failed"
                log.error("install_schedule failed: %s", msg)
                return {"success": False, "error": msg}
            log.info("Installed cron schedule at %s", canonical)
            return {"success": True, "platform": "linux", "time": canonical}
        except Exception as exc:
            log.exception("install_schedule error")
            return {"success": False, "error": str(exc)}

    # Windows path
    try:
        result = _run(cmd)
        if result.returncode != 0:
            msg = result.stderr.strip() or result.stdout.strip() or "schtasks create failed"
            log.error("install_schedule failed: %s", msg)
            return {"success": False, "error": msg}
        log.info("Installed Windows scheduled task at %s", canonical)
        return {"success": True, "platform": "windows", "time": canonical}
    except Exception as exc:
        log.exception("install_schedule error")
        return {"success": False, "error": str(exc)}


def remove_schedule() -> dict:
    """Remove the nightly scheduled task.

    Returns
    -------
    dict
        ``{"success": True, "platform": ...}`` on success,
        ``{"success": False, "error": ...}`` on failure.
    """
    if _IS_WINDOWS:
        try:
            result = _run(["schtasks", "/delete", "/tn", TASK_NAME, "/f"])
            if result.returncode != 0:
                msg = result.stderr.strip() or result.stdout.strip() or "schtasks delete failed"
                log.error("remove_schedule failed: %s", msg)
                return {"success": False, "error": msg}
            log.info("Removed Windows scheduled task '%s'", TASK_NAME)
            return {"success": True, "platform": "windows"}
        except Exception as exc:
            log.exception("remove_schedule error")
            return {"success": False, "error": str(exc)}
    else:
        try:
            existing = _run(["crontab", "-l"])
            if existing.returncode != 0:
                return {"success": True, "platform": "linux"}  # no crontab at all
            lines = existing.stdout.splitlines()
            filtered = [ln for ln in lines if "nightly.sh" not in ln]
            new_crontab = "\n".join(filtered) + "\n" if filtered else ""
            result = _run(["crontab", "-"], input=new_crontab)
            if result.returncode != 0:
                msg = result.stderr.strip() or "crontab write failed"
                log.error("remove_schedule failed: %s", msg)
                return {"success": False, "error": msg}
            log.info("Removed cron entry for nightly.sh")
            return {"success": True, "platform": "linux"}
        except Exception as exc:
            log.exception("remove_schedule error")
            return {"success": False, "error": str(exc)}


def is_scheduled() -> bool:
    """Return ``True`` if a nightly schedule currently exists."""
    if _IS_WINDOWS:
        try:
            result = _run(["schtasks", "/query", "/tn", TASK_NAME])
            return result.returncode == 0
        except Exception:
            return False
    else:
        try:
            result = _run(["crontab", "-l"])
            if result.returncode != 0:
                return False
            return any("nightly.sh" in ln for ln in result.stdout.splitlines())
        except Exception:
            return False


def get_schedule_info() -> dict:
    """Return details about the current nightly schedule.

    Returns
    -------
    dict
        ``{"scheduled": True, "time": "03:00", "next_run": ..., "last_result": ...}``
        when a schedule exists, or ``{"scheduled": False}`` otherwise.
    """
    if _IS_WINDOWS:
        try:
            result = _run([
                "schtasks", "/query", "/tn", TASK_NAME,
                "/v", "/fo", "list",
            ])
            if result.returncode != 0:
                return {"scheduled": False}

            info: dict = {"scheduled": True, "time": "", "next_run": "", "last_result": ""}
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("Start Time:"):
                    info["time"] = line.split(":", 1)[1].strip()
                elif line.startswith("Next Run Time:"):
                    info["next_run"] = line.split(":", 1)[1].strip()
                elif line.startswith("Last Run Time:"):
                    info["last_result"] = line.split(":", 1)[1].strip()
                elif line.startswith("Status:"):
                    info["status"] = line.split(":", 1)[1].strip()
            return info
        except Exception as exc:
            log.exception("get_schedule_info error")
            return {"scheduled": False}
    else:
        try:
            result = _run(["crontab", "-l"])
            if result.returncode != 0:
                return {"scheduled": False}
            for line in result.stdout.splitlines():
                if "nightly.sh" in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        minute, hour = parts[0], parts[1]
                        try:
                            canonical = f"{int(hour):02d}:{int(minute):02d}"
                        except ValueError:
                            canonical = f"{hour}:{minute}"
                        return {
                            "scheduled": True,
                            "time": canonical,
                            "next_run": "",
                            "last_result": "",
                        }
            return {"scheduled": False}
        except Exception as exc:
            log.exception("get_schedule_info error")
            return {"scheduled": False}
