"""Window geometry persistence — saves/restores position and size.

All Forge windows import from here so there's no circular dependency.
Data stored in ~/.forge/window_geometry.json.
"""
from __future__ import annotations

import json
from pathlib import Path


class WindowGeo:
    """Save and restore window geometry (position + size) across sessions.

    Usage:
        WindowGeo.restore("dashboard", widget, default="400x700")
        WindowGeo.track("dashboard", widget)   # auto-saves on move/resize
    """
    _GEO_FILE = Path.home() / ".forge" / "window_geometry.json"
    _pending: "dict[str, object]" = {}

    @classmethod
    def _load(cls) -> dict:
        try:
            if cls._GEO_FILE.exists():
                return json.loads(cls._GEO_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    @classmethod
    def _flush(cls, win_id: str, geo: str) -> None:
        try:
            data = cls._load()
            data[win_id] = geo
            cls._GEO_FILE.write_text(
                json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    @classmethod
    def restore(cls, win_id: str, widget, default: str = "") -> None:
        """Apply saved geometry, falling back to *default* if none saved."""
        geo = cls._load().get(win_id, "")
        target = geo or default
        if target:
            try:
                widget.geometry(target)
                return
            except Exception:
                pass
            if default and default != target:
                try:
                    widget.geometry(default)
                except Exception:
                    pass

    @classmethod
    def track(cls, win_id: str, widget) -> None:
        """Bind <Configure> to persist geometry changes (debounced 600 ms)."""
        def _on_configure(event):
            if event.widget is not widget:
                return
            old = cls._pending.get(win_id)
            if old is not None:
                try:
                    widget.after_cancel(old)
                except Exception:
                    pass
            cls._pending[win_id] = widget.after(
                600, lambda: cls._save_now(win_id, widget))

        widget.bind("<Configure>", _on_configure, add="+")

    @classmethod
    def _save_now(cls, win_id: str, widget) -> None:
        cls._pending.pop(win_id, None)
        try:
            geo = widget.geometry()
            # geometry() returns e.g. "960x720+100+200"
            # Skip if window is minimized / withdrawn
            if geo and "x" in geo:
                cls._flush(win_id, geo)
        except Exception:
            pass
