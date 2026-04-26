"""
Zoro AI Robot - Personalization Service Wrapper
Thin client over your existing personalization engine.
Zoro does NOT own student profiles — it reads them through this interface.
"""

import logging
from typing import Optional

import httpx
from app.core.config import settings

logger = logging.getLogger("zoro.personalization_svc")


class PersonalizationService:
    """
    Interface to your existing personalization engine.
    Endpoint contract (adapt to your actual API):
      GET  /personalization/profile/{student_id}
      POST /personalization/update  { student_id, interaction_data }
    """

    def __init__(self, base_url: Optional[str] = None):
        self._base_url = (base_url or settings.PERSONALIZATION_SERVICE_URL).rstrip("/")
        self._timeout = 5.0

    async def get_profile(self, student_id: str) -> dict:
        """
        Fetch student personalization profile.
        Returns dict with keys like: name, learning_style, weak_topics, pace.
        Returns empty dict if not found or service unavailable.
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._base_url}/personalization/profile/{student_id}"
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                logger.info(f"No profile found for student {student_id}.")
                return {}
            logger.error(f"Personalization profile fetch failed: {exc}")
            return {}
        except httpx.RequestError as exc:
            logger.error(f"Personalization service unreachable: {exc}")
            return {}

    async def record_interaction(
        self,
        student_id: str,
        mode: str,
        query: str,
        response: str,
        subject: Optional[str] = None,
    ) -> bool:
        """
        Push an interaction event to your personalization engine
        so it can update the student's profile over time.
        Returns True on success.
        """
        payload = {
            "student_id": student_id,
            "mode": mode,
            "query": query,
            "response": response,
            "subject": subject,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/personalization/update", json=payload
                )
                resp.raise_for_status()
                return True
        except Exception as exc:
            logger.warning(f"Personalization update failed (non-critical): {exc}")
            return False

