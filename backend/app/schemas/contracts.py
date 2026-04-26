
"""
schemas/contracts.py
====================
Zoro Robot — Unified Knowledge Retrieval System
All typed data contracts used by every agent and service layer.

Merges v1 (single-agent RAG) and v2 (multi-agent pipeline) into one
coherent schema. Every object is a plain dataclass — no external deps.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

# ═════════════════════════════════════════════════════════════
# ENUMS
# ═════════════════════════════════════════════════════════════


class Subject(str, Enum):
    MATH = "math"
    SCIENCE = "science"
    PHYSICS = "physics"
    CHEMISTRY = "chemistry"
    BIOLOGY = "biology"
    HISTORY = "history"
    GEOGRAPHY = "geography"
    ENGLISH = "english"
    HINDI = "hindi"
    SOCIAL = "social"
    GENERAL = "general"


class Intent(str, Enum):
    EXPLAIN = "explain"
    SOLVE = "solve"
    COMPARE = "compare"
    SUMMARIZE = "summarize"
    HINT = "hint"
    QUIZ = "quiz"
    DEFINE = "define"
    EXAMPLE = "example"
    UNKNOWN = "unknown"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class TeachingMode(str, Enum):
    EXPLAIN = "explain"
    HINT = "hint"
    SOCRATIC = "socratic"
    QUIZ = "quiz"
    SUMMARY = "summary"
    STEPWISE = "stepwise"
    COMPARE = "compare"


class SourceType(str, Enum):
    TEXTBOOK = "textbook"
    NOTES = "notes"
    QA = "qa"
    PDF = "pdf"
    DOCUMENT = "document"
    CSV = "csv"


class SafetyStatus(str, Enum):
    APPROVED = "approved"
    MODIFIED = "modified"
    BLOCKED = "blocked"


class PipelineMode(str, Enum):
    """Controls whether the full 7-agent pipeline or fast single-agent path runs."""

    FULL = "full"  # 7-agent multi-agent pipeline (default)
    FAST = "fast"  # direct retrieval + prompt (v1 single-agent path)


# ═════════════════════════════════════════════════════════════
# STUDENT PROFILE  (v2, extended)
# ═════════════════════════════════════════════════════════════


@dataclass
class StudentProfile:
    student_id: str = "anonymous"
    name: str = "Student"
    grade: int = 8
    section: str = "A"
    level: Difficulty = Difficulty.MEDIUM
    language: str = "en"
    weak_topics: list[str] = field(default_factory=list)
    strong_topics: list[str] = field(default_factory=list)
    recent_mistakes: list[str] = field(default_factory=list)
    interaction_count: int = 0
    last_subject: str = ""


# ═════════════════════════════════════════════════════════════
# CLASSROOM CONTEXT  (unified from v1 + v2)
# ═════════════════════════════════════════════════════════════


@dataclass
class ClassroomContext:
    """
    Single context object accepted by every layer.
    v1 callers set flat string fields.
    v2 callers also set student: StudentProfile.
    """

    subject: str = ""
    topic: str = ""
    current_lesson: str = ""
    class_section: str = ""  # v1 compat alias
    mode: TeachingMode = TeachingMode.EXPLAIN
    student: StudentProfile = field(default_factory=StudentProfile)
    session_id: str = ""
    timestamp: float = field(default_factory=time.time)
    pipeline_mode: PipelineMode = PipelineMode.FULL

    # ── v1 flat-field accessors (backwards compatibility) ──
    @property
    def student_level(self) -> str:
        return self.student.level.value

    @property
    def language(self) -> str:
        return self.student.language

    @property
    def grade(self) -> int:
        return self.student.grade


# ═════════════════════════════════════════════════════════════
# DOCUMENT CHUNK  (unified)
# ═════════════════════════════════════════════════════════════


@dataclass
class DocumentChunk:
    """
    A single retrievable knowledge segment.
    Carries both the v1 numpy embedding (for FAISS build)
    and the v2 embedding_score (set at search time).
    """

    chunk_id: str
    text: str
    source: str
    source_type: str  # SourceType value
    subject: str = ""
    topic: str = ""
    grade: int = 0
    page: int = 0
    word_count: int = 0
    embedding_score: float = 0.0  # cosine sim filled by retriever

    # numpy embedding stored only during indexing; not persisted in metadata
    _embedding: Any = field(default=None, repr=False)

    @property
    def embedding(self):
        return self._embedding

    @embedding.setter
    def embedding(self, v):
        self._embedding = v


# ═════════════════════════════════════════════════════════════
# INGESTION
# ═════════════════════════════════════════════════════════════


@dataclass
class IngestionResult:
    status: str
    docs_loaded: int
    chunks_created: int
    time_seconds: float
    source_path: str


# ═════════════════════════════════════════════════════════════
# RETRIEVAL LAYER  (v1 + v2 merged)
# ═════════════════════════════════════════════════════════════


@dataclass
class RawQuery:
    text: str
    context: ClassroomContext
    query_id: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class QueryIntent:
    """Output of QueryUnderstandingAgent (v2 Agent 1)."""

    raw_query: str
    classified_subject: Subject
    intent: Intent
    difficulty: Difficulty
    keywords: list[str]
    reformulated_query: str
    is_off_topic: bool = False
    confidence: float = 1.0
    reasoning: str = ""


@dataclass
class RetrievalRequest:
    query: str
    subject: str
    grade: int
    top_k: int = 5
    filters: dict = field(default_factory=dict)
    require_source_types: list[str] = field(default_factory=list)


@dataclass
class RetrievedContext:
    """
    Unified retrieval result.
    v1 direct callers use .chunks + .scores + .as_text_block().
    v2 agents promote this into RetrievalResult for the reranker.
    """

    chunks: list[DocumentChunk]
    query: str
    scores: list[float]
    retrieval_time_ms: float
    total_searched: int = 0

    @property
    def best_chunk(self) -> Optional[DocumentChunk]:
        return self.chunks[0] if self.chunks else None

    def as_text_block(self) -> str:
        parts = []
        for i, (chunk, score) in enumerate(zip(self.chunks, self.scores), 1):
            parts.append(
                f"[Source {i}: {chunk.source} | {chunk.subject} | score={score:.2f}]\n"
                f"{chunk.text.strip()}"
            )
        return "\n\n---\n\n".join(parts)

    def to_retrieval_result(self) -> "RetrievalResult":
        """Promote to v2 RetrievalResult for the reranker pipeline."""
        for chunk, score in zip(self.chunks, self.scores):
            chunk.embedding_score = score
        return RetrievalResult(
            chunks=self.chunks,
            query=self.query,
            retrieval_time_ms=self.retrieval_time_ms,
            total_searched=self.total_searched,
        )


@dataclass
class RetrievalResult:
    """v2 internal retrieval result (alias from RetrievedContext)."""

    chunks: list[DocumentChunk]
    query: str
    retrieval_time_ms: float
    total_searched: int


# ═════════════════════════════════════════════════════════════
# RERANKING  (v2 Agent 3)
# ═════════════════════════════════════════════════════════════


@dataclass
class RankedChunk:
    chunk: DocumentChunk
    original_score: float
    rerank_score: float
    final_score: float
    rank: int


@dataclass
class RerankedResult:
    ranked_chunks: list[RankedChunk]
    query: str
    rerank_time_ms: float
    strategy_used: str


# ═════════════════════════════════════════════════════════════
# PERSONALIZATION  (v2 Agent 4)
# ═════════════════════════════════════════════════════════════


@dataclass
class PersonalizationDirective:
    tone: str = "encouraging"
    depth: str = "moderate"
    use_examples: bool = True
    use_analogy: bool = True
    ask_followup: bool = True
    hint_only: bool = False
    step_by_step: bool = False
    language: str = "en"
    notes: str = ""


# ═════════════════════════════════════════════════════════════
# SAFETY  (v2 Agent 5)
# ═════════════════════════════════════════════════════════════


@dataclass
class SafetyVerdict:
    status: SafetyStatus
    original_text: str
    sanitized_text: str
    flags: list[str] = field(default_factory=list)
    reason: str = ""


# ═════════════════════════════════════════════════════════════
# FINAL RESPONSE  (unified output)
# ═════════════════════════════════════════════════════════════


@dataclass
class FinalResponse:
    """
    Unified output from both pipeline modes.
    Fast mode (v1): answer="" — caller passes prompt to LLM.
    Full mode (v2): answer contains LLM output if llm_caller is wired.
    prompt dict is always present for client-side LLM calls.
    """

    query_id: str
    answer: str
    sources: list[str]
    mode: str
    intent: str
    subject: str
    difficulty: str
    chunks_used: int
    total_time_ms: float
    prompt: dict[str, str] = field(default_factory=dict)
    pipeline_trace: dict[str, float] = field(default_factory=dict)
    safety_status: str = "approved"
    follow_up_question: str = ""
    pipeline_mode: str = "full"
    context_text: str = ""  # v1 compat: raw retrieved text

