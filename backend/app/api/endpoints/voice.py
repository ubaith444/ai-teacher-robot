"""
app/api/endpoints/voice.py
───────────────────────────
Zoro Robot Voice Agent — FastAPI endpoints.

Endpoints:
  POST  /voice/query          — REST full pipeline (audio or text in → audio + text out)
  POST  /voice/speak          — TTS only (text → streaming WAV)
  POST  /voice/transcribe     — STT only (audio → transcript)
  WS    /voice/stream/{sid}   — Streaming WebSocket pipeline (full duplex)
  POST  /voice/mode           — Set/switch classroom mode
  GET   /voice/mode/{sid}     — Get current classroom mode
  POST  /voice/context/{sid}  — Update classroom context
  POST  /voice/face-event     — Face recognition attendance hook
  GET   /voice/session/{sid}  — Session info
  DELETE /voice/session/{sid} — End session
  GET   /voice/health         — Full pipeline health check

Language support:
  en     — English
  ta     — Tamil
  mixed  — Tamil-English code-mixed (Tanglish)
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.security import get_current_user  # noqa: F401 — correct path
from app.schemas import (
    FaceVoiceSyncRequest,
    Language,
    UserRole,
    VoiceQueryRequest,
    VoiceQueryResponse,
)
from app.services.deepgram_service import deepgram_tts
from app.services.face_voice_sync import (
    build_attendance_announcement,
    face_voice_sync,
)
from app.services.voice_orchestrator import session_manager, voice_orchestrator
from app.voice.classroom_modes import (
    ClassroomContext,
    ClassroomMode,
    detect_intent,
)
from app.voice.pipeline import (
    ClassroomSessionManager,
    VoiceTurn,
    announce_attendance,
    attach_rag_context,
    attach_student_profile,
    classroom_sessions,
    detect_intent_hook,
    generate_teacher_response,
    process_voice_input,
    set_classroom_mode,
    stream_voice_response,
    synthesize_speech,
    transcribe_audio,
)

log = logging.getLogger("voice_agent.api")

router = APIRouter(prefix="/voice", tags=["Voice Agent"])


# ── Request / response schemas ────────────────────────────────────────────────

class VoiceQueryV2Request(BaseModel):
    """Extended voice query with classroom context."""
    session_id: Optional[str] = Field(default=None)
    audio_b64: Optional[str] = Field(default=None, description="Base64-encoded WAV audio")
    text_query: Optional[str] = Field(default=None, description="Text query (bypass STT)")
    mode: Optional[ClassroomMode] = Field(default=None)
    class_section: Optional[str] = Field(default=None)
    lesson_topic: Optional[str] = Field(default=None)
    student_name: Optional[str] = Field(default=None)
    student_id: Optional[str] = Field(default=None)
    rag_context: Optional[str] = Field(default=None)
    language: Optional[Language] = Field(default=None)
    return_audio: bool = Field(default=True)


class ModeUpdateRequest(BaseModel):
    mode: ClassroomMode
    class_section: Optional[str] = None
    lesson_topic: Optional[str] = None


class ContextUpdateRequest(BaseModel):
    mode: Optional[ClassroomMode] = None
    class_section: Optional[str] = None
    lesson_topic: Optional[str] = None
    student_name: Optional[str] = None
    student_id: Optional[str] = None
    rag_context: Optional[str] = None
    language: Optional[Language] = None
    attendance_state: Optional[str] = None


# ── POST /voice/query ─────────────────────────────────────────────────────────

@router.post(
    "/query",
    summary="Process a voice or text query through Zoro's full pipeline.",
)
async def voice_query(
    body: VoiceQueryV2Request,
    _user: str = Depends(get_current_user),
) -> dict:
    """
    Full pipeline:
      audio_b64 or text → STT → Intent → Mode Gate → Gemini → TTS → response

    Returns a VoiceTurn with transcript, response text, and optional base64 WAV.
    """
    if not body.audio_b64 and not body.text_query:
        raise HTTPException(status_code=400, detail="Provide audio_b64 or text_query")

    sid = body.session_id or str(uuid.uuid4())

    ctx = ClassroomContext(
        mode=body.mode or ClassroomMode.IDLE,
        class_section=body.class_section,
        lesson_topic=body.lesson_topic,
        student_name=body.student_name,
        student_id=body.student_id,
        language=body.language or Language.ENGLISH,
        rag_context=body.rag_context,
    )

    try:
        if body.audio_b64:
            audio_bytes = base64.b64decode(body.audio_b64)
            turn = await process_voice_input(
                audio_bytes=audio_bytes,
                context=ctx,
                session_id=sid,
                return_audio=body.return_audio,
            )
        else:
            # Text-only shortcut: skip STT, go straight to LLM
            response, tools, tokens = await generate_teacher_response(
                text=body.text_query,
                context=ctx,
                session_id=sid,
            )
            wav: Optional[bytes] = None
            if body.return_audio:
                wav = await synthesize_speech(response, ctx.language)
            intent = detect_intent(body.text_query)
            turn = VoiceTurn(
                session_id=sid,
                transcript=body.text_query,
                intent=intent,
                response_text=response,
                language=ctx.language,
                mode=ctx.mode,
                pipeline_mode="online",
                audio_b64=base64.b64encode(wav).decode() if wav else None,
                tool_results=tools,
            )

        return {
            "session_id": turn.session_id,
            "transcript": turn.transcript,
            "intent": turn.intent,
            "response_text": turn.response_text,
            "audio_b64": turn.audio_b64,
            "language": turn.language,
            "mode": turn.mode,
            "pipeline_mode": turn.pipeline_mode,
            "latency_ms": turn.latency_ms,
            "restricted": turn.restricted,
            "tool_results": turn.tool_results,
        }

    except Exception as exc:
        log.exception("voice_query error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ── POST /voice/speak ─────────────────────────────────────────────────────────

@router.post(
    "/speak",
    summary="Text → streaming WAV audio via Deepgram TTS.",
)
async def speak_text(
    text: str = Body(..., embed=True),
    language: Language = Language.ENGLISH,
    _user: str = Depends(get_current_user),
) -> StreamingResponse:
    """Convert text to speech. Returns streaming WAV (Content-Type: audio/wav)."""
    if not text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    async def audio_gen():
        async for chunk in deepgram_tts.synthesize_stream(text):
            yield chunk

    return StreamingResponse(audio_gen(), media_type="audio/wav")


# ── POST /voice/transcribe ────────────────────────────────────────────────────

@router.post(
    "/transcribe",
    summary="Audio → transcript via Deepgram STT.",
)
async def transcribe(
    audio: UploadFile = File(..., description="WAV or PCM audio file"),
    language: Optional[str] = Query(default=None, description="en / ta / mixed"),
    _user: str = Depends(get_current_user),
) -> dict:
    """STT only endpoint. Returns transcript and confidence."""
    raw = await audio.read()
    lang_hint = Language(language) if language in ("en", "ta", "mixed") else None

    from app.services.deepgram_service import deepgram_stt
    result = await deepgram_stt.transcribe_audio_bytes(raw, lang_hint)

    return {
        "transcript": result.transcript,
        "confidence": result.confidence,
        "language": result.language,
        "duration_ms": result.duration_ms,
    }


# ── WS /voice/stream/{session_id} ─────────────────────────────────────────────

@router.websocket("/stream/{session_id}")
async def voice_stream_ws(
    websocket: WebSocket,
    session_id: str,
    mode: Optional[str] = None,
    lang: Optional[str] = None,
    class_section: Optional[str] = None,
):
    """
    Full duplex streaming WebSocket.

    Client → Server (binary): raw PCM (16-bit mono 16 kHz)
    Client → Server (JSON):
      {"type": "session_start", "payload": {"mode": "teaching", "class_section": "10-A"}}
      {"type": "audio_done"}       — signal end of utterance
      {"type": "mode_change",  "payload": {"mode": "practice"}}
      {"type": "session_end"}

    Server → Client (JSON):
      {"type": "transcript_interim", "text": "..."}
      {"type": "transcript_final",   "text": "..."}
      {"type": "intent",             "intent": "..."}
      {"type": "llm_chunk",          "text": "..."}
      {"type": "tts_chunk",          "data_b64": "..."}
      {"type": "exam_restricted",    "message": "..."}
      {"type": "done",               "latency_ms": N}
      {"type": "error",              "message": "..."}
      {"type": "pong",               "ts": N}
    """
    await websocket.accept()
    log.info("WS connected: session=%s mode=%s lang=%s", session_id, mode, lang)

    # Build initial context
    ctx = ClassroomContext(
        mode=ClassroomMode(mode) if mode in [m.value for m in ClassroomMode] else ClassroomMode.IDLE,
        language=Language(lang) if lang in ("en", "ta", "mixed") else Language.ENGLISH,
        class_section=class_section,
    )

    audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=300)
    pipeline_task: Optional[asyncio.Task] = None
    active = asyncio.Event()

    async def audio_gen():
        while True:
            chunk = await audio_queue.get()
            if chunk == b"__END__":
                break
            yield chunk

    async def send(msg_type: str, payload: Dict):
        try:
            await websocket.send_json({
                "type": msg_type,
                "session_id": session_id,
                "ts": time.time(),
                **payload,
            })
        except Exception:
            pass

    async def run_pipeline():
        try:
            async for event in stream_voice_response(
                audio_gen(),
                context=ctx,
                session_id=session_id,
            ):
                ev_type = event.pop("type", "unknown")
                await send(ev_type, event)
        except Exception as exc:
            await send("error", {"message": str(exc)})
        finally:
            active.clear()

    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive(), timeout=30.0)
            except asyncio.TimeoutError:
                await send("ping", {})
                continue

            if data.get("type") == "websocket.disconnect":
                break

            # Binary audio frame
            if data.get("bytes"):
                audio_queue.put_nowait(data["bytes"])
                if not pipeline_task or pipeline_task.done():
                    log.debug("Starting voice pipeline for session=%s", session_id)
                    active.set()
                    pipeline_task = asyncio.create_task(run_pipeline())
                continue

            # JSON control
            if data.get("text"):
                try:
                    msg = json.loads(data["text"])
                except json.JSONDecodeError:
                    continue

                t = msg.get("type", "")
                p = msg.get("payload", {})

                if t == "session_start":
                    ctx.mode = ClassroomMode(p.get("mode", ctx.mode))
                    ctx.class_section = p.get("class_section", ctx.class_section)
                    ctx.lesson_topic = p.get("lesson_topic")
                    await send("session_start", {"session_id": session_id, "mode": ctx.mode})

                elif t == "mode_change":
                    ctx.mode = ClassroomMode(p.get("mode", ctx.mode))
                    await send("mode_ack", {"mode": ctx.mode})

                elif t == "audio_done":
                    await audio_queue.put(b"__END__")
                    if pipeline_task:
                        await pipeline_task
                    pipeline_task = None
                    active.clear()

                elif t == "session_end":
                    await audio_queue.put(b"__END__")
                    if pipeline_task:
                        await pipeline_task
                    break

                elif t == "ping":
                    await send("pong", {"ts": time.time()})

    except WebSocketDisconnect:
        log.info("WS disconnected: session=%s", session_id)
    except Exception as exc:
        log.exception("WS error session=%s: %s", session_id, exc)
    finally:
        await audio_queue.put(b"__END__")
        if pipeline_task and not pipeline_task.done():
            pipeline_task.cancel()
        log.info("WS session closed: %s", session_id)


# ── POST /voice/mode ──────────────────────────────────────────────────────────

@router.post(
    "/mode",
    summary="Set classroom mode for a session.",
)
async def set_mode(
    session_id: str = Query(...),
    body: ModeUpdateRequest = Body(...),
    _user: str = Depends(get_current_user),
) -> dict:
    """Switch classroom mode (idle/attendance/teaching/practice/exam)."""
    set_classroom_mode(session_id, body.mode)
    if body.class_section or body.lesson_topic:
        s = classroom_sessions._sessions.get(session_id)
        if s:
            if body.class_section:
                s.context.class_section = body.class_section
            if body.lesson_topic:
                s.context.lesson_topic = body.lesson_topic
    return {"session_id": session_id, "mode": body.mode}


# ── GET /voice/mode/{session_id} ────────────────────────────────────────────────

@router.get("/mode/{session_id}", summary="Get current classroom mode.")
async def get_mode(
    session_id: str,
    _user: str = Depends(get_current_user),
) -> dict:
    from app.voice.pipeline import get_classroom_mode
    mode = get_classroom_mode(session_id)
    return {"session_id": session_id, "mode": mode}


# ── POST /voice/context/{session_id} ──────────────────────────────────────────

@router.post(
    "/context/{session_id}",
    summary="Update classroom context (RAG, student profile, lesson topic, etc.).",
)
async def update_context(
    session_id: str,
    body: ContextUpdateRequest,
    _user: str = Depends(get_current_user),
) -> dict:
    """
    Attach context to a voice session.
    Typically called by:
      - RAG service (after document retrieval)
      - Teacher dashboard (lesson topic, mode)
      - Face recognition (student identity)
      - Attendance service (attendance state)
    """
    session = classroom_sessions._sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id!r} not found")

    if body.mode:
        session.context.mode = body.mode
    if body.class_section:
        session.context.class_section = body.class_section
    if body.lesson_topic:
        session.context.lesson_topic = body.lesson_topic
    if body.student_name:
        session.context.student_name = body.student_name
    if body.student_id:
        session.context.student_id = body.student_id
    if body.rag_context:
        session.context.rag_context = body.rag_context[:1200]
    if body.language:
        session.set_language(body.language)
    if body.attendance_state:
        session.context.attendance_state = body.attendance_state

    return {"updated": True, "session_id": session_id}


# ── POST /voice/face-event ────────────────────────────────────────────────────

@router.post(
    "/face-event",
    summary="Inject face recognition event → voice attendance confirmation.",
)
async def face_event(
    body: FaceVoiceSyncRequest,
    _user: str = Depends(get_current_user),
) -> dict:
    """
    Receive a face detection event from the face recognition service.
    Runs: blur filter → multi-frame vote → TTS announcement.
    """
    try:
        result = await face_voice_sync.process_event(body.event, language=body.language)
        if result:
            # Generate and return TTS audio for robot speaker
            wav = await announce_attendance(
                student_name=result["student_name"],
                status=result["status"],
                language=body.language,
            )
            return {
                "confirmed": True,
                "attendance": result,
                "audio_b64": base64.b64encode(wav).decode() if wav else None,
            }
        return {"confirmed": False, "message": "Collecting more frames..."}
    except Exception as exc:
        log.exception("face_event error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ── GET /voice/session/{session_id} ───────────────────────────────────────────

@router.get("/session/{session_id}", summary="Get voice session info.")
async def get_session(
    session_id: str,
    _user: str = Depends(get_current_user),
) -> dict:
    s = classroom_sessions._sessions.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "mode": s.context.mode,
        "language": s.context.language,
        "class_section": s.context.class_section,
        "lesson_topic": s.context.lesson_topic,
        "student_name": s.context.student_name,
        "has_rag_context": bool(s.context.rag_context),
        "history_turns": len(s.voice_session.history) // 2,
    }


# ── DELETE /voice/session/{session_id} ────────────────────────────────────────

@router.delete("/session/{session_id}", summary="End and clear a voice session.")
async def delete_session(
    session_id: str,
    _user: str = Depends(get_current_user),
) -> dict:
    classroom_sessions.expire(session_id)
    session_manager.expire_session(session_id)
    return {"deleted": True, "session_id": session_id}


# ── GET /voice/health ─────────────────────────────────────────────────────────

@router.get("/health", summary="Voice agent pipeline health check.")
async def health(_user: str = Depends(get_current_user)) -> dict:
    """Check Gemini, Deepgram, Piper, internet connectivity."""
    return await voice_orchestrator.health()

