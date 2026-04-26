"""
app/voice/wake_word.py
───────────────────────
Wake-word detection and Voice Activity Detection (VAD) pipeline.

Architecture
─────────────
Ring buffer stores PCM frames continuously.
VAD gates whether audio frames go to STT.
Wake-word engine (OpenWakeWord) runs on every ring buffer flush.

On Pi Zero 2 W:
  • OpenWakeWord runs ≈ 4 ms/frame via TFLite
  • WebRTC VAD runs ≈ 0.1 ms/frame in C extension
  • Ring buffer = 2 seconds of audio = 64 KB RAM

Supported wake words (OpenWakeWord models):
  "Hey Jarvis"  → treated as "Hey Zoro" for compatibility
  "Alexa"       → alternate trigger for demo mode
  Custom model  → train at https://openWakeWord.com

If OpenWakeWord is not installed, the system falls back to
a keyword-spotting heuristic (searches transcript for "hey zoro").

NOTE: This module only DETECTS wake word + VAD.
Audio routing and STT submission are handled by VoicePipeline.
"""

from __future__ import annotations

import asyncio
import collections
import logging
import time
from typing import AsyncGenerator, Callable, Deque, List, Optional

logger = logging.getLogger("voice_agent.wake_word")

# ── Optional imports ──────────────────────────────────────────────────────────

try:
    import webrtcvad
    VAD_AVAILABLE = True
except ImportError:
    VAD_AVAILABLE = False
    logger.warning("webrtcvad not installed — energy-based VAD fallback active")

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import openwakeword  # type: ignore
    from openwakeword.model import Model as OWWModel  # type: ignore
    OWW_AVAILABLE = True
except ImportError:
    OWW_AVAILABLE = False
    logger.info("openwakeword not installed — transcript-based wake-word fallback active")


# ── Constants ─────────────────────────────────────────────────────────────────

SAMPLE_RATE = 16_000
SAMPLE_WIDTH = 2        # 16-bit PCM
CHUNK_MS = 20           # WebRTC VAD requires 10 / 20 / 30 ms
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_MS / 1000)
CHUNK_BYTES = CHUNK_SAMPLES * SAMPLE_WIDTH

# Ring buffer: 2 seconds pre-buffer so we don't miss speech after wake word
PRE_SPEECH_BUFFER_S = 1.5
PRE_SPEECH_FRAMES = int(PRE_SPEECH_BUFFER_S * 1000 / CHUNK_MS)

# VAD hysteresis
SPEECH_ONSET_FRAMES = 3     # consecutive voiced frames to enter SPEECH state
SPEECH_OFFSET_FRAMES = 25   # consecutive silent frames to exit SPEECH state
MAX_UTTERANCE_S = 15        # hard cap on utterance length

# OpenWakeWord threshold
OWW_THRESHOLD = 0.5

# Transcript-based fallback phrases (case-insensitive)
WAKE_PHRASES = [
    "hey zoro", "hi zoro", "okay zoro", "ok zoro",
    "zoro", "hello zoro", "vanakkam zoro",
]


# ── Energy / RMS helper ───────────────────────────────────────────────────────

def _rms(pcm: bytes) -> float:
    if not NUMPY_AVAILABLE or len(pcm) < 2:
        return 0.0
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(samples ** 2))) if len(samples) else 0.0


# ── VAD wrapper ───────────────────────────────────────────────────────────────

class VoiceActivityDetector:
    """
    WebRTC VAD with hysteresis state machine.
    Falls back to energy-based detection if webrtcvad unavailable.
    """

    def __init__(self, aggressiveness: int = 2):
        self._vad = webrtcvad.Vad(aggressiveness) if VAD_AVAILABLE else None
        self._voiced = 0
        self._unvoiced = 0
        self.in_speech = False

    def is_voiced(self, frame: bytes) -> bool:
        if self._vad:
            try:
                return self._vad.is_speech(frame, SAMPLE_RATE)
            except Exception:
                return False
        # Energy fallback
        return _rms(frame) > 400

    def process(self, frame: bytes) -> tuple[bool, bool]:
        """Returns (in_speech, state_changed)."""
        voiced = self.is_voiced(frame)
        prev = self.in_speech

        if voiced:
            self._voiced += 1
            self._unvoiced = 0
            if not self.in_speech and self._voiced >= SPEECH_ONSET_FRAMES:
                self.in_speech = True
        else:
            self._unvoiced += 1
            self._voiced = 0
            if self.in_speech and self._unvoiced >= SPEECH_OFFSET_FRAMES:
                self.in_speech = False

        return self.in_speech, self.in_speech != prev

    def reset(self):
        self._voiced = 0
        self._unvoiced = 0
        self.in_speech = False


# ── OpenWakeWord wrapper ───────────────────────────────────────────────────────

class WakeWordDetector:
    """
    OpenWakeWord-based wake word detector.
    Falls back to transcript phrase matching if OWW not available.
    """

    def __init__(self, model_names: Optional[List[str]] = None, threshold: float = OWW_THRESHOLD):
        self._threshold = threshold
        self._model: Optional[OWWModel] = None
        self._enabled = OWW_AVAILABLE

        if OWW_AVAILABLE:
            try:
                m_names = model_names or ["hey_jarvis"]  # closest free model to "Hey Zoro"
                self._model = OWWModel(
                    wakeword_models=m_names,
                    inference_framework="tflite",   # Pi-safe (no TF)
                )
                logger.info("OpenWakeWord loaded: models=%s", m_names)
            except Exception as exc:
                logger.warning("OWW model load failed: %s — using transcript fallback", exc)
                self._enabled = False

    def detect_in_frame(self, pcm_frame: bytes) -> bool:
        """
        Run OWW inference on a single 20 ms frame.
        Returns True if wake word detected above threshold.
        """
        if not self._enabled or self._model is None:
            return False
        try:
            samples = np.frombuffer(pcm_frame, dtype=np.int16)
            preds = self._model.predict(samples)
            score = max(preds.values()) if preds else 0.0
            if score >= self._threshold:
                logger.info("Wake word detected (OWW score=%.3f)", score)
                return True
        except Exception as exc:
            logger.debug("OWW predict error: %s", exc)
        return False

    def detect_in_transcript(self, transcript: str) -> bool:
        """Fallback: check if transcript contains a wake phrase."""
        lower = transcript.lower().strip()
        return any(phrase in lower for phrase in WAKE_PHRASES)


# ── Main pipeline ─────────────────────────────────────────────────────────────

class VoicePipeline:
    """
    Complete local voice pipeline:
      Mic → ring buffer → wake word → VAD → utterance collector

    Usage (standalone robot mode):
        pipeline = VoicePipeline()
        async for utterance_pcm in pipeline.run():
            # Send utterance_pcm to STT
            transcript = await stt.transcribe(utterance_pcm)

    Usage (server mode, audio from WebSocket):
        pipeline = VoicePipeline(wake_word_enabled=False)
        async for utterance_pcm in pipeline.feed_stream(ws_audio_gen):
            ...
    """

    def __init__(
        self,
        wake_word_enabled: bool = True,
        vad_aggressiveness: int = 2,
        on_wake: Optional[Callable[[], None]] = None,
        on_speech_start: Optional[Callable[[], None]] = None,
        on_speech_end: Optional[Callable[[], None]] = None,
    ):
        self.wake_word_enabled = wake_word_enabled
        self.vad = VoiceActivityDetector(vad_aggressiveness)
        self.wake_detector = WakeWordDetector() if wake_word_enabled else None

        # Pre-speech ring buffer
        self._ring: Deque[bytes] = collections.deque(maxlen=PRE_SPEECH_FRAMES)
        self._awake = False   # True after wake word detected, until end of utterance
        self._collecting = False

        # Callbacks
        self.on_wake = on_wake
        self.on_speech_start = on_speech_start
        self.on_speech_end = on_speech_end

    # ── Wakeword-gated VAD loop ────────────────────────────────────────────

    async def run(self) -> AsyncGenerator[bytes, None]:
        """
        Full robot mode: capture from mic, detect wake word, yield utterances.
        Requires sounddevice installed.
        """
        try:
            from app.utils.audio_utils import MicrophoneStream
        except ImportError:
            logger.error("MicrophoneStream not available — cannot run standalone pipeline")
            return

        logger.info("VoicePipeline: starting mic capture")
        async with MicrophoneStream() as mic:
            async for utterance in self._process_stream(mic):
                yield utterance

    async def feed_stream(
        self, audio_gen: AsyncGenerator[bytes, None]
    ) -> AsyncGenerator[bytes, None]:
        """
        Server mode: process audio from external generator (WebSocket, file, etc.)
        Wake word detection is active even here if enabled.
        """
        async for utterance in self._process_stream(audio_gen):
            yield utterance

    async def _process_stream(
        self, audio_gen: AsyncGenerator[bytes, None]
    ) -> AsyncGenerator[bytes, None]:
        """Core frame processing loop."""
        speech_buffer: List[bytes] = []
        speech_start_ts = 0.0
        in_speech = False

        async for raw in audio_gen:
            # Chunk raw into CHUNK_BYTES frames
            for i in range(0, max(len(raw), CHUNK_BYTES), CHUNK_BYTES):
                frame = raw[i: i + CHUNK_BYTES]
                if len(frame) < CHUNK_BYTES:
                    # Pad last small frame
                    frame = frame.ljust(CHUNK_BYTES, b"\x00")

                # Always fill ring buffer
                self._ring.append(frame)

                # ── Wake word gate ─────────────────────────────────────
                if self.wake_word_enabled and not self._awake:
                    if self.wake_detector and self.wake_detector.detect_in_frame(frame):
                        self._awake = True
                        if self.on_wake:
                            self.on_wake()
                        logger.info("Wake word detected — listening for utterance")
                    continue  # Don't process VAD until awake

                # ── VAD ────────────────────────────────────────────────
                currently_speech, changed = self.vad.process(frame)

                if currently_speech and not in_speech:
                    # Speech onset
                    in_speech = True
                    speech_start_ts = time.monotonic()
                    # Include pre-speech ring buffer
                    speech_buffer = list(self._ring)
                    if self.on_speech_start:
                        self.on_speech_start()
                    logger.debug("VAD: speech start")

                elif in_speech:
                    speech_buffer.append(frame)

                    # Hard cap
                    elapsed = time.monotonic() - speech_start_ts
                    utterance_ended = not currently_speech and changed

                    if utterance_ended or elapsed >= MAX_UTTERANCE_S:
                        # Utterance complete
                        in_speech = False
                        self._awake = False  # require new wake word
                        self.vad.reset()

                        if self.on_speech_end:
                            self.on_speech_end()

                        utterance_pcm = b"".join(speech_buffer)
                        speech_buffer = []
                        logger.info(
                            "VAD: utterance ended (%.2fs, %d bytes)",
                            elapsed, len(utterance_pcm),
                        )
                        yield utterance_pcm

    def set_awake(self, awake: bool = True):
        """Manually trigger wake state (e.g., robot enters classroom)."""
        self._awake = awake

    def reset(self):
        self._awake = False
        self._collecting = False
        self._ring.clear()
        self.vad.reset()


# ── Module-level instances ─────────────────────────────────────────────────────

# Robot mode: full wake-word + VAD pipeline
robot_pipeline = VoicePipeline(wake_word_enabled=True)

# Server mode: VAD only (wake word not needed for explicit API calls)
server_pipeline = VoicePipeline(wake_word_enabled=False)

