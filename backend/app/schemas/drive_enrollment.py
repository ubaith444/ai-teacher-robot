"""
app/schemas/drive_enrollment.py
─────────────────────────────────
Pydantic schemas for the Google Drive enrollment API.

Keeps API contracts strict and serializable.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, model_validator


# ── Request schemas ────────────────────────────────────────────────────────────


class DriveAnalyseRequest(BaseModel):
    """Request body for dataset analysis — analysis only, no enrollment."""
    folder_url: str = Field(
        description="Google Drive folder URL (must be shared as 'Anyone with the link').",
        example="https://drive.google.com/drive/folders/1BrRZuPCjDyFhywwGlI51YrcsdRre1pmg",
    )


class DriveBulkEnrollRequest(BaseModel):
    """Request body to bulk-enroll from a Drive folder."""
    folder_url: str = Field(
        description="Google Drive shared folder URL.",
        example="https://drive.google.com/drive/folders/1BrRZuPCjDyFhywwGlI51YrcsdRre1pmg",
    )
    class_section: Optional[str] = Field(
        default=None,
        description="Override class section for all enrolled students, e.g. '10-A'.",
        example="10-A",
    )
    dry_run: bool = Field(
        default=False,
        description=(
            "If true, analyse the folder and return what WOULD be enrolled "
            "without actually writing to DB or training the model."
        ),
    )


# ── Per-image analysis ─────────────────────────────────────────────────────────


class ImageAnalysisOut(BaseModel):
    file_name: str
    loadable: bool
    width: int = 0
    height: int = 0
    size_bytes: int = 0
    blur_score: float = 0.0
    is_blurry: bool = False
    face_count: int = 0
    has_face: bool = False
    is_duplicate: bool = False
    error: Optional[str] = None

    model_config = {"from_attributes": True}


# ── Per-student analysis ───────────────────────────────────────────────────────


class StudentAnalysisOut(BaseModel):
    student_name: str
    folder_id: str
    total_files: int = 0
    valid_images: int = 0
    invalid_images: int = 0
    images_with_faces: int = 0
    blurry_images: int = 0
    duplicate_images: int = 0
    low_resolution_images: int = 0
    is_enrollable: bool = False
    warnings: List[str] = []
    image_analyses: List[ImageAnalysisOut] = []

    model_config = {"from_attributes": True}


# ── Full dataset analysis report ───────────────────────────────────────────────


class DatasetReportOut(BaseModel):
    folder_url: str
    folder_id: str
    total_files: int = 0
    total_image_files: int = 0
    total_invalid_files: int = 0
    total_subfolders: int = 0
    format_distribution: Dict[str, int] = {}
    total_size_mb: float = 0.0
    student_count: int = 0
    enrollable_student_count: int = 0
    ambiguous_entries: List[str] = []
    student_analyses: List[StudentAnalysisOut] = []
    overall_face_detection_rate: float = 0.0
    enrollment_readiness_score: float = 0.0
    warnings: List[str] = []
    recommendations: List[str] = []
    analyzed_at: float = 0.0

    model_config = {"from_attributes": True}

    @classmethod
    def from_dataclass(cls, report: Any) -> "DatasetReportOut":
        """Convert the internal DatasetReport dataclass to this schema."""
        return cls(
            folder_url=report.folder_url,
            folder_id=report.folder_id,
            total_files=report.total_files,
            total_image_files=report.total_image_files,
            total_invalid_files=report.total_invalid_files,
            total_subfolders=report.total_subfolders,
            format_distribution=report.format_distribution,
            total_size_mb=round(report.total_size_bytes / (1024 * 1024), 2),
            student_count=report.student_count,
            enrollable_student_count=report.enrollable_student_count,
            ambiguous_entries=report.ambiguous_entries,
            student_analyses=[
                StudentAnalysisOut(
                    student_name=s.student_name,
                    folder_id=s.folder_id,
                    total_files=s.total_files,
                    valid_images=s.valid_images,
                    invalid_images=s.invalid_images,
                    images_with_faces=s.images_with_faces,
                    blurry_images=s.blurry_images,
                    duplicate_images=s.duplicate_images,
                    low_resolution_images=s.low_resolution_images,
                    is_enrollable=s.is_enrollable,
                    warnings=s.warnings,
                    image_analyses=[
                        ImageAnalysisOut(
                            file_name=a.file_name,
                            loadable=a.loadable,
                            width=a.width,
                            height=a.height,
                            size_bytes=a.size_bytes,
                            blur_score=round(a.blur_score, 2),
                            is_blurry=a.is_blurry,
                            face_count=a.face_count,
                            has_face=a.has_face,
                            is_duplicate=a.is_duplicate,
                            error=a.error,
                        )
                        for a in s.image_analyses
                    ],
                )
                for s in report.student_analyses
            ],
            overall_face_detection_rate=report.overall_face_detection_rate,
            enrollment_readiness_score=report.enrollment_readiness_score,
            warnings=report.warnings,
            recommendations=report.recommendations,
            analyzed_at=report.analyzed_at,
        )


# ── Per-student enrollment result ──────────────────────────────────────────────


class DriveEnrollItemOut(BaseModel):
    student_name: str
    student_id: str
    class_section: Optional[str] = None
    success: bool
    status: str   # ok | duplicate | no_face | download_error | db_error | train_error
    detail: str = ""
    label_id: Optional[int] = None
    valid_images: int = 0
    invalid_images: int = 0
    faces_extracted: int = 0
    enrolled_at: float = 0.0


# ── Bulk enrollment report ─────────────────────────────────────────────────────


class DriveEnrollReportOut(BaseModel):
    folder_url: str
    total_students: int = 0
    enrolled: int = 0
    skipped_duplicates: int = 0
    failed: int = 0
    results: List[DriveEnrollItemOut] = []
    enrolled_at: float = 0.0

    @classmethod
    def from_dataclass(cls, report: Any) -> "DriveEnrollReportOut":
        return cls(
            folder_url=report.folder_url,
            total_students=report.total_students,
            enrolled=report.enrolled,
            skipped_duplicates=report.skipped_duplicates,
            failed=report.failed,
            results=[
                DriveEnrollItemOut(
                    student_name=r.student_name,
                    student_id=r.student_id,
                    class_section=r.class_section,
                    success=r.success,
                    status=r.status,
                    detail=r.detail,
                    label_id=r.label_id,
                    valid_images=r.valid_images,
                    invalid_images=r.invalid_images,
                    faces_extracted=r.faces_extracted,
                    enrolled_at=r.enrolled_at,
                )
                for r in report.results
            ],
            enrolled_at=report.enrolled_at,
        )
