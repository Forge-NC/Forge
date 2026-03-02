"""Sound manager for Forge Neural Cortex.

Plays wav files for UI events — boot, ready, thinking, etc.
Uses sounddevice (already installed for voice input).

Volume levels:
  - One-shot sounds (boot, ready, error, terminal, swapping): 60%
  - Looping sounds (thinking, indexing): 25% — subtle background
  - Fade-out over 1.5s when looping sound stops
"""

import logging
import threading
import time
import wave
from pathlib import Path
from typing import Optional

try:
    import numpy as np
    import sounddevice as sd
    HAS_AUDIO = True
except ImportError:
    HAS_AUDIO = False

log = logging.getLogger(__name__)

SOUNDS_DIR = Path(__file__).parent.parent / "ui" / "assets" / "sounds"

# Sound file mapping: state name -> wav filename
SOUND_MAP = {
    "boot":     "boot.wav",
    "ready":    "ready.wav",
    "thinking": "thinking.wav",
    "indexing":  "indexing.wav",
    "swapping": "swapping.wav",
    "error":    "error.wav",
    "terminal": "terminal.wav",
}

# Which sounds should loop until state changes
LOOPING_SOUNDS = {"thinking", "indexing"}

# Volume levels (0.0 - 1.0)
VOLUME_ONESHOT = 0.60    # one-shot: boot, ready, error, terminal
VOLUME_LOOP = 0.25       # looping: thinking, indexing — subtle background

# Fade-out duration when stopping a looping sound (seconds)
FADE_OUT_DURATION = 1.5


class SoundManager:
    """Plays wav sounds for Forge events. Thread-safe, non-blocking."""

    def __init__(self, enabled: bool = True, preload: bool = True):
        self._enabled = enabled and HAS_AUDIO
        self._cache: dict[str, tuple[np.ndarray, int]] = {}
        self._current_sound: Optional[str] = None
        self._loop_flag = threading.Event()
        self._stop_flag = threading.Event()  # signals fade-out
        self._loop_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Preload all sounds into memory so first play is instant
        if preload and self._enabled:
            self._preload_all()

    def _preload_all(self):
        """Load all sound files into cache at startup for zero-latency playback."""
        for name in SOUND_MAP:
            self._load(name)
        cached = len(self._cache)
        if cached:
            log.debug("Preloaded %d/%d sounds", cached, len(SOUND_MAP))

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value and HAS_AUDIO
        if not self._enabled:
            self.stop()

    def play(self, sound_name: str):
        """Play a sound by name. Non-blocking."""
        if not self._enabled:
            return

        with self._lock:
            # Don't restart the same sound
            if sound_name == self._current_sound:
                return

            # Stop any current looping sound (with fade-out)
            if self._loop_flag.is_set():
                self._stop_flag.set()
                self._loop_flag.clear()

            self._current_sound = sound_name

        data = self._load(sound_name)
        if data is None:
            return

        audio, samplerate = data

        try:
            if sound_name in LOOPING_SOUNDS:
                # Apply loop volume
                quiet_audio = audio * VOLUME_LOOP
                self._start_loop(quiet_audio, samplerate, sound_name)
            else:
                # One-shot: apply volume and play
                sd.stop()
                sd.play(audio * VOLUME_ONESHOT, samplerate)
        except Exception as e:
            log.debug("Sound play failed: %s", e)

    def stop(self):
        """Stop any currently playing sound immediately."""
        with self._lock:
            self._current_sound = None
            self._stop_flag.set()
            self._loop_flag.clear()
        try:
            sd.stop()
        except Exception:
            pass

    def stop_with_fade(self):
        """Stop looping sound with a fade-out."""
        with self._lock:
            if self._current_sound in LOOPING_SOUNDS:
                self._stop_flag.set()
                self._loop_flag.clear()
                self._current_sound = None
            else:
                self._current_sound = None
                try:
                    sd.stop()
                except Exception:
                    pass

    def on_state_change(self, new_state: str):
        """React to animation state changes from the dashboard.

        Maps animation states to sounds:
          thinking -> thinking (loop), indexing -> indexing (loop),
          swapping -> swapping, error -> error
          idle -> fade-out any looping sound
          tool_exec -> keep thinking sound playing (tool is part of thinking)
        """
        state = new_state.lower()

        if state in SOUND_MAP:
            self.play(state)
        elif state == "threat":
            # Threat uses error sound (urgent alert)
            self.play("error")
        elif state == "idle":
            # Idle = fade-out looping sounds
            self.stop_with_fade()
        elif state == "tool_exec":
            # Tool exec is part of thinking — keep thinking sound going
            pass

    def _load(self, sound_name: str) -> Optional[tuple]:
        """Load and cache a wav file. Returns (numpy_array, samplerate)."""
        if sound_name in self._cache:
            return self._cache[sound_name]

        filename = SOUND_MAP.get(sound_name)
        if not filename:
            return None

        path = SOUNDS_DIR / filename
        if not path.exists():
            log.debug("Sound file not found: %s", path)
            return None

        try:
            with wave.open(str(path), "rb") as wf:
                samplerate = wf.getframerate()
                n_frames = wf.getnframes()
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()

                raw = wf.readframes(n_frames)

                if sampwidth == 2:
                    audio = np.frombuffer(raw, dtype=np.int16)
                    audio = audio.astype(np.float32) / 32768.0
                elif sampwidth == 4:
                    audio = np.frombuffer(raw, dtype=np.int32)
                    audio = audio.astype(np.float32) / 2147483648.0
                else:
                    audio = np.frombuffer(raw, dtype=np.uint8)
                    audio = (audio.astype(np.float32) - 128.0) / 128.0

                if n_channels > 1:
                    audio = audio.reshape(-1, n_channels)

            self._cache[sound_name] = (audio, samplerate)
            return (audio, samplerate)
        except Exception as e:
            log.debug("Failed to load sound %s: %s", sound_name, e)
            return None

    def _start_loop(self, audio: np.ndarray, samplerate: int,
                    sound_name: str):
        """Start looping a sound in a background thread with fade-out support."""
        # Stop previous loop thread
        if self._loop_thread and self._loop_thread.is_alive():
            self._stop_flag.set()
            self._loop_flag.clear()
            self._loop_thread.join(timeout=2)

        self._loop_flag.set()
        self._stop_flag.clear()

        def loop_worker():
            try:
                while self._loop_flag.is_set():
                    sd.play(audio, samplerate)
                    duration = (audio.shape[0] if audio.ndim > 1
                                else len(audio)) / samplerate

                    # Wait for playback to finish or stop signal
                    elapsed = 0.0
                    while elapsed < duration:
                        if self._stop_flag.is_set():
                            # Fade out remaining playback
                            self._do_fade_out(audio, samplerate, elapsed)
                            return
                        if not self._loop_flag.is_set():
                            self._do_fade_out(audio, samplerate, elapsed)
                            return
                        time.sleep(0.05)
                        elapsed += 0.05
            except Exception as e:
                log.debug("Loop playback error: %s", e)

        self._loop_thread = threading.Thread(
            target=loop_worker, daemon=True,
            name=f"ForgeSound-{sound_name}")
        self._loop_thread.start()

    def _do_fade_out(self, audio: np.ndarray, samplerate: int,
                     current_pos: float):
        """Fade out the currently playing audio over FADE_OUT_DURATION seconds."""
        try:
            sd.stop()  # stop current playback

            # Calculate remaining audio from current position
            sample_pos = int(current_pos * samplerate)
            total_samples = audio.shape[0] if audio.ndim > 1 else len(audio)
            if sample_pos >= total_samples:
                return

            remaining = audio[sample_pos:]
            fade_samples = int(FADE_OUT_DURATION * samplerate)

            # Only fade what we have left (or the fade duration, whichever is shorter)
            fade_len = min(fade_samples, (remaining.shape[0] if remaining.ndim > 1
                                          else len(remaining)))
            if fade_len < samplerate // 10:
                return  # less than 100ms remaining, just stop

            fade_audio = remaining[:fade_len].copy()

            # Apply linear fade envelope
            if fade_audio.ndim == 1:
                envelope = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
                fade_audio *= envelope
            else:
                envelope = np.linspace(1.0, 0.0, fade_len, dtype=np.float32)
                fade_audio *= envelope[:, np.newaxis]

            sd.play(fade_audio, samplerate)
            sd.wait()
        except Exception as e:
            log.debug("Fade-out error: %s", e)
