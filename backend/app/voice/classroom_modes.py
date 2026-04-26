"""
app/voice/classroom_modes.py
─────────────────────────────
Classroom mode definitions, intent detection, and persona prompt engine.

Classroom Modes
───────────────
  idle        — Robot is waiting; ready to assist
  attendance  — Attendance session active; answering roll-call queries
  teaching    — Structured lesson delivery; step-by-step explanations
  practice    — Exercise mode; guiding with hints, Socratic method
  exam        — Strict mode; minimal help, no direct answers

Intent Categories
──────────────────
  ATTENDANCE_QUERY    — "Who is absent?", "Mark me present"
  EXPLAIN_CONCEPT     — "Explain photosynthesis"
  PRACTICE_HELP       — "I don't understand this problem"
  EXAM_INFO           — "When is the exam?" (allowed in exam mode)
  EXAM_ANSWER         — "What is the answer to Q3?" (restricted)
  LANGUAGE_SWITCH     — "Reply in Tamil please"
  GREETING            — "Hello Zoro", "Good morning"
  IDLE_CHAT           — General chat unrelated to classroom
  UNKNOWN             — Cannot determine intent
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional

from app.schemas import Language


# ── Mode enum ────────────────────────────────────────────────────────────────

class ClassroomMode(str, Enum):
    IDLE = "idle"
    ATTENDANCE = "attendance"
    TEACHING = "teaching"
    PRACTICE = "practice"
    EXAM = "exam"


# ── Intent enum ───────────────────────────────────────────────────────────────

class Intent(str, Enum):
    ATTENDANCE_QUERY = "attendance_query"
    EXPLAIN_CONCEPT = "explain_concept"
    PRACTICE_HELP = "practice_help"
    EXAM_INFO = "exam_info"
    EXAM_ANSWER = "exam_answer"
    LANGUAGE_SWITCH = "language_switch"
    GREETING = "greeting"
    IDLE_CHAT = "idle_chat"
    UNKNOWN = "unknown"


# ── Intent detection (heuristic, no extra LLM call) ───────────────────────────

_ATTENDANCE_PATTERNS = re.compile(
    r"\b(absent|present|attendance|mark|who.*miss|roll call|vanthurukkaar|vandhaangala"
    r"|varugai|vanthirukkiingala|eppadi irukkaanga)\b",
    re.IGNORECASE,
)
_EXPLAIN_PATTERNS = re.compile(
    r"\b(explain|what is|definition|meaning|how does|describe|tell me about"
    r"|enna|engappa|eppadi|sollu|vilakku)\b",
    re.IGNORECASE,
)
_PRACTICE_PATTERNS = re.compile(
    r"\b(solve|help|hint|stuck|confused|don.*understand|not getting|ennakku puriyala"
    r"|konjam help|eppadi solve|solve pannuvom|doubt)\b",
    re.IGNORECASE,
)
_EXAM_ANSWER_PATTERNS = re.compile(
    r"\b(answer|solution|what.*correct|tell.*answer|give.*answer|exam answer"
    r"|question \d+|Q\d+)\b",
    re.IGNORECASE,
)
_EXAM_INFO_PATTERNS = re.compile(
    r"\b(when.*exam|exam date|which chapter|syllabus|portions|what.*exam)\b",
    re.IGNORECASE,
)
_LANG_SWITCH_PATTERNS = re.compile(
    r"\b(tamil|english|tanglish|switch.*language|tamilil pesungal|in tamil"
    r"|in english|ஆங்கிலத்தில்|தமிழில்)\b",
    re.IGNORECASE,
)
_GREETING_PATTERNS = re.compile(
    r"^(hi|hello|good morning|good afternoon|good evening|hey zoro|vanakkam|namaste|hola)\b",
    re.IGNORECASE,
)


def detect_intent(text: str) -> Intent:
    """
    Fast heuristic intent detection.
    No LLM call — runs in microseconds on Pi Zero 2 W.
    """
    t = text.strip()
    if _GREETING_PATTERNS.search(t):
        return Intent.GREETING
    if _LANG_SWITCH_PATTERNS.search(t):
        return Intent.LANGUAGE_SWITCH
    if _ATTENDANCE_PATTERNS.search(t):
        return Intent.ATTENDANCE_QUERY
    if _EXAM_ANSWER_PATTERNS.search(t):
        return Intent.EXAM_ANSWER
    if _EXAM_INFO_PATTERNS.search(t):
        return Intent.EXAM_INFO
    if _PRACTICE_PATTERNS.search(t):
        return Intent.PRACTICE_HELP
    if _EXPLAIN_PATTERNS.search(t):
        return Intent.EXPLAIN_CONCEPT
    if len(t) > 0:
        return Intent.IDLE_CHAT
    return Intent.UNKNOWN


# ── Teacher persona system prompts ────────────────────────────────────────────

# Base persona description used in all modes
_ZORO_BASE = """You are Zoro, an AI teacher robot deployed in a school classroom.

PERSONA:
- Calm, patient, and encouraging — like a firm but kind teacher
- Never give direct answers too quickly; guide students to think
- Use the Socratic method: ask guiding questions first
- Break every explanation into numbered steps
- Adapt to student level — simpler language for younger students
- Keep voice responses short: 2-4 sentences max, no bullet points in voice
- Never use markdown, asterisks, brackets, or lists in responses (voice output)
- Use natural spoken language

LANGUAGE RULES:
- Respond in the same language the student used
- English + Tamil code-mixing (Tanglish) is perfectly acceptable
- If Tamil characters detected → respond in Tamil or Tanglish
- Numbers should be spoken out: "thirty-five" not "35"
"""

_MODE_PROMPTS: dict[ClassroomMode, str] = {
    ClassroomMode.IDLE: _ZORO_BASE + """
CURRENT MODE: IDLE
- You are waiting and available to help
- Greet naturally, offer to explain a concept or answer questions
- Keep idle responses very short (1-2 sentences)
""",

    ClassroomMode.ATTENDANCE: _ZORO_BASE + """
CURRENT MODE: ATTENDANCE
- Attendance session is active right now
- Use your attendance tools to answer any attendance questions
- Announce roll calls warmly: "Good morning everyone! Let's take attendance."
- Confirm each student with a short, warm acknowledgement
- If asked about absent students, check the database tool and report clearly
""",

    ClassroomMode.TEACHING: _ZORO_BASE + """
CURRENT MODE: TEACHING
- You are delivering a structured lesson
- Always follow this explanation format:
  1. Give a simple one-sentence overview
  2. Break it into 2-3 key steps or ideas
  3. Give one real-world example
  4. Ask a follow-up question to check understanding
- Do NOT rush to the complete answer
- If the student asks a follow-up, build on the previous explanation
- Use classroom-appropriate examples relevant to school curriculum
""",

    ClassroomMode.PRACTICE: _ZORO_BASE + """
CURRENT MODE: PRACTICE / EXERCISE
- Students are working on problems and need guided help
- NEVER give the direct answer
- Give hints in this order:
  1. First hint: remind them of the relevant concept/formula
  2. Second hint (if they're still stuck): show a similar worked example
  3. Third hint: walk through the method step by step
- Praise effort: "Good thinking! Now consider this..."
- Ask "What have you tried so far?" before giving any hint
""",

    ClassroomMode.EXAM: _ZORO_BASE + """
CURRENT MODE: EXAM (Strict)
- Students are in an active exam or test
- You MUST NOT provide answers, solutions, or direct hints to exam questions
- You MAY answer: general exam instructions, timing, allowed materials
- For any answer request: "I can't help with exam answers. You can do this!"
- Keep the atmosphere calm and confidence-boosting
- Enforce exam rules firmly but kindly
""",
}

# Tamil/Tanglish additions
_TAMIL_ADDENDUM = """
TAMIL/TANGLISH GUIDANCE:
- Use a warm mix of Tamil and English
- Common classroom phrases:
  "நல்லா யோசிங்க" (think well)
  "ஒரு step-by-step பாக்கலாம்" (let's look step by step)
  "சரியான answer-ku close ஆ இருக்கீங்க" (you're close to the right answer)
  "Doubt irundha kelu" (ask if you have a doubt)
"""


def build_system_prompt(
    mode: ClassroomMode,
    language: Language,
    lesson_topic: Optional[str] = None,
    class_section: Optional[str] = None,
    student_name: Optional[str] = None,
) -> str:
    """
    Build the complete Gemini system prompt for Zoro.

    Parameters
    ----------
    mode           : current classroom mode
    language       : detected/preferred language
    lesson_topic   : current lesson being taught (for teaching mode)
    class_section  : e.g. "10-A" (for personalised greetings)
    student_name   : if known (for personalised responses)
    """
    prompt = _MODE_PROMPTS.get(mode, _MODE_PROMPTS[ClassroomMode.IDLE])

    if language in (Language.TAMIL, Language.MIXED):
        prompt += _TAMIL_ADDENDUM

    if lesson_topic:
        prompt += f"\n\nCURRENT LESSON TOPIC: {lesson_topic}\n"
        prompt += "Focus all explanations on this topic unless the student asks otherwise.\n"

    if class_section:
        prompt += f"\nCLASS: {class_section}\n"

    if student_name:
        prompt += f"\nSTUDENT NAME: {student_name}. Address them by name occasionally.\n"

    return prompt.strip()


# ── Exam mode guard ───────────────────────────────────────────────────────────

def is_exam_restricted(intent: Intent, mode: ClassroomMode) -> bool:
    """
    Returns True if the request is restricted in exam mode.
    """
    if mode != ClassroomMode.EXAM:
        return False
    return intent in (Intent.PRACTICE_HELP, Intent.EXPLAIN_CONCEPT, Intent.EXAM_ANSWER)


# ── Context container ─────────────────────────────────────────────────────────

class ClassroomContext:
    """
    Holds the full context of the current classroom session.
    Passed into the voice orchestrator to enrich prompts.
    """
    __slots__ = (
        "mode", "class_section", "lesson_topic", "student_name",
        "student_id", "language", "rag_context", "attendance_state",
    )

    def __init__(
        self,
        mode: ClassroomMode = ClassroomMode.IDLE,
        class_section: Optional[str] = None,
        lesson_topic: Optional[str] = None,
        student_name: Optional[str] = None,
        student_id: Optional[str] = None,
        language: Language = Language.ENGLISH,
        rag_context: Optional[str] = None,
        attendance_state: Optional[str] = None,
    ):
        self.mode = mode
        self.class_section = class_section
        self.lesson_topic = lesson_topic
        self.student_name = student_name
        self.student_id = student_id
        self.language = language
        self.rag_context = rag_context
        self.attendance_state = attendance_state

    def to_prompt_suffix(self) -> str:
        """Build context suffix to append to system prompt."""
        parts = []
        if self.rag_context:
            parts.append(f"REFERENCE MATERIAL:\n{self.rag_context[:800]}")
        if self.attendance_state:
            parts.append(f"ATTENDANCE STATUS: {self.attendance_state}")
        return "\n\n".join(parts)

