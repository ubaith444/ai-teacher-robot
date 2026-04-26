"""
app/services/drive_enrollment_service.py
─────────────────────────────────────────
Bulk enrollment orchestration: ties together Drive ingestion, image validation,
LBPH face training, and database writes.

This module is the ONLY entry point for Drive-based enrollment.
It calls the existing FaceService.enroll_student() and the same DB helpers
used in students.py — no attendance logic is duplicated here.

Enrollment flow (per student):
  1. Discover images in Drive subfolder.
  2. Download + decode images.
  3. Call FaceService.enroll_student() — extracts faces, updates LBPH.
  4. Insert or update a Student row in PostgreSQL.
  5. Fix up label_map with the real DB UUID.
  6. If any step fails → rollback for that student only; continue with others.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Student
from app.services.drive_service import (
    DatasetReport,
    StudentImageGroup,
    analyse_drive_dataset,
    discover_students_in_folder,
    extract_folder_id,
    fetch_student_images,
)
from app.services.face_service import FaceService, _model_lock, _save_label_map, _state

log = structlog.get_logger(__name__)

# ── Result Models ──────────────────────────────────────────────────────────────

MAX_DRIVE_IMAGES_PER_STUDENT = 10   # Cap per student to stay Pi-friendly


@dataclass
class DriveEnrollItemResult:
    student_name: str
    student_id: str              # school-issued ID (derived from folder name or manifest)
    class_section: Optional[str] = None
    success: bool = False
    status: str = "pending"      # ok | duplicate | no_face | download_error | db_error | train_error
    detail: str = ""
    label_id: Optional[int] = None
    valid_images: int = 0
    invalid_images: int = 0
    faces_extracted: int = 0
    enrolled_at: float = field(default_factory=time.time)


@dataclass
class DriveEnrollReport:
    folder_url: str
    total_students: int = 0
    enrolled: int = 0
    skipped_duplicates: int = 0
    failed: int = 0
    results: List[DriveEnrollItemResult] = field(default_factory=list)
    enrolled_at: float = field(default_factory=time.time)


# ── Student ID & Name Mapping ──────────────────────────────────────────────────

def _derive_student_id(student_name: str, index: int) -> str:
    """
    Derive a school-issued student_id from the folder name.

    Format: DRIVE-<index+1:04d>  e.g. DRIVE-0001, DRIVE-0002
    Allows re-running without conflicts — caller checks for duplicates.
    """
    safe = student_name.upper().replace(" ", "")[:8]
    return f"DRIVE-{index + 1:04d}-{safe}"


def _derive_class_section(folder_name: str) -> Optional[str]:
    """
    Try to extract class section from folder name.
    Examples: '10-A_John_Doe' → '10-A', '10A_Jane' → '10A'
    Returns None if no match.
    """
    import re
    m = re.match(r"^(\d{1,2}[-_]?[A-Za-z])\b", folder_name)
    if m:
        return m.group(1).replace("_", "-")
    return None


# ── Enrollment Logic ────────────────────────────────────────────────────────────

async def _enroll_one_student(
    db: AsyncSession,
    group: StudentImageGroup,
    student_id_text: str,
    class_section: Optional[str],
) -> DriveEnrollItemResult:
    """
    Enroll a single student from a Drive image group.
    Returns a result record regardless of success or failure.
    """
    result = DriveEnrollItemResult(
        student_name=group.student_name,
        student_id=student_id_text,
        class_section=class_section,
    )

    # ── Duplicate check ────────────────────────────────────────────────────
    existing = await db.execute(
        select(Student).where(Student.student_id == student_id_text)
    )
    if existing.scalar_one_or_none() is not None:
        result.status = "duplicate"
        result.detail = f"Student '{student_id_text}' is already enrolled."
        log.info("drive_enroll.duplicate", student_id=student_id_text)
        return result

    # ── Download images ────────────────────────────────────────────────────
    bgr_images, valid_count, invalid_count = await fetch_student_images(
        group, max_images=MAX_DRIVE_IMAGES_PER_STUDENT
    )
    result.valid_images = valid_count
    result.invalid_images = invalid_count

    if not bgr_images:
        result.status = "download_error"
        result.detail = "Could not download any valid images from Drive."
        log.warning("drive_enroll.no_images", student_name=group.student_name)
        return result

    # ── Face training ──────────────────────────────────────────────────────
    temp_id = str(uuid.uuid4())
    try:
        label_id, n_faces = await FaceService.enroll_student(
            student_internal_id=temp_id,
            student_id_text=student_id_text,
            student_name=group.student_name,
            bgr_images=bgr_images,
        )
    except ValueError:
        result.status = "no_face"
        result.detail = "No face detected in any downloaded image."
        log.warning("drive_enroll.no_face", student_name=group.student_name)
        return result
    except Exception as exc:
        result.status = "train_error"
        result.detail = f"LBPH training failed: {exc}"
        log.error("drive_enroll.train_error", student_name=group.student_name, error=str(exc))
        return result

    result.label_id = label_id
    result.faces_extracted = n_faces

    # ── Database insert ────────────────────────────────────────────────────
    try:
        student = Student(
            student_id=student_id_text,
            name=group.student_name,
            class_section=class_section,
            label_id=label_id,
            active=True,
        )
        db.add(student)
        await db.flush()  # get the UUID without committing

        # Fix up label map
        with _model_lock:
            if label_id in _state.label_map:
                _state.label_map[label_id]["student_internal_id"] = str(student.id)
            _save_label_map(_state.label_map)

        await db.commit()

    except Exception as exc:
        await db.rollback()
        result.status = "db_error"
        result.detail = f"Database write failed: {exc}"
        log.error("drive_enroll.db_error", student_name=group.student_name, error=str(exc))
        return result

    result.success = True
    result.status = "ok"
    result.detail = f"Enrolled with {n_faces} face image(s)."
    log.info(
        "drive_enroll.success",
        student_name=group.student_name,
        student_id=student_id_text,
        label_id=label_id,
        n_faces=n_faces,
    )
    return result


async def bulk_enroll_from_drive(
    folder_url: str,
    db: AsyncSession,
    class_section_override: Optional[str] = None,
) -> DriveEnrollReport:
    """
    Main entry point: bulk-enroll all students discovered in a Drive folder.

    Each student is processed sequentially.
    A per-student failure does NOT abort subsequent students.

    Args:
        folder_url:            Google Drive folder URL (shared link).
        db:                    Async SQLAlchemy session (injected by FastAPI).
        class_section_override: If provided, assign all students this class.

    Returns:
        DriveEnrollReport — full per-student result log.
    """
    report = DriveEnrollReport(folder_url=folder_url)

    folder_id = extract_folder_id(folder_url)
    import os
    if not folder_id and not os.path.exists(folder_url):
        report.failed = 1
        report.total_students = 0
        log.error("drive_enroll.invalid_url", url=folder_url)
        return report

    if not folder_id:
        folder_id = "local_dir"

    # Discover student groups
    try:
        # Pass the full URL to the new gdown discovery service
        groups = await discover_students_in_folder(folder_url)
    except Exception as exc:
        log.error("drive_enroll.discover_failed", error=str(exc))
        raise

    report.total_students = len(groups)

    if not groups:
        log.warning("drive_enroll.no_students_found", folder_id=folder_id)
        return report

    # Enroll sequentially
    try:
        for idx, group in enumerate(groups):
            student_id_text = _derive_student_id(group.student_name, idx)
            class_section = class_section_override or _derive_class_section(
                group.student_name
            )

            result = await _enroll_one_student(
                db=db,
                group=group,
                student_id_text=student_id_text,
                class_section=class_section,
            )
            report.results.append(result)

            if result.success:
                report.enrolled += 1
            elif result.status == "duplicate":
                report.skipped_duplicates += 1
            else:
                report.failed += 1
    finally:
        # ALWAYS clean up the temporary files after processing
        from app.services.drive_service import cleanup_drive_temp
        cleanup_drive_temp(groups)

    log.info(
        "drive_enroll.batch_complete",
        total=report.total_students,
        enrolled=report.enrolled,
        duplicates=report.skipped_duplicates,
        failed=report.failed,
    )
    return report
