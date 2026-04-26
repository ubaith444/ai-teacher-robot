"""
app/services/attendance_service.py
────────────────────────────────────
Business-logic layer for attendance marking and session management.

This service is the single source of truth for:
  • Checking if a student is already marked in a session (DB + in-memory cache)
  • Writing attendance records with correct present/late status
  • Auto-creating Session rows from the timetable
  • Determining if a session should be auto-completed
  • Resolving the current active timetable period

It is deliberately kept stateless regarding the robot scan state
(that lives in the robot endpoint), but owns the DB + recognition logic.

Pi Zero 2 W notes
──────────────────
• Uses a simple dict-based in-memory cache per session to avoid repeated DB
  round-trips for duplicate-check during a scan loop.
• Cache is keyed by session_id and maps to a frozenset of student UUIDs already marked.
• Session cache is cleared when a session is completed or a new robot.start() is called.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, time
from typing import Dict, Optional, Set, Tuple

import structlog
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.models import Attendance, Session, Student, Timetable
from app.utils.helpers import (
    build_session_id,
    compute_attendance_status,
    current_date_local,
    current_time_local,
    day_of_week_str,
)

log = structlog.get_logger(__name__)


# ── In-memory session cache ────────────────────────────────────────────────────
# Maps session_id → set of student UUIDs already marked in that session.
# This avoids a DB query on every scan frame for duplicate detection.
_session_cache: Dict[str, Set[str]] = {}  # session_id → set of student UUID strings


def cache_get_marked(session_id: str) -> Set[str]:
    """Return the set of student UUIDs already marked in *session_id*."""
    return _session_cache.get(session_id, set())


def cache_add_marked(session_id: str, student_uuid: str) -> None:
    """Add *student_uuid* to the in-memory already-marked cache."""
    if session_id not in _session_cache:
        _session_cache[session_id] = set()
    _session_cache[session_id].add(student_uuid)


def cache_clear(session_id: str) -> None:
    """Clear the in-memory cache for *session_id* when the session ends."""
    _session_cache.pop(session_id, None)
    log.info("attendance_service.cache_cleared", session_id=session_id)


def cache_clear_all() -> None:
    """Wipe all session caches (e.g. on server restart)."""
    _session_cache.clear()


# ── Session helpers ────────────────────────────────────────────────────────────

async def get_session(db: AsyncSession, session_id: str) -> Optional[Session]:
    """Fetch a Session row by its session_id PK."""
    result = await db.execute(
        select(Session).where(Session.session_id == session_id)
    )
    return result.scalar_one_or_none()


async def ensure_session_exists(
    db: AsyncSession,
    session_id: str,
    today: date,
    entry: Timetable,
) -> Session:
    """
    Return the Session row for *session_id*, creating it if absent.
    Sessions are auto-created from the timetable on first access.
    """
    session = await get_session(db, session_id)
    if session is None:
        session = Session(
            session_id=session_id,
            date=today,
            start_time=entry.start_time,
            end_time=entry.end_time,
            class_section=entry.class_section,
            period_number=entry.period_number,
            subject=entry.subject,
            teacher_id=entry.teacher_id,
            status="active",
        )
        db.add(session)
        await db.flush()   # get the row into the transaction without committing
        log.info("attendance_service.session_auto_created", session_id=session_id)
    return session


async def complete_session(db: AsyncSession, session_id: str) -> None:
    """Mark a session as 'completed' in the DB and clear its in-memory cache."""
    result = await db.execute(
        select(Session).where(Session.session_id == session_id)
    )
    session: Optional[Session] = result.scalar_one_or_none()
    if session and session.status != "completed":
        session.status = "completed"
        await db.flush()
    cache_clear(session_id)
    log.info("attendance_service.session_completed", session_id=session_id)


async def resolve_current_period(
    db: AsyncSession,
    class_section: str,
) -> Optional[Tuple[Timetable, Session]]:
    """
    Find the timetable entry whose [start_time, end_time) window contains
    the current wall-clock time for *class_section*.

    Returns:
        (Timetable entry, Session row) — auto-creating Session if needed.
        None if no active period exists.
    """
    now_t = current_time_local(settings.TIMEZONE)
    today = current_date_local(settings.TIMEZONE)
    dow = day_of_week_str(today, settings.TIMEZONE)

    result = await db.execute(
        select(Timetable).where(
            and_(
                Timetable.class_section == class_section,
                Timetable.day_of_week == dow,
                Timetable.start_time <= now_t,
                Timetable.end_time > now_t,
            )
        )
    )
    entry: Optional[Timetable] = result.scalar_one_or_none()
    if entry is None:
        return None

    session_id = build_session_id(today, class_section, entry.period_number)
    session = await ensure_session_exists(db, session_id, today, entry)
    await db.commit()
    return entry, session


async def get_next_period(
    db: AsyncSession,
    class_section: str,
    after_session_id: str,
) -> Optional[Timetable]:
    """
    Return the next timetable entry after the period represented by *after_session_id*.
    Used by the robot to auto-advance to the next classroom.
    """
    from app.utils.helpers import parse_session_id

    parsed = parse_session_id(after_session_id)
    if not parsed:
        return None

    dow = day_of_week_str(parsed["date"], settings.TIMEZONE)
    current_period = parsed["period_number"]

    result = await db.execute(
        select(Timetable)
        .where(
            and_(
                Timetable.class_section == class_section,
                Timetable.day_of_week == dow,
                Timetable.period_number > current_period,
            )
        )
        .order_by(Timetable.period_number)
        .limit(1)
    )
    return result.scalar_one_or_none()


# ── Student helpers ────────────────────────────────────────────────────────────

async def get_active_student_by_code(
    db: AsyncSession,
    student_id_code: str,
) -> Optional[Student]:
    """Fetch an active student by their school-issued student_id text."""
    result = await db.execute(
        select(Student).where(
            Student.student_id == student_id_code,
            Student.active == True,  # noqa: E712
        )
    )
    return result.scalar_one_or_none()


# ── Duplicate check ────────────────────────────────────────────────────────────

async def is_already_marked(
    db: AsyncSession,
    session_id: str,
    student_uuid: uuid.UUID,
) -> bool:
    """
    Check if *student_uuid* is already marked for *session_id*.

    Fast path: in-memory cache (no DB hit).
    Slow path: DB query (on cache miss, then update cache).
    """
    # Fast path — in-memory cache
    if str(student_uuid) in cache_get_marked(session_id):
        return True

    # Slow path — DB query
    result = await db.execute(
        select(Attendance).where(
            and_(
                Attendance.session_id == session_id,
                Attendance.student_id == student_uuid,
            )
        )
    )
    found = result.scalar_one_or_none() is not None
    if found:
        cache_add_marked(session_id, str(student_uuid))
    return found


# ── Mark attendance ────────────────────────────────────────────────────────────

async def mark_attendance(
    db: AsyncSession,
    session: Session,
    student: Student,
    confidence: Optional[float] = None,
    bounding_box: Optional[dict] = None,
) -> Tuple[str, Attendance]:
    """
    Write one attendance record.

    Returns:
        (status, Attendance) where status is 'present' or 'late'.

    Raises:
        ValueError("already_marked") if the student was already recorded.
        ValueError("session_closed") if the session is completed or time expired.
    """
    # Session closed guard
    if session.status == "completed":
        raise ValueError("session_closed")
    now_t = current_time_local(settings.TIMEZONE)
    if session.end_time and now_t >= session.end_time:
        raise ValueError("session_closed")

    # Duplicate guard
    if await is_already_marked(db, session.session_id, student.id):
        raise ValueError("already_marked")

    # Determine status
    att_status = compute_attendance_status(session.start_time, settings.GRACE_MINUTES)

    # Write record
    record = Attendance(
        session_id=session.session_id,
        student_id=student.id,
        status=att_status,
        confidence=confidence,
        bounding_box=bounding_box,
    )
    db.add(record)
    try:
        await db.flush()
    except Exception as exc:
        # Handle race-condition duplicate (unique constraint violation)
        await db.rollback()
        log.warning(
            "attendance_service.mark_duplicate_race",
            session_id=session.session_id,
            student_id=str(student.id),
            error=str(exc),
        )
        raise ValueError("already_marked")

    # Update cache
    cache_add_marked(session.session_id, str(student.id))

    log.info(
        "attendance_service.marked",
        session_id=session.session_id,
        student_id=student.student_id,
        status=att_status,
        confidence=confidence,
    )
    return att_status, record


# ── Session time check ─────────────────────────────────────────────────────────

def session_is_open(session: Session) -> bool:
    """
    Return True if the session is still within its time window and not completed.
    """
    if session.status == "completed":
        return False
    now_t = current_time_local(settings.TIMEZONE)
    if session.end_time and now_t >= session.end_time:
        return False
    return True
