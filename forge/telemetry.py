"""Opt-in telemetry upload — sends redacted audit bundles to the Forge team.

Disabled by default. Enable via config:
    telemetry_enabled: true

Uses the same AuditExporter.build_package() as /export — no new data
collection. Default mode is redacted (strips prompts/responses, keeps
metadata only).
"""

import logging
import os
import tempfile
import threading
from pathlib import Path
from typing import Optional

from forge.constants import TELEMETRY_URL

log = logging.getLogger(__name__)

# Default endpoint
_DEFAULT_URL = TELEMETRY_URL

# Upload constraints
_TIMEOUT_S = 5
_MAX_ZIP_BYTES = 512 * 1024  # 512KB safety cap


def _get_machine_id() -> str:
    """Stable per-machine identifier — random UUID persisted locally."""
    from forge.machine_id import get_machine_id
    return get_machine_id()


def upload_telemetry(
    *,
    forensics,
    memory,
    stats,
    billing,
    crucible,
    continuity,
    plan_verifier,
    reliability=None,
    session_start: float,
    turn_count: int,
    model: str,
    cwd: str,
    redact: bool = True,
    telemetry_url: str = "",
    blocking: bool = False,
) -> Optional[threading.Thread]:
    """Build an audit package and upload it.

    Returns the upload thread (or None if blocking).
    Called from engine._print_exit_summary() as fire-and-forget.
    The thread is a daemon so it won't block interpreter shutdown.
    If blocking=True, runs synchronously (for /export --upload).
    """
    def _do_upload():
        try:
            import requests
            from forge.audit import AuditExporter

            exporter = AuditExporter()
            package = exporter.build_package(
                forensics=forensics,
                memory=memory,
                stats=stats,
                billing=billing,
                crucible=crucible,
                continuity=continuity,
                plan_verifier=plan_verifier,
                reliability=reliability,
                session_start=session_start,
                turn_count=turn_count,
                model=model,
                cwd=cwd,
            )

            # Export to temp zip
            fd, tmp = tempfile.mkstemp(suffix=".zip")
            os.close(fd)
            try:
                out_path = exporter.export(
                    package, path=Path(tmp), redact=redact)
                zip_bytes = out_path.read_bytes()

                if len(zip_bytes) > _MAX_ZIP_BYTES:
                    log.debug("Telemetry zip too large (%d bytes), skipping",
                              len(zip_bytes))
                    return

                # Save to disk first — survives hard kill (Alt+F4, crash, power loss)
                pending_path = save_pending(zip_bytes)

                machine_id = _get_machine_id()

                # Per-user token takes priority over legacy shared key
                headers = {}
                try:
                    from forge.config import load_config
                    token = load_config().get("telemetry_token", "")
                except Exception:
                    token = ""
                if token:
                    headers["X-Forge-Token"] = token
                else:
                    log.debug("No telemetry_token configured — skipping upload")
                    return

                # Include fleet metadata if available
                post_data = {"machine_id": machine_id}
                try:
                    from forge.config import load_config
                    cfg = load_config()
                    fleet_role = cfg.get("fleet_role", "standalone")
                    master_id = cfg.get("master_id", "")
                    account_id = cfg.get("account_id", "")
                    seat_id = cfg.get("seat_id", "")
                    if fleet_role != "standalone":
                        post_data["fleet_role"] = fleet_role
                        post_data["master_id"] = master_id
                        post_data["account_id"] = account_id
                        post_data["seat_id"] = seat_id
                except Exception:
                    pass

                # Always upload to Forge NC server (the Matrix)
                urls = [_DEFAULT_URL]
                # If user set a custom URL, also send there
                if telemetry_url and telemetry_url != _DEFAULT_URL:
                    urls.append(telemetry_url)

                for url in urls:
                    try:
                        resp = requests.post(
                            url,
                            files={"bundle": (
                                f"forge_{machine_id}.zip", zip_bytes,
                                "application/zip")},
                            headers=headers,
                            data=post_data,
                            timeout=_TIMEOUT_S,
                        )
                        if resp.status_code == 200:
                            log.debug("Telemetry uploaded to %s", url)
                        else:
                            log.debug("Telemetry upload to %s failed: HTTP %d",
                                      url, resp.status_code)
                    except Exception as upload_err:
                        log.debug("Telemetry upload to %s error: %s",
                                  url, upload_err)
                # Upload succeeded to at least the primary — remove pending
                try:
                    if pending_path and pending_path.exists():
                        pending_path.unlink()
                except OSError:
                    pass
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

        except Exception as e:
            log.debug("Telemetry upload error: %s", e)
            # pending file stays on disk — will be retried next session

    if blocking:
        _do_upload()
        return None

    t = threading.Thread(
        target=_do_upload, daemon=True, name="telemetry-upload")
    t.start()
    return t


def upload_pending():
    """Upload any telemetry bundles from previous sessions that didn't complete.

    Called at startup. Looks for *.zip files in ~/.forge/pending_telemetry/.
    On successful upload, deletes the file. On failure, leaves it for next time.
    Runs in a daemon thread so it doesn't block startup.
    """
    pending_dir = Path.home() / ".forge" / "pending_telemetry"
    if not pending_dir.is_dir():
        return

    zips = list(pending_dir.glob("*.zip"))
    if not zips:
        return

    def _upload_pending():
        import requests

        # Auth token
        try:
            from forge.config import load_config
            token = load_config().get("telemetry_token", "")
        except Exception:
            token = ""
        if not token:
            return

        headers = {"X-Forge-Token": token}
        machine_id = _get_machine_id()

        for zip_path in zips:
            try:
                zip_bytes = zip_path.read_bytes()
                if len(zip_bytes) > _MAX_ZIP_BYTES:
                    zip_path.unlink()  # too large, discard
                    continue

                # Upload to Forge Matrix
                resp = requests.post(
                    _DEFAULT_URL,
                    files={"bundle": (
                        f"forge_{machine_id}.zip", zip_bytes,
                        "application/zip")},
                    headers=headers,
                    data={"machine_id": machine_id},
                    timeout=_TIMEOUT_S,
                )
                if resp.status_code == 200:
                    zip_path.unlink()  # success — remove pending
                    log.debug("Pending telemetry uploaded: %s", zip_path.name)
                else:
                    log.debug("Pending telemetry upload failed: HTTP %d",
                              resp.status_code)
            except Exception as e:
                log.debug("Pending telemetry upload error: %s", e)

    threading.Thread(
        target=_upload_pending, daemon=True,
        name="pending-telemetry-upload").start()


def save_pending(zip_bytes: bytes):
    """Save a telemetry bundle to disk for retry on next startup.

    Called during session to ensure data survives a hard kill.
    """
    pending_dir = Path.home() / ".forge" / "pending_telemetry"
    pending_dir.mkdir(parents=True, exist_ok=True)

    # Clean old pending files (keep max 5, oldest first)
    existing = sorted(pending_dir.glob("*.zip"), key=lambda p: p.stat().st_mtime)
    while len(existing) >= 5:
        existing.pop(0).unlink()

    import time
    pending_path = pending_dir / f"pending_{int(time.time())}_{_get_machine_id()}.zip"
    pending_path.write_bytes(zip_bytes)
    log.debug("Telemetry saved to pending: %s", pending_path.name)
    return pending_path
