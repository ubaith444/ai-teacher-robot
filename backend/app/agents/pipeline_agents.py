"""
agents/pipeline_agents.py
==========================
Zoro Robot — Unified 7-Agent Pipeline
All agents in one module. Each is independently testable.

Agent 1  QueryUnderstandingAgent   classify intent, subject, difficulty
Agent 2  RetrieverAgent            FAISS vector search
Agent 3  RerankerAgent             hybrid score: embedding + keyword + grade + source
Agent 4  PersonalizationAgent      student memory + teaching directives
Agent 5  SafetyPolicyAgent         classroom content policy
Agent 6  TeacherPersonaAgent       build structured LLM prompt (Zoro's 14 rules)
Agent 7  ResponseComposerAgent     assemble FinalResponse

v1 compatibility: ContextFormatter is kept as an alias for TeacherPersonaAgent.build_prompt()
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

from app.schemas.contracts import (
    RawQuery, QueryIntent, RetrievalRequest, RetrievalResult,
    RerankedResult, RankedChunk, PersonalizationDirective,
    SafetyVerdict, SafetyStatus, FinalResponse,
    ClassroomContext, DocumentChunk, RetrievedContext,
    Subject, Intent, Difficulty, TeachingMode,
)

logger = logging.getLogger("zoro.agents")


# ═════════════════════════════════════════════════════════════
# AGENT 1 — QUERY UNDERSTANDING
# ═════════════════════════════════════════════════════════════

class QueryUnderstandingAgent:
    """
    Fully local classification — no LLM call.
    Extracts subject, intent, difficulty, keywords.
    Reformulates query with classroom context for better retrieval.
    """

    SUBJECT_KEYWORDS: dict[Subject, list[str]] = {
        Subject.MATH:      ["equation","solve","calculate","algebra","geometry","triangle",
                            "probability","fraction","integer","matrix","derivative","integral",
                            "linear","polynomial","angle","arithmetic"],
        Subject.PHYSICS:   ["force","velocity","acceleration","newton","gravity","momentum",
                            "energy","power","wave","current","voltage","resistance","optics",
                            "lens","magnetic","electric","motion","work"],
        Subject.CHEMISTRY: ["atom","molecule","element","compound","reaction","acid","base",
                            "bond","periodic","valence","oxidation","reduction","mole",
                            "solution","concentration","electrolysis"],
        Subject.BIOLOGY:   ["cell","photosynthesis","respiration","dna","rna","enzyme",
                            "protein","organism","ecosystem","evolution","mitosis","meiosis",
                            "chromosome","osmosis","diffusion","nutrition"],
        Subject.HISTORY:   ["war","empire","revolution","colonial","independence","dynasty",
                            "treaty","civilization","king","queen","movement","freedom",
                            "constitution","parliament","revolt"],
        Subject.GEOGRAPHY: ["latitude","longitude","climate","continent","river","mountain",
                            "ecosystem","rainfall","erosion","plateau","delta","ocean",
                            "tectonic","monsoon","vegetation","soil"],
        Subject.ENGLISH:   ["grammar","poem","story","verb","noun","adjective","metaphor",
                            "simile","tense","pronoun","essay","paragraph","comprehension",
                            "alliteration","synonym","antonym"],
        Subject.HINDI:     ["sandhi","samas","karak","vibhakti","kriya","visheshana",
                            "kavita","doha","nibandh","vyakaran"],
    }

    INTENT_PATTERNS: dict[Intent, list[str]] = {
        Intent.SOLVE:    ["solve","calculate","find the value","evaluate","compute",
                          "what is the answer","how much","simplify","find x","find y"],
        Intent.COMPARE:  ["difference between","compare","vs","versus","distinguish",
                          "contrast","similarities","what is better","how are"],
        Intent.SUMMARIZE:["summarize","summary","brief","overview","in short","gist",
                          "main points","key points","recap"],
        Intent.HINT:     ["hint","clue","help me","stuck","don't tell me","guide me",
                          "push in right direction","just a hint"],
        Intent.QUIZ:     ["quiz me","test me","ask me","question on","practice",
                          "mcq","multiple choice","test my knowledge"],
        Intent.DEFINE:   ["what is","what does","define","meaning of","definition",
                          "what are","what do you mean"],
        Intent.EXAMPLE:  ["example","give me an","show me","illustrate","instance of",
                          "real world example","for example"],
        Intent.EXPLAIN:  ["explain","how does","why does","tell me about","describe",
                          "elaborate","what happens","how do","walk me through"],
    }

    DIFFICULTY_SIGNALS: dict[Difficulty, list[str]] = {
        Difficulty.EASY: ["simple","basic","easy","beginner","class 6","class 7",
                          "primary","what is","for kids"],
        Difficulty.HARD: ["advanced","derive","prove","complex","class 11","class 12",
                          "college","analyze","critical","in depth","rigorous"],
    }

    OFF_TOPIC = ["movie","cricket","game","instagram","tiktok","social media",
                 "boyfriend","girlfriend","fight","politics","election",
                 "violence","weapon","drug","alcohol"]

    def analyze(self, raw: RawQuery) -> QueryIntent:
        t0   = time.perf_counter()
        text = raw.text.strip().lower()
        ctx  = raw.context

        subject      = self._classify_subject(text, ctx)
        intent       = self._classify_intent(text)
        difficulty   = self._estimate_difficulty(text, ctx)
        keywords     = self._extract_keywords(text)
        off_topic    = any(sig in text for sig in self.OFF_TOPIC)
        reformulated = self._reformulate(raw.text, subject, intent, ctx)

        ms = (time.perf_counter() - t0) * 1000
        logger.debug(f"QueryAgent {intent.value}/{subject.value} in {ms:.1f}ms")

        return QueryIntent(
            raw_query           = raw.text,
            classified_subject  = subject,
            intent              = intent,
            difficulty          = difficulty,
            keywords            = keywords,
            reformulated_query  = reformulated,
            is_off_topic        = off_topic,
            confidence          = self._confidence(text, subject, intent),
        )

    def _classify_subject(self, text: str, ctx: ClassroomContext) -> Subject:
        if ctx.subject:
            for subj in Subject:
                if subj.value in ctx.subject.lower():
                    return subj
        scores = {s: sum(1 for kw in kws if kw in text)
                  for s, kws in self.SUBJECT_KEYWORDS.items()}
        best = max(scores, key=lambda s: scores[s])
        return best if scores[best] > 0 else Subject.GENERAL

    def _classify_intent(self, text: str) -> Intent:
        scores = {i: sum(1 for p in pats if p in text)
                  for i, pats in self.INTENT_PATTERNS.items()}
        best = max(scores, key=lambda i: scores[i])
        return best if scores[best] > 0 else Intent.EXPLAIN

    def _estimate_difficulty(self, text: str, ctx: ClassroomContext) -> Difficulty:
        if ctx.student.level != Difficulty.MEDIUM:
            return ctx.student.level
        for diff, signals in self.DIFFICULTY_SIGNALS.items():
            if any(s in text for s in signals):
                return diff
        g = ctx.student.grade
        if g and g <= 7:
            return Difficulty.EASY
        if g and g >= 11:
            return Difficulty.HARD
        return Difficulty.MEDIUM

    def _extract_keywords(self, text: str) -> list[str]:
        stops = {"the","a","an","is","are","was","were","be","been","being","have","has",
                 "do","does","did","will","would","can","could","should","may","might",
                 "shall","must","to","of","in","for","on","with","at","by","from","what",
                 "how","why","when","where","who","which","me","my","i","you","he","she",
                 "it","we","they","this","that","these","those","about","and","or","but"}
        words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
        seen, out = set(), []
        for w in words:
            if w not in stops and w not in seen:
                seen.add(w); out.append(w)
        return out[:10]

    def _reformulate(self, original: str, subject: Subject, intent: Intent, ctx: ClassroomContext) -> str:
        if intent == Intent.DEFINE:
            return f"definition explanation {original.strip()}"
        parts = [original.strip()]
        if subject.value != "general":
            parts.append(subject.value)
        if ctx.topic:
            parts.append(ctx.topic)
        if ctx.current_lesson:
            parts.append(ctx.current_lesson)
        return " ".join(parts)

    def _confidence(self, text: str, subject: Subject, intent: Intent) -> float:
        score = 1.0
        if subject == Subject.GENERAL: score -= 0.25
        if intent  == Intent.UNKNOWN:  score -= 0.25
        if len(text.split()) < 3:      score -= 0.20
        return max(0.1, score)


# ═════════════════════════════════════════════════════════════
# AGENT 2 — RETRIEVER
# ═════════════════════════════════════════════════════════════

class RetrieverAgent:
    """
    FAISS / numpy vector search.
    Accepts QueryIntent + RetrievalRequest.
    Returns RetrievedContext (unified v1/v2 object).
    """

    def __init__(self, store, embedder):
        self.store   = store
        self.embedder = embedder

    def retrieve(
        self,
        intent:  QueryIntent,
        request: RetrievalRequest,
    ) -> RetrievedContext:
        t0 = time.perf_counter()
        query_vec = self.embedder.encode_single(request.query)
        chunks, scores = self.store.search(
            query_vec,
            top_k          = request.top_k,
            subject_filter = request.subject,
            grade_filter   = request.grade,
        )
        ms = (time.perf_counter() - t0) * 1000
        logger.debug(f"Retriever: {len(chunks)} chunks in {ms:.1f}ms")
        return RetrievedContext(
            chunks            = chunks,
            query             = request.query,
            scores            = scores,
            retrieval_time_ms = ms,
            total_searched    = len(self.store.chunks),
        )

    async def retrieve_async(self, intent: QueryIntent, request: RetrievalRequest) -> RetrievedContext:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.retrieve, intent, request)


# ═════════════════════════════════════════════════════════════
# AGENT 3 — RERANKER
# ═════════════════════════════════════════════════════════════

class RerankerAgent:
    """
    Hybrid reranking: embedding score + keyword overlap + source trust + grade proximity.
    No cross-encoder needed — runs <5ms on Pi Zero.
    """

    SOURCE_TRUST = {"textbook": 1.0, "ncert": 1.0, "notes": 0.85, "qa": 0.80,
                    "pdf": 0.75, "csv": 0.70, "document": 0.65}
    WEIGHTS      = {"embedding": 0.50, "keyword": 0.30, "source": 0.10, "grade": 0.10}

    def rerank(
        self,
        retrieved:     RetrievedContext,
        intent:        QueryIntent,
        student_grade: int = 8,
    ) -> RerankedResult:
        t0       = time.perf_counter()
        keywords = set(intent.keywords)
        ranked   = []

        for chunk in retrieved.chunks:
            emb_score    = chunk.embedding_score
            kw_score     = self._keyword_score(chunk.text, keywords)
            source_score = self.SOURCE_TRUST.get(chunk.source_type.lower(), 0.65)
            grade_score  = self._grade_score(chunk.grade, student_grade)
            final        = (self.WEIGHTS["embedding"] * emb_score +
                            self.WEIGHTS["keyword"]   * kw_score   +
                            self.WEIGHTS["source"]    * source_score +
                            self.WEIGHTS["grade"]     * grade_score)
            ranked.append(RankedChunk(
                chunk=chunk, original_score=emb_score,
                rerank_score=kw_score, final_score=final, rank=0,
            ))

        ranked.sort(key=lambda r: r.final_score, reverse=True)
        for i, r in enumerate(ranked):
            r.rank = i + 1

        ms = (time.perf_counter() - t0) * 1000
        logger.debug(f"Reranker: top={ranked[0].final_score:.3f} | {ms:.1f}ms")
        return RerankedResult(
            ranked_chunks=ranked, query=retrieved.query,
            rerank_time_ms=ms, strategy_used="weighted_hybrid",
        )

    def _keyword_score(self, text: str, keywords: set[str]) -> float:
        if not keywords:
            return 0.5
        words   = set(re.findall(r"\b\w+\b", text.lower()))
        overlap = len(keywords & words) / len(keywords)
        density = sum(1 for kw in keywords if kw in text.lower()) / max(len(text.split()) / 100, 1)
        return min(1.0, overlap * 0.7 + min(density, 1.0) * 0.3)

    def _grade_score(self, chunk_grade: int, student_grade: int) -> float:
        if chunk_grade == 0: return 0.5
        diff = abs(chunk_grade - student_grade)
        return {0: 1.0, 1: 0.75, 2: 0.5}.get(diff, 0.2)


# ═════════════════════════════════════════════════════════════
# AGENT 4 — PERSONALIZATION
# ═════════════════════════════════════════════════════════════

class PersonalizationAgent:
    """
    Reads student profile + persistent interaction memory.
    Emits PersonalizationDirective controlling Zoro's response style.
    Tracks weak topics across sessions; boosts depth for repeated mistakes.
    """

    def __init__(self, memory_path: str = "data/student_memory"):
        self.memory_path = Path(memory_path)
        self.memory_path.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict] = {}

    def get_directive(self, intent: QueryIntent, ctx: ClassroomContext) -> PersonalizationDirective:
        profile  = ctx.student
        mode     = ctx.mode
        memory   = self._load(profile.student_id)
        d        = PersonalizationDirective(language=profile.language, ask_followup=True)

        # Mode hard-overrides
        if mode == TeachingMode.HINT:
            d.hint_only = True; d.tone = "encouraging"; return d
        if mode == TeachingMode.QUIZ:
            d.hint_only = False; d.tone = "strict"
            d.notes = "Quiz mode: ask questions, do not answer them."; return d
        if mode == TeachingMode.SOCRATIC:
            d.hint_only = True; d.tone = "calm"
            d.notes = "Use only Socratic questions throughout."; return d

        # Level-based defaults
        level = profile.level
        if level == Difficulty.EASY:
            d.tone = "warm"; d.depth = "shallow"
            d.use_examples = True; d.use_analogy = True; d.step_by_step = True
        elif level == Difficulty.HARD:
            d.tone = "challenging"; d.depth = "deep"
            d.use_examples = False; d.use_analogy = False; d.step_by_step = False
            d.notes = "Challenge the student; expect prior knowledge."
        else:
            d.tone = "encouraging"; d.depth = "moderate"
            d.use_examples = True
            d.step_by_step = intent.intent in (Intent.SOLVE, Intent.EXPLAIN)

        # Weak topic boost
        if ctx.topic and ctx.topic in memory.get("weak_topics", []):
            d.depth = "deep"; d.step_by_step = True; d.use_examples = True
            d.notes += " | Student has struggled with this topic before."

        return d

    def update_memory(self, student_id: str, interaction: dict):
        memory = self._load(student_id)
        memory["interaction_count"] = memory.get("interaction_count", 0) + 1
        memory.setdefault("topics_seen", [])
        if t := interaction.get("topic"):
            memory["topics_seen"].append(t)
        if interaction.get("was_wrong"):
            memory.setdefault("weak_topics", [])
            if t and t not in memory["weak_topics"]:
                memory["weak_topics"].append(t)
        self._cache[student_id] = memory
        self._persist(student_id, memory)

    def _load(self, sid: str) -> dict:
        if sid in self._cache: return self._cache[sid]
        p = self.memory_path / f"{sid}.json"
        if p.exists():
            data = json.loads(p.read_text())
            self._cache[sid] = data
            return data
        return {}

    def _persist(self, sid: str, memory: dict):
        (self.memory_path / f"{sid}.json").write_text(json.dumps(memory, indent=2))


# ═════════════════════════════════════════════════════════════
# AGENT 5 — SAFETY / POLICY
# ═════════════════════════════════════════════════════════════

BLOCKED_TERMS = ["violence","weapon","drug","alcohol","explicit","adult",
                 "nsfw","harmful","abuse","gore"]

OFF_TOPIC_MSG = ("That's an interesting question! Let's stay focused on today's lesson. "
                 "If you'd like to discuss this further, please speak with your teacher. "
                 "Now, shall we continue with {subject}?")

class SafetyPolicyAgent:
    """
    Validates query intent and LLM output before delivery.
    Returns SafetyVerdict: APPROVED / MODIFIED / BLOCKED.
    """

    def check(
        self,
        text:         str,
        is_off_topic: bool = False,
        subject:      str  = "our lesson",
    ) -> SafetyVerdict:
        flags  = []
        status = SafetyStatus.APPROVED
        output = text

        for term in BLOCKED_TERMS:
            if term in text.lower():
                return SafetyVerdict(
                    status=SafetyStatus.BLOCKED, original_text=text,
                    sanitized_text="I'm sorry, I can't answer that in class. Please ask your teacher.",
                    flags=[f"blocked:{term}"], reason="Content policy violation",
                )

        if is_off_topic:
            flags.append("off_topic")
            status = SafetyStatus.MODIFIED
            output = OFF_TOPIC_MSG.format(subject=subject)

        if len(text.split()) > 600:
            flags.append("too_long")
            output = " ".join(output.split()[:500]) + " [...]"
            status = SafetyStatus.MODIFIED

        return SafetyVerdict(
            status=status, original_text=text, sanitized_text=output,
            flags=flags, reason=", ".join(flags) or "ok",
        )


# ═════════════════════════════════════════════════════════════
# AGENT 6 — TEACHER PERSONA (prompt builder)
# ═════════════════════════════════════════════════════════════

ZORO_SYSTEM = """You are an AI classroom teacher integrated into a physical robot.

Your role is to assist students and teachers with:
- Explaining concepts clearly
- Answering questions briefly
- Reporting attendance information
- Guiding classroom interaction

----------------------------------------
CORE BEHAVIOR RULES
----------------------------------------

1. Clarity First
- Speak in simple, clear English.
- Use short sentences.
- Avoid complex vocabulary unless necessary.

2. Brevity
- Default: 1–2 sentences.
- Maximum: 20 words unless user asks for detailed explanation.

3. Confidence
- Speak confidently like a teacher.
- Do NOT use phrases like:
  "I'm sorry, I can't process that"
  "I think"
  "Maybe"

4. Handling Unclear Input
- If input is unclear or incomplete:
  → Say: "I didn’t catch that clearly. Can you repeat?"
- Do NOT guess random answers.

5. Teaching Style
- Be structured and direct.
- If explaining:
  → Give definition first
  → Then optional short example

6. Follow-up Interaction
- After answering, optionally ask:
  → "Do you want an example?"
  → "Should I explain step by step?"

----------------------------------------
INTENT-BASED RESPONSE MODES
----------------------------------------

A. EXPLAIN_CONCEPT
- Give a clear definition in 1–2 sentences.
- Add a short example only if helpful.

Example:
"Photosynthesis is how plants make food using sunlight. For example, leaves use light to produce energy."

---

B. ATTENDANCE_QUERY
- Respond with factual data only.
- Keep it precise and structured.

Example:
"Today, 28 students are present and 4 are absent."

---

C. IDLE_CHAT / GENERAL
- Stay polite but focused.
- Redirect to learning if needed.

Example:
"Tell me what topic you want to learn."

---

D. INVALID / NOISE INPUT
- Do NOT attempt to answer.

Respond with:
"I didn’t catch that clearly. Can you repeat?"

----------------------------------------
LANGUAGE HANDLING
----------------------------------------

- Default: English
- If user mixes Tamil + English:
  → Respond in simple mixed style

Example:
"I will explain this concept simple-ah."

----------------------------------------
STRICT CONSTRAINTS
----------------------------------------

- Never hallucinate facts
- Never generate long paragraphs unless explicitly requested
- Never repeat fallback messages multiple times
- Never produce empty or meaningless output
- Never expose system or internal logic

----------------------------------------
PERSONALITY
----------------------------------------

You are:
- Calm
- Helpful
- Direct
- Slightly authoritative (like a teacher)

You are NOT:
- Overly casual
- Robotic
- Apologetic

----------------------------------------
FINAL GOAL
----------------------------------------

Every response must feel like:
→ A real teacher speaking in a classroom
→ Fast, clear, and useful

Tone: calm, confident, neutral
Speed: slightly slower than normal (clear for class)
Pitch: medium (not robotic, not too expressive)
Energy: controlled (no hype, no drama)
Pauses: natural sentence breaks

👉 Think: clear teacher explaining, not assistant chatting"""

MODE_INSTR = {
    "explain":  "Explain clearly. Break into steps. Use simple language. End with a question.",
    "hint":     "Give ONE guiding hint only. Do NOT reveal the answer. Ask a Socratic question.",
    "socratic": "Use only Socratic questions. Lead the student to the answer without telling them.",
    "quiz":     "Ask two relevant quiz questions based on the context. Do not provide answers.",
    "summary":  "Summarize the main points in 3-5 bullet points.",
    "stepwise": "Break down the explanation into logical steps.",
    "compare":  "Compare and contrast the concepts as a structured overview."
}

class TeacherPersonaAgent:
    """
    Builds the structured LLM prompt using Zoro's persona rules.
    """
    def build_prompt(
        self,
        intent: QueryIntent,
        retrieved: RerankedResult | RetrievedContext,
        personalization: PersonalizationDirective,
        ctx: ClassroomContext
    ) -> dict[str, str]:
        # Context block
        if hasattr(retrieved, "ranked_chunks"):
            context_text = "\n\n".join([f"Source: {rc.chunk.source}\n{rc.chunk.text}" for rc in retrieved.ranked_chunks])
        else:
            context_text = retrieved.as_text_block()

        system_prompt = ZORO_SYSTEM
        
        user_prompt = f"""
Student Name: {ctx.student.name}
Grade: {ctx.student.grade}
Subject: {intent.classified_subject.value}
Student Level: {personalization.depth}
Tone: {personalization.tone}
Mode: {ctx.mode.value}

Instruction: {MODE_INSTR.get(ctx.mode.value, "Explain clearly.")}
Additional Notes: {personalization.notes}

Retrieved Knowledge:
{context_text}

Student Question: {intent.raw_query}
"""
        return {"system": system_prompt, "user": user_prompt}

class ResponseComposerAgent:
    """
    Assembles the final response. Calls the LLM if llm_caller is provided.
    """
    def __init__(self, llm_caller=None):
        self.llm_caller = llm_caller

    async def compose(
        self,
        query_id: str,
        intent: QueryIntent,
        retrieved: RerankedResult | RetrievedContext,
        verdict: SafetyVerdict,
        prompt: dict[str, str],
        ctx: ClassroomContext,
        pipeline_trace: dict[str, float],
        total_start: float
    ) -> FinalResponse:
        answer = ""
        if self.llm_caller and verdict.status == SafetyStatus.APPROVED:
            try:
                answer = await self.llm_caller(prompt["system"], prompt["user"])
            except Exception as e:
                logger.warning(f"LLM call failed: {type(e).__name__} — using offline echo answer")
                # Degrade gracefully: produce a structured classroom answer from the retrieved text
                try:
                    from app.core.llm_caller import _format_echo_answer
                    answer = _format_echo_answer(prompt["user"])
                except Exception:
                    answer = (
                        "Good question! Let me look that up in your notes. "
                        "Here is what I found: "
                        + prompt.get("user", "")[:300]
                    )
        elif verdict.status != SafetyStatus.APPROVED:
            answer = verdict.sanitized_text
        else:
            # No llm_caller wired — still produce a useful answer from retrieved context
            try:
                from app.core.llm_caller import _format_echo_answer
                answer = _format_echo_answer(prompt["user"])
            except Exception:
                answer = prompt.get("user", "")[:600]

        # Extract source names
        if hasattr(retrieved, "ranked_chunks"):
            sources = list(set([rc.chunk.source for rc in retrieved.ranked_chunks]))
            chunks_used = len(retrieved.ranked_chunks)
        else:
            sources = list(set([c.source for c in retrieved.chunks]))
            chunks_used = len(retrieved.chunks)

        total_ms = (time.perf_counter() - total_start) * 1000

        return FinalResponse(
            query_id=query_id,
            answer=answer,
            sources=sources,
            mode=ctx.mode.value,
            intent=intent.intent.value,
            subject=intent.classified_subject.value,
            difficulty=intent.difficulty.value,
            chunks_used=chunks_used,
            total_time_ms=total_ms,
            prompt=prompt,
            pipeline_trace=pipeline_trace,
            safety_status=verdict.status.value,
            pipeline_mode=ctx.pipeline_mode.value,
            context_text=prompt["user"] # For backward compatibility
        )
