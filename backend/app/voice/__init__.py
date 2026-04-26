"""
app/voice/__init__.py
─────────────────────
Voice Agent package for Zoro Robot.

Public API:
  from app.voice import (
      process_voice_input,
      transcribe_audio,
      synthesize_speech,
      generate_teacher_response,
      detect_intent_hook as detect_intent,
      set_classroom_mode,
      attach_rag_context,
      attach_student_profile,
      set_lesson_topic,
      announce_attendance,
      ClassroomMode,
      ClassroomContext,
      Intent,
      VoiceTurn,
  )
"""

from app.voice.classroom_modes import (
    ClassroomContext,
    ClassroomMode,
    Intent,
    build_system_prompt,
    detect_intent,
    is_exam_restricted,
)
from app.voice.pipeline import (
    VoiceTurn,
    announce_attendance,
    attach_rag_context,
    attach_student_profile,
    detect_intent_hook,
    generate_teacher_response,
    process_voice_input,
    set_classroom_mode,
    set_lesson_topic,
    stream_voice_response,
    synthesize_speech,
    transcribe_audio,
)
from app.voice.wake_word import VoicePipeline, WakeWordDetector, VoiceActivityDetector

__all__ = [
    # Pipeline hooks
    "process_voice_input",
    "transcribe_audio",
    "synthesize_speech",
    "generate_teacher_response",
    "detect_intent_hook",
    "set_classroom_mode",
    "get_classroom_mode",
    "attach_rag_context",
    "attach_student_profile",
    "set_lesson_topic",
    "announce_attendance",
    "stream_voice_response",
    # Mode / context
    "ClassroomMode",
    "ClassroomContext",
    "Intent",
    "VoiceTurn",
    "build_system_prompt",
    "detect_intent",
    "is_exam_restricted",
    # Wake word / VAD
    "VoicePipeline",
    "WakeWordDetector",
    "VoiceActivityDetector",
]

