"""
app/api/endpoints/attendance.py
────────────────────────────────
Attendance marking, querying, and export endpoints.

POST /attendance/mark              — mark one student (face image or student_id)
GET  /attendance/today             — today's records (filtered)
GET  /attendance/report            — records with date / class / session filters
GET  /attendance/session-summary   — aggregate counts per session
GET  /attendance/export/csv        — download as CSV
GET  /attendance/export/excel      — download as Excel (.xlsx)
"""

from __future__ import annotations

import io
from datetime import date, datetime, timezone
from typing import List, Optional

import structlog
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
    WebSocket,
    WebSocketDisconnect
)
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Attendance, Session, Student
from app.schemas.attendance import (
    AttendanceListResponse,
    AttendanceMarkRequest,
    AttendanceMarkResponse,
    AttendanceRecordOut,
    SessionSummaryOut,
)
from app.services.attendance_service import (
    get_active_student_by_code,
    get_session,
    is_already_marked,
    mark_attendance,
)
from app.services.face_service import FaceService
from app.utils.helpers import (
    build_csv_bytes,
    build_excel_bytes,
    current_date_local,
)
from app.utils.image_processing import bytes_to_bgr
from app.core.config import settings

router = APIRouter(prefix="/attendance", tags=["attendance"])
log = structlog.get_logger(__name__)

_EXPORT_FIELDS = [
    "student_id", "name", "class_section",
    "session_id", "date", "status", "confidence",
]


# ── POST /attendance/mark ──────────────────────────────────────────────────────

@router.post(
    "/mark",
    response_model=AttendanceMarkResponse,
    summary="Mark attendance for one student in a session.",
)
async def mark_attendance_endpoint(
    session_id: str = Query(..., description="Target session identifier."),
    student_id: Optional[str] = Query(
        default=None,
        description="School-issued student_id (skip recognition when provided).",
    ),
    confidence: Optional[float] = Query(default=None),
    bounding_box_json: Optional[str] = Query(
        default=None, description="JSON string {x,y,w,h}."
    ),
    face_image: Optional[UploadFile] = File(
        default=None, description="Face image for recognition pipeline."
    ),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> AttendanceMarkResponse:
    """
    Mark one student attendance in *session_id*.

    Resolution order:
      1. face_image supplied → run face recognition, identify student.
      2. student_id supplied → direct DB lookup (no recognition).
    """
    import json as _json

    # Validate session
    session = await get_session(db, session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found.",
        )
    if session.status == "completed":
        return AttendanceMarkResponse(status="session_closed", session_id=session_id)

    # Parse optional bounding box
    bbox: Optional[dict] = None
    if bounding_box_json:
        try:
            bbox = _json.loads(bounding_box_json)
        except Exception:
            bbox = None

    # Identify student
    recognised_confidence = confidence
    recognised_bbox = bbox
    resolved_student: Optional[Student] = None

    if face_image is not None:
        raw = await face_image.read()
        bgr = bytes_to_bgr(raw)
        if bgr is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Uploaded file is not a readable image.",
            )
        face_results = await FaceService.recognise_frame(bgr)
        known_result = next((r for r in face_results if r["known"]), None)
        if known_result is None:
            log.info("mark_attendance.unknown_face", session_id=session_id)
            return AttendanceMarkResponse(status="unknown", session_id=session_id)

        recognised_confidence = known_result["confidence"]
        recognised_bbox = known_result["bounding_box"]
        stu_code = (known_result.get("student_info") or {}).get("student_id")
        if stu_code:
            resolved_student = await get_active_student_by_code(db, stu_code)

    elif student_id is not None:
        resolved_student = await get_active_student_by_code(db, student_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide either 'face_image' or 'student_id'.",
        )

    if resolved_student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found or inactive.",
        )

    # Mark attendance via service
    try:
        att_status, record = await mark_attendance(
            db=db,
            session=session,
            student=resolved_student,
            confidence=recognised_confidence,
            bounding_box=recognised_bbox,
        )
        await db.commit()
    except ValueError as ve:
        reason = str(ve)
        if reason in ("already_marked", "session_closed"):
            return AttendanceMarkResponse(
                status=reason,
                session_id=session_id,
                student_id=resolved_student.student_id,
                student_name=resolved_student.name,
                confidence=recognised_confidence,
                bounding_box=recognised_bbox,
            )
        raise HTTPException(status_code=500, detail=reason)

    return AttendanceMarkResponse(
        status=att_status,
        session_id=session_id,
        student_id=resolved_student.student_id,
        student_name=resolved_student.name,
        confidence=recognised_confidence,
        bounding_box=recognised_bbox,
        marked_at=record.created_at,
    )

# ── WEBSOCKET /attendance/video-stream (Real-Time Recognition pipeline) ────────

# Global to store the latest frame for the dashboard preview
latest_frame: Optional[bytes] = None

@router.websocket("/video-stream")
async def video_stream_endpoint(websocket: WebSocket, db: AsyncSession = Depends(get_db)):
    """
    WebSocket for the Raspberry Pi to stream camera frames to the laptop.
    The laptop runs OpenCV/LBPH locally and returns the recognized student name.
    """
    global latest_frame
    await websocket.accept()
    log.info("video_stream.connected", client=websocket.client)
    try:
        while True:
            # Receive JPEG bytes from Pi
            data = await websocket.receive_bytes()
            latest_frame = data # Update global preview
            
            # Decode JPEG
            bgr = bytes_to_bgr(data)
            if bgr is None:
                continue

            # Run Heavy AI Face Recognition on Laptop
            face_results = await FaceService.recognise_frame(bgr)
            known_result = next((r for r in face_results if r["known"]), None)
            
            if known_result:
                stu_code = (known_result.get("student_info") or {}).get("student_id")
                student_name = (known_result.get("student_info") or {}).get("name", "Unknown")
                
                # Optionally mark attendance automatically here or wait for UI.
                await websocket.send_json({
                    "type": "recognition",
                    "student_id": stu_code,
                    "student_name": student_name,
                    "confidence": known_result["confidence"]
                })
    except WebSocketDisconnect:
        log.info("video_stream.disconnected", client=websocket.client)
    except Exception as exc:
        log.error("video_stream.error", error=str(exc))
        try:
            await websocket.close()
        except:
            pass

@router.get("/stream")
async def video_feed():
    """
    MJPEG streaming endpoint for the frontend to view the robot's camera.
    """
    async def frame_generator():
        global latest_frame
        while True:
            if latest_frame:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + latest_frame + b'\r\n')
            await asyncio.sleep(0.1) # 10 FPS matching the Pi client

    return StreamingResponse(frame_generator(), media_type='multipart/x-mixed-replace; boundary=frame')


# ── GET /attendance/today ──────────────────────────────────────────────────────

@router.get(
    "/today",
    response_model=AttendanceListResponse,
    summary="Get today's attendance records.",
)
async def get_today_attendance(
    class_section: Optional[str] = Query(default=None),
    session_id: Optional[str] = Query(default=None),
    student_id: Optional[str] = Query(default=None, description="School-issued student_id."),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> AttendanceListResponse:
    today = current_date_local(settings.TIMEZONE)
    return await _query_attendance(
        db,
        date_filter=today,
        class_section=class_section,
        session_id=session_id,
        student_id_code=student_id,
    )


# ── GET /attendance/report ─────────────────────────────────────────────────────

@router.get(
    "/report",
    response_model=AttendanceListResponse,
    summary="Get attendance report with optional filters.",
)
async def get_attendance_report(
    date_filter: Optional[date] = Query(default=None, alias="date"),
    class_section: Optional[str] = Query(default=None),
    session_id: Optional[str] = Query(default=None),
    student_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> AttendanceListResponse:
    return await _query_attendance(
        db,
        date_filter=date_filter,
        class_section=class_section,
        session_id=session_id,
        student_id_code=student_id,
    )


# ── GET /attendance/session-summary ───────────────────────────────────────────

@router.get(
    "/session-summary",
    response_model=List[SessionSummaryOut],
    summary="Aggregate attendance counts per session.",
)
async def session_summary(
    date_filter: Optional[date] = Query(default=None, alias="date"),
    class_section: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> List[SessionSummaryOut]:
    """Return total / present / late counts for each session matching filters."""
    today = date_filter or current_date_local(settings.TIMEZONE)

    # Fetch sessions
    q = select(Session).where(Session.date == today)
    if class_section:
        q = q.where(Session.class_section == class_section)
    session_rows = (await db.execute(q)).scalars().all()

    summaries = []
    for sess in session_rows:
        # Aggregate attendance counts
        count_q = select(
            func.count(Attendance.id),
            func.count(Attendance.id).filter(Attendance.status == "present"),
            func.count(Attendance.id).filter(Attendance.status == "late"),
        ).where(Attendance.session_id == sess.session_id)
        total, present_c, late_c = (await db.execute(count_q)).one()
        summaries.append(
            SessionSummaryOut(
                session_id=sess.session_id,
                class_section=sess.class_section,
                date=sess.date,
                period_number=sess.period_number,
                subject=sess.subject,
                status=sess.status,
                total_marked=total,
                present_count=present_c,
                late_count=late_c,
            )
        )
    return summaries


# ── Shared query builder ───────────────────────────────────────────────────────

async def _query_attendance(
    db: AsyncSession,
    date_filter: Optional[date],
    class_section: Optional[str],
    session_id: Optional[str],
    student_id_code: Optional[str],
) -> AttendanceListResponse:
    """Generic query builder used by today + report endpoints."""
    q = select(Attendance).options(
        selectinload(Attendance.student),
        selectinload(Attendance.session),
    )
    conditions = []

    if session_id:
        conditions.append(Attendance.session_id == session_id)

    if date_filter or class_section:
        q = q.join(Session, Attendance.session_id == Session.session_id, isouter=True)
        if date_filter:
            conditions.append(Session.date == date_filter)
        if class_section:
            conditions.append(Session.class_section == class_section)

    if student_id_code:
        q = q.join(Student, Attendance.student_id == Student.id, isouter=True)
        conditions.append(Student.student_id == student_id_code)

    if conditions:
        q = q.where(and_(*conditions))

    rows = (await db.execute(q)).scalars().unique().all()
    items = [
        AttendanceRecordOut(
            id=r.id,
            session_id=r.session_id,
            student_id=r.student_id,
            student_code=r.student.student_id if r.student else None,
            student_name=r.student.name if r.student else None,
            class_section=r.student.class_section if r.student else None,
            status=r.status,
            confidence=r.confidence,
            bounding_box=r.bounding_box,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return AttendanceListResponse(items=items, total=len(items))


# ── GET /attendance/export/csv ─────────────────────────────────────────────────

@router.get(
    "/export/csv",
    summary="Download attendance as CSV.",
)
async def export_csv(
    date_filter: Optional[date] = Query(default=None, alias="date"),
    class_section: Optional[str] = Query(default=None),
    session_id: Optional[str] = Query(default=None),
    student_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> StreamingResponse:
    report = await _query_attendance(
        db,
        date_filter=date_filter,
        class_section=class_section,
        session_id=session_id,
        student_id_code=student_id,
    )
    rows = [
        {
            "student_id": r.student_code or "",
            "name": r.student_name or "",
            "class_section": r.class_section or "",
            "session_id": r.session_id or "",
            "date": str(r.created_at.date()) if r.created_at else "",
            "status": r.status,
            "confidence": str(round(r.confidence, 4)) if r.confidence is not None else "",
        }
        for r in report.items
    ]
    csv_bytes = build_csv_bytes(rows, _EXPORT_FIELDS)
    filename = f"attendance_{date_filter or 'all'}.csv"
    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── GET /attendance/export/excel ───────────────────────────────────────────────

@router.get(
    "/export/excel",
    summary="Download attendance as Excel (.xlsx).",
)
async def export_excel(
    date_filter: Optional[date] = Query(default=None, alias="date"),
    class_section: Optional[str] = Query(default=None),
    session_id: Optional[str] = Query(default=None),
    student_id: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> StreamingResponse:
    report = await _query_attendance(
        db,
        date_filter=date_filter,
        class_section=class_section,
        session_id=session_id,
        student_id_code=student_id,
    )
    rows = [
        {
            "student_id": r.student_code or "",
            "name": r.student_name or "",
            "class_section": r.class_section or "",
            "session_id": r.session_id or "",
            "date": str(r.created_at.date()) if r.created_at else "",
            "status": r.status,
            "confidence": round(r.confidence, 4) if r.confidence is not None else "",
        }
        for r in report.items
    ]
    try:
        xlsx_bytes = build_excel_bytes(rows, _EXPORT_FIELDS)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc),
        )
    filename = f"attendance_{date_filter or 'all'}.xlsx"
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
