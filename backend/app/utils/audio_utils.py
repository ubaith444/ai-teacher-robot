"""
utils/audio_utils.py — Audio helpers for the Voice Agent.

Handles:
  • PCM chunk splitting for streaming
  • WebRTC VAD integration
  • Audio format conversion (resample, encode/decode)
  • Piper offline TTS subprocess wrapper
  • Playback via ALSA / sounddevice (Pi-friendly)
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import struct
import subprocess
import tempfile
import time
import wave
from typing import AsyncGenerator, Generator, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("voice_agent.audio")

# Optional heavy imports — gracefully degrade on minimal Pi installs
try:
    import webrtcvad
    VAD_AVAILABLE = True
except ImportError:
    VAD_AVAILABLE = False
    logger.warning("webrtcvad not installed — VAD disabled")

try:
    import sounddevice as sd
    SD_AVAILABLE = True
except ImportError:
    SD_AVAILABLE = False
    logger.warning("sounddevice not installed — mic/speaker disabled")

try:
    import scipy.signal as scipy_signal
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2          # 16-bit PCM
CHUNK_MS = 20             # WebRTC VAD requires 10/20/30 ms frames
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_MS / 1000)
CHUNK_BYTES = CHUNK_SAMPLES * SAMPLE_WIDTH


# ─────────────────────────────────────────────────────────────────────────────
# VAD
# ─────────────────────────────────────────────────────────────────────────────

class VoiceActivityDetector:
    """
    Wraps WebRTC VAD with a small state machine:
      SILENCE → SPEECH (after N voiced frames)
      SPEECH  → SILENCE (after M unvoiced frames)
    """

    def __init__(
        self,
        aggressiveness: int = 2,
        speech_onset_frames: int = 3,
        speech_offset_frames: int = 20,
    ):
        self.aggressiveness = aggressiveness
        self.speech_onset = speech_onset_frames
        self.speech_offset = speech_offset_frames
        self._vad = None
        self._voiced_count = 0
        self._unvoiced_count = 0
        self._in_speech = False
        self._init_vad()

    def _init_vad(self):
        if VAD_AVAILABLE:
            self._vad = webrtcvad.Vad(self.aggressiveness)
        else:
            self._vad = None

    def is_speech(self, pcm_frame: bytes) -> bool:
        """Returns True if frame contains speech."""
        if self._vad is None:
            # Simple energy-based fallback
            samples = np.frombuffer(pcm_frame, dtype=np.int16)
            rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))
            return rms > 500
        try:
            return self._vad.is_speech(pcm_frame, SAMPLE_RATE)
        except Exception:
            return False

    def process_frame(self, pcm_frame: bytes) -> Tuple[bool, bool]:
        """
        Returns (is_currently_speech, state_changed).
        Implements hysteresis to avoid rapid toggling.
        """
        voiced = self.is_speech(pcm_frame)
        prev = self._in_speech

        if voiced:
            self._voiced_count += 1
            self._unvoiced_count = 0
            if not self._in_speech and self._voiced_count >= self.speech_onset:
                self._in_speech = True
        else:
            self._unvoiced_count += 1
            self._voiced_count = 0
            if self._in_speech and self._unvoiced_count >= self.speech_offset:
                self._in_speech = False

        return self._in_speech, (self._in_speech != prev)

    def reset(self):
        self._voiced_count = 0
        self._unvoiced_count = 0
        self._in_speech = False


# ─────────────────────────────────────────────────────────────────────────────
# PCM / WAV helpers
# ─────────────────────────────────────────────────────────────────────────────

def pcm_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Wrap raw PCM (16-bit mono) in a WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def wav_to_pcm(wav_bytes: bytes) -> Tuple[bytes, int]:
    """Extract PCM bytes and sample_rate from WAV bytes."""
    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as wf:
        sr = wf.getframerate()
        pcm = wf.readframes(wf.getnframes())
    return pcm, sr


def resample_pcm(pcm: bytes, from_rate: int, to_rate: int) -> bytes:
    """Resample 16-bit mono PCM to target rate."""
    if from_rate == to_rate:
        return pcm
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    if SCIPY_AVAILABLE:
        ratio = to_rate / from_rate
        new_len = int(len(samples) * ratio)
        resampled = scipy_signal.resample(samples, new_len)
    else:
        # Nearest-neighbour fallback (low quality but Pi-safe)
        ratio = to_rate / from_rate
        indices = (np.arange(int(len(samples) * ratio)) / ratio).astype(int)
        indices = np.clip(indices, 0, len(samples) - 1)
        resampled = samples[indices]
    return resampled.astype(np.int16).tobytes()


def chunk_audio(pcm: bytes, chunk_bytes: int = CHUNK_BYTES) -> Generator[bytes, None, None]:
    """Yield fixed-size PCM chunks."""
    for i in range(0, len(pcm), chunk_bytes):
        yield pcm[i : i + chunk_bytes]


def b64_to_pcm(b64: str) -> Tuple[bytes, int]:
    """Decode base64 WAV → (pcm_bytes, sample_rate)."""
    wav_bytes = base64.b64decode(b64)
    return wav_to_pcm(wav_bytes)


def pcm_to_b64(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> str:
    """Encode PCM → base64 WAV string."""
    return base64.b64encode(pcm_to_wav(pcm, sample_rate)).decode()


def compute_rms(pcm: bytes) -> float:
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples ** 2)))


# ─────────────────────────────────────────────────────────────────────────────
# Piper TTS (offline)
# ─────────────────────────────────────────────────────────────────────────────

class PiperTTS:
    """
    Wraps the Piper binary for offline Tamil + English TTS.
    Piper reads text from stdin and writes WAV to stdout.
    """

    def __init__(
        self,
        piper_bin: str,
        tamil_model: str,
        english_model: str,
        sample_rate: int = 22050,
    ):
        self.piper_bin = piper_bin
        self.tamil_model = tamil_model
        self.english_model = english_model
        self.sample_rate = sample_rate

    def _model_for_lang(self, language: str) -> str:
        return self.tamil_model if language == "ta" else self.english_model

    def synthesize(self, text: str, language: str = "en") -> Optional[bytes]:
        """
        Synchronous Piper call → returns WAV bytes or None on failure.
        Runs in a subprocess; safe for Pi Zero 2 W.
        """
        model = self._model_for_lang(language)
        if not os.path.exists(self.piper_bin):
            logger.error("Piper binary not found: %s", self.piper_bin)
            return None
        if not os.path.exists(model):
            logger.error("Piper model not found: %s", model)
            return None

        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                out_path = tf.name

            cmd = [
                self.piper_bin,
                "--model", model,
                "--output_file", out_path,
            ]
            result = subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                capture_output=True,
                timeout=10,
            )
            if result.returncode != 0:
                logger.error("Piper error: %s", result.stderr.decode())
                return None

            with open(out_path, "rb") as f:
                wav_data = f.read()
            os.unlink(out_path)
            return wav_data

        except subprocess.TimeoutExpired:
            logger.error("Piper TTS timed out for text length %d", len(text))
            return None
        except Exception as e:
            logger.exception("Piper TTS unexpected error: %s", e)
            return None

    async def synthesize_async(self, text: str, language: str = "en") -> Optional[bytes]:
        """Async wrapper — runs Piper in a thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.synthesize, text, language)

    async def stream_chunks(
        self, text: str, language: str = "en", chunk_ms: int = 100
    ) -> AsyncGenerator[bytes, None]:
        """Synthesize and yield PCM chunks (for streaming playback)."""
        wav = await self.synthesize_async(text, language)
        if wav is None:
            return
        pcm, sr = wav_to_pcm(wav)
        # Resample to pipeline rate if needed
        if sr != SAMPLE_RATE:
            pcm = resample_pcm(pcm, sr, SAMPLE_RATE)
        chunk_bytes = int(SAMPLE_RATE * chunk_ms / 1000) * SAMPLE_WIDTH
        for chunk in chunk_audio(pcm, chunk_bytes):
            yield chunk


# ─────────────────────────────────────────────────────────────────────────────
# Microphone capture (streaming, Pi-friendly)
# ─────────────────────────────────────────────────────────────────────────────

class MicrophoneStream:
    """
    Async generator that captures audio from the default mic device.
    Uses sounddevice with a asyncio.Queue to bridge callback → async.
    """

    def __init__(
        self,
        device: int = 0,
        sample_rate: int = SAMPLE_RATE,
        chunk_ms: int = CHUNK_MS,
    ):
        self.device = device
        self.sample_rate = sample_rate
        self.chunk_frames = int(sample_rate * chunk_ms / 1000)
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._stream = None
        self._running = False

    def _callback(self, indata, frames, time_info, status):
        if status:
            logger.warning("Mic status: %s", status)
        if self._running:
            pcm = indata[:, 0].tobytes() if indata.ndim > 1 else indata.tobytes()
            try:
                self._queue.put_nowait(pcm)
            except asyncio.QueueFull:
                pass  # drop on overflow — real-time priority

    async def __aenter__(self):
        if not SD_AVAILABLE:
            raise RuntimeError("sounddevice not available")
        self._running = True
        self._stream = sd.InputStream(
            device=self.device,
            samplerate=self.sample_rate,
            channels=CHANNELS,
            dtype="int16",
            blocksize=self.chunk_frames,
            callback=self._callback,
        )
        self._stream.start()
        return self

    async def __aexit__(self, *args):
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()

    async def __aiter__(self) -> AsyncGenerator[bytes, None]:
        while self._running:
            try:
                chunk = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                yield chunk
            except asyncio.TimeoutError:
                continue


# ─────────────────────────────────────────────────────────────────────────────
# Speaker playback
# ─────────────────────────────────────────────────────────────────────────────

async def play_audio(pcm: bytes, sample_rate: int = SAMPLE_RATE, device: int = 0):
    """Play PCM bytes on the speaker (non-blocking async)."""
    if not SD_AVAILABLE:
        logger.warning("sounddevice unavailable — cannot play audio")
        return

    def _play():
        samples = np.frombuffer(pcm, dtype=np.int16)
        sd.play(samples, samplerate=sample_rate, device=device, blocking=True)

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _play)


async def play_audio_stream(
    gen: AsyncGenerator[bytes, None], sample_rate: int = SAMPLE_RATE
):
    """Stream PCM chunks to speaker as they arrive."""
    if not SD_AVAILABLE:
        logger.warning("sounddevice unavailable — cannot play audio stream")
        async for _ in gen:
            pass
        return

    buffer = bytearray()
    async for chunk in gen:
        buffer.extend(chunk)
        # Play in 200 ms bursts to reduce latency
        burst = int(sample_rate * 0.2) * SAMPLE_WIDTH
        if len(buffer) >= burst:
            samples = np.frombuffer(bytes(buffer[:burst]), dtype=np.int16)
            sd.play(samples, samplerate=sample_rate, blocking=True)
            buffer = buffer[burst:]

    # Flush remainder
    if buffer:
        samples = np.frombuffer(bytes(buffer), dtype=np.int16)
        sd.play(samples, samplerate=sample_rate, blocking=True)


# ─────────────────────────────────────────────────────────────────────────────
# Noise / classroom utilities
# ─────────────────────────────────────────────────────────────────────────────

def estimate_noise_floor(pcm_frames: List[bytes]) -> float:
    """Estimate ambient noise RMS from a list of silent frames."""
    if not pcm_frames:
        return 300.0
    rms_vals = [compute_rms(f) for f in pcm_frames]
    return float(np.median(rms_vals))


def apply_gain(pcm: bytes, gain_db: float) -> bytes:
    """Apply linear gain (dB) to PCM."""
    factor = 10 ** (gain_db / 20.0)
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) * factor
    return np.clip(samples, -32768, 32767).astype(np.int16).tobytes()


def trim_silence(pcm: bytes, threshold_rms: float = 200.0) -> bytes:
    """Trim leading/trailing silence from PCM."""
    chunk = CHUNK_BYTES
    chunks = list(chunk_audio(pcm, chunk))
    # Find first and last voiced chunk
    start, end = 0, len(chunks) - 1
    for i, c in enumerate(chunks):
        if compute_rms(c) > threshold_rms:
            start = i
            break
    for i in range(len(chunks) - 1, -1, -1):
        if compute_rms(chunks[i]) > threshold_rms:
            end = i
            break
    return b"".join(chunks[start : end + 1])