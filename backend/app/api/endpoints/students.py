"""
app/api/endpoints/students.py
──────────────────────────────
Student enrollment and listing endpoints.

POST /students/enroll          — enroll one student (multipart: fields + images)
POST /students/bulk-enroll     — enroll many students (JSON with base64 images)
GET  /students/                — paginated student list
PATCH /students/{student_id}   — update name / class_section / active flag
DELETE /students/{student_id}  — soft-delete (sets active=False)
"""

from __future__ import annotations

import uuid
from typing import List, Optional

import structlog
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.models import Student
from app.schemas.student import (
    BulkEnrollItemResult,
    BulkEnrollRequest,
    BulkEnrollResponse,
    StudentEnrollResponse,
    StudentListResponse,
    StudentOut,
    StudentUpdateRequest,
)
from app.services.face_service import FaceService
from app.utils.image_processing import b64_to_bgr, bytes_to_bgr, validate_image_file

router = APIRouter(prefix="/students", tags=["students"])
log = structlog.get_logger(__name__)

# ── Internal helpers ───────────────────────────────────────────────────────────

async def _student_exists(db: AsyncSession, student_id: str) -> bool:
    """Return True if a student with this school-issued student_id already exists."""
    result = await db.execute(
        select(Student).where(Student.student_id == student_id)
    )
    return result.scalar_one_or_none() is not None


async def _create_student_record(
    db: AsyncSession,
    student_id: str,
    name: str,
    class_section: Optional[str],
    label_id: Optional[int],
) -> Student:
    """Insert a new student row and flush (does not commit)."""
    student = Student(
        student_id=student_id,
        name=name,
        class_section=class_section,
        label_id=label_id,
        active=True,
    )
    db.add(student)
    await db.flush()   # get id without committing
    return student


# ── POST /students/enroll ─────────────────────────────────────────────────────

@router.post(
    "/enroll",
    response_model=StudentEnrollResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enroll a single student with 1–5 face images.",
)
async def enroll_student(
    student_id: str = Form(..., description="Unique school-issued student ID, e.g. 'S1001'."),
    name: str = Form(..., description="Full name."),
    class_section: Optional[str] = Form(default=None, description="Class + section, e.g. '10-A'."),
    images: List[UploadFile] = File(..., description="1–5 JPEG/PNG face images."),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> StudentEnrollResponse:
    """
    Enroll one student.

    Steps:
    1. Validate image count (1–5).
    2. Reject duplicate student_id.
    3. Decode + validate images.
    4. Detect faces and train LBPH incrementally.
    5. Insert student row and update label map with real UUID.
    6. Commit.

    If face training fails → DB is not written; old model retained.
    """
    student_id = student_id.strip()
    name = name.strip()

    if not 1 <= len(images) <= 5:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide between 1 and 5 face images.",
        )

    if await _student_exists(db, student_id):
        return StudentEnrollResponse(
            success=False,
            student_id=student_id,
            status="duplicate_id",
            detail=f"Student '{student_id}' is already enrolled.",
        )

    # Decode images
    bgr_images = []
    for upload in images:
        raw = await upload.read()
        err = validate_image_file(raw)
        if err:
            log.warning("enroll.invalid_image", filename=upload.filename, reason=err)
            continue
        bgr = bytes_to_bgr(raw)
        if bgr is not None:
            bgr_images.append(bgr)

    if not bgr_images:
        return StudentEnrollResponse(
            success=False,
            student_id=student_id,
            status="error",
            detail="All uploaded images were unreadable.",
        )

    # 1. Create student record first
    try:
        student = await _create_student_record(db, student_id, name, class_section, label_id=None)
        await db.flush()
    except Exception as exc:
        await db.rollback()
        log.error("enroll.db_failed", student_id=student_id, error=str(exc))
        return StudentEnrollResponse(
            success=False,
            student_id=student_id,
            status="error",
            detail="Database write failed.",
        )

    # 2. Train face model (compute and save embedding)
    try:
        _, n_faces = await FaceService.enroll_student(
            student_internal_id=str(student.id),
            student_id_text=student_id,
            student_name=name,
            bgr_images=bgr_images,
        )
        await db.commit()
    except ValueError:
        await db.rollback()
        return StudentEnrollResponse(
            success=False,
            student_id=student_id,
            status="no_face",
            detail="No face detected in any of the uploaded images.",
        )
    except Exception as exc:
        await db.rollback()
        log.error("enroll.training_failed", student_id=student_id, error=str(exc))
        return StudentEnrollResponse(
            success=False,
            student_id=student_id,
            status="error",
            student_id=student_id,
            status="error",
            detail="Database write failed after face training.",
        )

    log.info("enroll.success", student_id=student_id, n_faces=n_faces)
    return StudentEnrollResponse(
        success=True,
        student_id=student_id,
        label_id=None,
        faces_extracted=n_faces,
        status="ok",
        detail=f"Enrolled with {n_faces} face image(s).",
    )


# ── POST /students/bulk-enroll ────────────────────────────────────────────────

@router.post(
    "/bulk-enroll",
    response_model=BulkEnrollResponse,
    status_code=status.HTTP_200_OK,
    summary="Bulk-enroll multiple students (base64 images in JSON body).",
)
async def bulk_enroll_students(
    payload: BulkEnrollRequest,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> BulkEnrollResponse:
    """
    Enroll multiple students in one request.

    Processed SEQUENTIALLY (Pi Zero 2 W CPU constraint).
    Partial success: one failure does NOT abort subsequent students.
    Returns per-student status.
    """
    results: List[BulkEnrollItemResult] = []
    enrolled_count = 0
    failed_count = 0

    for item in payload.students:
        sid = item.student_id.strip()

        # Duplicate check
        if await _student_exists(db, sid):
            results.append(BulkEnrollItemResult(
                student_id=sid, status="duplicate_id", detail="Already enrolled.",
            ))
            failed_count += 1
            continue

        # Decode base64 images
        bgr_images = []
        for b64 in item.images_b64:
            bgr = b64_to_bgr(b64)
            if bgr is not None:
                bgr_images.append(bgr)

        if not bgr_images:
            results.append(BulkEnrollItemResult(
                student_id=sid, status="error", detail="All images unreadable.",
            ))
            failed_count += 1
            continue

        # 1. DB insert first
        try:
            student = await _create_student_record(
                db, sid, item.name, item.class_section, label_id=None
            )
            await db.flush()
        except Exception as exc:
            await db.rollback()
            log.error("bulk_enroll.db_failed", student_id=sid, error=str(exc))
            results.append(BulkEnrollItemResult(
                student_id=sid, status="error", detail="DB write failed.",
            ))
            failed_count += 1
            continue

        # 2. Train
        try:
            _, n_faces = await FaceService.enroll_student(
                student_internal_id=str(student.id),
                student_id_text=sid,
                student_name=item.name,
                bgr_images=bgr_images,
            )
            await db.commit()
        except ValueError:
            await db.rollback()
            results.append(BulkEnrollItemResult(
                student_id=sid, status="no_face", detail="No face detected.",
            ))
            failed_count += 1
            continue
        except Exception as exc:
            await db.rollback()
            log.error("bulk_enroll.train_failed", student_id=sid, error=str(exc))
            results.append(BulkEnrollItemResult(
                student_id=sid, status="error", detail=str(exc),
            ))
            failed_count += 1
            continue
        except Exception as exc:
            await db.rollback()
            log.error("bulk_enroll.db_failed", student_id=sid, error=str(exc))
            results.append(BulkEnrollItemResult(
                student_id=sid, status="error", detail="DB write failed.",
            ))
            failed_count += 1
            continue

        results.append(BulkEnrollItemResult(
            student_id=sid,
            status="ok",
            label_id=label_id,
            faces_extracted=n_faces,
            detail=f"Enrolled with {n_faces} face(s).",
        ))
        enrolled_count += 1

    return BulkEnrollResponse(
        results=results,
        total=len(payload.students),
        enrolled=enrolled_count,
        failed=failed_count,
    )


# ── GET /students/ ────────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=StudentListResponse,
    summary="List all enrolled students (paginated).",
)
async def list_students(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    class_section: Optional[str] = Query(default=None),
    active_only: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> StudentListResponse:
    """Return a paginated list of enrolled students."""
    q = select(Student)
    if active_only:
        q = q.where(Student.active == True)  # noqa: E712
    if class_section:
        q = q.where(Student.class_section == class_section)

    count_q = select(func.count()).select_from(q.subquery())
    total: int = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    rows = (await db.execute(q.offset(offset).limit(page_size))).scalars().all()

    return StudentListResponse(
        items=[StudentOut.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── PATCH /students/{student_id} ──────────────────────────────────────────────

@router.patch(
    "/{student_id}",
    response_model=StudentOut,
    summary="Partially update a student record.",
)
async def update_student(
    student_id: str,
    payload: StudentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> StudentOut:
    result = await db.execute(
        select(Student).where(Student.student_id == student_id)
    )
    student: Optional[Student] = result.scalar_one_or_none()
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student '{student_id}' not found.",
        )

    if payload.name is not None:
        student.name = payload.name.strip()
        # Also update in LBPH label map for recognition output
        if student.label_id is not None:
            FaceService.update_label_map_entry(student.label_id, name=student.name)
    if payload.class_section is not None:
        student.class_section = payload.class_section.strip()
    if payload.active is not None:
        student.active = payload.active

    await db.commit()
    log.info("student.updated", student_id=student_id)
    return StudentOut.model_validate(student)


# ── DELETE /students/{student_id} (soft delete) ────────────────────────────────

@router.delete(
    "/{student_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Soft-delete a student (sets active=False).",
)
async def delete_student(
    student_id: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> Response:
    result = await db.execute(
        select(Student).where(Student.student_id == student_id)
    )
    student: Optional[Student] = result.scalar_one_or_none()
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student '{student_id}' not found.",
        )
    student.active = False
    await db.commit()
    log.info("student.soft_deleted", student_id=student_id)
    return Response(status_code=204)
