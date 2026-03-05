"""Speech-to-text for Forge using faster-whisper.

Supports push-to-talk (hotkey) and VOX (voice-activated) modes.
All dependencies are optional — graceful fallback if not installed.

Install: pip install faster-whisper sounddevice pynput
"""

import logging
import threading
import time
from typing import Optional, Callable

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

log = logging.getLogger(__name__)

# Check optional dependencies
HAS_STT = False
HAS_AUDIO = False
HAS_HOTKEY = False

try:
    from faster_whisper import WhisperModel
    HAS_STT = True
except ImportError:
    pass

try:
    import sounddevice as sd
    HAS_AUDIO = True
except ImportError:
    pass

try:
    from pynput import keyboard as pynput_kb
    HAS_HOTKEY = True
except ImportError:
    pass


def check_voice_deps() -> dict:
    """Check which voice dependencies are available."""
    return {
        "stt": HAS_STT,
        "audio": HAS_AUDIO,
        "hotkey": HAS_HOTKEY,
        "ready": HAS_STT and HAS_AUDIO and HAS_NUMPY,
        "missing": [
            pkg for available, pkg in [
                (HAS_STT, "faster-whisper"),
                (HAS_AUDIO, "sounddevice"),
                (HAS_HOTKEY, "pynput"),
            ] if not available
        ],
    }


class VoiceInput:
    """Voice input for Forge terminal — push-to-talk with whisper STT.

    Usage:
        voice = VoiceInput(on_transcription=my_callback)
        voice.initialize()      # loads whisper model (~1s)
        voice.start_hotkey()    # starts listening for backtick key
        # ... user holds backtick, speaks, releases ...
        # on_transcription("user's spoken text") is called
        voice.stop()
    """

    SAMPLE_RATE = 16000
    CHANNELS = 1
    MIN_DURATION = 0.5       # minimum seconds to count as speech
    MIN_AMPLITUDE = 0.01     # minimum peak amplitude

    # VOX settings
    VOX_THRESHOLD = 0.02
    VOX_SILENCE_TIMEOUT = 1.5

    def __init__(self, model_size: str = "tiny",
                 hotkey: str = "`",
                 mode: str = "ptt",
                 language: str = "en",
                 on_transcription: Optional[Callable[[str], None]] = None,
                 on_state_change: Optional[Callable[[str], None]] = None):
        """
        Args:
            model_size: Whisper model size (tiny/base/small/medium)
            hotkey: Key for push-to-talk (default: backtick)
            mode: "ptt" (push-to-talk) or "vox" (voice-activated)
            on_transcription: callback(text) when speech is transcribed
            on_state_change: callback(state) for UI updates
                             states: "ready", "recording", "transcribing",
                                     "idle", "error"
        """
        self._model_size = model_size
        self._hotkey = hotkey
        self._mode = mode
        self._language = language
        self._on_transcription = on_transcription
        self._on_state_change = on_state_change

        self._model = None
        self._ready = False
        self._recording = False
        self._audio_buffer = []
        self._buffer_lock = threading.Lock()
        self._stream = None
        self._record_start = 0.0
        self._hotkey_listener = None
        self._ptt_pressed = False

        # VOX state
        self._vox_running = False
        self._vox_thread = None
        self._vox_muted = False

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, value: str):
        if value in ("ptt", "vox"):
            old = self._mode
            self._mode = value
            if old == "vox" and value == "ptt":
                self._stop_vox()
            elif old == "ptt" and value == "vox":
                self._start_vox()

    def initialize(self) -> bool:
        """Load the whisper model. Returns True on success."""
        if not HAS_STT:
            log.warning("faster-whisper not installed")
            return False
        if not HAS_AUDIO:
            log.warning("sounddevice not installed")
            return False

        # Enumerate audio devices for diagnostics
        try:
            devices = sd.query_devices()
            default_in = sd.query_devices(kind='input')
            log.info("Audio input device: %s", default_in.get('name', '?'))
        except Exception as e:
            log.warning("Failed to enumerate audio devices: %s", e)

        # Detect CUDA for GPU-accelerated transcription
        device = "cpu"
        compute_type = "int8"
        try:
            import torch
            if torch.cuda.is_available():
                device = "cuda"
                compute_type = "float16"
                log.info("CUDA detected — using GPU for Whisper")
        except ImportError:
            pass

        try:
            self._model = WhisperModel(
                self._model_size,
                device=device,
                compute_type=compute_type,
            )
            self._ready = True
            self._set_state("ready")
            log.info("Voice input initialized (whisper-%s, %s)",
                     self._model_size, device)
            return True
        except Exception as e:
            log.warning("Voice init failed: %s", e)
            self._set_state("error")
            return False

    def start_hotkey(self):
        """Start listening for the PTT hotkey."""
        if not HAS_HOTKEY:
            log.warning("pynput not installed — hotkey disabled")
            return

        def on_press(key):
            try:
                if hasattr(key, 'char') and key.char == self._hotkey:
                    if not self._ptt_pressed:
                        self._ptt_pressed = True
                        if self._mode == "ptt":
                            self._start_recording()
            except AttributeError:
                pass

        def on_release(key):
            try:
                if hasattr(key, 'char') and key.char == self._hotkey:
                    self._ptt_pressed = False
                    if self._mode == "ptt" and self._recording:
                        threading.Thread(
                            target=self._stop_and_transcribe,
                            daemon=True).start()
            except AttributeError:
                pass

        self._hotkey_listener = pynput_kb.Listener(
            on_press=on_press, on_release=on_release)
        self._hotkey_listener.daemon = True
        self._hotkey_listener.start()
        log.info("Hotkey listener started (key='%s', mode=%s)",
                 self._hotkey, self._mode)

        if self._mode == "vox":
            self._start_vox()

    def stop(self):
        """Stop everything — recording, hotkey, VOX."""
        self._stop_vox()
        if self._recording:
            self._recording = False
            if self._stream:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
                self._hotkey_listener.join(timeout=2.0)
            except Exception:
                pass
            self._hotkey_listener = None
        self._set_state("idle")

    # ── PTT recording ──

    def _start_recording(self):
        if not self._ready or self._recording:
            return

        self._audio_buffer = []
        self._recording = True
        self._record_start = time.monotonic()
        self._set_state("recording")

        try:
            self._stream = sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype="float32",
                callback=self._audio_callback,
                blocksize=1024,
            )
            self._stream.start()
        except Exception as e:
            log.warning("Failed to start recording: %s", e)
            self._recording = False
            self._set_state("error")

    def _stop_and_transcribe(self):
        """Stop recording and run transcription in background."""
        if not self._recording:
            return

        self._recording = False
        duration = time.monotonic() - self._record_start

        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        with self._buffer_lock:
            if not self._audio_buffer:
                self._set_state("ready")
                return
            audio = np.concatenate(self._audio_buffer, axis=0).flatten()
            self._audio_buffer = []

        if len(audio) < self.SAMPLE_RATE * self.MIN_DURATION:
            self._set_state("ready")
            return
        if np.abs(audio).max() < self.MIN_AMPLITUDE:
            self._set_state("ready")
            return

        self._set_state("transcribing")
        text = self._transcribe(audio)

        if text and self._on_transcription:
            self._on_transcription(text)

        self._set_state("ready")

    def _audio_callback(self, indata, frames, time_info, status):
        if self._recording:
            with self._buffer_lock:
                self._audio_buffer.append(indata.copy())

    # ── VOX mode ──

    def _start_vox(self):
        if not self._ready or self._vox_running:
            return
        self._vox_running = True
        self._vox_thread = threading.Thread(
            target=self._vox_loop, daemon=True, name="ForgeVOX")
        self._vox_thread.start()
        self._set_state("ready")

    def _stop_vox(self):
        self._vox_running = False
        if self._vox_thread:
            self._vox_thread.join(timeout=2)
            self._vox_thread = None

    def _vox_loop(self):
        """Continuous mic monitoring — transcribe when silence detected."""
        try:
            stream = sd.InputStream(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype="float32",
                blocksize=1600,  # 100ms chunks at 16kHz
            )
            stream.start()
        except Exception as e:
            log.warning("VOX stream failed: %s", e)
            self._vox_running = False
            return

        speech_buffer = []
        is_speaking = False
        silence_start = 0.0

        try:
            while self._vox_running:
                data, overflowed = stream.read(1600)
                if self._vox_muted:
                    speech_buffer = []
                    is_speaking = False
                    continue

                chunk = data.flatten()
                rms = float(np.sqrt(np.mean(chunk ** 2)))

                if rms > self.VOX_THRESHOLD:
                    is_speaking = True
                    silence_start = 0.0
                    speech_buffer.append(chunk)
                    self._set_state("recording")
                elif is_speaking:
                    speech_buffer.append(chunk)
                    if silence_start == 0.0:
                        silence_start = time.monotonic()
                    elif time.monotonic() - silence_start > self.VOX_SILENCE_TIMEOUT:
                        # Silence timeout — transcribe
                        audio = np.concatenate(speech_buffer)
                        speech_buffer = []
                        is_speaking = False
                        silence_start = 0.0

                        if (len(audio) >= self.SAMPLE_RATE * self.MIN_DURATION
                                and np.abs(audio).max() >= self.MIN_AMPLITUDE):
                            self._set_state("transcribing")
                            text = self._transcribe(audio)
                            if text and self._on_transcription:
                                self._on_transcription(text)
                        self._set_state("ready")
        finally:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    # ── Transcription ──

    def _transcribe(self, audio) -> str:
        """Run whisper on audio array. Returns text or empty string."""
        try:
            segments, info = self._model.transcribe(
                audio,
                language=self._language,
                beam_size=3,
                vad_filter=True,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            if text:
                log.info("Transcribed: %s", text[:80])
            return text
        except Exception as e:
            log.warning("Transcription failed: %s", e)
            return ""

    # ── State callbacks ──

    def _set_state(self, state: str):
        if self._on_state_change:
            try:
                self._on_state_change(state)
            except Exception:
                pass
