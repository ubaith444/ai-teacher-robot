"""
services/voice_orchestrator.py — CENTRAL PIPELINE COORDINATOR

Full pipeline: Audio → VAD → STT → LLM (Gemini / offline) → TTS (Deepgram / Piper)

Routing rules:
  ┌─────────────────────────────────────────────────────────────────┐
  │  ONLINE mode (internet OK, Gemini OK, Deepgram OK)              │
  │    STT : Deepgram Nova-3 streaming                              │
  │    LLM : Gemini 2.5 Flash + function calling                    │
  │    TTS : Deepgram Aura streaming                                │
  ├─────────────────────────────────────────────────────────────────┤
  │  PARTIAL ONLINE (Gemini OK but Deepgram TTS fails)              │
  │    STT : Deepgram Nova-3                                        │
  │    LLM : Gemini 2.5 Flash                                       │
  │    TTS : Piper (offline)                                        │
  ├─────────────────────────────────────────────────────────────────┤
  │  OFFLINE mode (no internet or Gemini timeout)                   │
  │    STT : Deepgram Nova-3 (with local cache) or skip             │
  │    LLM : local llama.cpp                                        │
  │    TTS : Piper                                                  │
  ├─────────────────────────────────────────────────────────────────┤
  │  TEXT ONLY (all audio fails)                                    │
  │    Return text response only, display on screen                 │
  └─────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from app.core.config import settings
from app.schemas import (FallbackReason, Language, LLMResponse, PipelineMode,
                         STTResult, UserRole, VoiceQueryRequest,
                         VoiceQueryResponse)
from app.services.deepgram_service import deepgram_stt, deepgram_tts
from app.services.openai_service import openai_service
from app.services.gemini_service import get_system_prompt
from app.services.offline_llm_service import offline_llm
from app.utils.audio_utils import (PiperTTS, b64_to_pcm, pcm_to_b64,
                                   trim_silence)

logger = logging.getLogger("voice_agent.orchestrator")

# Module-level Piper instance
_piper = PiperTTS(
    piper_bin=settings.PIPER_BIN,
    tamil_model=settings.PIPER_TAMIL_MODEL,
    english_model=settings.PIPER_ENGLISH_MODEL,
    sample_rate=settings.PIPER_SAMPLE_RATE,
)


# ─────────────────────────────────────────────────────────────────────────────
# Connectivity probe
# ─────────────────────────────────────────────────────────────────────────────

class ConnectivityMonitor:
    """
    Lightweight connectivity checker.
    Caches state for 30 s to avoid hammering network checks.
    """

    def __init__(self, cache_ttl: float = 30.0):
        self._last_check: float = 0.0
        self._last_result: bool = True
        self._cache_ttl = cache_ttl
        self._gemini_ok: bool = True
        self._gemini_check_ts: float = 0.0

    async def is_online(self) -> bool:
        now = time.time()
        if now - self._last_check < self._cache_ttl:
            return self._last_result

        try:
            import httpx
            async with httpx.AsyncClient(timeout=2.0) as c:
                await c.get("https://dns.google/resolve?name=example.com&type=A")
            self._last_result = True
        except Exception:
            self._last_result = False

        self._last_check = now
        return self._last_result

    async def is_llm_available(self) -> bool:
        """Check if OpenAI (primary) or Gemini (secondary) is available."""
        # For simplicity, we just check internet. 
        # In production, we'd do a model health check.
        return await self.is_online()

    def mark_gemini_failed(self):
        self._gemini_ok = False
        self._gemini_check_ts = time.time()

    def mark_gemini_ok(self):
        self._gemini_ok = True
        self._gemini_check_ts = time.time()


connectivity = ConnectivityMonitor()


# ─────────────────────────────────────────────────────────────────────────────
# Session state
# ─────────────────────────────────────────────────────────────────────────────

class ConversationSession:
    """
    Maintains per-session conversation history + metadata.
    Automatically expires after settings.SESSION_TIMEOUT_S seconds.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.history: List[Dict[str, str]] = []
        self.created_at = time.time()
        self.last_activity = time.time()
        self.mode: PipelineMode = PipelineMode.ONLINE
        self.language: Language = Language.ENGLISH
        self.user_role: UserRole = UserRole.STUDENT
        self.class_section: Optional[str] = None

    def touch(self):
        self.last_activity = time.time()

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.last_activity) > settings.SESSION_TIMEOUT_S

    def add_turn(self, user_text: str, assistant_text: str):
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": assistant_text})
        # Keep last 10 turns to respect context window on Pi
        if len(self.history) > 20:
            self.history = self.history[-20:]
        self.touch()


class SessionManager:
    def __init__(self):
        self._sessions: Dict[str, ConversationSession] = {}

    def get_or_create(self, session_id: str) -> ConversationSession:
        if session_id in self._sessions:
            s = self._sessions[session_id]
            if s.is_expired:
                logger.info("Session %s expired, creating new", session_id)
                del self._sessions[session_id]
            else:
                return s
        session = ConversationSession(session_id)
        self._sessions[session_id] = session
        return session

    def expire_session(self, session_id: str):
        self._sessions.pop(session_id, None)

    def cleanup_expired(self):
        expired = [sid for sid, s in self._sessions.items() if s.is_expired]
        for sid in expired:
            del self._sessions[sid]
        if expired:
            logger.info("Cleaned up %d expired sessions", len(expired))


session_manager = SessionManager()


# ─────────────────────────────────────────────────────────────────────────────
# STT routing
# ─────────────────────────────────────────────────────────────────────────────

async def _run_stt(
    audio_pcm: bytes,
    language_hint: Optional[Language] = None,
) -> Tuple[STTResult, FallbackReason]:
    """
    Run STT with Deepgram. Returns (result, fallback_reason).
    """
    try:
        t0 = time.perf_counter()
        result = await asyncio.wait_for(
            deepgram_stt.transcribe_audio_bytes(audio_pcm, language_hint),
            timeout=settings.GEMINI_TIMEOUT_S,
        )
        logger.info(
            "STT (%dms): '%s' conf=%.2f",
            int((time.perf_counter() - t0) * 1000),
            result.transcript[:60],
            result.confidence,
        )
        return result, FallbackReason.NONE
    except asyncio.TimeoutError:
        logger.warning("STT timeout")
        return (
            STTResult(transcript="", confidence=0.0, language=Language.ENGLISH, is_final=False),
            FallbackReason.TIMEOUT,
        )
    except Exception as e:
        logger.exception("STT error: %s", e)
        return (
            STTResult(transcript="", confidence=0.0, language=Language.ENGLISH, is_final=False),
            FallbackReason.NETWORK_ERROR,
        )


# ─────────────────────────────────────────────────────────────────────────────
# LLM routing
# ─────────────────────────────────────────────────────────────────────────────

async def _run_llm(
    prompt: str,
    session: ConversationSession,
    user_role: UserRole,
) -> LLMResponse:
    """
    Route LLM request to Gemini (online) or local LLM (offline).
    Returns LLMResponse.
    """
    system_prompt = get_system_prompt(user_role, session.language)
    t0 = time.perf_counter()

    # ── Try GPT-4o-mini ───────────────────────────────────────────────────
    llm_ok = await connectivity.is_llm_available()
    if llm_ok:
        try:
            text, tool_results, tokens = await asyncio.wait_for(
                openai_service.generate(
                    prompt,
                    system_prompt,
                    history=session.history,
                ),
                timeout=settings.GEMINI_TIMEOUT_S,
            )
            latency = int((time.perf_counter() - t0) * 1000)
            logger.info("GPT-4o-mini OK: latency=%dms tokens=%d", latency, tokens)
            return LLMResponse(
                text=text,
                tool_results=tool_results,
                mode=PipelineMode.ONLINE,
                latency_ms=latency,
                tokens_used=tokens,
            )
        except asyncio.TimeoutError:
            logger.warning("GPT timeout — falling back to offline LLM")
        except Exception as e:
            logger.exception("GPT error: %s", e)

    # ── Offline LLM fallback ──────────────────────────────────────────────
    try:
        text = await offline_llm.generate(
            prompt,
            language=session.language,
            user_role=user_role,
            history=session.history,
        )
        latency = int((time.perf_counter() - t0) * 1000)
        logger.info("Offline LLM: latency=%dms", latency)
        return LLMResponse(
            text=text,
            mode=PipelineMode.OFFLINE,
            fallback_reason=FallbackReason.TIMEOUT,
            latency_ms=latency,
        )
    except Exception as e:
        logger.exception("Offline LLM error: %s", e)

    # ── Hard fallback ─────────────────────────────────────────────────────
    return LLMResponse(
        text="I'm having trouble processing your request right now. Please try again.",
        mode=PipelineMode.OFFLINE,
        fallback_reason=FallbackReason.NETWORK_ERROR,
        latency_ms=int((time.perf_counter() - t0) * 1000),
    )


# ─────────────────────────────────────────────────────────────────────────────
# TTS routing
# ─────────────────────────────────────────────────────────────────────────────

async def _run_tts(
    text: str,
    language: Language,
    preferred_mode: PipelineMode,
) -> Tuple[Optional[bytes], PipelineMode, FallbackReason]:
    """
    Run TTS, returning (wav_bytes, mode_used, fallback_reason).
    Falls back: Deepgram → Piper → None (text only)
    """
    # ── Try Deepgram TTS ──────────────────────────────────────────────────
    if preferred_mode == PipelineMode.ONLINE:
        try:
            wav = await asyncio.wait_for(
                deepgram_tts.synthesize_full(text),
                timeout=8.0,
            )
            if wav:
                return wav, PipelineMode.ONLINE, FallbackReason.NONE
        except asyncio.TimeoutError:
            logger.warning("Deepgram TTS timeout — falling back to Piper")
        except Exception as e:
            logger.warning("Deepgram TTS error: %s", e)

    # ── Try Piper ─────────────────────────────────────────────────────────
    try:
        lang_str = "ta" if language == Language.TAMIL else "en"
        wav = await _piper.synthesize_async(text, lang_str)
        if wav:
            return wav, PipelineMode.OFFLINE, FallbackReason.TTS_FAILURE
    except Exception as e:
        logger.warning("Piper TTS error: %s", e)

    # ── Text only ─────────────────────────────────────────────────────────
    logger.error("All TTS failed — text-only mode")
    return None, PipelineMode.TEXT_ONLY, FallbackReason.TTS_FAILURE


# ─────────────────────────────────────────────────────────────────────────────
# Main orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class VoiceOrchestrator:
    """
    Top-level voice pipeline orchestrator.

    Exposes:
      • process_request(VoiceQueryRequest) → VoiceQueryResponse
      • stream_pipeline(audio_gen, ...) → AsyncGenerator[dict, None]
      • handle_face_event(event, ...) → str (TTS text)
    """

    async def process_request(self, req: VoiceQueryRequest) -> VoiceQueryResponse:
        """
        REST-mode: full pipeline in one call.
        Returns complete VoiceQueryResponse with optional audio.
        """
        t_start = time.perf_counter()
        session = session_manager.get_or_create(req.session_id)

        # Set session metadata
        if req.user_role:
            session.user_role = req.user_role
        if req.class_section:
            session.class_section = req.class_section

        # ── Step 1: STT ───────────────────────────────────────────────────
        stt_fallback = FallbackReason.NONE
        transcript = req.text_query or ""

        if req.audio_b64 and not transcript:
            try:
                audio_pcm, _ = b64_to_pcm(req.audio_b64)
                audio_pcm = trim_silence(audio_pcm)
            except Exception as e:
                logger.error("Audio decode error: %s", e)
                audio_pcm = b""

            if audio_pcm:
                stt_result, stt_fallback = await _run_stt(audio_pcm, req.language_hint)
                transcript = stt_result.transcript
                if not session.language or req.language_hint is None:
                    session.language = await gemini_service.detect_language(transcript)

        if req.language_hint:
            session.language = req.language_hint

        if not transcript:
            return VoiceQueryResponse(
                session_id=req.session_id,
                transcript="",
                response_text="I didn't catch that. Could you speak again?",
                language=session.language,
                mode=PipelineMode.TEXT_ONLY,
                fallback_reason=stt_fallback,
            )

        # ── Step 2: LLM ───────────────────────────────────────────────────
        llm_resp = await _run_llm(transcript, session, req.user_role)

        # ── Step 3: TTS ───────────────────────────────────────────────────
        wav_bytes, tts_mode, tts_fallback = await _run_tts(
            llm_resp.text, session.language, llm_resp.mode
        )

        # ── Update session ────────────────────────────────────────────────
        session.add_turn(transcript, llm_resp.text)
        session.mode = llm_resp.mode

        # ── Build response ────────────────────────────────────────────────
        audio_b64 = base64.b64encode(wav_bytes).decode() if wav_bytes else None
        total_latency = int((time.perf_counter() - t_start) * 1000)
        final_mode = tts_mode if tts_mode != PipelineMode.ONLINE else llm_resp.mode
        final_fallback = tts_fallback if tts_fallback != FallbackReason.NONE else llm_resp.fallback_reason

        logger.info(
            "Pipeline complete: %dms | mode=%s | lang=%s | transcript='%s'",
            total_latency, final_mode, session.language, transcript[:40],
        )

        return VoiceQueryResponse(
            session_id=req.session_id,
            transcript=transcript,
            response_text=llm_resp.text,
            audio_b64=audio_b64,
            language=session.language,
            mode=final_mode,
            fallback_reason=final_fallback,
            latency_ms=total_latency,
            attendance_data=llm_resp.tool_results[0]["result"] if llm_resp.tool_results else None,
        )

    # ─────────────────────────────────────────────────────────────────────
    # Streaming pipeline (WebSocket mode)
    # ─────────────────────────────────────────────────────────────────────

    async def stream_pipeline(
        self,
        audio_gen: AsyncGenerator[bytes, None],
        session_id: str,
        user_role: UserRole = UserRole.STUDENT,
        language_hint: Optional[Language] = None,
        on_transcript: Optional[Any] = None,
        on_llm_chunk: Optional[Any] = None,
        on_tts_chunk: Optional[Any] = None,
    ) -> AsyncGenerator[Dict, None]:
        """
        Fully streaming WebSocket pipeline.

        Yields dict events:
          {"type": "transcript_interim", "text": ...}
          {"type": "transcript_final",   "text": ...}
          {"type": "llm_chunk",          "text": ...}
          {"type": "tts_chunk",          "data_b64": ...}
          {"type": "done",               "latency_ms": ...}
          {"type": "error",              "message": ...}
        """
        session = session_manager.get_or_create(session_id)
        if language_hint:
            session.language = language_hint
        session.user_role = user_role
        t_start = time.perf_counter()

        # ── Streaming STT ─────────────────────────────────────────────────
        transcript_parts = []
        try:
            async for chunk in deepgram_stt.transcribe_stream(audio_gen, language_hint):
                if not chunk.is_final:
                    yield {"type": "transcript_interim", "text": chunk.text}
                else:
                    transcript_parts.append(chunk.text)
                    yield {"type": "transcript_final", "text": chunk.text}
        except Exception as e:
            logger.exception("Streaming STT error: %s", e)
            yield {"type": "error", "message": f"STT failed: {e}"}
            return

        full_transcript = " ".join(transcript_parts).strip()
        if not full_transcript:
            yield {"type": "error", "message": "No speech detected"}
            return

        # Heuristic language detection — zero network cost
        if not language_hint:
            tamil_chars = sum(1 for c in full_transcript if "\u0B80" <= c <= "\u0BFF")
            if tamil_chars > 2:
                session.language = Language.TAMIL
            elif tamil_chars > 0:
                session.language = Language.MIXED
            # else: keep existing session.language (default English)

        # ── Streaming LLM ─────────────────────────────────────────────────
        system_prompt = get_system_prompt(user_role, session.language)
        llm_text_buffer = []
        llm_mode = PipelineMode.ONLINE

        llm_ok = await connectivity.is_llm_available()
        llm_gen = (
            openai_service.stream_generate(
                full_transcript, system_prompt, session.history,
            )
            if llm_ok
            else offline_llm.stream_generate(
                full_transcript, session.language, user_role, session.history
            )
        )
        if not llm_ok:
            llm_mode = PipelineMode.OFFLINE

        # Collect LLM stream and simultaneously start TTS on sentence boundaries
        sentence_buffer = ""
        tts_tasks = []

        async for text_chunk in llm_gen:
            llm_text_buffer.append(text_chunk)
            sentence_buffer += text_chunk
            yield {"type": "llm_chunk", "text": text_chunk}

            # TTS pipeline: fire TTS on sentence boundary for low latency
            if any(sentence_buffer.rstrip().endswith(p) for p in (".", "!", "?", "।")):
                tts_text = sentence_buffer.strip()
                sentence_buffer = ""
                if tts_text:
                    tts_tasks.append(asyncio.create_task(
                        self._stream_tts_chunks(tts_text, session.language, on_tts_chunk)
                    ))

        # Flush remaining sentence buffer
        if sentence_buffer.strip():
            tts_tasks.append(asyncio.create_task(
                self._stream_tts_chunks(sentence_buffer.strip(), session.language, on_tts_chunk)
            ))

        # Wait for all TTS tasks
        if tts_tasks:
            tts_results = await asyncio.gather(*tts_tasks, return_exceptions=True)
            for r in tts_results:
                if isinstance(r, Exception):
                    logger.warning("TTS task error: %s", r)

        # ── Finalise ──────────────────────────────────────────────────────
        full_llm_text = "".join(llm_text_buffer)
        session.add_turn(full_transcript, full_llm_text)
        total_ms = int((time.perf_counter() - t_start) * 1000)

        yield {
            "type": "done",
            "latency_ms": total_ms,
            "mode": llm_mode,
            "transcript": full_transcript,
            "response": full_llm_text,
        }

    async def _stream_tts_chunks(
        self,
        text: str,
        language: Language,
        callback: Optional[Any] = None,
    ):
        """Stream TTS for a sentence, calling callback with each chunk."""
        async for chunk in deepgram_tts.synthesize_stream(text):
            b64 = base64.b64encode(chunk).decode()
            if callback:
                await callback({"type": "tts_chunk", "data_b64": b64})

    # ─────────────────────────────────────────────────────────────────────
    # Face recognition integration
    # ─────────────────────────────────────────────────────────────────────

    async def speak_attendance_confirmation(
        self,
        student_name: str,
        period_id: int,
        language: Language = Language.MIXED,
    ) -> Optional[bytes]:
        """
        Generate and return TTS audio for attendance confirmation.
        Called by face_voice_sync after confirming a student.
        """
        from app.services.face_voice_sync import build_attendance_announcement
        text = build_attendance_announcement(student_name, period_id, "Present", language)

        wav, _, _ = await _run_tts(text, language, PipelineMode.ONLINE)
        return wav

    # ─────────────────────────────────────────────────────────────────────
    # Health
    # ─────────────────────────────────────────────────────────────────────

    async def health(self) -> Dict[str, Any]:
        """Return pipeline health status."""
        gemini_ok, gemini_lat = await gemini_service.health_check()
        online = await connectivity.is_online()

        return {
            "internet": online,
            "gemini": {"ok": gemini_ok, "latency_ms": round(gemini_lat, 1)},
            "offline_llm": {"loaded": offline_llm.is_ready},
            "deepgram_stt": {"configured": bool(settings.DEEPGRAM_API_KEY)},
            "deepgram_tts": {"configured": bool(settings.DEEPGRAM_API_KEY)},
            "piper": {"bin_exists": __import__("os").path.exists(settings.PIPER_BIN)},
            "mode": PipelineMode.ONLINE if (online and gemini_ok) else PipelineMode.OFFLINE,
        }


# ── Module-level singleton ─────────────────────────────────────────────────────
voice_orchestrator = VoiceOrchestrator()
