"""
app/main.py
────────────
Zoro Robot — Unified AI Classroom System.
FastAPI application entry point.

This file integrates:
  • Attendance (Face recognition + Timetable)
  • Voice Agent (Streaming pipeline)
  • Robot Control (WebSockets + Motor Service)
  • Drive Enrollment (Google Drive ingestion)
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.endpoints import (
    attendance,
    auth,
    drive_enrollment,
    mode as mode_router,
    robot,             # Attendance automation (start/stop/scan)
    robot_control,     # Hardware motion control (WebSocket)
    students,
    timetable,
)
from app.api.endpoints import voice as voice_router
from app.core.config import settings
from app.core.database import close_db, init_db
from app.services.face_service import FaceService
from app.services.deepgram_service import close_tts_client
from app.services.face_ws_server import FaceWSServer
from app.services.face_voice_sync import face_voice_sync
from app.services.motor_service import MotorService
from app.services.robot_state_service import RobotStateService


# ── Logging configuration ─────────────────────────────────────────────────────

def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.DEBUG if settings.DEBUG else logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            (
                structlog.dev.ConsoleRenderer()
                if settings.DEBUG
                else structlog.processors.JSONRenderer()
            ),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if settings.DEBUG else logging.INFO
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
    )


_configure_logging()
log = structlog.get_logger(__name__)


# ── Lifespan (Startup + Shutdown) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup + shutdown hooks for all modules."""
    log.info("system.starting", version=settings.APP_VERSION)

    # 1. Database
    try:
        await init_db()
        log.info("system.db_ready")
    except Exception as exc:
        log.error("system.db_failed", error=str(exc))
        raise

    # 2. Face recognition models
    try:
        FaceService.startup()
        log.info("system.face_ready", trained=FaceService.is_trained())
    except Exception as exc:
        log.warning("system.face_load_warning", error=str(exc))

    # 3. Hardware / Robot control
    motor_svc: MotorService = app.state.motor_service
    try:
        await motor_svc.initialize()
        log.info("system.motor_service_ready")
    except Exception as exc:
        log.warning("system.motor_service_failed", error=str(exc))

    # 4. Robot state service
    state_svc: RobotStateService = app.state.state_service
    await state_svc.initialize()

    # 5. Face WS Server (publish events)
    face_ws = FaceWSServer()
    app.state.face_ws = face_ws
    try:
        await face_ws.start()
        log.info("system.face_ws_server_ready", port=face_ws.port)
    except Exception as exc:
        log.warning("system.face_ws_server_failed", error=str(exc))

    # 6. Background listeners
    try:
        face_voice_sync.start_ws_listener()
        log.info("system.face_voice_sync_started")
    except Exception as exc:
        log.warning("system.face_voice_sync_failed", error=str(exc))

    app.state.start_time = time.time()
    log.info("system.ready")

    yield  # application runs

    # ── Shutdown ───────────────────────────────────────────────────────────
    log.info("system.shutting_down")
    
    # Stop motors physically
    await motor_svc.emergency_stop()
    await motor_svc.cleanup()

    FaceService.shutdown()
    if hasattr(app, "state") and hasattr(app.state, "face_ws"):
        await app.state.face_ws.stop()
    await face_voice_sync.stop()
    await close_tts_client()
    await close_db()
    log.info("system.shutdown_complete")


# ── FastAPI application ────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description="Unified Pi Zero 2 W Classroom System - Attendance + Voice + Robot Control",
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

    # Shared service instances preserved in app state
    motor_svc = MotorService()
    app.state.motor_service = motor_svc
    app.state.state_service = RobotStateService(motor_svc)

    # Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Request logger
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        t0 = time.perf_counter()
        if request.url.path in ("/health", "/"):
             return await call_next(request)
             
        response = await call_next(request)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        log.debug("http.request", path=request.url.path, status=response.status_code, ms=elapsed_ms)
        return response

    # ── Routers — Core Modules (All prefixed with /api) ──────────────────────
    app.include_router(auth.router, prefix="/api", tags=["Auth"])
    app.include_router(students.router, prefix="/api", tags=["Students"])
    app.include_router(attendance.router, prefix="/api", tags=["Attendance"])
    app.include_router(timetable.router, prefix="/api", tags=["Timetable"])
    app.include_router(robot.router, prefix="/api", tags=["Robot Automation"])
    app.include_router(voice_router.router, prefix="/api", tags=["Voice Agent"])
    app.include_router(drive_enrollment.router, prefix="/api", tags=["Drive Enrollment"])
    app.include_router(robot_control.router, prefix="/api/robot", tags=["Robot Control"])
    app.include_router(mode_router.router, prefix="/api/mode", tags=["Mode"])
    from app.api.endpoints import syllabus
    app.include_router(syllabus.router, prefix="/api", tags=["Syllabus"])

    # ── Serve static UI (Control Panel) ──────────────────────────────────────
    # Use absolute path so this works regardless of CWD.
    _web_dir = Path(__file__).resolve().parent.parent.parent / "web"
    try:
        app.mount("/", StaticFiles(directory=str(_web_dir), html=True), name="web")
    except Exception:
        log.warning("main.static_files_missing", directory=str(_web_dir))

    return app


app = create_app()


# ── Global exception handler ──────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("http.unhandled_error", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


# ── Health endpoint ───────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
async def health(request: Request) -> dict:
    uptime = time.time() - getattr(request.app.state, "start_time", time.time())
    return {
        "status": "ok",
        "uptime_seconds": round(uptime, 1),
        "face_model_trained": FaceService.is_trained(),
        "known_students": FaceService.known_student_count(),
        "version": settings.APP_VERSION,
    }


# ── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        workers=1,
    )
