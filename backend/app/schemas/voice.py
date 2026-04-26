from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel


# ✅ ALWAYS DEFINE REQUEST FIRST
class VoiceQueryRequest(BaseModel):
    session_id: Optional[str] = None
    audio_b64: Optional[str] = None
    text_query: Optional[str] = None
    user_role: Optional[str] = "student"
    class_section: Optional[str] = None
    language_hint: Optional[str] = None
    period_id: Optional[int] = None


# ✅ THEN RESPONSE
class VoiceQueryResponse(BaseModel):
    session_id: str
    transcript: str
    response_text: str
    audio_b64: Optional[str] = None
    language: Optional[str] = None
    mode: Optional[str] = None
    fallback_reason: Optional[str] = None
    latency_ms: Optional[int] = 0
    attendance_data: Optional[Dict[str, Any]] = None


# ✅ CRITICAL FOR PYDANTIC V2
VoiceQueryRequest.model_rebuild()
VoiceQueryResponse.model_rebuild()
