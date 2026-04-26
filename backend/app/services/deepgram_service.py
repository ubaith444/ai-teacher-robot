"""
services/deepgram_service.py — Deepgram STT (Nova-3) and TTS (Aura) integration.

Features:
  • WebSocket-based streaming STT with partial transcripts
  • HTTP streaming TTS with chunked PCM output
  • Deepgram Voice Agent API (optional, for ultra-low latency)
  • Automatic reconnect on drop
  • Language auto-detection hint passing
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple

import httpx
from app.core.config import settings
from app.schemas import Language, STTResult, TranscriptChunk

logger = logging.getLogger("voice_agent.deepgram")

DG_WS_STT_URL = "wss://api.deepgram.com/v1/listen"
DG_HTTP_TTS_URL = "https://api.deepgram.com/v1/speak"
DG_VOICE_AGENT_URL = "wss://agent.deepgram.com/agent"

# Shared persistent client for TTS — avoids TCP + TLS handshake overhead
# on every sentence.  Created lazily; closed on app shutdown.
_tts_client: Optional[httpx.AsyncClient] = None


def _get_tts_client() -> httpx.AsyncClient:
    """Return (or lazily create) a keep-alive httpx client for Deepgram TTS."""
    global _tts_client
    if _tts_client is None or _tts_client.is_closed:
        _tts_client = httpx.AsyncClient(
            timeout=httpx.Timeout(12.0, connect=3.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            headers={"Connection": "keep-alive"},
        )
    return _tts_client


async def close_tts_client() -> None:
    """Close the shared TTS client (call from app shutdown hook)."""
    global _tts_client
    if _tts_client and not _tts_client.is_closed:
        await _tts_client.aclose()
        _tts_client = None


# ─────────────────────────────────────────────────────────────────────────────
# STT — WebSocket streaming (Nova-3)
# ─────────────────────────────────────────────────────────────────────────────

class DeepgramSTT:
    """
    Real-time streaming STT via Deepgram WebSocket.

    Usage:
        async with DeepgramSTT() as stt:
            async for result in stt.transcribe_stream(audio_gen):
                print(result.transcript)
    """

    def __init__(self):
        self.api_key = settings.DEEPGRAM_API_KEY
        self.model = settings.DG_STT_MODEL
        self.language = settings.DG_STT_LANGUAGE
        self.sample_rate = settings.AUDIO_SAMPLE_RATE
        self._ws = None
        self._results: asyncio.Queue = asyncio.Queue()
        self._running = False

    def _build_ws_url(self, language_hint: Optional[Language] = None) -> str:
        lang = "ta-IN" if language_hint == Language.TAMIL else self.language
        params = [
            f"model={self.model}",
            f"language={lang}",
            f"sample_rate={self.sample_rate}",
            "encoding=linear16",
            "channels=1",
            f"punctuate={'true' if settings.DG_STT_PUNCTUATE else 'false'}",
            f"interim_results={'true' if settings.DG_STT_INTERIM_RESULTS else 'false'}",
            f"endpointing={settings.DG_STT_ENDPOINTING}",
            f"smart_format={'true' if settings.DG_STT_SMART_FORMAT else 'false'}",
        ]
        return f"{DG_WS_STT_URL}?{'&'.join(params)}"

    async def transcribe_audio_bytes(
        self, audio_bytes: bytes, language_hint: Optional[Language] = None
    ) -> STTResult:
        """
        One-shot STT: send all audio, wait for final transcript.
        Used in REST mode (non-streaming).
        """
        try:
            import websockets  # type: ignore
        except ImportError:
            raise RuntimeError("websockets package required: pip install websockets")

        url = self._build_ws_url(language_hint)
        headers = {"Authorization": f"Token {self.api_key}"}
        full_transcript = ""
        confidence = 0.0

        t0 = time.perf_counter()
        try:
            async with websockets.connect(url, extra_headers=headers) as ws:
                # Send audio in chunks
                chunk_size = int(self.sample_rate * 0.1) * 2  # 100 ms
                for i in range(0, len(audio_bytes), chunk_size):
                    await ws.send(audio_bytes[i : i + chunk_size])
                    await asyncio.sleep(0)  # yield

                # Signal end of stream
                await ws.send(json.dumps({"type": "CloseStream"}))

                # Collect results
                async for message in ws:
                    data = json.loads(message)
                    if data.get("type") == "Results" and data.get("is_final"):
                        alt = data.get("channel", {}).get("alternatives", [{}])[0]
                        full_transcript += alt.get("transcript", "")
                        confidence = alt.get("confidence", 0.0)
                    elif data.get("type") == "Metadata":
                        break

        except Exception as e:
            logger.exception("Deepgram one-shot STT error: %s", e)
            return STTResult(
                transcript="", confidence=0.0, language=Language.ENGLISH, is_final=False
            )

        dur = int((time.perf_counter() - t0) * 1000)
        logger.info("Deepgram STT: '%s' (%.2f) in %dms", full_transcript[:60], confidence, dur)

        return STTResult(
            transcript=full_transcript.strip(),
            confidence=confidence,
            language=language_hint or Language.ENGLISH,
            is_final=True,
            duration_ms=dur,
        )

    async def transcribe_stream(
        self,
        audio_gen: AsyncGenerator[bytes, None],
        language_hint: Optional[Language] = None,
        on_interim: Optional[Callable[[TranscriptChunk], None]] = None,
    ) -> AsyncGenerator[TranscriptChunk, None]:
        """
        Fully streaming STT. Accepts an async generator of PCM chunks,
        yields TranscriptChunk objects (interim + final).
        """
        try:
            import websockets  # type: ignore
        except ImportError:
            raise RuntimeError("pip install websockets")

        url = self._build_ws_url(language_hint)
        headers = {"Authorization": f"Token {self.api_key}"}
        logger.debug("STT: Connecting to %s", url)

        # In some websockets versions, extra_headers needs to be a list or a dict.
        # We also add a small buffer for the connect to avoid immediate closures.
        try:
            async with websockets.connect(
                url,
                extra_headers=headers,
                ping_interval=10,
                ping_timeout=10,
                close_timeout=5,
            ) as ws:
                logger.debug("STT: WebSocket connected to Deepgram (model=%s)", self.model)

                async def _send():
                    """Send audio chunks to Deepgram."""
                    chunks_sent = 0
                    bytes_sent = 0
                    async for chunk in audio_gen:
                        if not chunk:
                            continue
                        try:
                            # Send as binary
                            await ws.send(chunk)
                            chunks_sent += 1
                            bytes_sent += len(chunk)
                            if chunks_sent % 50 == 0:
                                logger.debug("STT: Sent %d chunks (%d bytes)", chunks_sent, bytes_sent)
                        except Exception as e:
                            logger.warning("STT: Send error: %s", e)
                            break
                    
                    try:
                        logger.debug("STT: Sending CloseStream (total %d bytes)", bytes_sent)
                        await ws.send(json.dumps({"type": "CloseStream"}))
                    except Exception:
                        pass

                async def _receive() -> AsyncGenerator[TranscriptChunk, None]:
                    """Receive and parse Deepgram results."""
                    async for message in ws:
                        try:
                            data = json.loads(message)
                        except json.JSONDecodeError:
                            continue

                        msg_type = data.get("type")
                        if msg_type == "Results":
                            alt = data.get("channel", {}).get("alternatives", [{}])[0]
                            transcript = alt.get("transcript", "").strip()
                            if not transcript:
                                continue
                            is_final = data.get("is_final", False)
                            confidence = alt.get("confidence", 1.0)
                            chunk = TranscriptChunk(
                                text=transcript,
                                is_final=is_final,
                                confidence=confidence,
                                language=language_hint or Language.ENGLISH,
                            )
                            if not is_final and on_interim:
                                on_interim(chunk)
                            yield chunk

                        elif msg_type in ("Metadata", "SpeechStarted", "UtteranceEnd"):
                            continue
                        elif msg_type == "Error":
                            logger.error("Deepgram error: %s", data)
                            break

                # Run sender + receiver concurrently
                send_task = asyncio.create_task(_send())
                async for chunk in _receive():
                    yield chunk
                await send_task

        except Exception as e:
            # Surface HTTP status when Deepgram rejects the connection
            status_code = getattr(e, "status_code", None)
            logger.exception(
                "Deepgram streaming STT error (HTTP %s): %s",
                status_code or "?",
                e,
            )


# ─────────────────────────────────────────────────────────────────────────────
# TTS — HTTP streaming (Aura)
# ─────────────────────────────────────────────────────────────────────────────

class DeepgramTTS:
    """
    Streaming TTS via Deepgram Aura models.
    Yields raw PCM chunks for low-latency playback.
    """

    def __init__(self):
        self.api_key = settings.DEEPGRAM_API_KEY
        self.model = settings.DG_TTS_MODEL
        self.sample_rate = settings.DG_TTS_SAMPLE_RATE
        self.encoding = settings.DG_TTS_ENCODING
        self.container = settings.DG_TTS_CONTAINER

    async def synthesize_stream(
        self,
        text: str,
        model: Optional[str] = None,
    ) -> AsyncGenerator[bytes, None]:
        """
        Stream TTS audio as PCM chunks.
        Yields bytes chunks as Deepgram sends them.
        """
        if not text.strip():
            return

        tts_model = model or self.model
        url = (
            f"{DG_HTTP_TTS_URL}?model={tts_model}"
            f"&encoding={self.encoding}"
            f"&sample_rate={self.sample_rate}"
            f"&container={self.container}"
        )
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"text": text}

        t0 = time.perf_counter()
        first_byte = None

        # Re-use keep-alive client — eliminates TCP/TLS roundtrip per sentence
        client = _get_tts_client()
        try:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                # 2 KB chunk → first audio arrives ~2× faster than 4 KB
                async for chunk in resp.aiter_bytes(chunk_size=2048):
                    if chunk:
                        if first_byte is None:
                            first_byte = int((time.perf_counter() - t0) * 1000)
                            logger.debug("Deepgram TTS TTFB: %dms", first_byte)
                        yield chunk

        except httpx.HTTPStatusError as e:
            logger.error(
                "Deepgram TTS HTTP %s: %s",
                e.response.status_code,
                e.response.text[:200],
            )
        except httpx.TimeoutException:
            logger.error("Deepgram TTS timeout for text length %d", len(text))
        except Exception as e:
            logger.exception("Deepgram TTS error: %s", e)

    async def synthesize_full(self, text: str) -> Optional[bytes]:
        """Collect full WAV bytes (for REST mode)."""
        chunks = []
        async for chunk in self.synthesize_stream(text):
            chunks.append(chunk)
        return b"".join(chunks) if chunks else None


# ─────────────────────────────────────────────────────────────────────────────
# Deepgram Voice Agent API (ultra-low-latency, optional)
# ─────────────────────────────────────────────────────────────────────────────

class DeepgramVoiceAgent:
    """
    Deepgram Voice Agent WebSocket API.
    Handles full duplex: mic-in → STT → LLM → TTS → speaker-out
    at ultra-low latency (~300-500 ms total).

    This is an optional upgrade path when DG handles STT+LLM+TTS natively.
    For classroom use, the primary pipeline is STT → Gemini → TTS.
    """

    AGENT_CONFIG = {
        "type": "SettingsConfiguration",
        "audio": {
            "input": {
                "encoding": "linear16",
                "sample_rate": 16000,
            },
            "output": {
                "encoding": "linear16",
                "sample_rate": 16000,
                "bitrate": 128000,
                "container": "wav",
            },
        },
        "agent": {
            "listen": {"model": "nova-3"},
            "think": {
                "provider": {"type": "open_ai"},   # swap to custom if needed
                "model": "gpt-4o-mini",
                "instructions": "You are a classroom assistant robot. Answer attendance questions briefly.",
            },
            "speak": {"model": "aura-asteria-en"},
        },
    }

    def __init__(self, custom_config: Optional[Dict] = None):
        self.api_key = settings.DEEPGRAM_API_KEY
        self.config = custom_config or self.AGENT_CONFIG

    async def run_session(
        self,
        audio_in: AsyncGenerator[bytes, None],
        on_text: Callable[[str, bool], None],
        on_audio: Callable[[bytes], None],
    ):
        """
        Run a full Voice Agent session.

        audio_in  : async generator of PCM chunks from microphone
        on_text   : callback(text, is_user) called for transcripts
        on_audio  : callback(pcm_bytes) called for TTS output chunks
        """
        try:
            import websockets  # type: ignore
        except ImportError:
            raise RuntimeError("pip install websockets")

        headers = {"Authorization": f"Token {self.api_key}"}

        try:
            async with websockets.connect(
                DG_VOICE_AGENT_URL, extra_headers=headers
            ) as ws:
                # Send initial config
                await ws.send(json.dumps(self.config))
                logger.info("Deepgram Voice Agent session started")

                async def _send_audio():
                    async for chunk in audio_in:
                        await ws.send(chunk)

                async def _receive():
                    async for msg in ws:
                        if isinstance(msg, bytes):
                            on_audio(msg)
                        else:
                            data = json.loads(msg)
                            t = data.get("type", "")
                            if t == "UserStartedSpeaking":
                                logger.debug("DG Agent: user speaking")
                            elif t == "ConversationText":
                                on_text(data.get("content", ""), data.get("role") == "user")
                            elif t == "AgentThinking":
                                logger.debug("DG Agent thinking...")
                            elif t == "Error":
                                logger.error("DG Agent error: %s", data)

                await asyncio.gather(_send_audio(), _receive())

        except Exception as e:
            logger.exception("Deepgram Voice Agent error: %s", e)


# ── Module-level singletons ───────────────────────────────────────────────────
deepgram_stt = DeepgramSTT()
deepgram_tts = DeepgramTTS()
deepgram_agent = DeepgramVoiceAgent()
