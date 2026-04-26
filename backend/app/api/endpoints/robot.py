"""
app/api/endpoints/robot.py
──────────────────────────
Robot automation endpoints for Zoro Robot.

GET  /robot/status   — current robot mode and session info
POST /robot/start    — enter classroom; detect session; begin scanning
POST /robot/stop     — complete current session; clear cache; set idle
POST /robot/scan     — submit one camera frame; detect + mark attendance

Robot operation overview
─────────────────────────
1. Robot enters classroom → POST /robot/start {class_section}
2. Backend auto-detects current session from timetable.
3. Robot loops: POST /robot/scan {face_image} every FRAME_SKIP frames.
4. Backend recognises faces, marks attendance (present/late), avoids duplicates.
5. Auto-complete triggers when:
   a. No new face for ROBOT_NO_NEW_FACE_TIMEOUT_SEC seconds, OR
   b. ROBOT_MAX_SCANS exceeded, OR
   c. Session end_time reached.
6. Robot calls GET /robot/status to confirm completion.
7. Robot moves to next classroom.

Fail-safe rules
───────────────
• Retry up to ROBOT_RETRY_ATTEMPTS if a scan returns no faces.
• After retry cap → skip this frame (no infinite loops).
• On any backend error → return error dict; robot continues.
• asyncio.Lock protects all shared robot state mutations.
"""

from __future__ import annotations

import asyncio
import time as _time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

import structlog
from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Attendance, Session, Student
from app.services.attendance_service import (
    complete_session,
    get_active_student_by_code,
    is_already_marked,
    mark_attendance,
    resolve_current_period,
    session_is_open,
)
from app.services.face_service import FaceService
from app.utils.helpers import current_time_local
from app.utils.image_processing import bytes_to_bgr

router = APIRouter(prefix="/robot", tags=["robot"])
log = structlog.get_logger(__name__)


# ── In-memory robot state ─────────────────────────────────────────────────────

class _RobotState:
    """
    All mutable robot state.
    Access is serialised via _robot_lock (asyncio.Lock) in coroutines.
    """
    mode: str = "idle"                      # idle | scanning | completed
    current_session_id: Optional[str] = None
    class_section: Optional[str] = None
    last_updated: Optional[datetime] = None
    already_marked: Set[str] = set()        # school-issued student_id codes (fast in-frame check)
    last_new_face_time: float = 0.0         # monotonic clock for idle-timeout
    scan_count: int = 0
    retry_count: int = 0                    # consecutive empty-scan retries
    error_count: int = 0                    # total errors this session


_robot = _RobotState()
_robot_lock = asyncio.Lock()


# ── GET /robot/status ─────────────────────────────────────────────────────────

@router.get(
    "/status",
    summary="Get the current robot operating status.",
)
async def get_robot_status(
    _user: str = Depends(get_current_user),
) -> dict:
    """Return robot mode, active session, scan counts, and last-updated timestamp."""
    return {
        "mode": _robot.mode,
        "current_session_id": _robot.current_session_id,
        "class_section": _robot.class_section,
        "last_updated": (
            _robot.last_updated.isoformat() if _robot.last_updated else None
        ),
        "scan_count": _robot.scan_count,
        "already_marked_count": len(_robot.already_marked),
        "already_marked": list(_robot.already_marked),
    }


# ── POST /robot/start ─────────────────────────────────────────────────────────

@router.post(
    "/start",
    summary="Signal robot entering a classroom; begin attendance scanning.",
)
async def robot_start(
    class_section: str = Body(..., embed=True, description="Target class section, e.g. '10-A'."),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> dict:
    """
    1. Auto-detect the current session for *class_section* from the timetable.
    2. Create the Session row if absent.
    3. Reset robot state and switch to 'scanning' mode.
    4. Clear in-memory already-marked cache for the new session.
    """
    async with _robot_lock:
        result = await resolve_current_period(db, class_section)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"No active timetable period for class '{class_section}' right now. "
                    "Verify the timetable is uploaded and the server time is correct."
                ),
            )
        _entry, session = result

        # Reset robot state for new session
        _robot.mode = "scanning"
        _robot.current_session_id = session.session_id
        _robot.class_section = class_section
        _robot.already_marked = set()
        _robot.last_new_face_time = _time.monotonic()
        _robot.scan_count = 0
        _robot.retry_count = 0
        _robot.error_count = 0
        _robot.last_updated = datetime.now(timezone.utc)

    log.info(
        "robot.start",
        session_id=session.session_id,
        class_section=class_section,
    )
    return {
        "acknowledged": True,
        "mode": "scanning",
        "session_id": session.session_id,
        "class_section": class_section,
        "start_time": str(session.start_time),
        "end_time": str(session.end_time),
    }


# ── POST /robot/stop ──────────────────────────────────────────────────────────

@router.post(
    "/stop",
    summary="Signal robot leaving classroom; complete the session.",
)
async def robot_stop(
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> dict:
    """
    • Mark the session as 'completed' in the DB.
    • Clear the in-memory attendance cache for this session.
    • Switch robot mode to 'idle'.
    """
    async with _robot_lock:
        session_id = _robot.current_session_id
        if session_id is None or _robot.mode == "idle":
            return {"acknowledged": True, "detail": "No active session to stop."}

        await complete_session(db, session_id)
        await db.commit()

        _robot.mode = "idle"
        _robot.current_session_id = None
        _robot.last_updated = datetime.now(timezone.utc)

    log.info("robot.stop", session_id=session_id)
    return {
        "acknowledged": True,
        "session_id": session_id,
        "mode": "idle",
    }


# ── POST /robot/scan ──────────────────────────────────────────────────────────

@router.post(
    "/scan",
    summary="Submit a camera frame; detect and auto-mark attendance.",
)
async def robot_scan(
    face_image: UploadFile = File(..., description="Camera frame (JPEG/PNG)."),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> dict:
    """
    Full robot scan pipeline:

    1. Validate robot is in 'scanning' mode.
    2. Check session time window; auto-complete if expired.
    3. Enforce ROBOT_MAX_SCANS cap.
    4. Decode + recognise faces from the uploaded frame.
    5. For each known, un-marked face:
       a. Look up student in DB.
       b. Mark attendance (present/late).
       c. Add to in-memory already-marked set.
    6. Check idle-timeout (ROBOT_NO_NEW_FACE_TIMEOUT_SEC).
    7. Return results + robot state.
    """
    # ── Pre-flight checks (under lock) ────────────────────────────────────
    async with _robot_lock:
        if _robot.mode != "scanning":
            return {
                "mode": _robot.mode,
                "detail": "Robot is not in scanning mode.",
                "results": [],
            }

        session_id = _robot.current_session_id
        if session_id is None:
            return {"mode": _robot.mode, "detail": "No active session.", "results": []}

        # Scan cap
        _robot.scan_count += 1
        if _robot.scan_count > settings.ROBOT_MAX_SCANS:
            await _auto_complete(db, session_id, reason="max_scan_cap_reached")
            return {
                "mode": "idle",
                "detail": f"Maximum scan limit ({settings.ROBOT_MAX_SCANS}) reached.",
                "results": [],
            }

    # ── Fetch + validate session (outside lock — DB I/O) ──────────────────
    from sqlalchemy import select as sa_select

    sess_result = await db.execute(
        sa_select(Session).where(Session.session_id == session_id)
    )
    session: Optional[Session] = sess_result.scalar_one_or_none()

    if session is None or not session_is_open(session):
        async with _robot_lock:
            _robot.mode = "idle"
            _robot.current_session_id = None
            _robot.last_updated = datetime.now(timezone.utc)
        if session and session.status != "completed":
            session.status = "completed"
            await db.commit()
        return {"mode": "idle", "detail": "Session ended.", "results": []}

    # ── Decode frame ───────────────────────────────────────────────────────
    raw = await face_image.read()
    bgr = await asyncio.get_event_loop().run_in_executor(None, bytes_to_bgr, raw)
    if bgr is None:
        return {"mode": _robot.mode, "detail": "Unreadable image.", "results": []}

    # ── Face recognition (CPU-bound, outside lock) ─────────────────────────
    face_results = await FaceService.recognise_frame(bgr)

    # ── Process results (under lock for state mutations) ───────────────────
    async with _robot_lock:
        if _robot.mode != "scanning":
            return {"mode": _robot.mode, "results": []}

        results: List[dict] = []
        new_face_detected = False

        for face in face_results:
            if not face["known"]:
                results.append({"status": "unknown", "confidence": face["confidence"]})
                continue

            student_info = face.get("student_info") or {}
            stu_code = student_info.get("student_id")
            stu_name = student_info.get("name", "Unknown")

            if not stu_code:
                results.append({"status": "unknown"})
                continue

            # In-memory fast duplicate check
            if stu_code in _robot.already_marked:
                results.append({
                    "status": "already_marked",
                    "student_id": stu_code,
                    "student_name": stu_name,
                })
                continue

            # DB lookup
            student = await get_active_student_by_code(db, stu_code)
            if student is None:
                results.append({"status": "not_found", "student_id": stu_code})
                continue

            # Mark via service (handles DB duplicate + status logic)
            try:
                att_status, _record = await mark_attendance(
                    db=db,
                    session=session,
                    student=student,
                    confidence=face["confidence"],
                    bounding_box=face["bounding_box"],
                )
                await db.commit()
            except ValueError as ve:
                reason = str(ve)
                if reason in ("already_marked", "session_closed"):
                    if reason == "already_marked":
                        _robot.already_marked.add(stu_code)
                    results.append({
                        "status": reason,
                        "student_id": stu_code,
                        "student_name": stu_name,
                    })
                    continue
                results.append({"status": "error", "detail": reason})
                continue
            except Exception as exc:
                _robot.error_count += 1
                log.error("robot.scan.mark_error", error=str(exc))
                results.append({"status": "error", "detail": str(exc)})
                continue

            _robot.already_marked.add(stu_code)
            _robot.last_new_face_time = _time.monotonic()
            _robot.retry_count = 0
            new_face_detected = True

            log.info(
                "robot.scan.marked",
                student_id=stu_code,
                status=att_status,
                session_id=session_id,
                confidence=round(face["confidence"], 3),
            )
            results.append({
                "status": att_status,
                "student_id": stu_code,
                "student_name": stu_name,
                "confidence": face["confidence"],
            })

        # ── Idle timeout check ─────────────────────────────────────────────
        if not new_face_detected:
            _robot.retry_count += 1

        no_new_timeout = (
            _time.monotonic() - _robot.last_new_face_time
            > settings.ROBOT_NO_NEW_FACE_TIMEOUT_SEC
        )
        retry_exhausted = _robot.retry_count >= settings.ROBOT_RETRY_ATTEMPTS

        if no_new_timeout and retry_exhausted:
            await _auto_complete(db, session_id, reason="no_new_face_timeout")

        _robot.last_updated = datetime.now(timezone.utc)

    return {
        "mode": _robot.mode,
        "session_id": session_id,
        "scan_count": _robot.scan_count,
        "results": results,
    }


# ── Internal auto-complete helper ─────────────────────────────────────────────

async def _auto_complete(
    db: AsyncSession,
    session_id: str,
    reason: str,
) -> None:
    """Mark session completed + switch robot to idle. Must be called under _robot_lock."""
    await complete_session(db, session_id)
    try:
        await db.commit()
    except Exception:
        pass
    _robot.mode = "idle"
    _robot.current_session_id = None
    _robot.last_updated = datetime.now(timezone.utc)
    log.info("robot.auto_completed", session_id=session_id, reason=reason)

