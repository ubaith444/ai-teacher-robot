"""
app/schemas/student.py
──────────────────────
Pydantic v2 request / response models for the students module.
"""

from __future__ import annotations

import uuid
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ── Enroll single student ──────────────────────────────────────────────────────

class StudentEnrollRequest(BaseModel):
    """
    JSON fields for POST /students/enroll.
    Images are sent separately as multipart file uploads.
    """

    student_id: str = Field(
        ..., min_length=1, max_length=64,
        description="Unique school-issued student ID, e.g. 'S1001'.",
    )
    name: str = Field(..., min_length=1, max_length=255)
    class_section: Optional[str] = Field(default=None, max_length=64)

    @field_validator("student_id", "name", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()


class StudentEnrollResponse(BaseModel):
    success: bool
    student_id: str
    label_id: Optional[int] = None
    faces_extracted: Optional[int] = None
    status: Literal["ok", "no_face", "duplicate_id", "error"]
    detail: Optional[str] = None


# ── Bulk enroll ────────────────────────────────────────────────────────────────

class BulkEnrollItem(BaseModel):
    """One entry in the bulk-enroll list."""

    student_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=255)
    class_section: Optional[str] = Field(default=None, max_length=64)
    images_b64: List[str] = Field(
        default_factory=list,
        description="Base64-encoded JPEG/PNG images (1–5 per student).",
        min_length=1,
        max_length=5,
    )

    @field_validator("student_id", "name", mode="before")
    @classmethod
    def strip_ws(cls, v: str) -> str:
        return v.strip()


class BulkEnrollRequest(BaseModel):
    students: List[BulkEnrollItem] = Field(..., min_length=1, max_length=100)


class BulkEnrollItemResult(BaseModel):
    student_id: str
    status: Literal["ok", "no_face", "duplicate_id", "error"]
    label_id: Optional[int] = None
    faces_extracted: Optional[int] = None
    detail: Optional[str] = None


class BulkEnrollResponse(BaseModel):
    results: List[BulkEnrollItemResult]
    total: int
    enrolled: int
    failed: int


# ── Student list ───────────────────────────────────────────────────────────────

class StudentOut(BaseModel):
    """Public-facing student representation."""

    id: uuid.UUID
    student_id: str
    name: str
    class_section: Optional[str]
    active: bool
    label_id: Optional[int]

    model_config = {"from_attributes": True}


class StudentListResponse(BaseModel):
    items: List[StudentOut]
    total: int
    page: int
    page_size: int


# ── Deactivate / update ────────────────────────────────────────────────────────

class StudentUpdateRequest(BaseModel):
    """PATCH /students/{student_id} — partial update."""

    name: Optional[str] = Field(default=None, max_length=255)
    class_section: Optional[str] = Field(default=None, max_length=64)
    active: Optional[bool] = None
