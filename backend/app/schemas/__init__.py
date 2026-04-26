"""
schemas/__init__.py — Pydantic data models for the Voice Agent API.
"""

import enum
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

# ── Enumerations ──────────────────────────────────────────────────────────────


class Language(str, enum.Enum):
    ENGLISH = "en"
    TAMIL = "ta"
    MIXED = "mixed"


class UserRole(str, enum.Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"


class AttendanceStatus(str, enum.Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    EXCUSED = "excused"


class PipelineMode(str, enum.Enum):
    ONLINE = "online"  # Gemini + Deepgram TTS
    OFFLINE = "offline"  # local LLM + Piper
    TEXT_ONLY = "text_only"  # last resort


class FallbackReason(str, enum.Enum):
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    API_QUOTA = "api_quota"
    TTS_FAILURE = "tts_failure"
    NONE = "none"


# ── Audio / STT ───────────────────────────────────────────────────────────────


class TranscriptChunk(BaseModel):
    text: str
    is_final: bool
    confidence: float = 1.0
    language_detected: Language = Language.ENGLISH
    timestamp_ms: int = 0


class STTResult(BaseModel):
    transcript: str
    confidence: float
    language: Language
    is_final: bool
    words: List[Dict[str, Any]] = Field(default_factory=list)
    duration_ms: int = 0


# ── Attendance ────────────────────────────────────────────────────────────────


class AttendanceRecord(BaseModel):
    student_id: int
    student_name: str
    roll_number: str
    status: AttendanceStatus
    period_id: Optional[int] = None
    period_name: Optional[str] = None
    marked_at: Optional[datetime] = None
    marked_by: str = "face_recognition"


class StudentAttendanceResponse(BaseModel):
    student_id: int
    student_name: str
    class_section: str
    date: date
    records: List[AttendanceRecord]
    present_count: int
    absent_count: int
    total_periods: int
    percentage: float


class ClassAttendanceResponse(BaseModel):
    class_section: str
    date: date
    period_id: Optional[int]
    period_name: Optional[str]
    present: List[str]
    absent: List[str]
    late: List[str]
    total_students: int
    present_count: int
    percentage: float


class TodaySummaryResponse(BaseModel):
    class_section: str
    date: date
    periods_completed: int
    overall_percentage: float
    perfect_attendance: List[str]  # present in ALL periods
    chronic_absent: List[str]  # absent ≥ 3 periods
    period_breakdown: List[Dict[str, Any]]


# ── Face Recognition ──────────────────────────────────────────────────────────


class FaceDetectionEvent(BaseModel):
    student_id: int
    student_name: str
    confidence: float
    period_id: int
    class_section: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    blur_score: float = 100.0
    frame_votes: int = 3


class FaceVoiceSyncRequest(BaseModel):
    event: FaceDetectionEvent
    speak: bool = True
    language: Language = Language.MIXED


# ── Voice / LLM ───────────────────────────────────────────────────────────────


class VoiceQueryRequest(BaseModel):
    session_id: str
    audio_b64: Optional[str] = None  # base64 WAV (REST mode)
    text_query: Optional[str] = None  # direct text (bypass STT)
    user_role: UserRole = UserRole.STUDENT
    class_section: Optional[str] = None
    language_hint: Optional[Language] = None
    period_id: Optional[int] = None

    @model_validator(mode="after")
    def at_least_one_input(self) -> "VoiceQueryRequest":
        if not self.audio_b64 and not self.text_query:
            # Allow empty at schema level; router validates at runtime
            pass
        return self


class LLMRequest(BaseModel):
    prompt: str
    system_prompt: str
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    language: Language = Language.ENGLISH
    user_role: UserRole = UserRole.STUDENT
    enable_tools: bool = True
    stream: bool = True


class LLMResponse(BaseModel):
    text: str
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    tool_results: List[Dict[str, Any]] = Field(default_factory=list)
    mode: PipelineMode
    fallback_reason: FallbackReason = FallbackReason.NONE
    latency_ms: int = 0
    tokens_used: int = 0


class VoiceQueryResponse(BaseModel):
    session_id: str
    transcript: str
    response_text: str
    audio_b64: Optional[str] = None  # base64 WAV response
    language: Language
    mode: PipelineMode
    fallback_reason: FallbackReason = FallbackReason.NONE
    latency_ms: int = 0
    attendance_data: Optional[Dict[str, Any]] = None


# ── WebSocket messages ────────────────────────────────────────────────────────


class WSMessageType(str, enum.Enum):
    AUDIO_CHUNK = "audio_chunk"
    TRANSCRIPT_INTERIM = "transcript_interim"
    TRANSCRIPT_FINAL = "transcript_final"
    LLM_CHUNK = "llm_chunk"
    LLM_DONE = "llm_done"
    TTS_CHUNK = "tts_chunk"
    TTS_DONE = "tts_done"
    FACE_EVENT = "face_event"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"
    SESSION_START = "session_start"
    SESSION_END = "session_end"


class WSMessage(BaseModel):
    type: WSMessageType
    session_id: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ── Health ────────────────────────────────────────────────────────────────────


class ServiceHealth(BaseModel):
    name: str
    status: str  # "ok" | "degraded" | "down"
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    mode: PipelineMode
    services: List[ServiceHealth]
    uptime_s: float
