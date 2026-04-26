"""
core/orchestrator.py
=====================
Zoro Robot — Unified Orchestrator
Coordinates the full RAG pipeline in two modes:

  FULL mode  (default)
    7-agent multi-agent pipeline:
    Query → Intent → Retrieve → Rerank → Personalize → Persona → Safety → Compose

  FAST mode  (v1 single-agent path)
    Direct retrieval + prompt build, no reranking or personalization overhead.
    ~30ms end-to-end on Pi Zero. Ideal for simple factual questions.

Both modes return the same FinalResponse object.
The caller selects mode via ClassroomContext.pipeline_mode.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from typing import AsyncIterator, Optional

from app.agents.pipeline_agents import (
    PersonalizationAgent,
    QueryUnderstandingAgent,
    RerankerAgent,
    ResponseComposerAgent,
    RetrieverAgent,
    SafetyPolicyAgent,
    TeacherPersonaAgent,
)
from app.core.document_loader import DocumentChunker, DocumentLoader
from app.core.vector_store import Embedder, VectorStore
from app.schemas.contracts import (
    ClassroomContext,
    FinalResponse,
    IngestionResult,
    PersonalizationDirective,
    PipelineMode,
    RawQuery,
    RetrievalRequest,
)

logger = logging.getLogger("zoro.orchestrator")


# ═════════════════════════════════════════════════════════════
# QUERY CACHE
# ═════════════════════════════════════════════════════════════


class QueryCache:
    def __init__(self, maxsize: int = 256, ttl: int = 300):
        self._store: dict[str, tuple[FinalResponse, float]] = {}
        self.maxsize = maxsize
        self.ttl = ttl

    def _key(
        self, query: str, subject: str, grade: int, mode: str, pipeline_mode: str
    ) -> str:
        raw = f"{query.lower().strip()}|{subject}|{grade}|{mode}|{pipeline_mode}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(
        self, query: str, subject: str, grade: int, mode: str, pipeline_mode: str
    ) -> Optional[FinalResponse]:
        k = self._key(query, subject, grade, mode, pipeline_mode)
        if k in self._store:
            result, ts = self._store[k]
            if time.time() - ts < self.ttl:
                logger.debug("Cache HIT")
                return result
            del self._store[k]
        return None

    def set(
        self,
        query: str,
        subject: str,
        grade: int,
        mode: str,
        pipeline_mode: str,
        result: FinalResponse,
    ):
        if len(self._store) >= self.maxsize:
            oldest = min(self._store, key=lambda k: self._store[k][1])
            del self._store[oldest]
        self._store[self._key(query, subject, grade, mode, pipeline_mode)] = (
            result,
            time.time(),
        )

    def invalidate(self):
        self._store.clear()

    def size(self) -> int:
        return len(self._store)


# ═════════════════════════════════════════════════════════════
# UNIFIED ORCHESTRATOR
# ═════════════════════════════════════════════════════════════


class ZoroOrchestrator:
    """
    Single entry point for Zoro's entire knowledge retrieval system.

    Initialises once; serves all queries via process() or stream_process().
    Handles ingestion, indexing, caching, memory, and both pipeline modes.
    """

    def __init__(
        self,
        index_path: str = "data/zoro_index",
        memory_path: str = "data/student_memory",
        embed_model: str = "all-MiniLM-L6-v2",
        use_fallback: bool = False,
        use_cache: bool = True,
        llm_caller=None,
    ):
        logger.info("Initialising ZoroOrchestrator (unified v1+v2)...")

        # ── Shared infrastructure ──────────────────────────────
        self.embedder = Embedder(model_name=embed_model, fallback=use_fallback)
        self.store = VectorStore(index_path=index_path, fallback=use_fallback)
        self.cache = QueryCache() if use_cache else None

        # ── Agents ────────────────────────────────────────────
        self.query_agent = QueryUnderstandingAgent()
        self.retriever = RetrieverAgent(self.store, self.embedder)
        self.reranker = RerankerAgent()
        self.personalizer = PersonalizationAgent(memory_path=memory_path)
        self.safety = SafetyPolicyAgent()
        self.teacher = TeacherPersonaAgent()
        self.composer = ResponseComposerAgent(llm_caller=llm_caller)

        # ── Ingestion helpers ──────────────────────────────────
        self.loader = DocumentLoader()
        self.chunker = DocumentChunker(min_words=80, max_words=280, overlap_words=30)

        # ── Load existing index ────────────────────────────────
        if self.store.load():
            logger.info(f"Index loaded: {len(self.store.chunks)} chunks")
        else:
            logger.info("No index found. Run ingest_documents() first.")

        logger.info("ZoroOrchestrator ready.")

    # ═══════════════════════════════════════════════════════
    # PUBLIC API
    # ═══════════════════════════════════════════════════════

    async def process(
        self,
        query: str,
        ctx: ClassroomContext,
        top_k: int = 5,
        use_cache: bool = True,
    ) -> FinalResponse:
        """
        Route to FULL (7-agent) or FAST (direct) pipeline based on ctx.pipeline_mode.
        Both return FinalResponse.
        """
        # Cache check
        if use_cache and self.cache:
            cached = self.cache.get(
                query,
                ctx.subject,
                ctx.student.grade,
                ctx.mode.value,
                ctx.pipeline_mode.value,
            )
            if cached:
                return cached

        if ctx.pipeline_mode == PipelineMode.FAST:
            result = await self._fast_pipeline(query, ctx, top_k)
        else:
            result = await self._full_pipeline(query, ctx, top_k)

        if self.cache:
            self.cache.set(
                query,
                ctx.subject,
                ctx.student.grade,
                ctx.mode.value,
                ctx.pipeline_mode.value,
                result,
            )

        # Update student memory
        self.personalizer.update_memory(
            ctx.student.student_id,
            {
                "topic": ctx.topic,
                "subject": ctx.subject,
                "intent": result.intent,
            },
        )

        return result

    async def stream_process(
        self,
        query: str,
        ctx: ClassroomContext,
        top_k: int = 5,
    ) -> AsyncIterator[dict]:
        """
        Yields stage events as NDJSON-ready dicts.
        Available in FULL mode only; falls back to single event in FAST mode.
        """
        if ctx.pipeline_mode == PipelineMode.FAST:
            result = await self._fast_pipeline(query, ctx, top_k)
            yield {"stage": "final", "data": self._response_dict(result)}
            return

        raw = RawQuery(text=query, context=ctx)
        intent = self.query_agent.analyze(raw)
        yield {
            "stage": "intent",
            "data": {
                "subject": intent.classified_subject.value,
                "intent": intent.intent.value,
                "difficulty": intent.difficulty.value,
                "keywords": intent.keywords,
            },
        }

        request = self._build_request(intent, ctx, top_k)
        retrieved = await self.retriever.retrieve_async(intent, request)
        yield {
            "stage": "retrieved",
            "data": {
                "count": len(retrieved.chunks),
                "chunks": [
                    {
                        "source": c.source,
                        "score": c.embedding_score,
                        "preview": c.text[:80],
                    }
                    for c in retrieved.chunks
                ],
            },
        }

        reranked = self.reranker.rerank(retrieved, intent, ctx.student.grade)
        yield {
            "stage": "reranked",
            "data": {
                "top_source": reranked.ranked_chunks[0].chunk.source
                if reranked.ranked_chunks
                else "",
                "top_score": reranked.ranked_chunks[0].final_score
                if reranked.ranked_chunks
                else 0,
            },
        }

        directive = self.personalizer.get_directive(intent, ctx)
        prompt = self.teacher.build_prompt(intent, reranked, directive, ctx)
        yield {
            "stage": "prompt",
            "data": {
                "system_len": len(prompt["system"]),
                "user_len": len(prompt["user"]),
            },
        }

        verdict = self.safety.check("", intent.is_off_topic, ctx.subject)
        response = await self.composer.compose(
            query_id=str(uuid.uuid4())[:8],
            intent=intent,
            retrieved=reranked,
            verdict=verdict,
            prompt=prompt,
            ctx=ctx,
            pipeline_trace={},
            total_start=time.perf_counter(),
        )
        yield {"stage": "final", "data": self._response_dict(response)}

    # ═══════════════════════════════════════════════════════
    # INGESTION
    # ═══════════════════════════════════════════════════════

    async def ingest_documents(self, source_path: str) -> IngestionResult:
        """Load → Chunk → Embed → Index → Save."""
        t0 = time.perf_counter()
        loop = asyncio.get_event_loop()

        raw_docs = await loop.run_in_executor(None, self.loader.load, source_path)
        chunks = await loop.run_in_executor(None, self.chunker.chunk, raw_docs)
        await loop.run_in_executor(None, self.store.build, chunks, self.embedder)

        if self.cache:
            self.cache.invalidate()

        elapsed = round(time.perf_counter() - t0, 2)
        logger.info(
            f"Ingested {len(raw_docs)} docs → {len(chunks)} chunks in {elapsed}s"
        )
        return IngestionResult(
            status="ok",
            docs_loaded=len(raw_docs),
            chunks_created=len(chunks),
            time_seconds=elapsed,
            source_path=source_path,
        )

    # ═══════════════════════════════════════════════════════
    # PIPELINE MODES
    # ═══════════════════════════════════════════════════════

    async def _full_pipeline(
        self, query: str, ctx: ClassroomContext, top_k: int
    ) -> FinalResponse:
        """7-agent pipeline: full reranking + personalization."""
        total_start = time.perf_counter()
        query_id = str(uuid.uuid4())[:8]
        trace: dict[str, float] = {}

        # Agent 1
        t = time.perf_counter()
        raw = RawQuery(text=query, context=ctx, query_id=query_id)
        intent = self.query_agent.analyze(raw)
        trace["query_ms"] = round((time.perf_counter() - t) * 1000, 1)

        # Off-topic early exit
        if intent.is_off_topic:
            verdict = self.safety.check(
                "", is_off_topic=True, subject=ctx.subject or "our lesson"
            )
            return self._off_topic_response(
                query_id, intent, verdict, ctx, trace, total_start
            )

        # Agent 2
        t = time.perf_counter()
        request = self._build_request(intent, ctx, top_k)
        retrieved = await self.retriever.retrieve_async(intent, request)
        trace["retrieve_ms"] = round((time.perf_counter() - t) * 1000, 1)

        # Agent 3
        t = time.perf_counter()
        reranked = self.reranker.rerank(retrieved, intent, ctx.student.grade)
        trace["rerank_ms"] = round((time.perf_counter() - t) * 1000, 1)

        # Agent 4
        t = time.perf_counter()
        directive = self.personalizer.get_directive(intent, ctx)
        trace["personalize_ms"] = round((time.perf_counter() - t) * 1000, 1)

        # Agent 6 (prompt)
        t = time.perf_counter()
        prompt = self.teacher.build_prompt(intent, reranked, directive, ctx)
        trace["prompt_ms"] = round((time.perf_counter() - t) * 1000, 1)

        # Agent 5 (safety)
        verdict = self.safety.check("", intent.is_off_topic, ctx.subject)

        # Agent 7
        t = time.perf_counter()
        response = await self.composer.compose(
            query_id=query_id,
            intent=intent,
            retrieved=reranked,
            verdict=verdict,
            prompt=prompt,
            ctx=ctx,
            pipeline_trace=trace,
            total_start=total_start,
        )
        trace["compose_ms"] = round((time.perf_counter() - t) * 1000, 1)
        trace["total_ms"] = round((time.perf_counter() - total_start) * 1000, 1)
        response.pipeline_trace = trace

        logger.info(
            f"[{query_id}] FULL pipeline {trace['total_ms']}ms | safety={response.safety_status}"
        )
        return response

    async def _fast_pipeline(
        self, query: str, ctx: ClassroomContext, top_k: int
    ) -> FinalResponse:
        """
        v1 direct path: embed → FAISS search → format prompt.
        No reranking, no personalization. ~30ms on Pi Zero.
        """
        total_start = time.perf_counter()
        query_id = str(uuid.uuid4())[:8]
        trace: dict[str, float] = {}

        # Classify (lightweight)
        t = time.perf_counter()
        raw = RawQuery(text=query, context=ctx, query_id=query_id)
        intent = self.query_agent.analyze(raw)
        trace["query_ms"] = round((time.perf_counter() - t) * 1000, 1)

        if intent.is_off_topic:
            verdict = self.safety.check(
                "", is_off_topic=True, subject=ctx.subject or "our lesson"
            )
            return self._off_topic_response(
                query_id, intent, verdict, ctx, trace, total_start
            )

        # Retrieve
        t = time.perf_counter()
        request = self._build_request(intent, ctx, top_k)
        retrieved = await self.retriever.retrieve_async(intent, request)
        trace["retrieve_ms"] = round((time.perf_counter() - t) * 1000, 1)

        # Build prompt with neutral directive (no personalization)
        directive = PersonalizationDirective(
            tone="encouraging",
            depth="moderate",
            language=ctx.student.language,
        )
        prompt = self.teacher.build_prompt(intent, retrieved, directive, ctx)
        verdict = self.safety.check("", intent.is_off_topic, ctx.subject)

        response = await self.composer.compose(
            query_id=query_id,
            intent=intent,
            retrieved=retrieved,
            verdict=verdict,
            prompt=prompt,
            ctx=ctx,
            pipeline_trace=trace,
            total_start=total_start,
        )
        trace["total_ms"] = round((time.perf_counter() - total_start) * 1000, 1)
        response.pipeline_trace = trace

        logger.info(f"[{query_id}] FAST pipeline {trace['total_ms']}ms")
        return response

    # ═══════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════

    def _build_request(
        self, intent, ctx: ClassroomContext, top_k: int
    ) -> RetrievalRequest:
        return RetrievalRequest(
            query=intent.reformulated_query,
            subject=intent.classified_subject.value,
            grade=ctx.student.grade,
            top_k=top_k,
        )

    def _off_topic_response(
        self, query_id, intent, verdict, ctx, trace, total_start
    ) -> FinalResponse:
        return FinalResponse(
            query_id=query_id,
            answer=verdict.sanitized_text,
            sources=[],
            mode=ctx.mode.value,
            intent=intent.intent.value,
            subject=intent.classified_subject.value,
            difficulty=intent.difficulty.value,
            chunks_used=0,
            total_time_ms=round((time.perf_counter() - total_start) * 1000, 1),
            pipeline_trace=trace,
            safety_status=verdict.status.value,
            pipeline_mode=ctx.pipeline_mode.value,
        )

    @staticmethod
    def _response_dict(r: FinalResponse) -> dict:
        return {
            "answer": r.answer[:400],
            "sources": r.sources,
            "total_ms": r.total_time_ms,
            "safety": r.safety_status,
            "follow_up": r.follow_up_question,
            "mode": r.pipeline_mode,
        }

    def get_stats(self) -> dict:
        s = self.store.stats()
        s["cache_size"] = self.cache.size() if self.cache else 0
        s["memory_students"] = len(self.personalizer._cache)
        return s


# ── Module-level singleton ─────────────────────────────────────────────────────

# We delay initialisation to avoid loading models at import time in some contexts,
# or we can initialise here if the server always needs it.
_orchestrator: Optional[ZoroOrchestrator] = None

def get_orchestrator() -> ZoroOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        from app.core.llm_caller import get_llm_caller
        _orchestrator = ZoroOrchestrator(
            llm_caller=get_llm_caller()
        )
    return _orchestrator

