"""
core/llm_caller.py
===================
Zoro Robot — Unified LLM Caller
Provides a single async `llm_caller(system, user)` coroutine that can be
wired directly into ZoroOrchestrator.

Backends (checked in priority order):
  1. Google Gemini (cascades: 2.0-flash -> 1.5-flash -> 1.5-pro)
  2. Ollama local model                — via HTTP REST (optional)
  3. Echo stub                         — always available; structured offline answer

All configuration is read from environment variables or the .env file;
no secrets are ever hard-coded here.

Environment variables
---------------------
GEMINI_API_KEY        Your Google AI Studio key            (required for Gemini)
GEMINI_MODEL          Primary model name                   (default: gemini-2.0-flash)
GEMINI_TIMEOUT_S      Per-request timeout in seconds       (default: 15)
GEMINI_MAX_TOKENS     Maximum output tokens                (default: 512)
GEMINI_TEMPERATURE    Sampling temperature                 (default: 0.7)

ZORO_LLM_BACKEND       Override backend: gemini | ollama | echo
OLLAMA_URL            Base URL for Ollama                  (default: http://localhost:11434)
OLLAMA_MODEL          Ollama model to use                  (default: mistral)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("zoro.llm")


# ── Load .env once at import time ─────────────────────────────────────────
def _load_env():
    """Load .env from project root."""
    env_path = Path(__file__).parent.parent.parent.parent / ".env"
    if not env_path.exists():
        env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_path, override=False)
            logger.debug(f"Loaded .env from {env_path}")
        except ImportError:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env()


# =============================================================
# GEMINI BACKEND
# =============================================================

class GeminiCaller:
    """
    Wraps google-genai SDK.

    On 429 / RESOURCE_EXHAUSTED, cascades through:
        gemini-2.0-flash  ->  gemini-1.5-flash  ->  gemini-1.5-pro

    Each model gets one automatic retry with the suggested retry-delay
    from the error body before cascading to the next model.
    """

    # Cascade order: fastest free-tier first, then lite fallback, then 2.5 capable
    MODEL_CASCADE = [
        "gemini-2.0-flash",       # primary: fastest, free-tier
        "gemini-2.0-flash-lite",  # lighter quota, same generation
        "gemini-2.5-flash",       # most capable, if quota allows
    ]
    DEFAULT_RETRY_WAIT = 2.0   # seconds between retry attempts
    MAX_RETRY_WAIT     = 15.0  # cap on extracted retry-delay

    def __init__(self):
        self.api_key     = os.getenv("GEMINI_API_KEY", "")
        self.model_name  = os.getenv("GEMINI_MODEL", self.MODEL_CASCADE[0])
        self.timeout     = float(os.getenv("GEMINI_TIMEOUT_S",    "15"))
        self.max_tokens  = int(os.getenv("GEMINI_MAX_TOKENS",     "512"))
        self.temperature = float(os.getenv("GEMINI_TEMPERATURE",  "0.7"))
        self._client     = None
        self._ready      = False
        self._init()

    def _init(self):
        if not self.api_key:
            logger.warning("GEMINI_API_KEY not set — Gemini backend disabled.")
            return
        try:
            from google import genai
            self._client = genai.Client(api_key=self.api_key)
            self._ready  = True
            logger.info(
                f"Gemini ready | primary={self.model_name} "
                f"| cascade={' -> '.join(self.MODEL_CASCADE)}"
            )
        except ImportError:
            logger.warning("google-genai not installed; run: pip install google-genai")
        except Exception as e:
            logger.error(f"Gemini init failed: {e}")

    @property
    def available(self) -> bool:
        return self._ready

    async def call(self, system_prompt: str, user_prompt: str) -> str:
        if not self._ready or not self._client:
            raise RuntimeError("Gemini backend not ready.")

        combined = f"{system_prompt}\n\n---\n\n{user_prompt}"
        loop     = asyncio.get_event_loop()

        # Build cascade list starting from the configured model
        start   = self.MODEL_CASCADE.index(self.model_name) \
                  if self.model_name in self.MODEL_CASCADE else 0
        cascade = self.MODEL_CASCADE[start:] + self.MODEL_CASCADE[:start]

        last_err: Exception | None = None

        for model in cascade:
            for attempt in range(2):          # 2 attempts per model
                t0 = time.perf_counter()
                try:
                    result = await asyncio.wait_for(
                        loop.run_in_executor(
                            None, self._sync_generate, model, combined
                        ),
                        timeout=self.timeout + 5,
                    )
                    ms = (time.perf_counter() - t0) * 1000
                    logger.info(
                        f"Gemini [{model}] OK in {ms:.0f}ms (attempt {attempt+1})"
                    )
                    return result.strip()

                except asyncio.TimeoutError as e:
                    logger.warning(f"Gemini [{model}] timed out after {self.timeout}s")
                    last_err = e
                    break   # cascade immediately

                except Exception as e:
                    err_str = str(e)
                    is_quota = (
                        "429"                in err_str or
                        "RESOURCE_EXHAUSTED" in err_str or
                        "quota"              in err_str.lower()
                    )
                    # Detect daily limit — no point sleeping; cascade immediately
                    is_daily = (
                        "PerDay"    in err_str or
                        "limit: 0," in err_str  # "limit: 0, model: ..." means 0 remaining
                    )
                    if is_quota and attempt == 0 and not is_daily:
                        wait = self._parse_retry_delay(err_str)
                        logger.warning(
                            f"Gemini [{model}] rate-limited (RPM) — "
                            f"retry in {wait:.1f}s..."
                        )
                        await asyncio.sleep(wait)
                        continue   # retry same model once
                    else:
                        action = "daily quota — cascading" if is_daily else (
                            "cascading" if is_quota else "error — skipping"
                        )
                        logger.warning(f"Gemini [{model}] failed ({action}): {type(e).__name__}")
                        last_err = e
                        break  # move to next model

        raise RuntimeError(
            f"All Gemini models quota-exhausted or failed: {last_err}"
        )

    def _sync_generate(self, model: str, prompt: str) -> str:
        from google import genai
        from google.genai import types

        response = self._client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_tokens,
                safety_settings=[
                    types.SafetySetting(
                        category="HARM_CATEGORY_HARASSMENT",
                        threshold="BLOCK_MEDIUM_AND_ABOVE",
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_HATE_SPEECH",
                        threshold="BLOCK_MEDIUM_AND_ABOVE",
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                        threshold="BLOCK_ONLY_HIGH",
                    ),
                    types.SafetySetting(
                        category="HARM_CATEGORY_DANGEROUS_CONTENT",
                        threshold="BLOCK_MEDIUM_AND_ABOVE",
                    ),
                ],
            ),
        )
        try:
            return response.text or ""
        except Exception:
            return (
                "I am not able to answer that question in the classroom setting. "
                "Please ask your teacher directly."
            )

    def _parse_retry_delay(self, err_msg: str) -> float:
        """Extract `retryDelay: Xs` from the 429 body if present."""
        m = re.search(r"retryDelay['\"]?\s*:\s*['\"]?(\d+(?:\.\d+)?)", err_msg)
        if m:
            return min(float(m.group(1)) + 0.5, self.MAX_RETRY_WAIT)
        return self.DEFAULT_RETRY_WAIT


# =============================================================
# OLLAMA BACKEND (optional local LLM)
# =============================================================

class OllamaCaller:
    """
    Calls a locally running Ollama instance via REST.
    Install: https://ollama.com  then: ollama pull mistral
    """

    def __init__(self):
        self.url   = os.getenv("OLLAMA_URL",   "http://localhost:11434")
        self.model = os.getenv("OLLAMA_MODEL", "mistral")
        self._ready = self._check()

    def _check(self) -> bool:
        try:
            import httpx
            r = httpx.get(f"{self.url}/api/tags", timeout=2.0)
            return r.status_code == 200
        except Exception:
            return False

    @property
    def available(self) -> bool:
        return self._ready

    async def call(self, system_prompt: str, user_prompt: str) -> str:
        import httpx
        payload = {
            "model":   self.model,
            "prompt":  f"{system_prompt}\n\n{user_prompt}",
            "stream":  False,
            "options": {"temperature": 0.7, "num_predict": 512},
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{self.url}/api/generate", json=payload)
            r.raise_for_status()
            return r.json().get("response", "").strip()


# =============================================================
# ECHO STUB  — always-available structured offline answer
# =============================================================

class EchoCaller:
    """
    Offline fallback. Synthesises a useful, structured classroom answer
    directly from the retrieved context without any network call.

    Active when:
     - GEMINI_API_KEY is not set
     - Gemini quota is exhausted across all cascade models
     - Running fully offline on Pi Zero
    """

    @property
    def available(self) -> bool:
        return True

    async def call(self, system_prompt: str, user_prompt: str) -> str:
        await asyncio.sleep(0)
        return _format_echo_answer(user_prompt)


def _format_echo_answer(user_prompt: str) -> str:
    """
    Parse the structured prompt produced by TeacherPersonaAgent and
    synthesise a concise, well-formatted classroom answer.
    """
    lines = user_prompt.splitlines()

    # Extract structured fields
    fields: dict = {}
    for line in lines:
        if ":" in line and not line.strip().startswith("Source:"):
            k, _, v = line.partition(":")
            key = k.strip().lower().replace(" ", "_")
            fields[key] = v.strip()

    name     = fields.get("student_name", "Student")
    mode     = fields.get("mode",         "explain")
    question = fields.get("student_question", "")

    # Extract retrieved knowledge block
    context = ""
    if "Retrieved Knowledge:" in user_prompt:
        idx     = user_prompt.index("Retrieved Knowledge:")
        block   = user_prompt[idx + len("Retrieved Knowledge:"):]
        context = block.split("Student Question:")[0].strip()

    # Strip source header lines ("Source: filename.md") and collapse whitespace
    context = re.sub(r"(?m)^Source:.*$", "", context).strip()
    context = re.sub(r"\n{3,}", "\n\n", context)

    # Limit to ~400 words
    words   = context.split()
    excerpt = " ".join(words[:400])
    if len(words) > 400:
        excerpt += " [...]"

    if not excerpt:
        excerpt = (
            f"I don't have enough information about '{question}' in my notes. "
            "Please check your textbook or ask your teacher."
        )

    # Format according to teaching mode
    if mode == "hint":
        body = (
            f"Here is a clue, {name}: look at the keywords in your question. "
            f"What does '{question}' remind you of from today's lesson? "
            "Think about it — you are closer than you think!"
        )
    elif mode == "quiz":
        body = (
            f"Quiz time, {name}!\n\n"
            f"1.  What is the main process described in your notes on this topic?\n"
            f"2.  Where does this process take place?\n\n"
            f"Take your time — I will check your answers when you are ready."
        )
    elif mode == "summary":
        body = f"Here is a quick summary, {name}:\n\n{excerpt}"
    elif mode == "compare":
        body = (
            f"Let us compare, {name}. From your notes:\n\n{excerpt}\n\n"
            f"Can you spot the key differences in what you just read?"
        )
    else:
        # explain / stepwise / default
        body = (
            f"Good question, {name}! Here is what your notes say:\n\n"
            f"{excerpt}\n\n"
            f"Now, can you think of a real-life example that connects to this?"
        )

    offline_note = (
        "\n\n[Offline mode: this answer was built directly from your classroom notes "
        "because the AI service is temporarily unavailable. "
        "Your teacher can provide a more detailed explanation.]"
    )
    return body + offline_note


# =============================================================
# UNIFIED FACTORY
# =============================================================

_gemini: Optional[GeminiCaller] = None
_ollama: Optional[OllamaCaller] = None
_echo = EchoCaller()


def _get_gemini() -> GeminiCaller:
    global _gemini
    if _gemini is None:
        _gemini = GeminiCaller()
    return _gemini


def _get_ollama() -> OllamaCaller:
    global _ollama
    if _ollama is None:
        _ollama = OllamaCaller()
    return _ollama


def get_llm_caller(backend: Optional[str] = None) -> Callable:
    """
    Returns an async `llm_caller(system, user) -> str` ready for ZoroOrchestrator.

    Resolution order:
      ZORO_LLM_BACKEND env  ->  explicit `backend` arg  ->  auto-detect
    Auto-detect: Gemini  ->  Ollama  ->  Echo (offline)
    """
    chosen = (backend or os.getenv("ZORO_LLM_BACKEND", "auto")).lower()

    if chosen == "gemini":  return _get_gemini().call
    if chosen == "ollama":  return _get_ollama().call
    if chosen == "echo":    return _echo.call

    # Auto-detect
    g = _get_gemini()
    if g.available:
        logger.info("LLM auto-select: Gemini (cascade: 2.0-flash -> 1.5-flash -> 2.5-flash)")
        return g.call

    o = _get_ollama()
    if o.available:
        logger.info("LLM auto-select: Ollama")
        return o.call

    logger.warning("LLM auto-select: Echo (offline). Set GEMINI_API_KEY for real answers.")
    return _echo.call


async def call_llm(system_prompt: str, user_prompt: str) -> str:
    """
    Convenience wrapper: call the best available LLM directly.
    Degrades gracefully: Gemini -> Ollama -> Echo (offline structured answer).
    """
    backends = [_get_gemini(), _get_ollama(), _echo]
    for b in backends:
        if b.available:
            try:
                return await b.call(system_prompt, user_prompt)
            except Exception as e:
                logger.warning(f"{type(b).__name__} failed ({type(e).__name__}), cascading...")
    # Final safety net — echo always works
    return _format_echo_answer(user_prompt)

