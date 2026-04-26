"""
Zoro AI Robot - Robot Control Endpoints
WebSocket for real-time motor control + REST safety endpoints.
"""

import asyncio
import json
import logging
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel

from app.core.security import verify_api_key
from app.services.motor_service import MotorService
from app.services.robot_state_service import RobotStateService

logger = logging.getLogger("zoro.robot_control")
router = APIRouter()


# ── Pydantic models ──────────────────────────────────────────────────────────


class MotionCommand(BaseModel):
    forward: bool = False
    backward: bool = False
    left: bool = False
    right: bool = False
    speed: int = 70  # 0-100


class RobotStatusResponse(BaseModel):
    mode: str
    is_moving: bool
    left_speed: int
    right_speed: int
    motors_enabled: bool
    watchdog_ok: bool


class StartStopRequest(BaseModel):
    action: str  # "start" | "stop"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _get_motor_service(request: Request) -> MotorService:
    return request.app.state.motor_service


def _get_state_service(request: Request) -> RobotStateService:
    return request.app.state.state_service


def _resolve_differential(cmd: MotionCommand):
    """
    Convert a MotionCommand into (left_speed, right_speed) using
    differential drive logic. Returns integers in [-100, 100].
    """
    from app.core.config import settings

    spd = max(0, min(100, cmd.speed))
    turn_ratio = settings.MOTOR_TURN_RATIO

    left = right = 0

    if cmd.forward and not cmd.backward:
        left = right = spd
    elif cmd.backward and not cmd.forward:
        left = right = -spd

    if cmd.left and not cmd.right:
        if left == 0 and right == 0:  # pivot turn (stationary)
            left = -spd
            right = spd
        else:  # curve turn
            left = int(left * turn_ratio)
    elif cmd.right and not cmd.left:
        if left == 0 and right == 0:  # pivot turn
            left = spd
            right = -spd
        else:  # curve turn
            right = int(right * turn_ratio)

    return left, right


# ── WebSocket ────────────────────────────────────────────────────────────────


@router.websocket("/ws/control")
async def websocket_control(websocket: WebSocket):
    """
    Real-time motor control via WebSocket.

    Client sends JSON at ~20 FPS:
    { "forward": bool, "backward": bool, "left": bool, "right": bool, "speed": int }

    Server sends back status JSON after each command.
    Motors stop automatically if no command arrives within watchdog timeout.
    """
    motor_svc: MotorService = websocket.app.state.motor_service
    state_svc: RobotStateService = websocket.app.state.state_service

    await websocket.accept()
    logger.info("WebSocket control client connected.")

    # Watchdog task: stops motors if no messages arrive
    watchdog_task: Optional[asyncio.Task] = None

    async def _watchdog():
        from app.core.config import settings

        await asyncio.sleep(settings.MOTOR_WATCHDOG_TIMEOUT)
        logger.warning("WebSocket watchdog triggered — stopping motors.")
        await motor_svc.emergency_stop()

    def _reset_watchdog():
        nonlocal watchdog_task
        if watchdog_task and not watchdog_task.done():
            watchdog_task.cancel()
        watchdog_task = asyncio.create_task(_watchdog())

    _reset_watchdog()

    try:
        while True:
            raw = await websocket.receive_text()
            _reset_watchdog()

            try:
                data = json.loads(raw)
                cmd = MotionCommand(**data)
            except Exception as exc:
                await websocket.send_json({"error": str(exc)})
                continue

            left_spd, right_spd = _resolve_differential(cmd)
            await motor_svc.control_motors(left_spd, right_spd)

            await websocket.send_json(
                {
                    "ok": True,
                    "left_speed": left_spd,
                    "right_speed": right_spd,
                    "mode": state_svc.current_mode.value,
                }
            )

    except WebSocketDisconnect:
        logger.info("WebSocket control client disconnected.")
    except Exception as exc:
        logger.error(f"WebSocket error: {exc}")
    finally:
        if watchdog_task and not watchdog_task.done():
            watchdog_task.cancel()
        await motor_svc.emergency_stop()
        logger.info("Motors stopped after WebSocket session ended.")


# ── REST endpoints ───────────────────────────────────────────────────────────


@router.get("/status", response_model=RobotStatusResponse)
async def get_status(
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """Return current robot motion and safety state."""
    motor_svc: MotorService = _get_motor_service(request)
    state_svc: RobotStateService = _get_state_service(request)
    snapshot = motor_svc.get_state()
    return RobotStatusResponse(
        mode=state_svc.current_mode.value,
        is_moving=snapshot["is_moving"],
        left_speed=snapshot["left_speed"],
        right_speed=snapshot["right_speed"],
        motors_enabled=snapshot["motors_enabled"],
        watchdog_ok=True,
    )


@router.post("/stop")
async def emergency_stop(
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """Immediately stop all motors."""
    motor_svc: MotorService = _get_motor_service(request)
    await motor_svc.emergency_stop()
    return {"ok": True, "message": "Motors stopped."}


@router.post("/startstop")
async def start_stop(
    body: StartStopRequest,
    request: Request,
    _key: str = Depends(verify_api_key),
):
    """Enable or disable motor driver (STBY pin)."""
    motor_svc: MotorService = _get_motor_service(request)
    if body.action == "start":
        await motor_svc.enable_motors()
        return {"ok": True, "message": "Motors enabled."}
    elif body.action == "stop":
        await motor_svc.emergency_stop()
        await motor_svc.disable_motors()
        return {"ok": True, "message": "Motors disabled."}
    raise HTTPException(status_code=400, detail="action must be 'start' or 'stop'.")

