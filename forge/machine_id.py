"""Stable anonymous machine identifier.

Generated once as a random 12-char hex string and persisted in
~/.forge/machine_id. Never derived from hostname or any user
environment data — clean for trust and compliance.

Optional telemetry_label in config gives machines a human-friendly
nickname (e.g., "DirtStar-RTX5070") for the fleet dashboard.
"""

import uuid
from pathlib import Path


def get_machine_id() -> str:
    """Return stable anonymous machine identifier.

    Generated once on first call, persists forever in ~/.forge/machine_id.
    """
    id_file = Path.home() / ".forge" / "machine_id"
    if id_file.exists():
        mid = id_file.read_text(encoding="utf-8").strip()
        if mid:
            return mid
    mid = uuid.uuid4().hex[:12]
    id_file.parent.mkdir(parents=True, exist_ok=True)
    id_file.write_text(mid, encoding="utf-8")
    return mid


def get_machine_label() -> str:
    """Return user-set nickname, or auto-generate from hostname + GPU."""
    try:
        from forge.config import load_config
        label = load_config().get("telemetry_label", "")
        if label:
            return label
        # Auto-generate: hostname-shortid
        import platform
        hostname = platform.node() or "machine"
        short_id = get_machine_id()[:6]
        return f"{hostname}-{short_id}"
    except Exception:
        return ""
