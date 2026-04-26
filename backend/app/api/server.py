"""
api/server.py
==============
Zoro Robot — Unified FastAPI Service
Exposes all endpoints from both v1 and v2 systems.

Endpoints
─────────
POST /ingest              Load, chunk, embed, index documents
GET  /health              System health + index stats
GET  /stats               Detailed stats
POST /ask                 Full 7-agent pipeline (FULL mode)
POST /ask/fast            Direct retrieval + prompt (FAST / v1 mode)
POST /ask/stream          Streaming pipeline (NDJSON events)
POST /analyze             Agent 1 only — intent classification
POST /retrieve            Agents 1–3 — retrieve + rerank, no LLM
POST /context             v1 compat — raw retrieved context block
POST /memory/update       Update student interaction memory
"""

from __future__ import annotations

import json
import logging
import os
from typing import AsyncIterator, Optional

from app.core.llm_caller import get_llm_caller
from app.core.orchestrator import ZoroOrchestrator
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.schemas.contracts import (
    ClassroomContext,
    Difficulty,
    PipelineMode,
    StudentProfile,
    TeachingMode,
)

logger = logging.getLogger("zoro.server")

app = FastAPI(
    title="Zoro Unified Knowledge API",
    description="Single-agent (fast) + 7-agent (full) RAG pipeline for classroom robot Zoro",
    version="3.0.0",
)

# ── Singleton orchestrator ────────────────────────────────────
_orch: Optional[ZoroOrchestrator] = None


def get_orch() -> ZoroOrchestrator:
    global _orch
    if _orch is None:
        _orch = ZoroOrchestrator(
            index_path=os.getenv("ZORO_INDEX_PATH", "data/zoro_index"),
            memory_path=os.getenv("ZORO_MEMORY_PATH", "data/student_memory"),
            embed_model=os.getenv("ZORO_EMBED_MODEL", "all-MiniLM-L6-v2"),
            use_fallback=os.getenv("ZORO_FALLBACK", "0") == "1",
            use_cache=True,
            llm_caller=get_llm_caller(),  # auto-selects Gemini → Ollama → Echo
        )
    return _orch


# ═════════════════════════════════════════════════════════════
# PYDANTIC SCHEMAS  (API request/response models)
# ═════════════════════════════════════════════════════════════


class StudentIn(BaseModel):
    student_id: str = "anon"
    name: str = "Student"
    grade: int = 8
    section: str = "A"
    level: str = "medium"
    language: str = "en"
    weak_topics: list[str] = []
    strong_topics: list[str] = []


class AskRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=600)
    subject: str = ""
    topic: str = ""
    current_lesson: str = ""
    class_section: str = ""
    mode: str = "explain"
    top_k: int = Field(default=5, ge=1, le=10)
    student: StudentIn = Field(default_factory=StudentIn)
    use_cache: bool = True


class IngestRequest(BaseModel):
    source_path: str


class MemoryUpdateRequest(BaseModel):
    student_id: str
    topic: str
    was_wrong: bool = False


# ═════════════════════════════════════════════════════════════
# HELPERS
# ═════════════════════════════════════════════════════════════


def _ctx(
    req: AskRequest, pipeline_mode: PipelineMode = PipelineMode.FULL
) -> ClassroomContext:
    level_map = {
        "easy": Difficulty.EASY,
        "medium": Difficulty.MEDIUM,
        "hard": Difficulty.HARD,
    }
    mode_map = {m.value: m for m in TeachingMode}
    profile = StudentProfile(
        student_id=req.student.student_id,
        name=req.student.name,
        grade=req.student.grade,
        section=req.student.section,
        level=level_map.get(req.student.level, Difficulty.MEDIUM),
        language=req.student.language,
        weak_topics=req.student.weak_topics,
        strong_topics=req.student.strong_topics,
    )
    return ClassroomContext(
        subject=req.subject,
        topic=req.topic,
        current_lesson=req.current_lesson,
        class_section=req.class_section,
        mode=mode_map.get(req.mode, TeachingMode.EXPLAIN),
        student=profile,
        pipeline_mode=pipeline_mode,
    )


def _serialize(response) -> dict:
    return {
        "query_id": response.query_id,
        "answer": response.answer,
        "sources": response.sources,
        "mode": response.mode,
        "intent": response.intent,
        "subject": response.subject,
        "difficulty": response.difficulty,
        "chunks_used": response.chunks_used,
        "total_ms": response.total_time_ms,
        "trace": response.pipeline_trace,
        "safety": response.safety_status,
        "follow_up": response.follow_up_question,
        "pipeline_mode": response.pipeline_mode,
        "system_prompt": response.prompt.get("system", ""),
        "user_prompt": response.prompt.get("user", ""),
        "context_text": response.context_text,
    }


# ═════════════════════════════════════════════════════════════
# ENDPOINTS
# ═════════════════════════════════════════════════════════════


@app.get("/health")
async def health():
    return {"status": "ok", **get_orch().get_stats()}


@app.get("/stats")
async def stats():
    return get_orch().get_stats()


@app.post("/ingest")
async def ingest(req: IngestRequest):
    result = await get_orch().ingest_documents(req.source_path)
    return {
        "status": result.status,
        "docs_loaded": result.docs_loaded,
        "chunks_created": result.chunks_created,
        "time_seconds": result.time_seconds,
    }


@app.post("/ask")
async def ask(req: AskRequest):
    """Full 7-agent pipeline (FULL mode). Best quality."""
    ctx = _ctx(req, PipelineMode.FULL)
    response = await get_orch().process(req.query, ctx, req.top_k, req.use_cache)
    return _serialize(response)


@app.post("/ask/fast")
async def ask_fast(req: AskRequest):
    """
    Direct single-agent retrieval + prompt (FAST / v1 mode).
    ~30ms. Use for simple factual questions or Pi Zero constrained environments.
    """
    ctx = _ctx(req, PipelineMode.FAST)
    response = await get_orch().process(req.query, ctx, req.top_k, req.use_cache)
    return _serialize(response)


@app.post("/ask/stream")
async def ask_stream(req: AskRequest):
    """Streaming 7-agent pipeline. Yields NDJSON events per stage."""
    ctx = _ctx(req, PipelineMode.FULL)

    async def gen() -> AsyncIterator[str]:
        async for event in get_orch().stream_process(req.query, ctx, req.top_k):
            yield json.dumps(event) + "\n"

    return StreamingResponse(gen(), media_type="application/x-ndjson")


@app.post("/analyze")
async def analyze(req: AskRequest):
    """Agent 1 only — intent classification. No retrieval."""
    from schemas.contracts import RawQuery

    ctx = _ctx(req)
    raw = RawQuery(text=req.query, context=ctx)
    intent = get_orch().query_agent.analyze(raw)
    return {
        "subject": intent.classified_subject.value,
        "intent": intent.intent.value,
        "difficulty": intent.difficulty.value,
        "keywords": intent.keywords,
        "reformulated": intent.reformulated_query,
        "is_off_topic": intent.is_off_topic,
        "confidence": intent.confidence,
    }


@app.post("/retrieve")
async def retrieve(req: AskRequest):
    """Agents 1–3: retrieve + rerank. No LLM call. Inspect ranked chunks."""
    from schemas.contracts import RawQuery, RetrievalRequest

    ctx = _ctx(req)
    raw = RawQuery(text=req.query, context=ctx)
    orch = get_orch()
    intent = orch.query_agent.analyze(raw)

    request = RetrievalRequest(
        query=intent.reformulated_query,
        subject=intent.classified_subject.value,
        grade=ctx.student.grade,
        top_k=req.top_k,
    )
    retrieved = await orch.retriever.retrieve_async(intent, request)
    reranked = orch.reranker.rerank(retrieved, intent, ctx.student.grade)

    return {
        "query": req.query,
        "reformulated": intent.reformulated_query,
        "chunks": [
            {
                "rank": rc.rank,
                "source": rc.chunk.source,
                "subject": rc.chunk.subject,
                "grade": rc.chunk.grade,
                "score": round(rc.final_score, 4),
                "preview": rc.chunk.text[:150],
            }
            for rc in reranked.ranked_chunks
        ],
        "retrieval_ms": round(retrieved.retrieval_time_ms, 1),
        "rerank_ms": round(reranked.rerank_time_ms, 1),
    }


@app.post("/context")
async def context_only(req: AskRequest):
    """
    v1 compatibility endpoint.
    Returns raw retrieved context block + LLM-ready prompt.
    Same as /ask/fast but exposes context_text prominently.
    """
    ctx = _ctx(req, PipelineMode.FAST)
    response = await get_orch().process(req.query, ctx, req.top_k, req.use_cache)
    return {
        "query": req.query,
        "context_text": response.context_text,
        "system_prompt": response.prompt.get("system", ""),
        "user_prompt": response.prompt.get("user", ""),
        "sources": response.sources,
        "retrieval_ms": response.pipeline_trace.get("retrieve_ms", 0),
    }


@app.post("/memory/update")
async def memory_update(req: MemoryUpdateRequest):
    get_orch().personalizer.update_memory(
        req.student_id, {"topic": req.topic, "was_wrong": req.was_wrong}
    )
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.server:app", host="0.0.0.0", port=8765, reload=False, log_level="info"
    )

