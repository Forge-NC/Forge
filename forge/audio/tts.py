"""Text-to-speech for Forge using edge-tts.

Speaks assistant responses when the turn was voice-initiated.
Non-blocking — audio plays in a background thread.
Only speaks conversational text, NOT tool output or status messages.

Install: pip install edge-tts
"""

import asyncio
import io
import logging
import tempfile
import threading
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

HAS_TTS = False
HAS_PLAYBACK = False

try:
    import edge_tts
    HAS_TTS = True
except ImportError:
    pass

try:
    import sounddevice as sd
    import numpy as np
    HAS_PLAYBACK = True
except ImportError:
    pass


# Default voice — natural-sounding US English male
DEFAULT_VOICE = "en-US-GuyNeural"
# Fallback voices in order of preference
VOICE_OPTIONS = [
    ("en-US-GuyNeural", "Guy (US male)"),
    ("en-US-ChristopherNeural", "Christopher (US male)"),
    ("en-US-EricNeural", "Eric (US male)"),
    ("en-US-JennyNeural", "Jenny (US female)"),
    ("en-US-AriaNeural", "Aria (US female)"),
]

# TTS rate adjustment (e.g., "+10%" for faster)
SPEAK_RATE = "+5%"
SPEAK_VOLUME = "+0%"


class TextToSpeech:
    """Non-blocking TTS using edge-tts (Microsoft Edge's free TTS API)."""

    def __init__(self, voice: str = DEFAULT_VOICE, enabled: bool = True):
        self._voice = voice
        self._enabled = enabled and HAS_TTS and HAS_PLAYBACK
        self._speaking = False
        self._stop_flag = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        if self._enabled:
            log.debug("TTS initialized (voice=%s)", voice)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value and HAS_TTS and HAS_PLAYBACK
        if not self._enabled:
            self.stop()

    @property
    def speaking(self) -> bool:
        with self._lock:
            return self._speaking

    def speak(self, text: str):
        """Speak text in background thread. Non-blocking.

        Stops any currently playing speech first.
        """
        if not self._enabled or not text.strip():
            return

        # Clean text for speech — remove markdown, code blocks, etc.
        clean = self._clean_for_speech(text)
        if not clean:
            return

        with self._lock:
            # Stop current speech
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
            sd.stop()
        except Exception:
            pass

    def _speak_worker(self, text: str):
        """Background worker: synthesize with edge-tts, play with sounddevice."""
        try:
            # Run async edge-tts in this thread's event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                audio_data = loop.run_until_complete(
                    self._synthesize(text))
            finally:
                loop.close()

            if self._stop_flag.is_set() or audio_data is None:
                return

            self._play_audio(audio_data)
        except Exception as e:
            log.debug("TTS failed: %s", e)
        finally:
            with self._lock:
                self._speaking = False

    async def _synthesize(self, text: str) -> Optional[bytes]:
        """Synthesize text to MP3 bytes using edge-tts."""
        try:
            communicate = edge_tts.Communicate(
                text, self._voice,
                rate=SPEAK_RATE,
                volume=SPEAK_VOLUME,
            )
            # Collect all audio chunks
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
            log.debug("TTS synthesis failed: %s", e)
            return None

    def _play_audio(self, mp3_data: bytes):
        """Play MP3 audio data through sounddevice."""
        try:
            # Write to temp file and decode with a simple approach
            # edge-tts outputs MP3, we need to decode it
            with tempfile.NamedTemporaryFile(
                    suffix=".mp3", delete=False) as f:
                f.write(mp3_data)
                tmp_path = f.name

            try:
                # Try using soundfile (if available) for direct decode
                import soundfile as sf
                audio, samplerate = sf.read(tmp_path)
                if self._stop_flag.is_set():
                    return
                sd.play(audio, samplerate)
                sd.wait()
            except ImportError:
                # Fallback: use the edge-tts built-in save + subprocess
                # or try pydub
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
                    # Last resort: subprocess ffplay/mpv
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
