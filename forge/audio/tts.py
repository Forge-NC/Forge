"""Text-to-speech for Forge — dual-engine support.

Two TTS backends:
  - "edge"  : Microsoft Edge neural voices via edge-tts (requires internet)
  - "local" : Offline system voices via pyttsx3 (works fully offline)

Users choose their preferred engine in config.yaml or the Settings dialog.
Falls back gracefully: if the preferred engine isn't installed, tries the other.

Install: pip install edge-tts   (cloud, high quality)
         pip install pyttsx3    (offline, system voices)
"""

import asyncio
import io
import logging
import tempfile
import threading
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# --- Engine availability ---
HAS_EDGE_TTS = False
HAS_PYTTSX3 = False
HAS_PLAYBACK = False

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    pass

try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    pass

try:
    import sounddevice as sd
    import numpy as np
    HAS_PLAYBACK = True
except ImportError:
    pass


# --- Edge-tts voice options ---
DEFAULT_EDGE_VOICE = "en-US-GuyNeural"
EDGE_VOICE_OPTIONS = [
    ("en-US-GuyNeural", "Guy (US male)"),
    ("en-US-ChristopherNeural", "Christopher (US male)"),
    ("en-US-EricNeural", "Eric (US male)"),
    ("en-US-JennyNeural", "Jenny (US female)"),
    ("en-US-AriaNeural", "Aria (US female)"),
]

# --- pyttsx3 settings ---
PYTTSX3_RATE = 175   # words per minute (default ~200, slightly slower is clearer)
PYTTSX3_VOLUME = 0.9

# TTS rate adjustment for edge-tts
SPEAK_RATE = "+5%"
SPEAK_VOLUME = "+0%"


def get_available_engines():
    """Return list of available TTS engine names."""
    engines = []
    if HAS_EDGE_TTS:
        engines.append("edge")
    if HAS_PYTTSX3:
        engines.append("local")
    return engines


def get_engine_info(engine: str) -> dict:
    """Return info dict about a TTS engine."""
    if engine == "edge":
        return {
            "name": "Edge Neural TTS",
            "quality": "High (neural voices)",
            "requires_internet": True,
            "installed": HAS_EDGE_TTS,
        }
    elif engine == "local":
        return {
            "name": "System TTS (pyttsx3)",
            "quality": "Standard (system voices)",
            "requires_internet": False,
            "installed": HAS_PYTTSX3,
        }
    return {"name": "Unknown", "quality": "N/A", "requires_internet": False, "installed": False}


class TextToSpeech:
    """Non-blocking TTS with dual-engine support (edge-tts / pyttsx3)."""

    def __init__(self, voice: str = DEFAULT_EDGE_VOICE, enabled: bool = True,
                 engine: str = "edge"):
        self._voice = voice
        self._engine = self._resolve_engine(engine)
        self._enabled = enabled and self._engine is not None
        self._speaking = False
        self._stop_flag = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._pyttsx3_engine = None  # lazy init

        if self._enabled:
            log.debug("TTS initialized (engine=%s, voice=%s)", self._engine, voice)

    @staticmethod
    def _resolve_engine(preferred: str) -> Optional[str]:
        """Resolve preferred engine, falling back if unavailable."""
        if preferred == "edge" and HAS_EDGE_TTS and HAS_PLAYBACK:
            return "edge"
        if preferred == "local" and HAS_PYTTSX3:
            return "local"
        # Fallback: try the other engine
        if preferred == "edge" and HAS_PYTTSX3:
            log.debug("edge-tts unavailable, falling back to pyttsx3")
            return "local"
        if preferred == "local" and HAS_EDGE_TTS and HAS_PLAYBACK:
            log.debug("pyttsx3 unavailable, falling back to edge-tts")
            return "edge"
        # Neither available
        return None

    @property
    def engine(self) -> Optional[str]:
        return self._engine

    @engine.setter
    def engine(self, value: str):
        resolved = self._resolve_engine(value)
        if resolved:
            self.stop()
            self._engine = resolved
            self._enabled = True
            log.debug("TTS engine switched to: %s", resolved)
        else:
            log.warning("TTS engine '%s' not available", value)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value and self._engine is not None
        if not self._enabled:
            self.stop()

    @property
    def speaking(self) -> bool:
        with self._lock:
            return self._speaking

    @property
    def engine_label(self) -> str:
        """Human-readable label for current engine."""
        if self._engine == "edge":
            return "Edge Neural TTS (cloud)"
        elif self._engine == "local":
            return "System TTS (offline)"
        return "None"

    def speak(self, text: str):
        """Speak text in background thread. Non-blocking.

        Stops any currently playing speech first.
        """
        if not self._enabled or not text.strip():
            return

        clean = self._clean_for_speech(text)
        if not clean:
            return

        with self._lock:
            if self._speaking:
                self._stop_flag.set()
                if self._thread and self._thread.is_alive():
                    self._thread.join(timeout=1)

            self._stop_flag.clear()
            self._speaking = True

        self._thread = threading.Thread(
            target=self._speak_worker, args=(clean,),
            daemon=True, name="ForgeTTS")
        self._thread.start()

    def stop(self):
        """Stop current speech immediately."""
        self._stop_flag.set()
        with self._lock:
            self._speaking = False
        try:
            if HAS_PLAYBACK:
                sd.stop()
        except Exception:
            pass
        # Stop pyttsx3 if active
        if self._pyttsx3_engine is not None:
            try:
                self._pyttsx3_engine.stop()
            except Exception:
                pass

    def _speak_worker(self, text: str):
        """Background worker: dispatch to the active engine."""
        try:
            if self._engine == "edge":
                self._speak_edge(text)
            elif self._engine == "local":
                self._speak_pyttsx3(text)
        except Exception as e:
            log.debug("TTS failed: %s", e)
        finally:
            with self._lock:
                self._speaking = False

    # ── Edge-tts engine ──

    def _speak_edge(self, text: str):
        """Synthesize and play using edge-tts (cloud neural voices)."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            audio_data = loop.run_until_complete(self._synthesize_edge(text))
        finally:
            loop.close()

        if self._stop_flag.is_set() or audio_data is None:
            return

        self._play_audio(audio_data)

    async def _synthesize_edge(self, text: str) -> Optional[bytes]:
        """Synthesize text to MP3 bytes using edge-tts."""
        try:
            communicate = edge_tts.Communicate(
                text, self._voice,
                rate=SPEAK_RATE,
                volume=SPEAK_VOLUME,
            )
            audio_chunks = []
            async for chunk in communicate.stream():
                if self._stop_flag.is_set():
                    return None
                if chunk["type"] == "audio":
                    audio_chunks.append(chunk["data"])

            if audio_chunks:
                return b"".join(audio_chunks)
            return None
        except Exception as e:
            log.debug("Edge TTS synthesis failed: %s", e)
            return None

    def _play_audio(self, mp3_data: bytes):
        """Play MP3 audio data through sounddevice."""
        try:
            with tempfile.NamedTemporaryFile(
                    suffix=".mp3", delete=False) as f:
                f.write(mp3_data)
                tmp_path = f.name

            try:
                import soundfile as sf
                audio, samplerate = sf.read(tmp_path)
                if self._stop_flag.is_set():
                    return
                sd.play(audio, samplerate)
                sd.wait()
            except ImportError:
                try:
                    from pydub import AudioSegment
                    seg = AudioSegment.from_mp3(tmp_path)
                    samples = np.array(seg.get_array_of_samples(),
                                       dtype=np.float32)
                    samples /= 32768.0
                    if seg.channels == 2:
                        samples = samples.reshape(-1, 2)
                    if self._stop_flag.is_set():
                        return
                    sd.play(samples, seg.frame_rate)
                    sd.wait()
                except ImportError:
                    import subprocess
                    subprocess.run(
                        ["ffplay", "-nodisp", "-autoexit", "-loglevel",
                         "quiet", tmp_path],
                        check=False, timeout=30)
            finally:
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except Exception:
                    pass
        except Exception as e:
            log.warning(
                "TTS playback failed — all backends exhausted "
                "(soundfile, pydub, ffplay). Error: %s", e)

    # ── pyttsx3 engine ──

    def _speak_pyttsx3(self, text: str):
        """Speak using pyttsx3 (offline system TTS).

        pyttsx3 manages its own audio playback — no sounddevice needed.
        Must create the engine fresh each call (pyttsx3 is not thread-safe
        across repeated calls from different threads).
        """
        try:
            engine = pyttsx3.init()
            engine.setProperty('rate', PYTTSX3_RATE)
            engine.setProperty('volume', PYTTSX3_VOLUME)
            self._pyttsx3_engine = engine

            if self._stop_flag.is_set():
                return

            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            log.debug("pyttsx3 TTS failed: %s", e)
        finally:
            self._pyttsx3_engine = None
            try:
                engine.stop()
            except Exception:
                pass

    # ── Text cleaning ──

    @staticmethod
    def _clean_for_speech(text: str) -> str:
        """Clean text for natural speech output.

        Removes code blocks, markdown formatting, file paths, etc.
        """
        import re
        # Remove code blocks
        text = re.sub(r'```[\s\S]*?```', '', text)
        # Remove inline code
        text = re.sub(r'`[^`]+`', '', text)
        # Remove markdown headers
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        # Remove markdown bold/italic
        text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)
        # Remove markdown links [text](url) -> text
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        # Remove file paths (C:\... or /path/to/...)
        text = re.sub(r'[A-Z]:\\[\w\\./\-]+', '', text)
        text = re.sub(r'/[\w/.\-]{10,}', '', text)
        # Collapse whitespace
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r'  +', ' ', text)

        return text.strip()
