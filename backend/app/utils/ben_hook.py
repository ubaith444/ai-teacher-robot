"""
utils/zoro_hook.py
==================
Zoro Robot — Unified Pi Zero Integration Hook
Lightweight HTTP client for Zoro's main controller.

Supports both pipeline modes transparently:
  zoro_ask(query, ctx)              → FULL 7-agent pipeline (default)
  zoro_ask(query, ctx, fast=True)   → FAST direct retrieval (~30ms)

Usage after STT transcription:
    text = await stt.transcribe(audio)
    ctx  = ZoroContext(subject="Science", grade=8, mode="explain")
    resp = await zoro_ask(text, ctx)
    if resp.ok:
        await tts.speak(resp.answer)          # server called LLM
        # or:
        llm_out = await call_llm(resp.system_prompt, resp.user_prompt)
        await tts.speak(llm_out)              # Pi calls LLM itself
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

import httpx

logger = logging.getLogger("zoro.hook")

ZORO_API = "http://localhost:8765"  # set to your server IP
TIMEOUT = 10.0


# ═════════════════════════════════════════════════════════════
# INPUT / OUTPUT TYPES
# ═════════════════════════════════════════════════════════════


@dataclass
class ZoroContext:
    subject: str = ""
    topic: str = ""
    current_lesson: str = ""
    mode: str = "explain"  # explain|hint|quiz|summary|socratic|stepwise
    student_id: str = "anon"
    student_name: str = "Student"
    grade: int = 8
    level: str = "medium"  # easy|medium|hard
    language: str = "en"
    weak_topics: list[str] = field(default_factory=list)


@dataclass
class ZoroResponse:
    answer: str
    system_prompt: str
    user_prompt: str
    context_text: str  # raw retrieved context (v1 compat)
    sources: list[str]
    mode: str
    intent: str
    subject: str
    total_ms: float
    follow_up: str = ""
    pipeline_mode: str = "full"
    safety: str = "approved"
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


# ═════════════════════════════════════════════════════════════
# MAIN HOOK
# ═════════════════════════════════════════════════════════════


async def zoro_ask(
    transcribed_text: str,
    ctx: Optional[ZoroContext] = None,
    top_k: int = 5,
    fast: bool = False,
) -> ZoroResponse:
    """
    Primary integration hook for Zoro's controller.

    fast=False (default): full 7-agent pipeline — best quality
    fast=True:            direct retrieval — ~30ms, ideal for Pi Zero
    """
    if not transcribed_text or len(transcribed_text.strip()) < 2:
        return _empty_response("Query too short or empty")

    endpoint = "/ask/fast" if fast else "/ask"
    payload = _build_payload(transcribed_text, ctx, top_k)

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(f"{ZORO_API}{endpoint}", json=payload)
            r.raise_for_status()
            data = r.json()

        return ZoroResponse(
            answer=data.get("answer", ""),
            system_prompt=data.get("system_prompt", ""),
            user_prompt=data.get("user_prompt", ""),
            context_text=data.get("context_text", ""),
            sources=data.get("sources", []),
            mode=data.get("mode", "explain"),
            intent=data.get("intent", "unknown"),
            subject=data.get("subject", ""),
            total_ms=data.get("total_ms", 0.0),
            follow_up=data.get("follow_up", ""),
            pipeline_mode=data.get("pipeline_mode", "full" if not fast else "fast"),
            safety=data.get("safety", "approved"),
        )

    except httpx.TimeoutException:
        logger.warning("Server timeout — using fallback")
        return _fallback(transcribed_text, ctx)
    except Exception as e:
        logger.error(f"zoro_ask error: {e}")
        return _empty_response(str(e))


async def zoro_ingest(source_path: str, timeout: float = 120.0) -> dict:
    """Trigger ingestion of new documents (teacher uploads)."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(f"{ZORO_API}/ingest", json={"source_path": source_path})
        r.raise_for_status()
        return r.json()


async def zoro_stream(
    transcribed_text: str,
    ctx: Optional[ZoroContext] = None,
    top_k: int = 5,
):
    """
    Streaming query — yields stage events as dicts.
    Zoro can say "Searching notes..." before the full answer arrives.

    Usage:
        async for event in zoro_stream(text, ctx):
            stage = event["stage"]
            if stage == "intent":
                await tts.speak("Let me check my notes...")
            elif stage == "final":
                await tts.speak(event["data"]["answer"])
    """
    payload = _build_payload(transcribed_text, ctx, top_k)
    import json as _json

    async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream("POST", f"{ZORO_API}/ask/stream", json=payload) as r:
            async for line in r.aiter_lines():
                if line.strip():
                    yield _json.loads(line)


# ═════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════


def _build_payload(query: str, ctx: Optional[ZoroContext], top_k: int) -> dict:
    return {
        "query": query.strip(),
        "subject": ctx.subject if ctx else "",
        "topic": ctx.topic if ctx else "",
        "current_lesson": ctx.current_lesson if ctx else "",
        "mode": ctx.mode if ctx else "explain",
        "top_k": top_k,
        "student": {
            "student_id": ctx.student_id if ctx else "anon",
            "name": ctx.student_name if ctx else "Student",
            "grade": ctx.grade if ctx else 8,
            "level": ctx.level if ctx else "medium",
            "language": ctx.language if ctx else "en",
            "weak_topics": ctx.weak_topics if ctx else [],
        },
    }


def _fallback(query: str, ctx: Optional[ZoroContext]) -> ZoroResponse:
    system = (
        "You are Zoro, a calm classroom robot teacher assistant. "
        "Answer the student's question clearly and encouragingly. "
        "Keep it short and classroom-appropriate."
    )
    user = f"Student question: {query}"
    return ZoroResponse(
        answer="",
        system_prompt=system,
        user_prompt=user,
        context_text="",
        sources=[],
        mode=ctx.mode if ctx else "explain",
        intent="unknown",
        subject=ctx.subject if ctx else "",
        total_ms=0.0,
        pipeline_mode="fast",
    )


def _empty_response(error: str) -> ZoroResponse:
    return ZoroResponse(
        answer="I didn't catch that. Could you repeat the question?",
        system_prompt="",
        user_prompt="",
        context_text="",
        sources=[],
        mode="explain",
        intent="unknown",
        subject="",
        total_ms=0.0,
        error=error,
    )


# ═════════════════════════════════════════════════════════════
# SMOKE TEST
# ═════════════════════════════════════════════════════════════

if __name__ == "__main__":

    async def _test():
        ctx = ZoroContext(
            subject="Science",
            topic="Photosynthesis",
            grade=8,
            level="medium",
            mode="explain",
        )
        print("=== FULL pipeline ===")
        r = await zoro_ask("How does photosynthesis work?", ctx)
        print(f"ok={r.ok} | mode={r.pipeline_mode} | {r.total_ms:.0f}ms")
        print(f"sources: {r.sources}")
        print(f"follow_up: {r.follow_up}")

        print("\n=== FAST pipeline ===")
        r = await zoro_ask("What is osmosis?", ctx, fast=True)
        print(f"ok={r.ok} | mode={r.pipeline_mode} | {r.total_ms:.0f}ms")

        print("\n=== STREAM ===")
        async for event in zoro_stream("Explain Newton's first law", ctx):
            print(f"  stage={event['stage']}")

    asyncio.run(_test())

