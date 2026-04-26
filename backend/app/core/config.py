"""
app/core/config.py
──────────────────
Central configuration for Zoro Robot Unified System.
Includes settings for Attendance, Voice AI, and Robot Hardware.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings resolved from environment / .env file.
    All fields from both Attendance and Robot Integration layers are unified here.
    """

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # CRITICAL: Ignore any unrelated env vars to prevent validation errors
    )

    # ── Application ────────────────────────────────────────────────────────
    APP_NAME: str = Field(default="Zoro Robot – AI Classroom System", alias="app_name")
    APP_VERSION: str = Field(default="2.0.0", alias="app_version")
    DEBUG: bool = False
    ALLOWED_ORIGINS: List[str] = ["*"]
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # ── Database ───────────────────────────────────────────────────────────
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:password@localhost:5432/attendance_db",
        description="Async PostgreSQL connection URL.",
    )
    SYNC_DATABASE_URL: str = Field(
        default="postgresql+psycopg2://postgres:password@localhost:5432/attendance_db",
        alias="sync_database_url",
    )
    DB_POOL_SIZE: int = Field(default=5, alias="db_pool_size")
    DB_MAX_OVERFLOW: int = Field(default=10, alias="db_max_overflow")
    DB_POOL_TIMEOUT: int = Field(default=30, alias="db_pool_timeout")

    # ── Security / JWT ─────────────────────────────────────────────────────
    SECRET_KEY: str = Field(
        default="change-me-in-production-use-a-long-random-string",
        description="HS256 secret key for JWT signing.",
    )
    ALGORITHM: str = Field(default="HS256", alias="algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=480, alias="access_token_expire_minutes")
    API_KEY_HEADER: str = "X-Zoro-API-Key"
    API_KEY: str = Field(default="", description="Static API key.")

    # ── Face Detection & Recognition ───────────────────────────────────────
    DETECTION_MODEL: str = Field(default="haar", alias="detection_model")
    HAAR_CASCADE_PATH: str = ""
    
    # MobileNet SSD (optional)
    MOBILENET_PROTOTXT: str = Field(default="models/deploy.prototxt", alias="mobilenet_prototxt")
    MOBILENET_CAFFEMODEL: str = Field(default="models/res10_300x300_ssd_iter_140000.caffemodel", alias="mobilenet_caffemodel")
    MOBILENET_CONFIDENCE_THRESHOLD: float = Field(default=0.5, alias="mobilenet_confidence_threshold")
    
    # LBPH
    LBPH_MODEL_PATH: str = Field(default="lbph_model.yml", alias="lbph_model_path")
    LABEL_MAP_PATH: str = Field(default="label_map.json", alias="label_map_path")
    LBPH_THRESHOLD: float = Field(default=80.0, alias="lbph_threshold")

    # ── Image Pipeline ─────────────────────────────────────────────────────
    MAX_IMAGE_WIDTH: int = Field(default=320, alias="max_image_width")
    MAX_FACES_PER_FRAME: int = Field(default=2, alias="max_faces_per_frame")
    FRAME_SKIP: int = Field(default=3, alias="frame_skip")

    # ── Attendance & session ───────────────────────────────────────────────
    GRACE_MINUTES: int = Field(default=10, alias="grace_minutes")
    PERIODS_PER_DAY: int = Field(default=8, alias="periods_per_day")
    ROBOT_NO_NEW_FACE_TIMEOUT_SEC: int = Field(default=30, alias="robot_no_new_face_timeout_sec")
    ROBOT_MAX_SCANS: int = Field(default=200, alias="robot_max_scans")
    TIMEZONE: str = "Asia/Kolkata"

    # ── Robot Hardware (TB6612FNG) ─────────────────────────────────────────
    MOTOR_WATCHDOG_TIMEOUT: float = 0.5
    MOTOR_MAX_SPEED: int = 100
    MOTOR_TURN_RATIO: float = 0.6
    PWM_FREQUENCY: int = 1000

    # GPIO pins
    MOTOR_A_IN1: int = 17
    MOTOR_A_IN2: int = 27
    MOTOR_A_PWM: int = 18
    MOTOR_B_IN1: int = 22
    MOTOR_B_IN2: int = 23
    MOTOR_B_PWM: int = 13
    MOTOR_STBY: Optional[int] = None  # None for L298N, 24 for TB6612FNG

    # ── Google Drive & Integration URLs ─────────────────────────────────────
    GOOGLE_API_KEY: str = ""
    DRIVE_DEFAULT_FOLDER_URL: str = Field(
        default="https://drive.google.com/drive/folders/1BrRZuPCjDyFhywwGlI51YrcsdRre1pmg",
        alias="drive_default_folder_url"
    )
    ATTENDANCE_SERVICE_URL: str = "http://localhost:8000"
    RAG_SERVICE_URL: str = "http://localhost:8002"
    PERSONALIZATION_SERVICE_URL: str = "http://localhost:8003"
    AI_BACKEND_URL: str = "http://localhost:8004"

    # ── Voice API Keys & Global Settings ─────────────────────────────────────
    DEEPGRAM_API_KEY: str = Field(default="", alias="deepgram_api_key")
    GEMINI_API_KEY: str = Field(default="", alias="gemini_api_key")
    OPENAI_API_KEY: str = Field(default="", alias="openai_api_key")
    PIPER_PATH: str = Field(default="", alias="piper_path")
    PIPER_MODEL: str = Field(default="", alias="piper_model")
    AUDIO_VAD_AGGRESSIVENESS: int = Field(default=2, alias="audio_vad_aggressiveness")
    GEMINI_TIMEOUT_S: float = Field(default=8.0, alias="gemini_timeout_s")
    ROBOT_VOICE_COOLDOWN_SEC: float = Field(default=2.5, alias="robot_voice_cooldown_sec")

    # ── Deepgram STT ─────────────────────────────────────────────────────────
    DG_STT_MODEL: str = "nova-2-general"
    DG_STT_LANGUAGE: str = "en-IN"
    DG_STT_PUNCTUATE: bool = True
    DG_STT_INTERIM_RESULTS: bool = True
    DG_STT_ENDPOINTING: int = 400
    DG_STT_SMART_FORMAT: bool = True

    # ── Deepgram TTS ─────────────────────────────────────────────────────────
    DG_TTS_MODEL: str = "aura-asteria-en"
    DG_TTS_ENCODING: str = "linear16"
    DG_TTS_SAMPLE_RATE: int = 16000
    DG_TTS_CONTAINER: str = "wav"

    # ── Gemini Additional Settings ───────────────────────────────────────────
    GEMINI_MODEL: str = "gemini-1.5-flash"
    GEMINI_MAX_TOKENS: int = 512
    GEMINI_TEMPERATURE: float = 0.4
    GEMINI_STREAM: bool = False

    # ── Offline / Local LLM ───────────────────────────────────────────────────
    OFFLINE_LLM_ENABLED: bool = True
    OFFLINE_LLM_MODEL_PATH: str = "/opt/models/phi3-mini-q4.gguf"
    OFFLINE_LLM_N_CTX: int = 2048
    OFFLINE_LLM_N_THREADS: int = 4
    OFFLINE_LLM_MAX_TOKENS: int = 256

    # ── Piper TTS ─────────────────────────────────────────────────────────────
    PIPER_BIN: str = Field(default="/usr/local/bin/piper", alias="piper_bin")
    PIPER_TAMIL_MODEL: str = Field(default="/opt/piper/ta_IN-coqui-medium.onnx", alias="piper_tamil_model")
    PIPER_ENGLISH_MODEL: str = Field(default="/opt/piper/en_US-lessac-medium.onnx", alias="piper_english_model")
    PIPER_SAMPLE_RATE: int = 22050

    # ── Audio Hardware ────────────────────────────────────────────────────────
    AUDIO_INPUT_DEVICE: int = 0
    AUDIO_OUTPUT_DEVICE: int = 0
    AUDIO_SAMPLE_RATE: int = 16000
    AUDIO_CHANNELS: int = 1
    AUDIO_CHUNK_MS: int = 20

    # ── Face Recognition Sync ─────────────────────────────────────────────────
    FACE_BLUR_THRESHOLD: float = 80.0
    FACE_FRAMES_NEEDED: int = 3
    FACE_CONFIDENCE_MIN: float = 0.72
    FACE_SOCKET_URL: str = "ws://localhost:8765"

    # ── Rate Limiting & Sessions ──────────────────────────────────────────────
    RATE_LIMIT_REQUESTS: int = 60
    RATE_LIMIT_WINDOW_S: int = 60
    SESSION_TIMEOUT_S: int = 120
    MAX_CONCURRENT_SESSIONS: int = 3

    # ── Internal Paths ─────────────────────────────────────────────────────
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent

    # ── Public Helpers ─────────────────────────────────────────────────────
    def resolved_haar_path(self) -> str:
        if self.HAAR_CASCADE_PATH:
            return self.HAAR_CASCADE_PATH
        import cv2
        data_dir = cv2.data.haarcascades
        return str(Path(data_dir) / "haarcascade_frontalface_default.xml")

    def lbph_model_abs(self) -> Path:
        p = Path(self.LBPH_MODEL_PATH)
        return p if p.is_absolute() else self.BASE_DIR / p

    def label_map_abs(self) -> Path:
        p = Path(self.LABEL_MAP_PATH)
        return p if p.is_absolute() else self.BASE_DIR / p


# Singleton instance
settings = Settings()

