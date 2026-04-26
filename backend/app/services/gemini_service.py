"""
services/gemini_service.py — Gemini 2.5 Flash integration.

Features:
  • Streaming chat completions
  • Function / tool calling for attendance DB
  • Structured multilingual system prompts
  • Timeout + retry with exponential back-off
  • Language-aware response formatting
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx
from app.core.config import settings
from app.schemas import Language, PipelineMode, UserRole
from app.services.attendance_tool import GEMINI_TOOL_DEFINITIONS, execute_tool

logger = logging.getLogger("voice_agent.gemini")

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# ── System prompts ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT_TEACHER_EN = """You are an intelligent AI assistant for a classroom teacher robot.

ROLE: Help teachers get precise, actionable attendance insights.

CAPABILITIES:
- Query real-time attendance database via provided tools
- Summarise class attendance with professional language
- Flag concerning patterns (chronic absence, late arrival trends)
- Give structured, concise responses (2-4 sentences max for voice)

VOICE OUTPUT RULES:
- Speak naturally as if talking aloud — no markdown, no bullet points
- Use numbers clearly: "seventy-five percent" or "75 percent"
- Say dates naturally: "today", "yesterday", "this Monday"
- Keep responses under 40 words for simple queries, 80 words max

TOOL USE:
- Always call tools before answering attendance questions
- If tool returns no data, say so clearly
- Interpret percentages: <75% = concern, 75-90% = acceptable, >90% = excellent

EXAMPLE RESPONSES:
- "Class 10A has 28 out of 32 students present today, giving an attendance rate of 87.5 percent."
- "Ravi has been absent for 3 periods today. You may want to follow up with his parents."
"""

SYSTEM_PROMPT_STUDENT_TA = """நீ ஒரு அன்பான ஆசிரியர் ரோபோ. மாணவர்களுக்கு எளிமையான தமிழிலும் ஆங்கிலத்திலும் பதில் சொல்.

உன்னால் முடிவது:
- மாணவரின் வருகை பதிவை சொல்ல முடியும்
- எந்த பீரியட்டில் வருகை இல்லை என்று சொல்ல முடியும்

பேச்சு விதிகள்:
- தமிழ் + ஆங்கில கலவையில் பேசு (Tanglish OK)
- குறுகிய பதில்கள் மட்டுமே — 2 வரிகளுக்கு மேல் வேண்டாம்
- எண்களை தமிழில் சொல்: "மூன்று பீரியட்" "தொண்ணூறு சதவீதம்"
- அன்பாக, உற்சாகமாக பேசு

எடுத்துக்காட்டு பதில்கள்:
- "உங்களுக்கு இன்று 4 பீரியட்டில் வருகை உள்ளது, 2 பீரியட்டில் absent ஆ இருந்தீங்க."
- "இன்று attendance 80 percent — நல்லா இருக்கு! நாளை எல்லா class-லயும் வாங்க."
"""

SYSTEM_PROMPT_MIXED = """You are a friendly bilingual classroom robot assistant.
Detect whether the user speaks English, Tamil, or a mix, and respond in the same style.
Be warm, brief, and classroom-appropriate.
Always use tools before answering attendance questions.
Keep all voice responses under 60 words.
"""


def get_system_prompt(user_role: UserRole, language: Language) -> str:
    if user_role == UserRole.TEACHER:
        return SYSTEM_PROMPT_TEACHER_EN
    if language == Language.TAMIL:
        return SYSTEM_PROMPT_STUDENT_TA
    return SYSTEM_PROMPT_MIXED


# ── Gemini client ─────────────────────────────────────────────────────────────

class GeminiService:
    """
    Async Gemini 2.5 Flash client with:
    - Streaming text generation
    - Function calling (tool_use)
    - Automatic tool execution and multi-turn loops
    - Health check
    """

    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self.model = settings.GEMINI_MODEL
        self.timeout = settings.GEMINI_TIMEOUT_S
        self.max_tokens = settings.GEMINI_MAX_TOKENS
        self.temperature = settings.GEMINI_TEMPERATURE
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=GEMINI_BASE_URL,
                timeout=httpx.Timeout(self.timeout, connect=3.0),
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Build request body ─────────────────────────────────────────────────

    def _build_request(
        self,
        messages: List[Dict],
        system_prompt: str,
        enable_tools: bool,
        stream: bool,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": messages,
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
                "candidateCount": 1,
            },
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
        }
        if enable_tools:
            body["tools"] = [{"functionDeclarations": GEMINI_TOOL_DEFINITIONS}]
            body["toolConfig"] = {"functionCallingConfig": {"mode": "AUTO"}}
        return body

    def _convert_history(self, history: List[Dict[str, str]]) -> List[Dict]:
        """Convert simple {role, content} history to Gemini format."""
        gemini_msgs = []
        for h in history:
            role = "model" if h["role"] == "assistant" else "user"
            gemini_msgs.append({"role": role, "parts": [{"text": h["content"]}]})
        return gemini_msgs

    # ── Non-streaming call ─────────────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        system_prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
        enable_tools: bool = True,
        language: Language = Language.ENGLISH,
        user_role: UserRole = UserRole.STUDENT,
    ) -> Tuple[str, List[Dict], int]:
        """
        Full (non-streaming) generation with automatic tool execution loop.

        Returns (final_text, tool_results_list, tokens_used)
        """
        client = await self._get_client()
        messages = self._convert_history(history or [])
        messages.append({"role": "user", "parts": [{"text": prompt}]})

        tool_results_log = []
        max_tool_rounds = 4

        for _round in range(max_tool_rounds):
            body = self._build_request(messages, system_prompt, enable_tools, stream=False)
            url = f"/models/{self.model}:generateContent?key={self.api_key}"

            try:
                resp = await client.post(url, json=body)
                resp.raise_for_status()
                data = resp.json()
            except httpx.TimeoutException:
                raise
            except httpx.HTTPStatusError as e:
                logger.error("Gemini HTTP %s: %s", e.response.status_code, e.response.text[:200])
                raise

            candidate = data["candidates"][0]
            content = candidate["content"]
            parts = content.get("parts", [])
            tokens = data.get("usageMetadata", {}).get("totalTokenCount", 0)

            # Check for function calls
            func_calls = [p for p in parts if "functionCall" in p]
            text_parts = [p["text"] for p in parts if "text" in p]

            if not func_calls:
                return "\n".join(text_parts), tool_results_log, tokens

            # Execute all tool calls in this round
            messages.append({"role": "model", "parts": parts})
            tool_response_parts = []

            for fc_part in func_calls:
                fc = fc_part["functionCall"]
                fn_name = fc["name"]
                fn_args = fc.get("args", {})
                logger.info("Gemini tool call: %s(%s)", fn_name, fn_args)

                result = await execute_tool(fn_name, fn_args)
                tool_results_log.append({"tool": fn_name, "args": fn_args, "result": result})

                tool_response_parts.append({
                    "functionResponse": {
                        "name": fn_name,
                        "response": {"content": json.dumps(result)},
                    }
                })

            messages.append({"role": "user", "parts": tool_response_parts})

        # Exceeded max rounds — return any text accumulated
        return "I encountered an issue processing your request. Please try again.", tool_results_log, 0

    # ── Streaming call ─────────────────────────────────────────────────────

    async def stream_generate(
        self,
        prompt: str,
        system_prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
        enable_tools: bool = True,
        language: Language = Language.ENGLISH,
        user_role: UserRole = UserRole.STUDENT,
    ) -> AsyncGenerator[str, None]:
        """
        Fast non-streaming wrapper.
        """
        RETRY_DELAYS = [2.0, 4.0, 8.0]
        text_out = "I'm sorry, I'm having trouble processing that right now."

        for attempt, delay in enumerate(RETRY_DELAYS + [None]):
            try:
                # Direct call to generate() - we use a longer timeout here
                text_out, _, _ = await asyncio.wait_for(
                    self.generate(prompt, system_prompt, history, enable_tools, language, user_role),
                    timeout=15.0
                )
                if text_out and text_out.strip():
                    break
            except Exception as exc:
                if "429" in str(exc) and delay is not None:
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Gemini error: {exc}")
                    break

        # Safety: if still empty
        if not text_out or not text_out.strip():
            text_out = "I heard you, but I'm unable to answer that specific question. Could you try asking something else?"

        # Stream words out
        for word in text_out.split():
            yield word + " "
            await asyncio.sleep(0.02)


    # ── Language detection ─────────────────────────────────────────────────

    async def detect_language(self, text: str) -> Language:
        """
        Quick heuristic language detection.
        Falls back to a lightweight Gemini call if unsure.
        """
        # Heuristic: Tamil Unicode range U+0B80–U+0BFF
        tamil_chars = sum(1 for c in text if "\u0B80" <= c <= "\u0BFF")
        if tamil_chars > 2:
            return Language.TAMIL
        if tamil_chars > 0:
            return Language.MIXED

        # Tamil transliteration words (common in Tanglish)
        tanglish_words = {
            "enna", "epdi", "yenna", "sollu", "paaru", "vandhaan",
            "irukku", "illai", "nalla", "romba", "konjam",
        }
        lower = text.lower()
        if any(w in lower for w in tanglish_words):
            return Language.MIXED

        return Language.ENGLISH

    # ── Health check ──────────────────────────────────────────────────────

    async def health_check(self) -> Tuple[bool, float]:
        """Returns (is_healthy, latency_ms)."""
        t0 = time.perf_counter()
        try:
            client = await self._get_client()
            body = {
                "contents": [{"role": "user", "parts": [{"text": "Hi"}]}],
                "generationConfig": {"maxOutputTokens": 5},
            }
            url = f"/models/{self.model}:generateContent?key={self.api_key}"
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            latency = (time.perf_counter() - t0) * 1000
            return True, latency
        except Exception as e:
            logger.warning("Gemini health check failed: %s", e)
            return False, (time.perf_counter() - t0) * 1000


# ── Module-level singleton ─────────────────────────────────────────────────────
gemini_service = GeminiService()
