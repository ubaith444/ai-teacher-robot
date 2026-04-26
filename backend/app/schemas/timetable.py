"""
app/schemas/timetable.py
────────────────────────
Pydantic v2 request / response models for the timetable module.
"""

from __future__ import annotations

import uuid
from datetime import time
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

_VALID_DAYS = frozenset(
    ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
)


# ── Timetable entry ────────────────────────────────────────────────────────────

class TimetableEntry(BaseModel):
    """Single timetable row in an upload payload."""

    class_section: str = Field(..., max_length=64)
    day_of_week: str = Field(..., description="Lowercase day name, e.g. 'monday'.")
    period_number: int = Field(..., ge=1, le=8)
    subject: Optional[str] = Field(default=None, max_length=128)
    teacher_id: Optional[str] = Field(default=None, max_length=64)
    start_time: time
    end_time: time

    @field_validator("day_of_week", mode="before")
    @classmethod
    def normalise_day(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in _VALID_DAYS:
            raise ValueError(f"day_of_week must be one of {sorted(_VALID_DAYS)}")
        return v

    @field_validator("class_section", mode="before")
    @classmethod
    def strip_section(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def end_after_start(self) -> "TimetableEntry":
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValueError("end_time must be strictly after start_time")
        return self


class TimetableUploadRequest(BaseModel):
    entries: List[TimetableEntry] = Field(..., min_length=1)


class TimetableUploadResponse(BaseModel):
    success: bool
    updated: int
    message: Optional[str] = None


# ── Output shapes ──────────────────────────────────────────────────────────────

class TimetableEntryOut(BaseModel):
    id: uuid.UUID
    class_section: str
    day_of_week: str
    period_number: int
    subject: Optional[str]
    teacher_id: Optional[str]
    start_time: Optional[time]
    end_time: Optional[time]

    model_config = {"from_attributes": True}


class CurrentPeriodResponse(BaseModel):
    """
    Response for GET /timetable/current.
    Returns status='none' when no period is active.
    """

    session_id: Optional[str] = None
    class_section: Optional[str] = None
    period_number: Optional[int] = None
    subject: Optional[str] = None
    teacher_id: Optional[str] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    # 'grace'  = within GRACE_MINUTES of start (status = present)
    # 'active' = past grace period (status = late)
    # 'none'   = no active period
    status: Literal["grace", "active", "none"] = "none"


class TimetableListResponse(BaseModel):
    items: List[TimetableEntryOut]
    total: int


# ── CSV-upload schema (alternative to JSON) ────────────────────────────────────

class TimetableCSVRow(BaseModel):
    """Parsed row from a CSV timetable upload."""

    class_section: str
    day_of_week: str
    period_number: int
    subject: Optional[str] = None
    teacher_id: Optional[str] = None
    start_time: time
    end_time: time

    @field_validator("day_of_week", mode="before")
    @classmethod
    def _day(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in _VALID_DAYS:
            raise ValueError(f"Invalid day: {v!r}")
        return v
