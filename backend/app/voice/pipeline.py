"""
app/voice/pipeline.py
──────────────────────
Zoro Robot — Main Voice Agent Pipeline

Full pipeline:
  Wake Word → VAD → Deepgram STT → Intent Detection → Classroom Mode Gate
  → Teacher Persona Prompt → Gemini 2.5 Flash → Deepgram TTS → Speaker

This module is the single integration point.
It wires together:
  • classroom_modes.py  — intent, mode, persona prompts
  • wake_word.py        — wake word + VAD
  • deepgram_service.py — STT + TTS
  • gemini_service.py   — LLM
  • voice_orchestrator.py — session + fallback routing
  • attendance_tool.py  — DB hooks for Gemini tools
  • face_voice_sync.py  — face recognition integration

API (integration hooks):
  transcribe_audio(audio_bytes)                    → str
  generate_teacher_response(text, context, ...)     → str
  synthesize_speech(text, language)                 → bytes
  process_voice_input(audio_bytes, context)         → VoiceTurn
  detect_intent(text)                              → Intent
  set_classroom_mode(mode)                         → None
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.core.config import settings
from app.schemas import FallbackReason, Language, PipelineMode, UserRole
from app.services.deepgram_service import deepgram_stt, deepgram_tts
from app.services.gemini_service import GeminiService, gemini_service
from app.services.voice_orchestrator import (
    ConversationSession,
    SessionManager,
    connectivity,
    session_manager,
    voice_orchestrator,
)
from app.voice.classroom_modes import (
    ClassroomContext,
    ClassroomMode,
    Intent,
    build_system_prompt,
    detect_intent,
    is_exam_restricted,
)
from app.services.integrations.rag_service import RAGService

log = logging.getLogger("voice_agent.pipeline")
rag_client = RAGService()


# ── Sanitize layer ────────────────────────────────────────────────────────────

import re

# Common STT artifacts / filler words to strip from transcripts
_STT_NOISE_PATTERNS = re.compile(
    r"\b(um+|uh+|hmm+|ah+|er+|trading|uh-huh|mm-hmm)\b",
    re.IGNORECASE,
)
# Trailing incomplete word after punctuation (e.g. "What is it? I")
_TRAILING_FRAGMENT = re.compile(r"[.!?]\s+[A-Z]?\s*$")


def sanitize_transcript(text: str) -> str:
    """
    Clean up STT output before sending to Gemini.
    - Removes filler words (um, uh, hmm...)
    - Removes known STT hallucinations (e.g. 'Trading' at end of audio)
    - Strips trailing incomplete sentence fragments
    """
    text = _STT_NOISE_PATTERNS.sub("", text)
    # Remove trailing single words after a sentence terminator
    text = re.sub(r"([.!?])\s+\w{1,3}\s*$", r"\1", text)
    # Collapse multiple spaces
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


_MD_BOLD      = re.compile(r"\*{1,2}(.+?)\*{1,2}")
_MD_HEADING   = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_MD_BULLETS   = re.compile(r"^\s*[-*•]\s+", re.MULTILINE)
_MD_NUMBERED  = re.compile(r"^\s*\d+\.\s+", re.MULTILINE)
_MD_CODE      = re.compile(r"`{1,3}[^`]*`{1,3}")
_MD_LINK      = re.compile(r"\[([^\]]+)\]\([^\)]+\)")


def sanitize_llm_output(text: str) -> str:
    """
    Strip markdown so Deepgram TTS doesn't read '**', '#', '-' aloud.
    Converts list items into comma-joined prose for natural speech.
    """
    text = _MD_CODE.sub("", text)          # remove code blocks
    text = _MD_BOLD.sub(r"\1", text)       # **bold** → bold
    text = _MD_HEADING.sub("", text)       # ## Heading → Heading
    text = _MD_LINK.sub(r"\1", text)       # [text](url) → text
    # Convert bullet lists to spoken prose
    lines = text.splitlines()
    cleaned: list[str] = []
    bullet_items: list[str] = []
    for line in lines:
        if _MD_BULLETS.match(line) or _MD_NUMBERED.match(line):
            item = _MD_BULLETS.sub("", _MD_NUMBERED.sub("", line)).strip()
            if item:
                bullet_items.append(item)
        else:
            if bullet_items:
                cleaned.append(". ".join(bullet_items) + ".")
                bullet_items = []
            if line.strip():
                cleaned.append(line.strip())
    if bullet_items:
        cleaned.append(". ".join(bullet_items) + ".")
    text = " ".join(cleaned)
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text

# ── Global LLM gate ──────────────────────────────────────────────────
# Fix 1: one LLM call at a time across ALL sessions
_llm_lock = asyncio.Lock()
# Fix 3: hard cooldown — minimum seconds between LLM calls
_MIN_CALL_GAP_S: float = 3.0
_last_llm_call_at: float = 0.0


def _can_call_llm() -> bool:
    """Return True only if enough time has passed since the last LLM call."""
    global _last_llm_call_at
    now = time.time()
    if now - _last_llm_call_at < _MIN_CALL_GAP_S:
        log.warning(
            "LLM cooldown active — %.1fs since last call (min %.1fs), skipping.",
            now - _last_llm_call_at, _MIN_CALL_GAP_S,
        )
        return False
    _last_llm_call_at = now
    return True


# ── Voice turn result ──────────────────────────────────────────────────────────

@dataclass
class VoiceTurn:
    """Result of one complete voice interaction turn."""
    session_id: str
    transcript: str
    intent: Intent
    response_text: str
    language: Language
    mode: ClassroomMode
    pipeline_mode: PipelineMode
    audio_b64: Optional[str] = None
    latency_ms: int = 0
    fallback_reason: FallbackReason = FallbackReason.NONE
    tool_results: List[Dict] = field(default_factory=list)
    restricted: bool = False    # True if exam mode blocked the request


# ── Classroom session (extends voice session) ─────────────────────────────────

class ClassroomSession:
    """
    Combines ConversationSession with ClassroomContext.
    One session per student or per class interaction.
    """

    def __init__(self, session_id: str, context: Optional[ClassroomContext] = None):
        self.session_id = session_id
        self.voice_session: ConversationSession = session_manager.get_or_create(session_id)
        self.context: ClassroomContext = context or ClassroomContext()
        self.created_at = time.time()

    def set_mode(self, mode: ClassroomMode):
        self.context.mode = mode

    def set_language(self, lang: Language):
        self.context.language = lang
        self.voice_session.language = lang

    @property
    def mode(self) -> ClassroomMode:
        return self.context.mode

    @property
    def language(self) -> Language:
        return self.context.language


# ── Session manager (classroom-aware) ─────────────────────────────────────────

class ClassroomSessionManager:
    def __init__(self):
        self._sessions: Dict[str, ClassroomSession] = {}

    def get_or_create(
        self,
        session_id: str,
        context: Optional[ClassroomContext] = None,
    ) -> ClassroomSession:
        if session_id not in self._sessions:
            self._sessions[session_id] = ClassroomSession(session_id, context)
        return self._sessions[session_id]

    def update_context(self, session_id: str, context: ClassroomContext):
        s = self._sessions.get(session_id)
        if s:
            s.context = context

    def expire(self, session_id: str):
        self._sessions.pop(session_id, None)


classroom_sessions = ClassroomSessionManager()


# ── Integration hooks (public API) ────────────────────────────────────────────

async def transcribe_audio(
    audio_bytes: bytes,
    language_hint: Optional[Language] = None,
) -> str:
    """
    Hook: STT — submit raw PCM (16-bit mono 16 kHz) → return transcript string.

    Integration: call this from robot firmware, ROS node, or WebSocket handler.
    """
    result = await deepgram_stt.transcribe_audio_bytes(audio_bytes, language_hint)
    return result.transcript


async def synthesize_speech(
    text: str,
    language: Language = Language.ENGLISH,
    tts_model: Optional[str] = None,
) -> Optional[bytes]:
    """
    Hook: TTS — convert text to WAV bytes.

    Language routing:
      English → Deepgram Aura (aura-asteria-en)
      Tamil   → Deepgram TTS if available; else Piper fallback
      Mixed   → Deepgram Aura (best code-mixed support)

    Integration: call this from attendance confirmation, robot announcements, etc.
    """
    model = tts_model
    if model is None and language == Language.TAMIL:
        model = "aura-asteria-en"   # Deepgram has limited Tamil; use English voice
        # TODO: swap to Piper Tamil when offline fallback is preferred

    wav = await deepgram_tts.synthesize_full(text)
    return wav


# ── Heuristic-only language detection (no Gemini round-trip) ──────────────────

def _detect_language_fast(text: str) -> Language:
    """
    Pure heuristic language detection — runs in microseconds, no network call.
    Replaces the gemini_service.detect_language() call in hot paths.
    """
    tamil_chars = sum(1 for c in text if "\u0B80" <= c <= "\u0BFF")
    if tamil_chars > 2:
        return Language.TAMIL
    if tamil_chars > 0:
        return Language.MIXED
    tanglish = {
        "enna", "epdi", "yenna", "sollu", "paaru", "vandhaan",
        "irukku", "illai", "nalla", "romba", "konjam",
    }
    if any(w in text.lower() for w in tanglish):
        return Language.MIXED
    return Language.ENGLISH


async def detect_intent_hook(text: str) -> Intent:
    """
    Hook: Intent detection — fast heuristic, no LLM call.

    Integration: pre-filter requests before expensive Gemini call.
    """
    return detect_intent(text)


async def generate_teacher_response(
    text: str,
    context: ClassroomContext,
    history: Optional[List[Dict]] = None,
    session_id: Optional[str] = None,
    enable_tools: bool = True,
) -> tuple[str, List[Dict], int]:
    """
    Hook: LLM — generate a Zoro teacher persona response.

    Parameters
    ----------
    text       : transcribed or typed student input
    context    : current classroom context (mode, topic, language, RAG, etc.)
    history    : conversation history (list of {role, content} dicts)
    session_id : used for logging
    enable_tools : allow Gemini to call attendance DB tools

    Returns
    -------
    (response_text, tool_results, tokens_used)

    Integration: call from any module needing a teacher-style LLM response.
    RAG context: set context.rag_context before calling.
    Personalization: set context.student_name, context.student_id.
    """
    system_prompt = build_system_prompt(
        mode=context.mode,
        language=context.language,
        lesson_topic=context.lesson_topic,
        class_section=context.class_section,
        student_name=context.student_name,
    )

    # Append RAG/attendance context to system prompt
    suffix = context.to_prompt_suffix()
    if suffix:
        system_prompt = system_prompt + "\n\n" + suffix

    # Only enable attendance tools in attendance mode
    use_tools = enable_tools and context.mode == ClassroomMode.ATTENDANCE

    try:
        text_out, tool_results, tokens = await asyncio.wait_for(
            gemini_service.generate(
                prompt=text,
                system_prompt=system_prompt,
                history=history or [],
                enable_tools=use_tools,
                language=context.language,
                user_role=UserRole.STUDENT,
            ),
            timeout=settings.GEMINI_TIMEOUT_S,
        )
        return text_out, tool_results, tokens
    except asyncio.TimeoutError:
        log.warning("generate_teacher_response: Gemini timeout, session=%s", session_id)
        return "Let me think about that. Could you ask again in a moment?", [], 0
    except Exception as exc:
        log.exception("generate_teacher_response error: %s", exc)
        return "I'm having a small technical issue. Please try again.", [], 0


async def process_voice_input(
    audio_bytes: bytes,
    context: Optional[ClassroomContext] = None,
    session_id: Optional[str] = None,
    return_audio: bool = True,
) -> VoiceTurn:
    """
    Hook: Full pipeline — audio in → VoiceTurn out.

    Latency optimisations (vs. original sequential flow):
      • Language detection is heuristic-only (no extra Gemini round-trip).
      • LLM uses streaming; TTS fires on each sentence boundary in parallel,
        so first audio chunk is ready before the LLM finishes.
      • TTS chunks are collected concurrently with ongoing LLM generation.

    Pipeline:
      1. STT (Deepgram)
      2. Language detection (heuristic, ~0 ms)
      3. Intent detection (regex, ~0 ms)
      4. Exam mode guard
      5. Gemini streaming → sentence-pipelined TTS
    """
    t0 = time.perf_counter()
    sid = session_id or str(uuid.uuid4())
    ctx = context or ClassroomContext()
    session = classroom_sessions.get_or_create(sid, ctx)

    # ── 1. STT ───────────────────────────────────────────────────────────
    transcript = await transcribe_audio(audio_bytes, ctx.language)
    if not transcript:
        return VoiceTurn(
            session_id=sid,
            transcript="",
            intent=Intent.UNKNOWN,
            response_text="I didn't hear anything. Please speak clearly.",
            language=ctx.language,
            mode=ctx.mode,
            pipeline_mode=PipelineMode.TEXT_ONLY,
            fallback_reason=FallbackReason.NONE,
        )

    # ── 2. Language detection (heuristic — zero network cost) ────────────
    detected_lang = _detect_language_fast(transcript)
    if detected_lang != ctx.language:
        log.debug("Language switch detected: %s → %s", ctx.language, detected_lang)
        ctx.language = detected_lang
        session.set_language(detected_lang)

    # ── 3. Intent detection ───────────────────────────────────────────────
    intent = detect_intent(transcript)
    log.info("Intent: %s | Mode: %s | Transcript: '%s'", intent, ctx.mode, transcript[:60])

    # ── 4. Exam mode guard ────────────────────────────────────────────────
    if is_exam_restricted(intent, ctx.mode):
        restricted_msg = (
            "I can't help with exam answers. But you can do this — trust yourself!"
            if ctx.language == Language.ENGLISH
            else "Exam-la direct answer sollikka maaten. Neeye yosikanum!"
        )
        wav = await synthesize_speech(restricted_msg, ctx.language) if return_audio else None
        return VoiceTurn(
            session_id=sid,
            transcript=transcript,
            intent=intent,
            response_text=restricted_msg,
            language=ctx.language,
            mode=ctx.mode,
            pipeline_mode=PipelineMode.ONLINE,
            audio_b64=base64.b64encode(wav).decode() if wav else None,
            latency_ms=int((time.perf_counter() - t0) * 1000),
            restricted=True,
        )

    # ── 5. Streaming LLM + pipelined TTS ─────────────────────────────────
    # Build system prompt once
    system_prompt = build_system_prompt(
        mode=ctx.mode,
        language=ctx.language,
        lesson_topic=ctx.lesson_topic,
        class_section=ctx.class_section,
        student_name=ctx.student_name,
    )
    suffix = ctx.to_prompt_suffix()
    if suffix:
        system_prompt = system_prompt + "\n\n" + suffix

    use_tools = ctx.mode == ClassroomMode.ATTENDANCE

    llm_buffer: List[str] = []
    tool_results: List[Dict] = []
    tokens_used: int = 0
    audio_chunks: List[bytes] = []   # collected TTS audio in order
    tts_queue: asyncio.Queue[bytes] = asyncio.Queue()
    sentence_buf = ""
    tts_tasks: List[asyncio.Task] = []

    async def _tts_to_queue(text: str) -> None:
        """Stream one sentence to TTS and push chunks to tts_queue."""
        try:
            async for chunk in deepgram_tts.synthesize_stream(text):
                await tts_queue.put(chunk)
        except Exception as exc:
            log.warning("TTS sentence error: %s", exc)

    try:
        if use_tools:
            # Tools need a full round-trip; fall back gracefully to non-streaming
            response_text, tool_results, tokens_used = await asyncio.wait_for(
                generate_teacher_response(
                    text=transcript,
                    context=ctx,
                    history=session.voice_session.history,
                    session_id=sid,
                ),
                timeout=settings.GEMINI_TIMEOUT_S,
            )
            llm_buffer.append(response_text)
        else:
            # True streaming — fire TTS after each completed sentence
            sentence_puncts = (".", "!", "?", "।")
            gen = gemini_service.stream_generate(
                transcript, system_prompt,
                history=session.voice_session.history,
                enable_tools=False,
                language=ctx.language,
                user_role=UserRole.STUDENT,
            )
            async for text_chunk in gen:
                llm_buffer.append(text_chunk)
                sentence_buf += text_chunk
                if return_audio and any(
                    sentence_buf.rstrip().endswith(p) for p in sentence_puncts
                ):
                    sent = sentence_buf.strip()
                    sentence_buf = ""
                    if sent:
                        tts_tasks.append(asyncio.create_task(_tts_to_queue(sent)))

            # Flush remainder
            if return_audio and sentence_buf.strip():
                tts_tasks.append(asyncio.create_task(_tts_to_queue(sentence_buf.strip())))

    except asyncio.TimeoutError:
        log.warning("process_voice_input: Gemini timeout, session=%s", sid)
        llm_buffer.append("Let me think about that. Could you ask again in a moment?")
    except Exception as exc:
        log.exception("process_voice_input error: %s", exc)
        llm_buffer.append("I'm having a small technical issue. Please try again.")

    response_text = "".join(llm_buffer)

    # Wait for all TTS tasks then collect audio
    if tts_tasks:
        await asyncio.gather(*tts_tasks, return_exceptions=True)
    # Drain the queue
    while not tts_queue.empty():
        audio_chunks.append(tts_queue.get_nowait())

    # If tools were used (no streaming TTS yet), synthesize full response now
    if use_tools and return_audio and response_text:
        wav = await synthesize_speech(response_text, ctx.language)
        if wav:
            audio_chunks.append(wav)

    # Update conversation history
    session.voice_session.add_turn(transcript, response_text)

    wav_bytes = b"".join(audio_chunks) if audio_chunks else None
    latency = int((time.perf_counter() - t0) * 1000)
    log.info(
        "VoiceTurn complete: %dms | intent=%s | mode=%s | tokens=%d",
        latency, intent, ctx.mode, tokens_used,
    )

    return VoiceTurn(
        session_id=sid,
        transcript=transcript,
        intent=intent,
        response_text=response_text,
        language=ctx.language,
        mode=ctx.mode,
        pipeline_mode=PipelineMode.ONLINE,
        audio_b64=base64.b64encode(wav_bytes).decode() if wav_bytes else None,
        latency_ms=latency,
        tool_results=tool_results,
    )


# ── Streaming pipeline variant ─────────────────────────────────────────────────

async def stream_voice_response(
    audio_gen: AsyncGenerator[bytes, None],
    context: Optional[ClassroomContext] = None,
    session_id: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Hook: Fully streaming WebSocket-compatible pipeline.

    Latency optimisations vs. original:
      • Heuristic language detection (no Gemini call).
      • TTS launches concurrently with LLM streaming via asyncio.Task.
        The first sentence's TTS starts as soon as the first '.' is seen,
        while subsequent LLM tokens keep arriving.
      • TTS chunks are immediately yielded as events — no buffering.

    Yields SSE/dict events:
      {"type": "transcript_interim", "text": "..."}
      {"type": "transcript_final",   "text": "..."}
      {"type": "llm_chunk",          "text": "..."}
      {"type": "tts_chunk",          "data_b64": "..."}
      {"type": "done",               "latency_ms": N, "intent": "...", "mode": "..."}
      {"type": "error",              "message": "..."}
      {"type": "exam_restricted",    "message": "..."}

    Integration: Use this inside WebSocket endpoint handlers.
    """
    t0 = time.perf_counter()
    sid = session_id or str(uuid.uuid4())
    ctx = context or ClassroomContext()
    session = classroom_sessions.get_or_create(sid, ctx)

    # ── Streaming STT ──────────────────────────────────────────────────────
    transcript_parts: List[str] = []
    chunks_count = 0
    try:
        async for chunk in deepgram_stt.transcribe_stream(audio_gen, ctx.language):
            chunks_count += 1
            if not chunk.is_final:
                yield {"type": "transcript_interim", "text": chunk.text}
            else:
                transcript_parts.append(chunk.text)
                yield {"type": "transcript_final", "text": chunk.text}
    except Exception as exc:
        log.exception("Streaming STT error: %s", exc)
        yield {"type": "error", "message": f"STT failed: {exc}"}
        return

    full_transcript = " ".join(transcript_parts).strip()
    # Intelligence upgrade: sanitize STT noise/artifacts before any processing
    full_transcript = sanitize_transcript(full_transcript)
    if not full_transcript:
        log.warning("Pipeline: No speech detected after %d STT chunks", chunks_count)
        yield {"type": "error", "message": "No speech detected. Please speak clearly into the microphone."}
        return

    # Heuristic language detection — zero network round-trip
    ctx.language = _detect_language_fast(full_transcript)
    intent = detect_intent(full_transcript)
    yield {"type": "intent", "intent": intent, "mode": ctx.mode}

    # Exam guard
    if is_exam_restricted(intent, ctx.mode):
        msg = "I can't help with exam answers. Believe in yourself!"
        yield {"type": "exam_restricted", "message": msg}
        async for chunk in deepgram_tts.synthesize_stream(msg):
            yield {"type": "tts_chunk", "data_b64": base64.b64encode(chunk).decode()}
        return

    # Fix 2: reject noise / single-word fragments before touching the LLM
    if len(full_transcript) < 3:
        log.warning("Pipeline: transcript too short (%d chars), skipping LLM.", len(full_transcript))
        yield {"type": "error", "message": "Could not understand. Please speak a full sentence."}
        return

    # Fix 3: hard cooldown check
    if not _can_call_llm():
        yield {"type": "error", "message": "Please wait a moment before asking again."}
        return

    # Fix 1: enforce one LLM call at a time (Fix 1)
    if _llm_lock.locked():
        yield {"type": "error", "message": "Still processing your last question — please wait."}
        return

    # ── Streaming LLM + concurrent sentence-level TTS ─────────────────────
    async with _llm_lock:
        
        # --- RAG INTEGRATION INJECTION ---
        # Only fetch RAG if the intent implies asking a question, or by default.
        if intent in [Intent.QUESTION, Intent.EXPLAIN]:
            retrieved_context = await rag_client.retrieve(full_transcript, subject=ctx.lesson_topic)
            if retrieved_context:
                ctx.rag_context = retrieved_context[:1500]

        system_prompt = build_system_prompt(
            mode=ctx.mode,
            language=ctx.language,
            lesson_topic=ctx.lesson_topic,
            class_section=ctx.class_section,
            student_name=ctx.student_name,
        )
        if ctx.to_prompt_suffix():
            system_prompt += "\n\n" + ctx.to_prompt_suffix()

        # Problem 2 fix: enrich prompt so short/partial speech still gets a real answer.
        enriched_transcript = (
            f"The student said: '{full_transcript}'\n"
            f"Intent detected: {intent}\n"
            f"Give a clear, helpful, conversational answer in 1-2 short sentences."
            f" Do NOT use bullet points or markdown."
        )

        llm_buffer: List[str] = []
        sentence_buf = ""
        tts_out: asyncio.Queue[Optional[str]] = asyncio.Queue()
        active_tts_tasks: List[asyncio.Task] = []

        async def _tts_sentence_to_queue(text: str) -> None:
            # Sanitize LLM output before TTS — strip markdown, bullets, **bold** etc.
            clean = sanitize_llm_output(text)
            if not clean.strip():
                await tts_out.put(None)
                return
            try:
                async for pcm in deepgram_tts.synthesize_stream(clean):
                    await tts_out.put(base64.b64encode(pcm).decode())
            except Exception as exc:
                log.warning("TTS sentence error: %s", exc)
            finally:
                await tts_out.put(None)

        use_tools = ctx.mode == ClassroomMode.ATTENDANCE
        gen = gemini_service.stream_generate(
            enriched_transcript, system_prompt,
            history=session.voice_session.history,
            enable_tools=use_tools,
            language=ctx.language,
            user_role=UserRole.STUDENT,
        )

        sentence_puncts = (".", "!", "?", "।")
        pending_tts = 0
        word_count_in_buf = 0
        TTS_WORD_TRIGGER = 6  # Problem 4 fix: fire TTS every 6 words, not just on punctuation

        async for text_chunk in gen:
            llm_buffer.append(text_chunk)
            sentence_buf += text_chunk
            word_count_in_buf += text_chunk.count(" ")
            yield {"type": "llm_chunk", "text": text_chunk}

            while not tts_out.empty():
                item = tts_out.get_nowait()
                if item is None:
                    pending_tts -= 1
                else:
                    yield {"type": "tts_chunk", "data_b64": item}

            # Problem 4 fix: trigger TTS on sentence boundary OR every 6 words
            should_flush = (
                any(sentence_buf.rstrip().endswith(p) for p in sentence_puncts)
                or word_count_in_buf >= TTS_WORD_TRIGGER
            )
            if should_flush:
                sent = sentence_buf.strip()
                sentence_buf = ""
                word_count_in_buf = 0
                if sent:
                    pending_tts += 1
                    active_tts_tasks.append(asyncio.create_task(_tts_sentence_to_queue(sent)))

        if sentence_buf.strip():
            pending_tts += 1
            active_tts_tasks.append(asyncio.create_task(_tts_sentence_to_queue(sentence_buf.strip())))

        while pending_tts > 0:
            item = await tts_out.get()
            if item is None:
                pending_tts -= 1
            else:
                yield {"type": "tts_chunk", "data_b64": item}

        full_response = "".join(llm_buffer)
        session.voice_session.add_turn(full_transcript, full_response)

    yield {
        "type": "done",
        "latency_ms": int((time.perf_counter() - t0) * 1000),
        "intent": intent,
        "mode": ctx.mode,
        "transcript": full_transcript,
        "response": full_response,
    }




# ── Mode controller hook ───────────────────────────────────────────────────────

def set_classroom_mode(session_id: str, mode: ClassroomMode) -> None:
    """
    Hook: Mode controller — switch classroom mode for a session.

    Integration: call from timetable service, teacher dashboard, or robot state.
    Example:
        set_classroom_mode("robot-session", ClassroomMode.TEACHING)
    """
    session = classroom_sessions._sessions.get(session_id)
    if session:
        session.set_mode(mode)
        log.info("Mode changed: session=%s mode=%s", session_id, mode)
    else:
        log.warning("set_classroom_mode: session %s not found", session_id)


def get_classroom_mode(session_id: str) -> ClassroomMode:
    """Hook: get current classroom mode for a session."""
    session = classroom_sessions._sessions.get(session_id)
    return session.mode if session else ClassroomMode.IDLE


# ── RAG + personalization hooks (interfaces only) ────────────────────────────

async def attach_rag_context(
    session_id: str,
    rag_context: str,
) -> None:
    """
    Hook: RAG integration — attach retrieved document context to session.

    Integration: call from RAG service after document retrieval.
    The context is automatically included in next Gemini prompt.

    Example:
        context = await rag_service.retrieve("photosynthesis", top_k=3)
        await attach_rag_context(session_id, context)
    """
    session = classroom_sessions._sessions.get(session_id)
    if session:
        session.context.rag_context = rag_context[:1200]  # cap for Pi token budget


async def attach_student_profile(
    session_id: str,
    student_name: str,
    student_id: Optional[str] = None,
    language: Optional[Language] = None,
) -> None:
    """
    Hook: Personalization — bind student identity to session.

    Integration: call from student login, face recognition, or QR scan.

    Example:
        await attach_student_profile(session_id, "Arjun", student_id="S1001")
    """
    session = classroom_sessions._sessions.get(session_id)
    if session:
        session.context.student_name = student_name
        session.context.student_id = student_id
        if language:
            session.set_language(language)
        log.info("Student profile attached: session=%s name=%s", session_id, student_name)


async def set_lesson_topic(session_id: str, topic: str) -> None:
    """
    Hook: Lesson topic — focus teaching mode on specific subject.

    Integration: call from teacher dashboard or lesson planner.

    Example:
        await set_lesson_topic(session_id, "Laws of Motion — Newton's Second Law")
    """
    session = classroom_sessions._sessions.get(session_id)
    if session:
        session.context.lesson_topic = topic
        log.info("Lesson topic set: session=%s topic=%s", session_id, topic)


# ── Attendance announcement hook ───────────────────────────────────────────────

async def announce_attendance(
    student_name: str,
    status: str,
    language: Language = Language.MIXED,
) -> Optional[bytes]:
    """
    Hook: Attendance confirmation TTS.

    Integration: call from face_voice_sync or robot attendance loop.
    Returns WAV bytes to play through speaker.

    Example:
        wav = await announce_attendance("Priya", "present", Language.MIXED)
        await play_audio(wav)
    """
    from app.services.face_voice_sync import build_attendance_announcement
    text = build_attendance_announcement(student_name, 0, status, language)
    return await synthesize_speech(text, language)

