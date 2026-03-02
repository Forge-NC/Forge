"""Floating Neural Cortex overlay -- brain animation for nightly test runs.

Standalone CTk window driven by queue.Queue commands:
    ("state", name)   -- set animation state
    ("status", text)  -- update status label
    ("close",)        -- destroy and exit

Reuses AnimationEngine from forge.ui.dashboard.
"""

import logging
import platform
import queue
import time
import tkinter as tk
from pathlib import Path

try:
    import customtkinter as ctk
    from PIL import Image
    import numpy as np
    HAS_GUI_DEPS = True
except ImportError:
    HAS_GUI_DEPS = False

from forge.ui.dashboard import (
    AnimationEngine, AnimState, BRAIN_IMAGE_PATH,
)

log = logging.getLogger(__name__)

# State-name mapping (queue strings -> AnimState enum)
_STATE_MAP: dict[str, AnimState] = {
    "boot": AnimState.BOOT, "idle": AnimState.IDLE,
    "thinking": AnimState.THINKING, "tool_exec": AnimState.TOOL_EXEC,
    "indexing": AnimState.INDEXING, "swapping": AnimState.SWAPPING,
    "error": AnimState.ERROR, "threat": AnimState.THREAT,
    "pass": AnimState.PASS,
    # Semantic aliases for test-runner integration
    "running_test": AnimState.THINKING, "test_passed": AnimState.PASS,
    "test_failed": AnimState.ERROR, "uploading": AnimState.INDEXING,
    "complete": AnimState.IDLE, "resource_check": AnimState.TOOL_EXEC,
    "initializing": AnimState.BOOT,
}

_BG = "#0d1117"
_QUEUE_POLL_MS = 50
_MARGIN = 20


def _create_engine(brain_path: Path, size: int) -> "AnimationEngine":
    """Load brain PNG at *size* and return a populated AnimationEngine."""
    img = Image.open(str(brain_path)).convert("RGBA").resize(
        (size, size), Image.LANCZOS)
    arr = np.array(img, dtype=np.float32)
    rgb, alpha = arr[:, :, :3], arr[:, :, 3] / 255.0
    bri = np.max(rgb, axis=2) / 255.0
    pathway = np.clip((bri * alpha) ** 0.7, 0, 1)
    depth = 1.0 - np.clip((bri * alpha) ** 0.5, 0, 1)
    cy, cx = size / 2.0, size / 2.0
    yy = np.arange(size, dtype=np.float32).reshape(-1, 1)
    xx = np.arange(size, dtype=np.float32).reshape(1, -1)
    dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    wave_dist = dist / np.sqrt(cy ** 2 + cx ** 2)
    sweep_x = np.broadcast_to(xx / float(size), (size, size)).copy()
    return AnimationEngine(pathway, wave_dist, depth, rgb, alpha, sweep_x)


class CortexOverlay:
    """Floating brain-animation window driven by queue commands."""

    def __init__(self, cmd_queue: queue.Queue, *,
                 position: str = "top_right", size: int = 180):
        self._queue = cmd_queue
        self._position = position
        self._size = size
        self._win_w = size
        self._win_h = size + 40
        self._root = None
        self._brain_lbl = None
        self._status_lbl = None
        self._engine = None
        self._last_tick = 0.0
        self._running = False
        self._drag_x = self._drag_y = 0

    # -- public API ---------------------------------------------------

    def run(self):
        """Build window, start loops, enter mainloop. Call from a thread."""
        if not HAS_GUI_DEPS:
            log.warning("cortex_overlay: missing deps (ctk/PIL/numpy)")
            return
        self._engine = _create_engine(BRAIN_IMAGE_PATH, self._size)
        self._build_window()
        self._last_tick = time.monotonic()
        self._running = True
        self._root.after(_QUEUE_POLL_MS, self._poll_queue)
        self._root.after(self._interval(), self._animate)
        self._root.mainloop()

    # -- window -------------------------------------------------------

    def _screen_size(self):
        """Return (width, height) using a disposable Tk probe."""
        try:
            probe = tk.Tk()
            probe.withdraw()
            w, h = probe.winfo_screenwidth(), probe.winfo_screenheight()
            probe.destroy()
            return w, h
        except Exception:
            return 1920, 1080

    def _corner_xy(self):
        sw, sh = self._screen_size()
        x = (sw - self._win_w - _MARGIN) if "right" in self._position else _MARGIN
        y = (sh - self._win_h - _MARGIN) if "bottom" in self._position else _MARGIN
        return x, y

    def _build_window(self):
        root = ctk.CTk()
        root.title("Cortex")
        cx, cy = self._corner_xy()
        root.geometry(f"{self._win_w}x{self._win_h}+{cx}+{cy}")
        root.overrideredirect(True)
        root.wm_attributes("-topmost", True)
        root.configure(fg_color=_BG)
        if platform.system() == "Windows":
            try:
                root.wm_attributes("-transparentcolor", "#010101")
            except Exception:
                pass

        self._brain_lbl = ctk.CTkLabel(
            root, text="", width=self._size, height=self._size, fg_color=_BG)
        self._brain_lbl.pack(side="top", fill="x")

        self._status_lbl = ctk.CTkLabel(
            root, text="initializing...", height=40,
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#cccccc", fg_color=_BG, anchor="center")
        self._status_lbl.pack(side="top", fill="x")

        self._brain_lbl.bind("<ButtonPress-1>", self._drag_start)
        self._brain_lbl.bind("<B1-Motion>", self._drag_move)
        self._root = root

    # -- drag ---------------------------------------------------------

    def _drag_start(self, ev):
        self._drag_x, self._drag_y = ev.x, ev.y

    def _drag_move(self, ev):
        if self._root is None:
            return
        nx = self._root.winfo_x() + ev.x - self._drag_x
        ny = self._root.winfo_y() + ev.y - self._drag_y
        self._root.geometry(f"+{nx}+{ny}")

    # -- queue --------------------------------------------------------

    def _poll_queue(self):
        if not self._running:
            return
        try:
            while True:
                self._handle(self._queue.get_nowait())
                if not self._running:
                    return
        except queue.Empty:
            pass
        if self._running and self._root:
            self._root.after(_QUEUE_POLL_MS, self._poll_queue)

    def _handle(self, cmd: tuple):
        if not cmd:
            return
        action = cmd[0]
        if action == "state" and len(cmd) >= 2:
            st = _STATE_MAP.get(str(cmd[1]).lower())
            if st and self._engine:
                self._engine.set_state(st)
        elif action == "status" and len(cmd) >= 2:
            if self._status_lbl:
                self._status_lbl.configure(text=str(cmd[1])[:40])
        elif action == "close":
            self._shutdown()

    # -- animation ----------------------------------------------------

    def _interval(self) -> int:
        if not self._engine:
            return 100
        return max(1000 // max(self._engine.fps, 1), 16)

    def _animate(self):
        if not self._running or not self._engine or not self._root:
            return
        now = time.monotonic()
        self._engine.advance(now - self._last_tick)
        self._last_tick = now

        frame = self._engine.render_frame()
        pil = Image.fromarray(frame, "RGBA")
        cimg = ctk.CTkImage(light_image=pil, dark_image=pil,
                             size=(self._size, self._size))
        self._brain_lbl.configure(image=cimg)
        self._brain_lbl._ctk_img_ref = cimg  # prevent GC

        self._root.after(self._interval(), self._animate)

    # -- shutdown -----------------------------------------------------

    def _shutdown(self):
        self._running = False
        if self._root:
            try:
                self._root.destroy()
            except Exception:
                pass
            self._root = None

    # -- demo ---------------------------------------------------------

    @classmethod
    def demo(cls):
        """Cycle through all states with 3s delays for visual testing."""
        import threading
        q = queue.Queue()
        overlay = cls(q, position="top_right", size=180)
        seq = [
            ("boot", "Booting..."), ("idle", "Idle"),
            ("thinking", "Thinking..."), ("tool_exec", "Executing tool"),
            ("indexing", "Indexing repo"), ("swapping", "Context swap"),
            ("error", "Error detected"), ("threat", "THREAT"),
            ("pass", "All tests passed"), ("running_test", "test_billing.py"),
            ("test_passed", "PASSED"), ("test_failed", "FAILED"),
            ("uploading", "Uploading results"),
            ("resource_check", "Checking GPU"),
            ("initializing", "Init phase"), ("complete", "Done"),
        ]

        def feed():
            time.sleep(1.0)
            for state, text in seq:
                q.put(("state", state))
                q.put(("status", text))
                time.sleep(3.0)
            time.sleep(1.0)
            q.put(("close",))

        threading.Thread(target=feed, daemon=True).start()
        overlay.run()


if __name__ == "__main__":
    CortexOverlay.demo()
