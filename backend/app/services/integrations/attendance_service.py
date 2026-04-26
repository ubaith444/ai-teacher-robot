"""
Zoro AI Robot - Attendance Service Wrapper (Aligned)
Thin HTTP client over your existing attendance backend.
Zoro does NOT own attendance logic — it only calls your service.
"""

import logging
from typing import Optional, List

import httpx
from app.core.config import settings

logger = logging.getLogger("zoro.attendance_svc")


class AttendanceService:
    """
    Interface to the existing attendance system.
    Aligned with the FastAPI endpoints in app/api/endpoints/attendance.py.
    """

    def __init__(self, base_url: Optional[str] = None):
        # Default to local server if not specified
        self._base_url = (base_url or settings.ATTENDANCE_SERVICE_URL).rstrip("/")
        self._timeout = 10.0

    async def mark_attendance(
        self,
        student_id: str,
        session_id: str,
        confidence: Optional[float] = None,
    ) -> dict:
        """
        Mark a student as present for a specific session ID.
        Uses Query parameters as defined in the attendance endpoint.
        """
        params = {
            "session_id": session_id,
            "student_id": student_id,
        }
        if confidence is not None:
            params["confidence"] = confidence

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/attendance/mark",
                    params=params
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.error(f"Attendance mark failed [{exc.response.status_code}]: {exc.response.text}")
            raise
        except httpx.RequestError as exc:
            logger.error(f"Attendance service unreachable at {self._base_url}: {exc}")
            raise

    async def get_today_attendance(
        self, 
        class_section: Optional[str] = None, 
        session_id: Optional[str] = None
    ) -> dict:
        """
        Fetch today's attendance records.
        """
        params = {}
        if class_section:
            params["class_section"] = class_section
        if session_id:
            params["session_id"] = session_id

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._base_url}/attendance/today",
                    params=params
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.error(f"Attendance query failed: {exc}")
            raise

    async def get_session_summary(self, session_id: str) -> dict:
        """
        Fetch summary for a specific session.
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._base_url}/attendance/session-summary"
                )
                resp.raise_for_status()
                summaries = resp.json()
                # Find the specific session in the list
                for s in summaries:
                    if s.get("session_id") == session_id:
                        return s
                return {}
        except Exception as exc:
            logger.info(f"Session summary fetch failed: {exc}")
            return {}

