"""
Zoro AI Robot - Teacher Behavior Service
Zoro's calm, structured teacher persona.
Generates mode-appropriate prompts and announcements.
Delegates to existing RAG / AI backend — does NOT run LLM locally.
"""

import logging
from typing import Optional

from app.services.integrations.personalization_service import PersonalizationService
from app.services.integrations.rag_service import RAGService
from app.services.integrations.voice_event_interface import VoiceEventInterface
from app.services.robot_state_service import RobotMode, RobotStateService

logger = logging.getLogger("zoro.teacher")


# ── Persona constants ────────────────────────────────────────────────────────

SYSTEM_PROMPT_BASE = """
You are Zoro, a calm and structured classroom teaching robot.
Your tone is warm, patient, and encouraging — never sarcastic or impatient.
You speak in short, clear sentences appropriate for students.
You always address the student by name when known.
You stay strictly on topic.
""".strip()

MODE_INSTRUCTIONS = {
    RobotMode.ATTENDANCE: (
        "You are taking attendance. "
        "Announce each student briefly and confirm their presence. "
        "Example: 'Arjun, present. Attendance marked.' "
        "Keep replies under 10 words."
    ),
    RobotMode.TEACHING: (
        "You are in teaching mode. "
        "Give step-by-step explanations. "
        "Ask one guiding question before giving the full answer. "
        "Use the provided context from the knowledge base. "
        "Keep explanations concise and structured."
    ),
    RobotMode.PRACTICE: (
        "You are in practice mode. "
        "Ask the student a question first. "
        "If they struggle, give a small hint — do not give the answer directly. "
        "Encourage independent thinking. "
        "Say things like: 'Good attempt — think about what happens when...'"
    ),
    RobotMode.EXAM: (
        "You are in exam mode. "
        "Give no hints. "
        "Only confirm correct or incorrect answers briefly. "
        "Keep all replies under 15 words. "
        "Do not explain unless the exam is over."
    ),
    RobotMode.IDLE: (
        "You are in idle standby mode. "
        "Do not speak unless directly addressed. "
        "If asked, say: 'I am in standby mode. How can I help?'"
    ),
}

MODE_ANNOUNCEMENTS = {
    RobotMode.ATTENDANCE: "Attendance mode active. Let us begin.",
    RobotMode.TEACHING: "Teaching mode active. I am ready to explain.",
    RobotMode.PRACTICE: "Practice mode active. Let us work through some questions.",
    RobotMode.EXAM: "Exam mode active. Please focus. No hints will be given.",
    RobotMode.IDLE: "Entering standby. I will wait quietly.",
}


class TeacherBehaviorService:
    """
    Builds prompts for Zoro's AI backend and returns announcements.
    Does NOT run inference locally — delegates to VoiceEventInterface.
    """

    def __init__(
        self,
        state_service: RobotStateService,
        rag_service: Optional[RAGService] = None,
        personalization_service: Optional[PersonalizationService] = None,
        voice_interface: Optional[VoiceEventInterface] = None,
    ):
        self._state = state_service
        self._rag = rag_service or RAGService()
        self._personalization = personalization_service or PersonalizationService()
        self._voice = voice_interface or VoiceEventInterface()

    # ── Public interface ─────────────────────────────────────────────────────

    async def get_mode_announcement(self, mode: RobotMode, context: dict = {}) -> str:
        """Return the canned announcement for a mode switch (for TTS)."""
        return MODE_ANNOUNCEMENTS.get(mode, "Mode changed.")

    async def handle_student_query(
        self,
        query: str,
        student_id: Optional[str] = None,
        subject: Optional[str] = None,
    ) -> str:
        """
        Main entry point for student interaction.
        1. Fetch RAG context (existing service)
        2. Fetch personalization profile (existing service)
        3. Build system prompt with mode instructions
        4. Send to AI backend via VoiceEventInterface
        5. Return response text
        """
        mode = self._state.current_mode

        # 1. RAG context
        rag_context = ""
        if mode in (RobotMode.TEACHING, RobotMode.PRACTICE) and subject:
            try:
                rag_context = await self._rag.retrieve(query=query, subject=subject)
            except Exception as exc:
                logger.warning(f"RAG retrieval failed: {exc}")

        # 2. Personalization
        personalization_note = ""
        if student_id:
            try:
                profile = await self._personalization.get_profile(student_id)
                personalization_note = self._build_personalization_note(profile)
            except Exception as exc:
                logger.warning(f"Personalization fetch failed: {exc}")

        # 3. Build system prompt
        system_prompt = self._build_system_prompt(
            mode, rag_context, personalization_note
        )

        # 4. Send to AI backend
        try:
            response = await self._voice.send_text_prompt(
                system_prompt=system_prompt,
                user_message=query,
                student_id=student_id,
            )
        except Exception as exc:
            logger.error(f"AI backend call failed: {exc}")
            response = "I am sorry, I could not process that right now."

        return response

    async def handle_attendance_event(self, student_name: str, marked: bool) -> str:
        """Generate attendance announcement for a student."""
        if marked:
            return f"{student_name}, present. Attendance marked."
        return f"{student_name}, attendance could not be confirmed. Please check."

    # ── Private helpers ──────────────────────────────────────────────────────

    def _build_system_prompt(
        self,
        mode: RobotMode,
        rag_context: str,
        personalization_note: str,
    ) -> str:
        parts = [SYSTEM_PROMPT_BASE]
        parts.append(f"\nCurrent mode instructions:\n{MODE_INSTRUCTIONS[mode]}")

        if rag_context:
            parts.append(f"\nKnowledge base context:\n{rag_context}")

        if personalization_note:
            parts.append(f"\nStudent profile note:\n{personalization_note}")

        return "\n".join(parts)

    def _build_personalization_note(self, profile: dict) -> str:
        if not profile:
            return ""
        notes = []
        if profile.get("learning_style"):
            notes.append(f"Learning style: {profile['learning_style']}.")
        if profile.get("weak_topics"):
            weak = ", ".join(profile["weak_topics"])
            notes.append(f"Needs extra support in: {weak}.")
        if profile.get("name"):
            notes.append(f"Student name: {profile['name']}.")
        return " ".join(notes)

