"""
routers/voice_attendance.py — FastAPI endpoints for the Voice Agent.

Endpoints:
  POST /voice/query          — REST: send audio/text, get audio/text response
  WS   /voice/stream/{sid}  — WebSocket: full duplex streaming pipeline
  POST /voice/face-event     — Face recognition attendance confirmation
  GET  /voice/session/{sid}  — Session info
  DELETE /voice/session/{sid} — End session
  GET  /voice/health          — Pipeline health check

FIX v1.0.1:
  - Removed `from __future__ import annotations`.
    With PEP 563 active, all annotations become strings (ForwardRef).
    When @limiter.limit() wraps a route handler, the wrapper's __globals__
    belong to slowapi's module — Pydantic cannot find 'VoiceQueryRequest'
    in that namespace → PydanticUndefinedAnnotation crash at import time.
  - Removed per-route @limiter.limit decorators entirely.
    Rate limiting is applied globally via SlowAPI middleware in main.py.
  - Fixed `request: Request = None` (invalid FastAPI default).
  - Removed unused imports (JSONResponse, Depends, WSMessage).
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from app.schemas import (
    FaceVoiceSyncRequest,
    Language,
    UserRole,
    VoiceQueryRequest,
    VoiceQueryResponse,
)
from app.services.face_voice_sync import face_voice_sync
from app.services.voice_orchestrator import session_manager, voice_orchestrator

logger = logging.getLogger("voice_agent.router")

router = APIRouter(prefix="/voice", tags=["Voice Agent"])

# ─────────────────────────────────────────────────────────────────────────────
# REST — voice query
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/query", response_model=VoiceQueryResponse, summary="Process a voice or text query"
)
async def voice_query(request: Request, body: VoiceQueryRequest):
    """
    Submit a voice query (base64 WAV) or text query.
    Returns transcription, LLM response text, and optional base64 WAV audio.
    """
    if not body.audio_b64 and not body.text_query:
        raise HTTPException(
            status_code=400, detail="Provide either audio_b64 or text_query"
        )

    if not body.session_id:
        body.session_id = str(uuid.uuid4())

    try:
        response = await voice_orchestrator.process_request(body)
        return response
    except Exception as e:
        logger.exception("voice_query error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# REST — streaming TTS only (send text, get audio stream)
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/speak", summary="Convert text to speech (streaming WAV)")
async def speak_text(
    request: Request,
    text: str,
    language: Language = Language.ENGLISH,
):
    """Return streaming WAV audio for given text."""
    from app.services.deepgram_service import deepgram_tts

    async def audio_generator():
        async for chunk in deepgram_tts.synthesize_stream(text):
            yield chunk

    return StreamingResponse(audio_generator(), media_type="audio/wav")


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket — full duplex streaming pipeline
# ─────────────────────────────────────────────────────────────────────────────


@router.websocket("/stream/{session_id}")
async def voice_stream_ws(
    websocket: WebSocket,
    session_id: str,
    role: str = "student",
    lang: Optional[str] = None,
):
    """
    WebSocket endpoint for the full streaming voice pipeline.

    Client sends:
      {"type": "session_start", "payload": {"class_section": "10A"}}
      Binary frames: raw PCM (16-bit mono 16kHz)
      {"type": "session_end"}

    Server sends:
      {"type": "transcript_interim", "payload": {"text": "..."}}
      {"type": "transcript_final",   "payload": {"text": "..."}}
      {"type": "llm_chunk",          "payload": {"text": "..."}}
      {"type": "tts_chunk",          "payload": {"data_b64": "..."}}
      {"type": "done",               "payload": {...}}
      {"type": "error",              "payload": {"message": "..."}}
    """
    await websocket.accept()
    logger.info("WS connected: session=%s role=%s", session_id, role)

    user_role = UserRole.TEACHER if role == "teacher" else UserRole.STUDENT
    language_hint = Language(lang) if lang in ("en", "ta", "mixed") else None

    # Audio buffer — accumulated from binary WS frames
    audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=200)
    pipeline_task: Optional[asyncio.Task] = None
    pipeline_running = asyncio.Event()

    async def audio_generator():
        """Feed audio_queue as async generator for STT."""
        while True:
            chunk = await audio_queue.get()
            if chunk == b"__END__":
                break
            yield chunk

    async def send_event(msg_type: str, payload: Dict):
        """Send JSON event to client."""
        msg = {
            "type": msg_type,
            "session_id": session_id,
            "payload": payload,
            "ts": time.time(),
        }
        try:
            await websocket.send_json(msg)
        except Exception:
            pass

    async def tts_callback(tts_event: Dict):
        await send_event(tts_event["type"], tts_event)

    async def run_pipeline():
        """Run the streaming pipeline and relay events to WS client."""
        try:
            async for event in voice_orchestrator.stream_pipeline(
                audio_generator(),
                session_id=session_id,
                user_role=user_role,
                language_hint=language_hint,
                on_tts_chunk=tts_callback,
            ):
                await send_event(event.get("type", "unknown"), event)
        except Exception as e:
            await send_event("error", {"message": str(e)})
        finally:
            pipeline_running.clear()

    try:
        while True:
            # Receive from client
            try:
                data = await asyncio.wait_for(websocket.receive(), timeout=30.0)
            except asyncio.TimeoutError:
                await send_event("ping", {})
                continue

            if data.get("type") == "websocket.disconnect":
                break

            # Handle binary audio
            if "bytes" in data and data["bytes"]:
                audio_queue.put_nowait(data["bytes"])

                # Start pipeline on first audio chunk
                if not pipeline_running.is_set():
                    pipeline_running.set()
                    pipeline_task = asyncio.create_task(run_pipeline())
                continue

            # Handle JSON control messages
            if "text" in data:
                try:
                    msg = json.loads(data["text"])
                except json.JSONDecodeError:
                    continue

                msg_type = msg.get("type", "")

                if msg_type == "session_start":
                    session = session_manager.get_or_create(session_id)
                    session.class_section = msg.get("payload", {}).get("class_section")
                    await send_event("session_start", {"session_id": session_id})

                elif msg_type == "session_end":
                    await audio_queue.put(b"__END__")
                    if pipeline_task:
                        await pipeline_task
                    break

                elif msg_type == "ping":
                    await send_event("pong", {"ts": time.time()})

                elif msg_type == "audio_done":
                    # Client signals end of utterance
                    await audio_queue.put(b"__END__")
                    if pipeline_task:
                        await pipeline_task
                    pipeline_task = None
                    pipeline_running.clear()

    except WebSocketDisconnect:
        logger.info("WS disconnected: session=%s", session_id)
    except Exception as e:
        logger.exception("WS error session=%s: %s", session_id, e)
    finally:
        await audio_queue.put(b"__END__")
        if pipeline_task and not pipeline_task.done():
            pipeline_task.cancel()
        logger.info("WS session closed: %s", session_id)


# ─────────────────────────────────────────────────────────────────────────────
# Face recognition event webhook
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/face-event", summary="Process a face recognition event")
async def face_event(body: FaceVoiceSyncRequest):
    """
    Receive a face detection event from the face recognition service.
    Runs blur filtering + multi-frame voting + TTS confirmation.
    """
    try:
        result = await face_voice_sync.process_event(
            body.event,
            language=body.language,
        )
        if result:
            return {"confirmed": True, "attendance": result}
        return {"confirmed": False, "message": "Collecting votes..."}
    except Exception as e:
        logger.exception("Face event error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Session management
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/session/{session_id}", summary="Get session info")
async def get_session(session_id: str):
    session = session_manager._sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "language": session.language,
        "user_role": session.user_role,
        "class_section": session.class_section,
        "history_turns": len(session.history) // 2,
        "mode": session.mode,
        "last_activity": session.last_activity,
    }


@router.delete("/session/{session_id}", summary="End and delete a session")
async def delete_session(session_id: str):
    session_manager.expire_session(session_id)
    return {"deleted": True, "session_id": session_id}


# ─────────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/health", summary="Pipeline health check")
async def health():
    return await voice_orchestrator.health()


# ─────────────────────────────────────────────────────────────────────────────
# Attendance query (direct — bypasses voice)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/attendance/student", summary="Direct attendance query for a student")
async def get_student_attendance(
    name: Optional[str] = None,
    student_id: Optional[int] = None,
    date: Optional[str] = None,
    period_id: Optional[int] = None,
):
    from app.services.attendance_tool import get_student_attendance as _get

    result = await _get(
        student_name=name,
        student_id=student_id,
        att_date=date,
        period_id=period_id,
    )
    if not result.get("found"):
        raise HTTPException(status_code=404, detail=result.get("message", "Not found"))
    return result


@router.get("/attendance/class", summary="Direct attendance query for a class")
async def get_class_attendance(
    class_section: str,
    date: Optional[str] = None,
    period_id: Optional[int] = None,
):
    from app.services.attendance_tool import get_class_attendance as _get

    result = await _get(
        class_section=class_section,
        att_date=date,
        period_id=period_id,
    )
    if not result.get("found"):
        raise HTTPException(status_code=404, detail=result.get("message", "Not found"))
    return result


@router.get("/attendance/today/{class_section}", summary="Today's summary for a class")
async def get_today_summary(class_section: str):
    from app.services.attendance_tool import get_today_summary as _get

    result = await _get(class_section=class_section)
    if not result.get("found"):
        raise HTTPException(status_code=404, detail=result.get("message", "Not found"))
    return result
