"""
Zoro AI Robot - Mode Endpoints
Switch between Zoro's behavioral modes via REST.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.core.security import verify_api_key
from app.services.robot_state_service import RobotMode, RobotStateService
from app.services.teacher_behavior_service import TeacherBehaviorService

logger = logging.getLogger("zoro.mode")
router = APIRouter()


class ModeSwitchRequest(BaseModel):
    mode: str  # "attendance" | "teaching" | "practice" | "exam" | "idle"
    context: dict = {}  # optional extra context (e.g., student_id, subject)


class ModeResponse(BaseModel):
    ok: bool
    mode: str
    announcement: str


@router.post("/switch", response_model=ModeResponse)
async def switch_mode(
    body: ModeSwitchRequest,
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """
    Switch Zoro's active mode.
    Returns a mode-appropriate announcement string for TTS.
    """
    state_svc: RobotStateService = request.app.state.state_service

    try:
        new_mode = RobotMode(body.mode)
    except ValueError:
        valid = [m.value for m in RobotMode]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{body.mode}'. Valid: {valid}",
        )

    await state_svc.set_mode(new_mode)

    behavior_svc = TeacherBehaviorService(state_svc)
    announcement = await behavior_svc.get_mode_announcement(new_mode, body.context)

    logger.info(f"Mode switched to {new_mode.value}. Announcement: {announcement}")
    return ModeResponse(ok=True, mode=new_mode.value, announcement=announcement)


@router.get("/current")
async def get_mode(request: Request, _key: str = Depends(verify_api_key)):
    """Return the current active mode."""
    state_svc: RobotStateService = request.app.state.state_service
    return {"mode": state_svc.current_mode.value}


@router.get("/list")
async def list_modes(_key: str = Depends(verify_api_key)):
    """Return all supported modes."""
    return {"modes": [m.value for m in RobotMode]}

