"""Opt-in telemetry upload — sends redacted audit bundles to the Forge team.

Disabled by default. Enable via config:
    telemetry_enabled: true

Uses the same AuditExporter.build_package() as /export — no new data
collection. Default mode is redacted (strips prompts/responses, keeps
metadata only).
"""

import hashlib
import logging
import os
import socket
import tempfile
import threading
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Shared API key — prevents drive-by spam, not cryptographic security.
_API_KEY = "fg_tel_2026_e7eb55900b70bd84eaeb62f7cd0153e7"

# Default endpoint
_DEFAULT_URL = "https://dirt-star.com/Forge/telemetry_receiver.php"

# Upload constraints
_TIMEOUT_S = 5
_MAX_ZIP_BYTES = 512 * 1024  # 512KB safety cap


def _get_machine_id() -> str:
    """Stable per-machine identifier (same algorithm as audit.py)."""
    return hashlib.sha256(socket.gethostname().encode()).hexdigest()[:12]


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

                url = telemetry_url or _DEFAULT_URL
                machine_id = _get_machine_id()

                resp = requests.post(
                    url,
                    files={"bundle": (
                        f"forge_{machine_id}.zip", zip_bytes,
                        "application/zip")},
                    headers={"X-Forge-Key": _API_KEY},
                    data={"machine_id": machine_id},
                    timeout=_TIMEOUT_S,
                )
                if resp.status_code == 200:
                    log.debug("Telemetry uploaded successfully")
                else:
                    log.debug("Telemetry upload failed: HTTP %d",
                              resp.status_code)
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

        except Exception as e:
            log.debug("Telemetry upload error: %s", e)

    if blocking:
        _do_upload()
        return None

    t = threading.Thread(
        target=_do_upload, daemon=True, name="telemetry-upload")
    t.start()
    return t
