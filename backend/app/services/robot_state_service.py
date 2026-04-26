"""
Zoro AI Robot - Robot State Service
Manages current mode, coordinates integration hooks to existing services.
"""

import logging
from enum import Enum
from typing import Optional

from app.services.motor_service import MotorService

logger = logging.getLogger("zoro.state")


class RobotMode(str, Enum):
    ATTENDANCE = "attendance"
    TEACHING = "teaching"
    PRACTICE = "practice"
    EXAM = "exam"
    IDLE = "idle"


class RobotStateService:
    """
    Central state object for Zoro.
    Coordinates mode changes, exposes shared state to other services.
    Does NOT own the database, attendance, RAG, or personalization logic —
    those are called through service wrappers in app/services/integrations/.
    """

    def __init__(self, motor_service: MotorService):
        self._motor_service = motor_service
        self._current_mode: RobotMode = RobotMode.IDLE
        self._active_student_id: Optional[str] = None
        self._active_subject: Optional[str] = None

    async def initialize(self):
        logger.info(
            f"Robot state initialized. Default mode: {self._current_mode.value}"
        )

    @property
    def current_mode(self) -> RobotMode:
        return self._current_mode

    @property
    def active_student_id(self) -> Optional[str]:
        return self._active_student_id

    @property
    def active_subject(self) -> Optional[str]:
        return self._active_subject

    async def set_mode(self, mode: RobotMode, context: dict = {}):
        """
        Switch modes. Performs mode-entry side-effects:
        - IDLE: stop motors gently
        - EXAM: disable movement (Zoro stays still)
        """
        prev = self._current_mode
        self._current_mode = mode

        # Carry context forward
        self._active_student_id = context.get("student_id", self._active_student_id)
        self._active_subject = context.get("subject", self._active_subject)

        # Side effects
        if mode == RobotMode.IDLE:
            await self._motor_service.emergency_stop()
        elif mode == RobotMode.EXAM:
            await self._motor_service.emergency_stop()

        logger.info(f"Mode changed: {prev.value} → {mode.value}")

    def summary(self) -> dict:
        return {
            "mode": self._current_mode.value,
            "active_student_id": self._active_student_id,
            "active_subject": self._active_subject,
            **self._motor_service.get_state(),
        }

