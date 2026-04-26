"""
app/models/models.py
────────────────────
SQLAlchemy 2.x ORM models for the Zoro Robot Automated Attendance System.

Tables
------
students     — enrolled students with LBPH label IDs
sessions     — individual class attendance sessions (auto-created from timetable)
attendance   — one record per student × session mark
timetable    — weekly recurring schedule

Design notes
------------
• All primary keys are UUID (server-generated).
• session_id uses a human-readable composite string for ease of debugging.
• JSONB for bounding_box allows arbitrary {x, y, w, h} storage without
  a separate table.
• Soft-delete on students (active=False) so attendance history is preserved.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ── students ───────────────────────────────────────────────────────────────────
class Student(Base):
    """
    An enrolled student.

    label_id is the integer label used by the LBPH face recognizer.
    It is assigned during face enrollment and must remain stable after training.
    NULL label_id means the student has no face enrolled yet.
    """

    __tablename__ = "students"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="School-issued student identifier, e.g. 'S1001'.",
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Full display name.",
    )
    label_id: Mapped[int | None] = mapped_column(
        Integer,
        unique=True,
        nullable=True,
        comment="LBPH integer label. NULL until at least one face image is enrolled.",
    )
    face_encoding: Mapped[list[float] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="128-d face embedding vector for face_recognition library.",
    )
    class_section: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True,
        comment="Class + section string, e.g. '10-A'.",
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Soft-delete flag. Inactive students are excluded from recognition.",
    )

    # ── Relationships ──────────────────────────────────────────────────────
    attendance_records: Mapped[list["Attendance"]] = relationship(
        "Attendance", back_populates="student", lazy="select"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Student {self.student_id!r} label={self.label_id}>"


# ── sessions ───────────────────────────────────────────────────────────────────
class Session(Base):
    """
    One class-period attendance session.

    session_id is a human-readable composite key built by helpers.build_session_id():
        '<YYYY-MM-DD>_<class_section>_P<period_number>'
        e.g. '2024-06-01_10-A_P3'

    Status lifecycle: 'active' → 'completed'
    """

    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(
        String(128),
        primary_key=True,
        comment="Composite human-readable session identifier.",
    )
    date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    class_section: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    period_number: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="1-indexed period number within the day (derived from timetable).",
    )
    subject: Mapped[str | None] = mapped_column(String(128), nullable=True)
    teacher_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="active",
        comment="'active' while the period runs; 'completed' afterwards.",
    )

    # ── Relationships ──────────────────────────────────────────────────────
    attendance_records: Mapped[list["Attendance"]] = relationship(
        "Attendance", back_populates="session", lazy="select"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Session {self.session_id!r} status={self.status}>"


# ── attendance ─────────────────────────────────────────────────────────────────
class Attendance(Base):
    """
    One attendance mark: one student × one session.

    The (session_id, student_id) unique constraint is enforced both in
    application logic and via a DB-level unique index defined below.
    """

    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "student_id", name="uq_attendance_session_student"
        ),
        Index("ix_attendance_session_id", "session_id"),
        Index("ix_attendance_student_id", "student_id"),
        Index("ix_attendance_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[str | None] = mapped_column(
        String(128),
        ForeignKey("sessions.session_id", ondelete="SET NULL"),
        nullable=True,
    )
    student_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("students.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="'present' or 'late'.",
    )
    confidence: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        comment="LBPH confidence score (lower = better match).",
    )
    bounding_box: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Face bounding box as {x, y, w, h} in image pixels.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # ── Relationships ──────────────────────────────────────────────────────
    student: Mapped["Student"] = relationship(
        "Student", back_populates="attendance_records", lazy="select"
    )
    session: Mapped["Session"] = relationship(
        "Session", back_populates="attendance_records", lazy="select"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Attendance session={self.session_id!r} "
            f"student={self.student_id} status={self.status!r}>"
        )


# ── timetable ──────────────────────────────────────────────────────────────────
class Timetable(Base):
    """
    Weekly recurring timetable entry.

    day_of_week is stored as a lowercase English string:
        'monday', 'tuesday', 'wednesday', 'thursday',
        'friday', 'saturday', 'sunday'
    """

    __tablename__ = "timetable"
    __table_args__ = (
        Index("ix_timetable_class_day", "class_section", "day_of_week"),
        UniqueConstraint(
            "class_section", "day_of_week", "period_number",
            name="uq_timetable_class_day_period",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    class_section: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    day_of_week: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="Lowercase English day name, e.g. 'monday'.",
    )
    period_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="1-indexed period number within the day (1–8).",
    )
    subject: Mapped[str | None] = mapped_column(String(128), nullable=True)
    teacher_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Timetable {self.class_section!r} "
            f"{self.day_of_week} P{self.period_number} {self.subject!r}>"
        )


# ── users (for auth) ───────────────────────────────────────────────────────────
class User(Base):
    """
    System user (admin / teacher / robot) for JWT authentication.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(
        String(128), unique=True, nullable=False, index=True
    )
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="teacher",
        comment="'admin', 'teacher', or 'robot'.",
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.username!r} role={self.role}>"


# ── personalization tables ──────────────────────────────────────────────────────

class LearningProfile(Base):
    """
    Long-term learning profile for a student.
    Tracks preferred language, learning pace, and overall performance.
    """
    __tablename__ = "learning_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    preferred_language: Mapped[str] = mapped_column(String(16), default="en")
    average_pace: Mapped[float] = mapped_column(Float, default=1.0, comment="Learning pace multiplier")
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)

    student: Mapped["Student"] = relationship("Student", lazy="select")


class TopicMastery(Base):
    """
    Topic mastery records per student.
    Helps the active memory personalization agent know what topics are weak.
    """
    __tablename__ = "topic_mastery"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    topic: Mapped[str] = mapped_column(String(128), nullable=False)
    mastery_level: Mapped[float] = mapped_column(Float, default=0.0, comment="Scale 0.0 to 1.0")

    student: Mapped["Student"] = relationship("Student", lazy="select")


class InteractionLog(Base):
    """
    Logs every spoken interaction between Zoro and the student.
    """
    __tablename__ = "interaction_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id", ondelete="SET NULL"), nullable=True, index=True
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str] = mapped_column(String(32), nullable=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    student: Mapped["Student"] = relationship("Student", lazy="select")


class PracticeAttempt(Base):
    """
    Records a student's attempt to answer a question or solve a problem.
    """
    __tablename__ = "practice_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    topic: Mapped[str] = mapped_column(String(128), nullable=False)
    was_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    hints_used: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    student: Mapped["Student"] = relationship("Student", lazy="select")


class Performance(Base):
    """
    Aggregated performance metrics over a session or week.
    """
    __tablename__ = "performance"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, nullable=False)
    record_date: Mapped[date] = mapped_column(Date, nullable=False, server_default=func.current_date())

    student: Mapped["Student"] = relationship("Student", lazy="select")

