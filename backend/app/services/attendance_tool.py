"""
services/attendance_tool.py — Safe READ-ONLY attendance DB tools.

All functions return structured dicts ready for Gemini function-calling.
No INSERT / UPDATE / DELETE operations are permitted.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from app.core.config import settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)

logger = logging.getLogger("voice_agent.attendance")

# ── DB engine (async, read-optimised) ────────────────────────────────────────
_engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with _session_factory() as session:
        yield session


# ─────────────────────────────────────────────────────────────────────────────
# Helper — safe param sanitisation
# ─────────────────────────────────────────────────────────────────────────────

def _safe_date(d: Any) -> date:
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        return date.fromisoformat(d)
    return date.today()


# ─────────────────────────────────────────────────────────────────────────────
# Tool 1 — get_student_attendance
# ─────────────────────────────────────────────────────────────────────────────

STUDENT_ATTENDANCE_SQL = text("""
    SELECT
        s.id            AS student_id,
        s.name          AS student_name,
        s.roll_number,
        s.class_section,
        a.attendance_date,
        a.status,
        p.id            AS period_id,
        p.name          AS period_name,
        p.start_time,
        a.marked_at,
        a.marked_by
    FROM attendance a
    JOIN students s ON s.id = a.student_id
    JOIN periods  p ON p.id = a.period_id
    WHERE
        a.attendance_date = :att_date
        AND (s.id = :student_id OR s.name ILIKE :student_name)
        AND (:period_id IS NULL OR a.period_id = :period_id)
    ORDER BY p.start_time
""")


async def get_student_attendance(
    *,
    student_id: Optional[int] = None,
    student_name: Optional[str] = None,
    att_date: Optional[str] = None,
    period_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Fetch one student's attendance for a given date (all or one period).

    Parameters
    ----------
    student_id   : DB primary key of student (preferred)
    student_name : partial name match (ILIKE) — used if id not given
    att_date     : ISO date string, defaults to today
    period_id    : if given, filter to that period only

    Returns structured dict safe for Gemini function-calling response.
    """
    try:
        resolved_date = _safe_date(att_date)
        search_name = f"%{student_name}%" if student_name else "%"

        async with _session_factory() as session:
            result = await session.execute(
                STUDENT_ATTENDANCE_SQL,
                {
                    "att_date": resolved_date,
                    "student_id": student_id or -1,
                    "student_name": search_name,
                    "period_id": period_id,
                },
            )
            rows = result.mappings().all()

        if not rows:
            return {
                "found": False,
                "message": f"No attendance records found for student '{student_name or student_id}' on {resolved_date}.",
            }

        first = rows[0]
        records = [
            {
                "period_id": r["period_id"],
                "period_name": r["period_name"],
                "start_time": str(r["start_time"]),
                "status": r["status"],
                "marked_at": str(r["marked_at"]) if r["marked_at"] else None,
                "marked_by": r["marked_by"],
            }
            for r in rows
        ]

        present = sum(1 for r in records if r["status"] == "present")
        total = len(records)

        return {
            "found": True,
            "student_id": first["student_id"],
            "student_name": first["student_name"],
            "roll_number": first["roll_number"],
            "class_section": first["class_section"],
            "date": str(resolved_date),
            "records": records,
            "present_count": present,
            "absent_count": total - present,
            "total_periods": total,
            "percentage": round(present / total * 100, 1) if total else 0.0,
        }

    except Exception as e:
        logger.exception("get_student_attendance error: %s", e)
        return {"found": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Tool 2 — get_class_attendance
# ─────────────────────────────────────────────────────────────────────────────

CLASS_ATTENDANCE_SQL = text("""
    SELECT
        s.id            AS student_id,
        s.name          AS student_name,
        s.roll_number,
        a.status,
        p.id            AS period_id,
        p.name          AS period_name
    FROM attendance a
    JOIN students s ON s.id = a.student_id
    JOIN periods  p ON p.id = a.period_id
    WHERE
        s.class_section = :class_section
        AND a.attendance_date = :att_date
        AND (:period_id IS NULL OR a.period_id = :period_id)
    ORDER BY s.roll_number
""")


async def get_class_attendance(
    *,
    class_section: str,
    att_date: Optional[str] = None,
    period_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Fetch full class attendance for a given date and optional period.
    """
    try:
        resolved_date = _safe_date(att_date)

        async with _session_factory() as session:
            result = await session.execute(
                CLASS_ATTENDANCE_SQL,
                {
                    "class_section": class_section,
                    "att_date": resolved_date,
                    "period_id": period_id,
                },
            )
            rows = result.mappings().all()

        if not rows:
            return {
                "found": False,
                "message": f"No records for class {class_section} on {resolved_date}.",
            }

        present = [r["student_name"] for r in rows if r["status"] == "present"]
        absent  = [r["student_name"] for r in rows if r["status"] == "absent"]
        late    = [r["student_name"] for r in rows if r["status"] == "late"]
        total   = len(rows)

        period_name = rows[0]["period_name"] if period_id else "All Periods"

        return {
            "found": True,
            "class_section": class_section,
            "date": str(resolved_date),
            "period_id": period_id,
            "period_name": period_name,
            "present": present,
            "absent": absent,
            "late": late,
            "total_students": total,
            "present_count": len(present),
            "percentage": round(len(present) / total * 100, 1) if total else 0.0,
        }

    except Exception as e:
        logger.exception("get_class_attendance error: %s", e)
        return {"found": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Tool 3 — get_today_summary
# ─────────────────────────────────────────────────────────────────────────────

TODAY_SUMMARY_SQL = text("""
    SELECT
        s.name              AS student_name,
        p.id                AS period_id,
        p.name              AS period_name,
        p.start_time,
        a.status
    FROM attendance a
    JOIN students s ON s.id = a.student_id
    JOIN periods  p ON p.id = a.period_id
    WHERE
        s.class_section = :class_section
        AND a.attendance_date = :att_date
    ORDER BY p.start_time, s.roll_number
""")


async def get_today_summary(*, class_section: str) -> Dict[str, Any]:
    """
    Today's full summary for a class:
    - Per-period breakdown
    - Perfect attendance students
    - Chronic absent students (≥ 3 periods absent)
    """
    try:
        today = date.today()

        async with _session_factory() as session:
            result = await session.execute(
                TODAY_SUMMARY_SQL,
                {"class_section": class_section, "att_date": today},
            )
            rows = result.mappings().all()

        if not rows:
            return {
                "found": False,
                "message": f"No attendance yet today for class {class_section}.",
            }

        # Group by period
        periods: Dict[int, Dict] = {}
        student_counts: Dict[str, Dict[str, int]] = {}

        for r in rows:
            pid = r["period_id"]
            if pid not in periods:
                periods[pid] = {
                    "period_id": pid,
                    "period_name": r["period_name"],
                    "start_time": str(r["start_time"]),
                    "present": [],
                    "absent": [],
                    "late": [],
                }
            status = r["status"]
            periods[pid][status].append(r["student_name"])

            name = r["student_name"]
            if name not in student_counts:
                student_counts[name] = {"present": 0, "absent": 0, "late": 0}
            student_counts[name][status] = student_counts[name].get(status, 0) + 1

        period_list = list(periods.values())
        total_periods = len(period_list)
        total_students = len(student_counts)

        perfect = [n for n, c in student_counts.items() if c.get("absent", 0) == 0 and c.get("late", 0) == 0]
        chronic = [n for n, c in student_counts.items() if c.get("absent", 0) >= 3]

        total_present = sum(len(p["present"]) for p in period_list)
        denom = total_periods * total_students if total_periods and total_students else 1

        return {
            "found": True,
            "class_section": class_section,
            "date": str(today),
            "periods_completed": total_periods,
            "total_students": total_students,
            "overall_percentage": round(total_present / denom * 100, 1),
            "perfect_attendance": perfect,
            "chronic_absent": chronic,
            "period_breakdown": period_list,
        }

    except Exception as e:
        logger.exception("get_today_summary error: %s", e)
        return {"found": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Gemini tool definitions (function-calling schema)
# ─────────────────────────────────────────────────────────────────────────────

GEMINI_TOOL_DEFINITIONS = [
    {
        "name": "get_student_attendance",
        "description": (
            "Fetch a single student's attendance records for a given date. "
            "Returns present/absent status per period with percentage."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "student_id": {
                    "type": "integer",
                    "description": "Student DB id (use if known, preferred over name)",
                },
                "student_name": {
                    "type": "string",
                    "description": "Student name (partial match allowed). Provide if id not known.",
                },
                "att_date": {
                    "type": "string",
                    "description": "ISO date YYYY-MM-DD. Defaults to today.",
                },
                "period_id": {
                    "type": "integer",
                    "description": "Filter to a specific period. Omit for all periods.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_class_attendance",
        "description": (
            "Fetch attendance for an entire class section on a given date. "
            "Returns lists of present, absent, and late students with percentage."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "class_section": {
                    "type": "string",
                    "description": "Class section identifier e.g. '10A', '9B'",
                },
                "att_date": {
                    "type": "string",
                    "description": "ISO date YYYY-MM-DD. Defaults to today.",
                },
                "period_id": {
                    "type": "integer",
                    "description": "Filter to a specific period. Omit for all.",
                },
            },
            "required": ["class_section"],
        },
    },
    {
        "name": "get_today_summary",
        "description": (
            "Get today's full attendance summary for a class: overall percentage, "
            "perfect attendance students, chronic absentees, and period-by-period breakdown."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "class_section": {
                    "type": "string",
                    "description": "Class section identifier e.g. '10A'",
                },
            },
            "required": ["class_section"],
        },
    },
]

# Router — maps tool name → async function
TOOL_REGISTRY = {
    "get_student_attendance": get_student_attendance,
    "get_class_attendance": get_class_attendance,
    "get_today_summary": get_today_summary,
}


async def execute_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dispatch a tool call by name with arguments.
    Returns structured result or error dict.
    """
    if name not in TOOL_REGISTRY:
        return {"error": f"Unknown tool: {name}"}
    fn = TOOL_REGISTRY[name]
    try:
        return await fn(**arguments)
    except TypeError as e:
        logger.error("Tool %s bad args %s: %s", name, arguments, e)
        return {"error": f"Invalid arguments for {name}: {e}"}
