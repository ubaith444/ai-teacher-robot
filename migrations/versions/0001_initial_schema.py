"""Initial schema: students, sessions, attendance, timetable

Revision ID: 0001_initial_schema
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── students ──────────────────────────────────────────────────────────
    op.create_table(
        "students",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("student_id", sa.String(64), unique=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("label_id", sa.Integer(), unique=True, nullable=True),
        sa.Column("class_section", sa.String(64), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("ix_students_student_id", "students", ["student_id"])
    op.create_index("ix_students_class_section", "students", ["class_section"])

    # ── sessions ──────────────────────────────────────────────────────────
    op.create_table(
        "sessions",
        sa.Column("session_id", sa.String(128), primary_key=True),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("class_section", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
    )
    op.create_index("ix_sessions_class_section", "sessions", ["class_section"])

    # ── attendance ────────────────────────────────────────────────────────
    op.create_table(
        "attendance",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            sa.String(128),
            sa.ForeignKey("sessions.session_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "student_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("students.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("bounding_box", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_attendance_session_id", "attendance", ["session_id"])
    op.create_index("ix_attendance_student_id", "attendance", ["student_id"])

    # Partial unique index: one attendance record per student per session
    op.execute(
        """
        CREATE UNIQUE INDEX uix_attendance_session_student
        ON attendance (session_id, student_id)
        WHERE session_id IS NOT NULL AND student_id IS NOT NULL
        """
    )

    # ── timetable ─────────────────────────────────────────────────────────
    op.create_table(
        "timetable",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("class_section", sa.String(64), nullable=False),
        sa.Column("day_of_week", sa.String(16), nullable=False),
        sa.Column("period_number", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(128), nullable=True),
        sa.Column("teacher_id", sa.String(64), nullable=True),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
    )
    op.create_index("ix_timetable_class_section", "timetable", ["class_section"])


def downgrade() -> None:
    op.drop_table("attendance")
    op.drop_table("sessions")
    op.drop_table("timetable")
    op.drop_table("students")
