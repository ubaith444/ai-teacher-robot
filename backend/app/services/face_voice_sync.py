"""
services/face_voice_sync.py — Motion-aware face recognition + voice feedback sync.

Integrates with the face recognition WebSocket service to:
  • Filter blurry frames (Laplacian variance)
  • Collect multi-frame embedding votes (3-5 frames)
  • Confirm attendance marking with spoken feedback
  • Trigger TTS announcement when a student is recognised
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.core.config import settings
from app.schemas import FaceDetectionEvent, Language

logger = logging.getLogger("voice_agent.face_voice")

# ── Optional numpy / cv2 for blur detection ───────────────────────────────────
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logger.warning("numpy not available — blur detection disabled")

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    logger.warning("OpenCV not available — frame-based blur detection disabled")


# ─────────────────────────────────────────────────────────────────────────────
# Blur detection
# ─────────────────────────────────────────────────────────────────────────────

def compute_laplacian_variance(frame_bytes: bytes, width: int, height: int) -> float:
    """
    Compute Laplacian variance to detect motion blur.
    Returns float — higher is sharper. Threshold: settings.FACE_BLUR_THRESHOLD
    """
    if not (NUMPY_AVAILABLE and CV2_AVAILABLE):
        return 999.0  # assume sharp if libs unavailable

    try:
        arr = np.frombuffer(frame_bytes, dtype=np.uint8).reshape((height, width, 3))
        gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        variance = cv2.Laplacian(gray, cv2.CV_64F).var()
        return float(variance)
    except Exception as e:
        logger.debug("Blur detection error: %s", e)
        return 999.0


def is_frame_sharp(frame_bytes: bytes, width: int = 640, height: int = 480) -> bool:
    variance = compute_laplacian_variance(frame_bytes, width, height)
    return variance >= settings.FACE_BLUR_THRESHOLD


# ─────────────────────────────────────────────────────────────────────────────
# Multi-frame vote tracker
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class StudentVoteState:
    student_id: int
    student_name: str
    class_section: str
    period_id: int
    vote_scores: List[float] = field(default_factory=list)
    first_seen: float = field(default_factory=time.time)
    confirmed: bool = False
    last_event_time: float = field(default_factory=time.time)

    def add_vote(self, confidence: float):
        self.vote_scores.append(confidence)
        self.last_seen = time.time()

    @property
    def vote_count(self) -> int:
        return len(self.vote_scores)

    @property
    def avg_confidence(self) -> float:
        return sum(self.vote_scores) / len(self.vote_scores) if self.vote_scores else 0.0

    @property
    def is_ready(self) -> bool:
        return (
            self.vote_count >= settings.FACE_FRAMES_NEEDED
            and self.avg_confidence >= settings.FACE_CONFIDENCE_MIN
        )


class MultiFrameVoteTracker:
    """
    Accumulates face recognition events for the same student
    until enough high-confidence frames have been collected.
    """

    def __init__(self, max_age_s: float = 5.0):
        self._states: Dict[Tuple[int, int], StudentVoteState] = {}  # (student_id, period_id) → state
        self.max_age_s = max_age_s

    def add_detection(self, event: FaceDetectionEvent) -> Optional[StudentVoteState]:
        """
        Add a detection event. Returns the state if vote threshold is reached.
        Returns None if still collecting.
        """
        key = (event.student_id, event.period_id)
        now = time.time()

        # Expire stale states
        expired = [k for k, s in self._states.items() if now - s.first_seen > self.max_age_s]
        for k in expired:
            del self._states[k]

        if key not in self._states:
            self._states[key] = StudentVoteState(
                student_id=event.student_id,
                student_name=event.student_name,
                class_section=event.class_section,
                period_id=event.period_id,
            )

        state = self._states[key]
        if state.confirmed:
            return None   # already processed

        state.add_vote(event.confidence)
        logger.debug(
            "Vote %d/%d for %s (conf=%.2f avg=%.2f)",
            state.vote_count, settings.FACE_FRAMES_NEEDED,
            event.student_name, event.confidence, state.avg_confidence,
        )

        if state.is_ready:
            state.confirmed = True
            return state

        return None

    def clear_student(self, student_id: int, period_id: int):
        key = (student_id, period_id)
        self._states.pop(key, None)


# ─────────────────────────────────────────────────────────────────────────────
# Voice announcement templates
# ─────────────────────────────────────────────────────────────────────────────

def build_attendance_announcement(
    student_name: str,
    period_id: int,
    status: str = "Present",
    language: Language = Language.MIXED,
) -> str:
    """Generate a short, warm voice announcement for attendance marking."""
    if language == Language.ENGLISH:
        return f"{student_name} marked {status} in Period {period_id}."
    if language == Language.TAMIL:
        status_ta = "வருகை உள்ளது" if status.lower() == "present" else "வருகை இல்லை"
        return f"{student_name}, {period_id}-வது வகுப்பில் {status_ta}."
    # Mixed (default for students)
    return f"{student_name} marked {status} in Period {period_id}."


def build_class_summary_announcement(
    class_section: str,
    present: int,
    total: int,
    language: Language = Language.MIXED,
) -> str:
    pct = round(present / total * 100) if total else 0
    if language == Language.ENGLISH:
        return f"Class {class_section}: {present} out of {total} students are present. Attendance is {pct} percent."
    if language == Language.TAMIL:
        return f"{class_section} வகுப்பில் {total} மாணவர்களில் {present} பேர் வந்துள்ளனர். {pct} சதவீதம்."
    return f"Class {class_section}: {present}/{total} present, {pct} percent."


# ─────────────────────────────────────────────────────────────────────────────
# Face Voice Sync Service
# ─────────────────────────────────────────────────────────────────────────────

class FaceVoiceSyncService:
    """
    Main service that:
    1. Receives face detection events (from WebSocket or internal calls)
    2. Filters blurry frames
    3. Accumulates multi-frame votes
    4. Triggers TTS voice confirmation on confirmed detection
    5. Logs confirmed attendance to callback
    """

    def __init__(self):
        self.vote_tracker = MultiFrameVoteTracker(max_age_s=8.0)
        self._tts_callback: Optional[Callable[[str, Language], None]] = None
        self._attendance_callback: Optional[Callable[[Dict], None]] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._connected = False

    def set_tts_callback(self, fn: Callable[[str, Language], None]):
        """Set callback to play TTS announcement. fn(text, language)."""
        self._tts_callback = fn

    def set_attendance_callback(self, fn: Callable[[Dict], None]):
        """Set callback when attendance is confirmed. fn(attendance_data)."""
        self._attendance_callback = fn

    async def process_event(
        self,
        event: FaceDetectionEvent,
        frame_bytes: Optional[bytes] = None,
        frame_width: int = 640,
        frame_height: int = 480,
        language: Language = Language.MIXED,
    ) -> Optional[Dict[str, Any]]:
        """
        Process a single face detection event.

        1. Check blur (if frame provided)
        2. Add to vote tracker
        3. If threshold reached → confirm and announce

        Returns attendance confirmation dict or None.
        """
        # Step 1: Blur filter
        if frame_bytes:
            blur_score = compute_laplacian_variance(frame_bytes, frame_width, frame_height)
            event.blur_score = blur_score
            if blur_score < settings.FACE_BLUR_THRESHOLD:
                logger.debug(
                    "Blurry frame rejected for %s (var=%.1f < %.1f)",
                    event.student_name, blur_score, settings.FACE_BLUR_THRESHOLD,
                )
                return None

        # Step 2: Vote tracking
        confirmed_state = self.vote_tracker.add_detection(event)
        if confirmed_state is None:
            return None

        # Step 3: Confirmed — build announcement
        logger.info(
            "✅ Attendance confirmed: %s Period %d (avg_conf=%.2f, votes=%d)",
            confirmed_state.student_name,
            confirmed_state.period_id,
            confirmed_state.avg_confidence,
            confirmed_state.vote_count,
        )

        attendance_data = {
            "student_id": confirmed_state.student_id,
            "student_name": confirmed_state.student_name,
            "class_section": confirmed_state.class_section,
            "period_id": confirmed_state.period_id,
            "status": "present",
            "confidence": round(confirmed_state.avg_confidence, 3),
            "votes": confirmed_state.vote_count,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Step 4: Voice announcement
        announcement = build_attendance_announcement(
            confirmed_state.student_name,
            confirmed_state.period_id,
            "Present",
            language,
        )
        if self._tts_callback:
            asyncio.create_task(
                self._async_tts(announcement, language)
            )

        # Step 5: Notify attendance system
        if self._attendance_callback:
            self._attendance_callback(attendance_data)

        return attendance_data

    async def _async_tts(self, text: str, language: Language):
        """Fire-and-forget TTS with error guard."""
        try:
            if self._tts_callback:
                await asyncio.get_event_loop().run_in_executor(
                    None, self._tts_callback, text, language
                )
        except Exception as e:
            logger.exception("TTS callback error: %s", e)

    # ── WebSocket listener (face recognition service) ──────────────────────

    async def connect_face_ws(self, language: Language = Language.MIXED):
        """
        Connect to the face recognition WebSocket service and process events.
        Automatically reconnects on disconnection.
        """
        retry_delay = 2.0
        while True:
            try:
                await self._ws_listener(language)
            except Exception as e:
                logger.warning("Face WS disconnected: %s. Retrying in %.1fs", e, retry_delay)
            await asyncio.sleep(retry_delay)
            retry_delay = min(retry_delay * 1.5, 30.0)

    async def _ws_listener(self, language: Language):
        """Inner WS listener loop."""
        try:
            import websockets  # type: ignore
        except ImportError:
            logger.error("websockets not installed — face WS listener disabled")
            return

        url = settings.FACE_SOCKET_URL
        logger.info("Connecting to face recognition WS: %s", url)

        async with websockets.connect(url, ping_interval=15) as ws:
            self._connected = True
            logger.info("Face recognition WS connected")

            async for message in ws:
                try:
                    data = json.loads(message)
                    event = FaceDetectionEvent(**data)
                    await self.process_event(event, language=language)
                except Exception as e:
                    logger.debug("Face WS parse error: %s", e)

        self._connected = False

    def start_ws_listener(self, language: Language = Language.MIXED):
        """Start WebSocket listener as a background task."""
        self._ws_task = asyncio.create_task(self.connect_face_ws(language))
        logger.info("Face WS listener task started")

    async def stop(self):
        if self._ws_task:
            self._ws_task.cancel()
            try:
                await self._ws_task
            except asyncio.CancelledError:
                pass
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected


# ── Module-level singleton ─────────────────────────────────────────────────────
face_voice_sync = FaceVoiceSyncService()
