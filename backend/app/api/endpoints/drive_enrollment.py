"""
app/api/endpoints/drive_enrollment.py
──────────────────────────────────────
FastAPI endpoints for Google Drive-based student enrollment.

Endpoints:
  GET  /students/analyze-drive-folder          — Dataset analysis (no writes)
  POST /students/enroll/from-drive             — Bulk enroll from Drive folder
  POST /students/bulk-enroll/from-drive        — Alias for the above

These endpoints integrate with the existing:
  • FaceService  — LBPH training (face_service.py)  [unchanged]
  • Student DB   — students table (models.py)        [read/write]
  • label_map    — JSON label ↔ student map          [updated atomically]

No attendance session or robot logic is touched here.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.schemas.drive_enrollment import (
    DatasetReportOut,
    DriveAnalyseRequest,
    DriveBulkEnrollRequest,
    DriveEnrollReportOut,
)
from app.services.drive_enrollment_service import bulk_enroll_from_drive
from app.services.drive_service import analyse_drive_dataset, extract_folder_id

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/students", tags=["Drive Enrollment"])


# ── GET /students/analyze-drive-folder ────────────────────────────────────────


@router.get(
    "/analyze-drive-folder",
    response_model=DatasetReportOut,
    summary="Analyse a Google Drive folder without enrolling anyone.",
    description=(
        "Inspects the Drive folder structure, downloads sample images, "
        "and returns a full dataset quality report including:\n"
        "- File format distribution\n"
        "- Per-student image counts\n"
        "- Blur/duplicate/resolution issues\n"
        "- Face detection success rate\n"
        "- Enrollment readiness score (0–100)\n\n"
        "No students are created. No model is modified."
    ),
)
async def analyse_drive_folder(
    folder_url: str = Query(
        ...,
        description="Google Drive shared folder URL.",
        example="https://drive.google.com/drive/folders/1BrRZuPCjDyFhywwGlI51YrcsdRre1pmg",
    ),
    _user: str = Depends(get_current_user),
) -> DatasetReportOut:
    import os
    is_local = os.path.isdir(folder_url)
    if not extract_folder_id(folder_url) and not is_local:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid Google Drive folder URL or Local Directory path.",
        )

    try:
        report = await analyse_drive_dataset(folder_url)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )
    except Exception as exc:
        log.exception("analyse_drive.error", url=folder_url, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Drive analysis failed: {exc}",
        )

    return DatasetReportOut.from_dataclass(report)


# ── POST /students/enroll/from-drive ──────────────────────────────────────────


@router.post(
    "/enroll/from-drive",
    response_model=DriveEnrollReportOut,
    status_code=status.HTTP_200_OK,
    summary="Bulk-enroll students from a Google Drive folder.",
    description=(
        "Discovers student subfolders in the given Drive folder, downloads images, "
        "validates faces, trains the LBPH recognizer, and inserts students into the database.\n\n"
        "**Folder structure expected:**\n"
        "```\n"
        "Shared Folder/\n"
        "  ├── John Doe/       ← student name\n"
        "  │     ├── 01.jpg\n"
        "  │     └── 02.jpg\n"
        "  └── Jane Smith/\n"
        "        ├── 01.png\n"
        "        └── 02.jpeg\n"
        "```\n\n"
        "**Partial success:** one student failing does NOT abort others.\n"
        "**Dry-run:** set `dry_run=true` to preview results without writing."
    ),
)
async def enroll_from_drive(
    body: DriveBulkEnrollRequest,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> DriveEnrollReportOut:
    import os
    is_local = os.path.isdir(body.folder_url)
    if not extract_folder_id(body.folder_url) and not is_local:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid Google Drive folder URL or Local Directory path.",
        )

    if body.dry_run:
        # Analysis-only: return the dataset report as an enrollment preview
        try:
            analysis = await analyse_drive_dataset(body.folder_url)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

        # Build a "preview" enrollment report from analysis data (no writes)
        from app.services.drive_enrollment_service import DriveEnrollReport, DriveEnrollItemResult
        preview = DriveEnrollReport(folder_url=body.folder_url)
        preview.total_students = analysis.student_count
        for s in analysis.student_analyses:
            preview.results.append(DriveEnrollItemResult(
                student_name=s.student_name,
                student_id="<not-assigned-yet>",
                class_section=body.class_section,
                success=False,
                status="dry_run",
                detail="Dry-run: would enroll" if s.is_enrollable else "Dry-run: would fail (no face detected)",
                valid_images=s.valid_images,
                invalid_images=s.invalid_images,
            ))
            if s.is_enrollable:
                preview.enrolled += 1
            else:
                preview.failed += 1
        return DriveEnrollReportOut.from_dataclass(preview)

    try:
        report = await bulk_enroll_from_drive(
            folder_url=body.folder_url,
            db=db,
            class_section_override=body.class_section,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except Exception as exc:
        log.exception("enroll_from_drive.error", url=body.folder_url, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bulk enrollment failed: {exc}",
        )

    return DriveEnrollReportOut.from_dataclass(report)


# ── POST /students/bulk-enroll/from-drive — alias ─────────────────────────────


@router.post(
    "/bulk-enroll/from-drive",
    response_model=DriveEnrollReportOut,
    status_code=status.HTTP_200_OK,
    summary="Alias for POST /students/enroll/from-drive.",
    include_in_schema=True,
)
async def bulk_enroll_from_drive_alias(
    body: DriveBulkEnrollRequest,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
) -> DriveEnrollReportOut:
    return await enroll_from_drive(body, db, _user)
