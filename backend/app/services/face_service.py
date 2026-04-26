"""
app/services/face_service.py
─────────────────────────────
Face recognition service using 'face_recognition' (dlib-based) for high accuracy.

Architecture:
• Loads all student embeddings from PostgreSQL into memory at startup.
• Uses a ThreadPoolExecutor for heavy dlib CPU work to keep event loop free.
• Detects faces and computes 128-d embeddings for matching.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_maker
from app.models.models import Student
from app.utils.image_processing import resize_to_max_width, bbox_to_dict

# Attempt to import face_recognition
try:
    import face_recognition
    FACE_REC_AVAILABLE = True
except ImportError:
    FACE_REC_AVAILABLE = False

logger = logging.getLogger("zoro.face_service")

# ── Global Cache ──────────────────────────────────────────────────────────────
_known_encodings: List[np.ndarray] = []
_known_students: List[Dict] = []  # List of {id, name, student_id}
_is_trained: bool = False
_lock = asyncio.Lock()

class FaceService:
    """
    Stateless façade for face recognition.
    Matches the old FaceService API for compatibility.
    """

    @staticmethod
    async def startup() -> None:
        """Load all student embeddings from the database."""
        if not FACE_REC_AVAILABLE:
            logger.error("face_recognition library not installed. Face recognition will be disabled.")
            return

        async with async_session_maker() as db:
            try:
                result = await db.execute(
                    select(Student).where(Student.face_encoding != None, Student.active == True)
                )
                students = result.scalars().all()
                
                global _known_encodings, _known_students, _is_trained
                async with _lock:
                    _known_encodings = [np.array(s.face_encoding) for s in students]
                    _known_students = [
                        {
                            "id": str(s.id), 
                            "name": s.name, 
                            "student_id": s.student_id
                        } 
                        for s in students
                    ]
                    _is_trained = len(_known_students) > 0
                
                logger.info(f"face_service.startup: Loaded {len(_known_students)} known faces.")
            except Exception as e:
                logger.error(f"face_service.startup_failed: {e}")

    @staticmethod
    def shutdown() -> None:
        pass

    @staticmethod
    async def recognise_frame(bgr_frame: np.ndarray) -> List[Dict]:
        """
        Detect and recognize faces in a frame.
        """
        if not FACE_REC_AVAILABLE or not _is_trained:
            return []

        # Process in thread pool to avoid blocking event loop
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, FaceService._sync_recognise, bgr_frame)

    @staticmethod
    def _sync_recognise(bgr_frame: np.ndarray) -> List[Dict]:
        """Synchronous part of recognition."""
        # Resize for speed
        small_frame = resize_to_max_width(bgr_frame, 640)
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        # Detect
        face_locations = face_recognition.face_locations(rgb_small_frame, model="hog") # 'hog' is faster than 'cnn' on CPU
        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

        results = []
        for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
            # Compare
            matches = face_recognition.compare_faces(_known_encodings, face_encoding, tolerance=0.5)
            
            student_info = None
            confidence = 1.0 # Default confidence (dlib doesn't give 0-1 easily like LBPH)
            
            if True in matches:
                # Find best match (lowest distance)
                face_distances = face_recognition.face_distance(_known_encodings, face_encoding)
                best_match_index = np.argmin(face_distances)
                if matches[best_match_index]:
                    student_info = _known_students[best_match_index]
                    confidence = 1.0 - face_distances[best_match_index] # 0 to 1 scale roughly

            results.append({
                "bounding_box": bbox_to_dict(left, top, right-left, bottom-top),
                "confidence": round(float(confidence), 4),
                "known": student_info is not None,
                "label_id": None, # LBPH legacy
                "student_info": student_info,
            })

        return results

    @staticmethod
    async def enroll_student(
        student_internal_id: str,
        student_id_text: str,
        student_name: str,
        bgr_images: List[np.ndarray],
    ) -> Tuple[Optional[int], int]:
        """
        Compute average encoding from images and save to DB.
        """
        if not FACE_REC_AVAILABLE:
            raise RuntimeError("face_recognition not available")

        all_encodings = []
        for img in bgr_images:
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            encs = face_recognition.face_encodings(rgb)
            if encs:
                all_encodings.append(encs[0])

        if not all_encodings:
            raise ValueError("no_face")

        # Average the encodings
        mean_encoding = np.mean(all_encodings, axis=0).tolist()

        # Update DB
        async with async_session_maker() as db:
            from uuid import UUID
            student = await db.get(Student, UUID(student_internal_id))
            if student:
                student.face_encoding = mean_encoding
                await db.commit()
                
                # Refresh cache
                await FaceService.startup()
                return None, len(all_encodings)
        
        return None, 0

    @staticmethod
    def is_trained() -> bool:
        return _is_trained

    @staticmethod
    def known_student_count() -> int:
        return len(_known_students)

# Legacy alias for singleton
face_service = FaceService()
