"""
app/schemas/attendance.py
─────────────────────────
Pydantic v2 request / response models for the attendance module.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ── Mark attendance request ────────────────────────────────────────────────────

class AttendanceMarkRequest(BaseModel):
    """
    POST /attendance/mark — mark one student for a session.

    Resolution precedence:
        1. If face_image is sent as multipart → run recognition pipeline.
        2. Else if student_id provided → direct DB lookup (no recognition).
    """

    session_id: str = Field(..., description="Session identifier for this period.")
    student_id: Optional[str] = Field(
        default=None,
        description="School-issued student_id (when not using face recognition).",
    )
    confidence: Optional[float] = Field(
        default=None,
        description="LBPH confidence score from a prior recognition step.",
    )
    bounding_box: Optional[dict] = Field(
        default=None,
        description="Face bounding box {x, y, w, h} in image pixels.",
    )


class AttendanceMarkResponse(BaseModel):
    status: Literal["present", "late", "already_marked", "unknown", "session_closed"]
    session_id: str
    student_id: Optional[str] = None
    student_name: Optional[str] = None
    confidence: Optional[float] = None
    bounding_box: Optional[dict] = None
    marked_at: Optional[datetime] = None


# ── Attendance record output ───────────────────────────────────────────────────

class AttendanceRecordOut(BaseModel):
    id: uuid.UUID
    session_id: Optional[str]
    student_id: Optional[uuid.UUID]         # internal UUID FK
    student_code: Optional[str] = None      # school-issued student_id text
    student_name: Optional[str] = None
    class_section: Optional[str] = None
    status: str                             # 'present' | 'late'
    confidence: Optional[float]
    bounding_box: Optional[dict]
    created_at: datetime

    model_config = {"from_attributes": True}


class AttendanceListResponse(BaseModel):
    items: List[AttendanceRecordOut]
    total: int


# ── Session summary ────────────────────────────────────────────────────────────

class SessionSummaryOut(BaseModel):
    """Used in GET /attendance/session-summary."""

    session_id: str
    class_section: Optional[str]
    date: Optional[date]
    period_number: Optional[int]
    subject: Optional[str]
    status: str
    total_marked: int
    present_count: int
    late_count: int

    model_config = {"from_attributes": True}


# ── Report query params ────────────────────────────────────────────────────────

class AttendanceReportQuery(BaseModel):
    """Query parameters for GET /attendance/report."""

    date: Optional[date] = None
    class_section: Optional[str] = None
    session_id: Optional[str] = None
    student_id: Optional[str] = None       # school-issued student_id (text)
