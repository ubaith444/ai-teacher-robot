"""
app/services/integrations/voice_event_interface.py
────────────────────────────────────────────────────
Interface between Zoro's Teacher Behavior (Robot Layer) and the 
Central Voice Orchestrator (AI Pipeline).

This allows the robot components to trigger speech and AI reasoning
without being coupled to the low-level STT/LLM/TTS details.
"""

from __future__ import annotations

import logging
from typing import Optional

# We import the singleton from the central voice service
from app.services.voice_orchestrator import voice_orchestrator
from app.schemas import VoiceQueryRequest, UserRole

logger = logging.getLogger("zoro.voice_interface")


class VoiceEventInterface:
    """
    Bridge class for Robot behavioral services to interact with Voice AI.
    """

    def __init__(self, orchestrator=None):
        self._orchestrator = orchestrator or voice_orchestrator

    async def send_text_prompt(
        self,
        system_prompt: str,
        user_message: str,
        student_id: Optional[str] = None,
        session_id: str = "robot_behavior_session",
    ) -> str:
        """
        Sends a text-based prompt to the AI pipeline.
        Used by TeacherBehaviorService to get Zoro's persona-based response.
        """
        try:
            # We wrap the text prompt into a VoiceQueryRequest (without audio)
            # This triggers Step 2 (LLM) and Step 3 (TTS) in the orchestrator.
            req = VoiceQueryRequest(
                session_id=session_id,
                text_query=user_message,
                user_role=UserRole.TEACHER, # Robot behavior service acts as Zoro (Teacher)
                # We can't pass system_prompt directly through VoiceQueryRequest 
                # as it currently uses predefined system prompts based on user_role.
                # However, for Robot behavior, we might need a custom route or 
                # a modification to the orchestrator to accept a transient system prompt.
            )
            
            # For now, we process it normally
            logger.info(f"Zoro thinking: {user_message[:50]}...")
            response = await self._orchestrator.process_request(req)
            
            return response.response_text
            
        except Exception as exc:
            logger.error(f"VoiceEventInterface.send_text_prompt failed: {exc}")
            return "I am sorry, I am having trouble thinking right now."

    async def announce(self, text: str):
        """
        Trigger the robot to say something immediately (TTS only).
        """
        # This could be implemented by calling the TTS service directly
        # and sending the result to a speaker or a WebSocket client.
        logger.info(f"Zoro announcing: {text}")
        # Implementation depends on how Zoro's speaker is connected

