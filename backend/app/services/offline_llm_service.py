"""
services/offline_llm_service.py — Local LLM fallback using llama-cpp-python.

Optimised for Raspberry Pi Zero 2 W constraints:
  • 4-thread inference
  • 2 GB RAM ceiling → Q4 quantised models only
  • Pre-loaded at startup (no cold-start penalty)
  • Short context (2048 tokens)
  • Built-in Tamil canned responses for common queries
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from app.core.config import settings
from app.schemas import Language, UserRole

logger = logging.getLogger("voice_agent.offline_llm")

# ── Try to import llama_cpp ───────────────────────────────────────────────────
try:
    from llama_cpp import Llama  # type: ignore
    LLAMA_AVAILABLE = True
except ImportError:
    LLAMA_AVAILABLE = False
    logger.warning("llama-cpp-python not installed. Offline LLM will use canned responses only.")


# ─────────────────────────────────────────────────────────────────────────────
# Canned responses (ultra-fast, zero inference needed)
# ─────────────────────────────────────────────────────────────────────────────

CANNED_EN = {
    "greeting": "Hello! I'm your classroom assistant. How can I help you today?",
    "no_internet": "I'm running in offline mode right now. I can answer basic questions, but attendance data may not be current.",
    "attendance_unknown": "I don't have live attendance data right now. Please check with your teacher.",
    "fallback": "I'm sorry, I didn't understand that. Could you please repeat?",
    "period_not_found": "I couldn't find that period in my records.",
    "student_not_found": "I couldn't find that student. Please check the name and try again.",
    "goodbye": "Thank you! Have a great class!",
}

CANNED_TA = {
    "greeting": "வணக்கம்! நான் உங்கள் வகுப்பறை உதவியாளர். என்ன உதவி வேண்டும்?",
    "no_internet": "இப்போது offline mode-ல் இருக்கேன். அடிப்படை கேள்விகளுக்கு பதில் சொல்ல முடியும்.",
    "attendance_unknown": "இப்போது வருகை பதிவு கிடைக்கவில்லை. ஆசிரியரிடம் கேளுங்கள்.",
    "fallback": "மன்னிக்கவும், புரியவில்லை. மீண்டும் சொல்லுங்கள்.",
    "period_not_found": "அந்த period கிடைக்கவில்லை.",
    "student_not_found": "அந்த மாணவர் பதிவு கிடைக்கவில்லை.",
    "goodbye": "நன்றி! நல்ல வகுப்பு கிடைக்கட்டும்!",
}

CANNED_MIXED = {
    "greeting": "Hello! Classroom assistant இங்கே. என்ன help வேண்டும்?",
    "no_internet": "Offline mode-ல் இருக்கேன். Basic questions மட்டும் answer பண்ண முடியும்.",
    "attendance_unknown": "Attendance data இப்போது இல்லை. Teacher-கிட்ட கேளுங்க.",
    "fallback": "Sorry, puriyaley. Repeat பண்றீங்களா?",
    "goodbye": "Thank you! Have a good day!",
}


def get_canned(key: str, language: Language) -> str:
    if language == Language.TAMIL:
        return CANNED_TA.get(key, CANNED_EN.get(key, ""))
    if language == Language.MIXED:
        return CANNED_MIXED.get(key, CANNED_EN.get(key, ""))
    return CANNED_EN.get(key, "")


# ─────────────────────────────────────────────────────────────────────────────
# Offline intent classifier (regex-based, zero-latency)
# ─────────────────────────────────────────────────────────────────────────────

INTENT_PATTERNS = [
    ("attendance_query_self",    r"\b(my|en|ennoda)\s+(attendance|varul|hajar)\b"),
    ("attendance_query_student", r"\b(who|yaar|யார்)\s+(is|absent|present)\b"),
    ("attendance_query_class",   r"\b(class|section|vakkup)\s+(attendance|present|absent)\b"),
    ("greeting",                 r"^\s*(hello|hi|vanakkam|வணக்கம்|hey|good\s+morning)\b"),
    ("goodbye",                  r"\b(bye|goodbye|thank|nandri|நன்றி)\b"),
    ("period_query",             r"\b(period|class|hour)\s*\d+\b"),
    ("summary_query",            r"\b(summary|today|innu|inniku|இன்று)\b"),
]


def classify_intent(text: str) -> str:
    """Returns intent string or 'unknown'."""
    lower = text.lower()
    for intent, pattern in INTENT_PATTERNS:
        if re.search(pattern, lower, re.IGNORECASE | re.UNICODE):
            return intent
    return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# System prompts for offline LLM
# ─────────────────────────────────────────────────────────────────────────────

OFFLINE_SYSTEM_EN = """You are a classroom robot assistant running in offline mode.
You cannot access the database right now.
Keep all responses under 30 words.
Be helpful, warm, and honest about your limitations.
Do not make up attendance data."""

OFFLINE_SYSTEM_TA = """நீ offline mode-ல் இயங்கும் வகுப்பறை ரோபோ உதவியாளர்.
தரவுத்தளத்தை அணுக முடியாது.
20 வார்த்தைகளுக்கு கீழ் மட்டுமே பதில் சொல்.
தவறான வருகை தகவல் சொல்லாதே."""


# ─────────────────────────────────────────────────────────────────────────────
# Offline LLM Service
# ─────────────────────────────────────────────────────────────────────────────

class OfflineLLMService:
    """
    Local LLM inference using llama-cpp-python.

    Fallback chain:
      1. Intent classifier (instant, regex)
      2. Canned response (instant)
      3. llama.cpp inference (1-5 seconds on Pi Zero 2 W)
    """

    def __init__(self):
        self._llm: Optional[Any] = None
        self._loaded = False
        self._load_error: Optional[str] = None

    def load_model(self):
        """Load model into memory. Call once at startup."""
        if not settings.OFFLINE_LLM_ENABLED:
            logger.info("Offline LLM disabled in config")
            return

        if not LLAMA_AVAILABLE:
            self._load_error = "llama-cpp-python not installed"
            logger.warning(self._load_error)
            return

        import os
        if not os.path.exists(settings.OFFLINE_LLM_MODEL_PATH):
            self._load_error = f"Model not found: {settings.OFFLINE_LLM_MODEL_PATH}"
            logger.warning(self._load_error)
            return

        try:
            logger.info("Loading offline LLM: %s", settings.OFFLINE_LLM_MODEL_PATH)
            t0 = time.perf_counter()
            self._llm = Llama(
                model_path=settings.OFFLINE_LLM_MODEL_PATH,
                n_ctx=settings.OFFLINE_LLM_N_CTX,
                n_threads=settings.OFFLINE_LLM_N_THREADS,
                n_gpu_layers=0,          # Pi Zero 2W has no GPU
                verbose=False,
                use_mlock=True,          # lock model in RAM
                use_mmap=True,
            )
            elapsed = time.perf_counter() - t0
            logger.info("Offline LLM loaded in %.1fs", elapsed)
            self._loaded = True
        except Exception as e:
            self._load_error = str(e)
            logger.exception("Failed to load offline LLM: %s", e)

    @property
    def is_ready(self) -> bool:
        return self._loaded and self._llm is not None

    def _build_prompt(
        self,
        user_text: str,
        system_prompt: str,
        history: List[Dict[str, str]],
    ) -> str:
        """Build Phi-3 / Mistral instruct prompt."""
        lines = [f"<|system|>\n{system_prompt}\n<|end|>"]
        for msg in history[-4:]:   # last 4 turns max (Pi memory constraint)
            role = "user" if msg["role"] == "user" else "assistant"
            lines.append(f"<|{role}|>\n{msg['content']}\n<|end|>")
        lines.append(f"<|user|>\n{user_text}\n<|end|>")
        lines.append("<|assistant|>")
        return "\n".join(lines)

    def _infer_sync(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float = 0.3,
    ) -> str:
        """Run synchronous llama.cpp inference."""
        if not self.is_ready:
            return ""
        try:
            output = self._llm(
                prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                stop=["<|end|>", "<|user|>", "\n\n\n"],
                echo=False,
            )
            return output["choices"][0]["text"].strip()
        except Exception as e:
            logger.exception("Offline LLM inference error: %s", e)
            return ""

    async def generate(
        self,
        user_text: str,
        language: Language = Language.ENGLISH,
        user_role: UserRole = UserRole.STUDENT,
        history: Optional[List[Dict[str, str]]] = None,
        tool_context: Optional[Dict] = None,
    ) -> str:
        """
        Generate a response using the fallback chain:
        1. Canned response if intent matches
        2. llama.cpp if loaded
        3. Hardcoded fallback message
        """
        intent = classify_intent(user_text)
        logger.info("Offline intent: %s | lang: %s", intent, language)

        # Fast path: canned responses
        if intent == "greeting":
            return get_canned("greeting", language)
        if intent == "goodbye":
            return get_canned("goodbye", language)
        if intent in ("attendance_query_self", "attendance_query_student", "attendance_query_class"):
            if tool_context:
                # Summarise pre-fetched tool context if available
                return self._format_attendance_response(tool_context, language)
            return get_canned("attendance_unknown", language)

        # LLM path
        if self.is_ready:
            sys_prompt = OFFLINE_SYSTEM_TA if language == Language.TAMIL else OFFLINE_SYSTEM_EN

            context_note = ""
            if tool_context and tool_context.get("found"):
                context_note = f"\n\nContext data: {json.dumps(tool_context, default=str)[:400]}"

            prompt = self._build_prompt(
                user_text + context_note,
                sys_prompt,
                history or [],
            )
            t0 = time.perf_counter()
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(
                None,
                self._infer_sync,
                prompt,
                settings.OFFLINE_LLM_MAX_TOKENS,
                0.3,
            )
            elapsed = int((time.perf_counter() - t0) * 1000)
            logger.info("Offline LLM inference: %dms → '%s'", elapsed, text[:60])
            if text:
                return text

        # Final fallback
        return get_canned("fallback", language)

    async def stream_generate(
        self,
        user_text: str,
        language: Language = Language.ENGLISH,
        user_role: UserRole = UserRole.STUDENT,
        history: Optional[List[Dict[str, str]]] = None,
        tool_context: Optional[Dict] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Streaming wrapper — generates full response then yields word by word.
        (llama-cpp streaming is CPU-intensive; word-by-word gives TTS head-start.)
        """
        text = await self.generate(user_text, language, user_role, history, tool_context)
        words = text.split()
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
            await asyncio.sleep(0)

    def _format_attendance_response(
        self, data: Dict, language: Language
    ) -> str:
        """Format attendance data dict into a short voice-friendly string."""
        if not data.get("found"):
            return get_canned("attendance_unknown", language)

        name = data.get("student_name", "")
        pct = data.get("percentage", 0)
        present = data.get("present_count", 0)
        total = data.get("total_periods", 0)

        if language == Language.TAMIL:
            return (
                f"{name} இன்று {present} பீரியட்டில் வந்தார். "
                f"மொத்தம் {total} பீரியட்டில் {pct} சதவீதம்."
            )
        if language == Language.MIXED:
            return (
                f"{name} இன்று {present} out of {total} periods present. "
                f"Attendance {pct} percent."
            )
        return (
            f"{name} is present for {present} out of {total} periods today, "
            f"giving an attendance rate of {pct} percent."
        )


# ── Module-level singleton ─────────────────────────────────────────────────────
offline_llm = OfflineLLMService()
