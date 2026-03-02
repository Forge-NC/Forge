"""Crucible threat overlay — pops up the avatar when a threat is detected.

Shows the Crucible eye avatar in a small borderless window that
appears in the bottom-right corner of the screen. Auto-dismisses
after a timeout, or stays until the user makes a choice.
"""

import threading
import logging
from pathlib import Path
from typing import Optional

from forge.ui.themes import _MONO_FAMILY

log = logging.getLogger(__name__)

_ASSET_PATH = Path(__file__).parent / "assets" / "crucible.png"

# Singleton overlay reference
_overlay_instance = None
_overlay_lock = threading.Lock()


def show_crucible_overlay(threat_text: str = "THREAT DETECTED",
                          duration_ms: int = 0,
                          level: str = "WARNING"):
    """Show the Crucible avatar overlay.

    Args:
        threat_text: Short text to display under the avatar.
        duration_ms: Auto-dismiss after this many ms. 0 = stay until dismiss().
        level: "WARNING", "CRITICAL", "SUSPICIOUS" — affects border color.
    """
    # Run in a thread so it doesn't block the terminal
    t = threading.Thread(
        target=_show_overlay_thread,
        args=(threat_text, duration_ms, level),
        daemon=True,
        name="CrucibleOverlay",
    )
    t.start()


def dismiss_crucible_overlay():
    """Dismiss the overlay if it's showing."""
    global _overlay_instance
    with _overlay_lock:
        if _overlay_instance is not None:
            try:
                _overlay_instance.destroy()
            except Exception:
                pass
            _overlay_instance = None


def _show_overlay_thread(threat_text: str, duration_ms: int, level: str):
    """Create and show the overlay in its own Tk mainloop."""
    global _overlay_instance

    try:
        import tkinter as tk
        from PIL import Image, ImageTk
    except ImportError:
        log.debug("Crucible overlay requires tkinter + Pillow")
        return

    if not _ASSET_PATH.exists():
        log.debug("Crucible avatar not found at %s", _ASSET_PATH)
        return

    # Grab theme colors for overlay background/text
    try:
        from forge.ui.themes import get_colors
        _tc = get_colors()
        _bg = _tc.get("bg_dark", "#0a0a0a")
        _fg = _tc.get("white", "#e0e0e0")
    except Exception:
        _bg = "#0a0a0a"
        _fg = "#e0e0e0"

    # Dismiss any existing overlay
    dismiss_crucible_overlay()

    try:
        root = tk.Tk()
        root.withdraw()  # hide the root window

        overlay = tk.Toplevel(root)
        overlay.overrideredirect(True)  # borderless
        overlay.attributes("-topmost", True)
        overlay.configure(bg=_bg)

        # Try to make it semi-transparent on Windows
        try:
            overlay.attributes("-alpha", 0.95)
        except Exception:
            pass

        # Level-based colors (semantic, not theme-dependent)
        colors = {
            "CRITICAL": "#ff2020",
            "WARNING": "#ff8800",
            "SUSPICIOUS": "#ffcc00",
        }
        accent = colors.get(level, "#ff8800")

        # Load and resize the avatar
        try:
            img = Image.open(str(_ASSET_PATH))
            img = img.resize((128, 128), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
        except Exception as e:
            log.debug("Failed to load crucible avatar: %s", e)
            root.destroy()
            return

        # Layout
        frame = tk.Frame(overlay, bg=_bg, padx=8, pady=6,
                         highlightbackground=accent,
                         highlightcolor=accent,
                         highlightthickness=2)
        frame.pack(fill="both", expand=True)

        # Avatar
        img_label = tk.Label(frame, image=photo, bg=_bg)
        img_label.image = photo  # prevent GC
        img_label.pack(pady=(4, 2))

        # "CRUCIBLE" header
        header = tk.Label(frame, text="CRUCIBLE",
                          font=(_MONO_FAMILY, 13, "bold"),
                          fg=accent, bg=_bg)
        header.pack()

        # Threat text
        text_label = tk.Label(frame, text=threat_text,
                              font=(_MONO_FAMILY, 11),
                              fg=_fg, bg=_bg,
                              wraplength=160, justify="center")
        text_label.pack(pady=(2, 4))

        # Position: bottom-right of screen
        overlay.update_idletasks()
        w = overlay.winfo_reqwidth()
        h = overlay.winfo_reqheight()
        screen_w = overlay.winfo_screenwidth()
        screen_h = overlay.winfo_screenheight()
        x = screen_w - w - 20
        y = screen_h - h - 60  # above taskbar
        overlay.geometry(f"+{x}+{y}")

        # Store reference
        with _overlay_lock:
            _overlay_instance = overlay

        # Click to dismiss
        def _dismiss(event=None):
            try:
                root.destroy()
            except Exception:
                pass
            with _overlay_lock:
                global _overlay_instance
                _overlay_instance = None

        overlay.bind("<Button-1>", _dismiss)

        # Auto-dismiss
        if duration_ms > 0:
            overlay.after(duration_ms, _dismiss)

        # Fade-in animation
        try:
            overlay.attributes("-alpha", 0.0)
            def _fade_in(step=0):
                if step <= 10:
                    alpha = step / 10.0 * 0.95
                    try:
                        overlay.attributes("-alpha", alpha)
                        overlay.after(30, lambda: _fade_in(step + 1))
                    except Exception:
                        pass
            _fade_in()
        except Exception:
            pass

        root.mainloop()

    except Exception as e:
        log.debug("Crucible overlay failed: %s", e)
