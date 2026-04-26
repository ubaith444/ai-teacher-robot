"""
app/api/endpoints/timetable.py
───────────────────────────────
Timetable management endpoints.

POST /timetable/upload     — replace timetable entries for class+day combos
POST /timetable/upload-csv — upload a CSV file as the timetable
GET  /timetable/current    — detect which period is active right now
GET  /timetable/list       — list all timetable entries (filterable)
DELETE /timetable/clear    — remove all entries for a class+day
"""

from __future__ import annotations

import csv
import io
from datetime import time
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
)
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Session as DbSession
from app.models.models import Timetable
from app.schemas.timetable import (
    CurrentPeriodResponse,
    TimetableCSVRow,
    TimetableEntry,
    TimetableEntryOut,
    TimetableListResponse,
    TimetableUploadRequest,
    TimetableUploadResponse,
)
from app.services.attendance_service import ensure_session_exists
from app.utils.helpers import (
    build_session_id,
    current_date_local,
    current_time_local,
    day_of_week_str,
)

router = APIRouter(prefix="/timetable", tags=["timetable"])
log = structlog.get_logger(__name__)


# ── POST /timetable/upload ────────────────────────────────────────────────────

@router.post(
    "/upload",
    response_model=TimetableUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload / replace timetable entries for class+day combinations.",
)
async def upload_timetable(
    payload: TimetableUploadRequest,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> TimetableUploadResponse:
    """
    Replace all timetable entries for each (class_section, day_of_week) pair
    present in the payload.  Other pairs are left untouched.

    Upsert strategy: delete-then-insert per group (atomic within one transaction).
    """
    pairs = {(e.class_section, e.day_of_week) for e in payload.entries}

    for cls, day in pairs:
        await db.execute(
            delete(Timetable).where(
                and_(
                    Timetable.class_section == cls,
                    Timetable.day_of_week == day,
                )
            )
        )

    new_rows = [
        Timetable(
            class_section=e.class_section,
            day_of_week=e.day_of_week,
            period_number=e.period_number,
            subject=e.subject,
            teacher_id=e.teacher_id,
            start_time=e.start_time,
            end_time=e.end_time,
        )
        for e in payload.entries
    ]
    db.add_all(new_rows)
    await db.commit()

    log.info("timetable.uploaded", n=len(new_rows))
    return TimetableUploadResponse(
        success=True,
        updated=len(new_rows),
        message=f"Replaced entries for {len(pairs)} class+day pair(s).",
    )


# ── POST /timetable/upload-csv ────────────────────────────────────────────────

@router.post(
    "/upload-csv",
    response_model=TimetableUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload timetable as a CSV file.",
)
async def upload_timetable_csv(
    file: UploadFile = File(..., description="CSV with columns: class_section, day_of_week, period_number, subject, teacher_id, start_time, end_time"),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> TimetableUploadResponse:
    """
    CSV format (header row required):
        class_section, day_of_week, period_number, subject, teacher_id, start_time, end_time

    Times must be in HH:MM or HH:MM:SS format.
    Rows that fail parsing are skipped; a count of skipped rows is returned.
    """
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")  # handles BOM from Excel
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    entries: List[TimetableEntry] = []
    skip_count = 0

    for row_num, row in enumerate(reader, start=2):  # start=2 → skip header
        try:
            # Normalise keys (strip whitespace)
            row = {k.strip().lower(): v.strip() for k, v in row.items()}
            start_t = _parse_time(row.get("start_time", ""))
            end_t = _parse_time(row.get("end_time", ""))
            entries.append(
                TimetableEntry(
                    class_section=row["class_section"],
                    day_of_week=row["day_of_week"],
                    period_number=int(row["period_number"]),
                    subject=row.get("subject") or None,
                    teacher_id=row.get("teacher_id") or None,
                    start_time=start_t,
                    end_time=end_t,
                )
            )
        except Exception as exc:
            log.warning("timetable.csv_row_skip", row=row_num, error=str(exc))
            skip_count += 1

    if not entries:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No valid rows found in CSV. {skip_count} row(s) skipped.",
        )

    # Reuse the JSON upload logic
    payload = TimetableUploadRequest(entries=entries)
    result = await upload_timetable(payload, db, _user)
    result.message = (
        f"Loaded {len(entries)} row(s) from CSV"
        + (f"; {skip_count} row(s) skipped." if skip_count else ".")
    )
    return result


def _parse_time(t_str: str) -> time:
    """Parse HH:MM or HH:MM:SS string to datetime.time."""
    parts = t_str.strip().split(":")
    if len(parts) == 2:
        return time(int(parts[0]), int(parts[1]))
    elif len(parts) == 3:
        return time(int(parts[0]), int(parts[1]), int(parts[2]))
    raise ValueError(f"Cannot parse time: {t_str!r}")


# ── GET /timetable/current ────────────────────────────────────────────────────

@router.get(
    "/current",
    response_model=CurrentPeriodResponse,
    summary="Detect the currently active period based on server time.",
)
async def get_current_period(
    class_section: Optional[str] = Query(
        default=None, description="Filter to a specific class section."
    ),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> CurrentPeriodResponse:
    """
    Return the timetable entry whose [start_time, end_time) window contains
    the current wall-clock time.

    Also auto-creates the Session row if it doesn't exist yet, so the robot
    can immediately call /robot/start without a prior call.
    """
    from datetime import datetime as dt, timedelta

    now_t = current_time_local(settings.TIMEZONE)
    today = current_date_local(settings.TIMEZONE)
    dow = day_of_week_str(today, settings.TIMEZONE)

    q = select(Timetable).where(
        and_(
            Timetable.day_of_week == dow,
            Timetable.start_time <= now_t,
            Timetable.end_time > now_t,
        )
    )
    if class_section:
        q = q.where(Timetable.class_section == class_section)

    result = await db.execute(q)
    entry: Optional[Timetable] = result.scalar_one_or_none()

    if entry is None:
        return CurrentPeriodResponse(status="none")

    session_id = build_session_id(today, entry.class_section, entry.period_number)
    await ensure_session_exists(db, session_id, today, entry)
    await db.commit()

    # Determine grace vs active
    dummy = dt(2000, 1, 1)
    start_dt = dt.combine(dummy, entry.start_time)
    grace_end = start_dt + timedelta(minutes=settings.GRACE_MINUTES)
    now_dt = dt.combine(dummy, now_t)
    period_status = "grace" if now_dt <= grace_end else "active"

    return CurrentPeriodResponse(
        session_id=session_id,
        class_section=entry.class_section,
        period_number=entry.period_number,
        subject=entry.subject,
        teacher_id=entry.teacher_id,
        start_time=entry.start_time,
        end_time=entry.end_time,
        status=period_status,
    )


# ── GET /timetable/list ────────────────────────────────────────────────────────

@router.get(
    "/list",
    response_model=TimetableListResponse,
    summary="List all timetable entries.",
)
async def list_timetable(
    class_section: Optional[str] = Query(default=None),
    day_of_week: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> TimetableListResponse:
    q = select(Timetable)
    if class_section:
        q = q.where(Timetable.class_section == class_section)
    if day_of_week:
        q = q.where(Timetable.day_of_week == day_of_week.strip().lower())
    q = q.order_by(Timetable.class_section, Timetable.day_of_week, Timetable.period_number)

    rows = (await db.execute(q)).scalars().all()
    return TimetableListResponse(
        items=[TimetableEntryOut.model_validate(r) for r in rows],
        total=len(rows),
    )


# ── DELETE /timetable/clear ────────────────────────────────────────────────────

@router.delete(
    "/clear",
    status_code=status.HTTP_200_OK,
    summary="Clear timetable entries for a specific class+day combination.",
)
async def clear_timetable(
    class_section: str = Query(...),
    day_of_week: str = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        delete(Timetable).where(
            and_(
                Timetable.class_section == class_section,
                Timetable.day_of_week == day_of_week.strip().lower(),
            )
        )
    )
    await db.commit()
    n = result.rowcount
    log.info("timetable.cleared", class_section=class_section, day=day_of_week, n=n)
    return {"deleted": n, "class_section": class_section, "day_of_week": day_of_week}
