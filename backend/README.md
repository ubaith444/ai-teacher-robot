# Zoro AI Classroom Robot — Unified System Architecture

**Version:** 3.0.0 (Unified Teacher System)
**Platform:** Raspberry Pi Zero 2 W · FastAPI · PostgreSQL · OpenCV LBPH · Deepgram API · Gemini 2.5 Flash

---

## 1. Overall System Goal

Zoro is a complete, production-ready AI-powered classroom teaching robot designed to run optimally on a Raspberry Pi Zero 2 W under strict hardware constraints. Zoro unifies computer vision, motor control, voice interactions, and a custom multi-agent RAG pipeline to operate autonomously inside a classroom context.

Zoro is capable of:
1. **Automated Attendance:** Scanning student faces, maintaining session state via a weekly timetable, and marking attendance.
2. **Bulk Enrollment:** Integrating with Google Drive to securely download student images for automated face training.
3. **Real-time Motor Control:** Differential drive logic for moving on a 4-tyre setup safely using a TB6612FNG controller via WebSocket.
4. **Voice Agent Stack:** Low-latency conversational interactions using Deepgram (STT/TTS) and Gemini 2.5 Flash.
5. **Multi-Agent RAG:** Real-time retrieval of educational content orchestrated by a localized 7-agent pipeline.
6. **Classroom Modes:** Automatically switching between idle, attendance, teaching, dictation, exam, and test modes.
7. **Personalized Learning:** Creating robust long-term learning profiles and dynamically tracking topic-level mastery over multiple sessions.
8. **Dashboard Data Tools:** Comprehensive CSV/Excel exports for administration.

---

## 2. Hardware Architecture & Safety Setup

### Architecture Overview

```text
┌────────────────────────────────────────────────────────────────────────┐
│ Raspberry Pi Zero 2 W                                                  │
│                                                                        │
│ ┌──────────────┐   ┌───────────────────────────────────────────────┐   │
│ │ USB Camera   ├──▶│ Automated Face Recognition Service & LBPH     │   │
│ └──────────────┘   └───────────────────────────────────────────────┘   │
│                                           │                            │
│ ┌──────────────┐   ┌──────────────────────▼────────────────────────┐   │
│ │ USB Mic /    ├──▶│ Voice Orchestrator / Gemini / Deepgram        │   │
│ │ USB Speaker  │   └──────────────────────▲────────────────────────┘   │
│ └──────────────┘                          │                            │
│                                           │                            │
│ ┌──────────────┐   ┌──────────────────────▼────────────────────────┐   │
│ │ 4×DC Motor / │   │ Motor Service / WebSocket Bridge              │   │
│ │ TB6612FNG    │◀──┤ (Differential Control, E-Stop Logic)          │   │
│ └──────────────┘   └───────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
            │ 
            ▼ (Secure Context Synchronization) 
   ┌─────────────────┐
   │  PostgreSQL DB  │
   │  (Users, Stats) │
   └─────────────────┘
```

### Safety & Power Specifications
> ⚠️ **CRITICAL — Follow exactly for classroom deployment**

* **Power Routing:** Never power the motors directly from the Pi. Route a 12V battery directly to the `VMOT` pin on the TB6612FNG motor driver.
* **Buck Conversion:** Use a DC-to-DC buck converter to step down the 12V supply to a clean 5V (min 2.5A) to run the Pi Zero.
* **Common Ground:** Tie the 12V battery (-), motor driver ground, and Pi ground together.
* **Emergency Stop:** `motor_service.py` is configured with a strict websocket timeout loop that forces all PWM signals `LOW` if client connectivity drops.

---

## 3. Modular Backend Structure

The system exposes its entire feature set via a unified FastAPI instance `app/main.py` connected safely to a modular service stack.

```text
backend/
├── app/
│   ├── api/                 # FastAPI REST and WebSocket hooks
│   │   ├── endpoints/
│   │   │   ├── attendance.py      # Face auth + Session checking
│   │   │   ├── drive_enrollment.py# Scalable Drive bulk imports
│   │   │   ├── robot_control.py   # Realtime websocket for TB6612FNG
│   │   │   ├── voice.py           # VAD + STT/LLM/TTS cascade streams
│   │   │   └── mode.py            # Global mode switches
│   ├── agents/              # Multi-Agent Pipeline Components
│   │   └── pipeline_agents.py # Agents 1 through 7 (Query, Retriever, Persona...)
│   ├── core/                # System Globals
│   │   ├── config.py          # .env loading and hardware overrides
│   │   ├── orchestrator.py    # Merges Voice & RAG Agent logic
│   │   └── llm_caller.py      # Fast-switching Online/Offline cascades
│   ├── models/              # Relational models
│   │   └── models.py          # Students, Sessions, Profiles, TopicMastery, etc.
│   ├── services/            # Core Business Logic 
│   │   ├── attendance*.py     # Rule-based DB logging
│   │   ├── face_ws_server.py  # Face event publisher
│   │   ├── offline_llm*.py    # GGML llama.cpp integration
│   │   └── voice_orch*.py     # Conversation buffer management
```

---

## 4. Subsystem Details

### A. Automated Attendance
* Handled efficiently via an `LBPHFaceRecognizer`.
* Auto-creates session instances off a `Timetable` and bounds present vs. late tags using strict `GRACE_MINUTES`.
* Publishes face bounding boxes asynchronously.
* Provides CSV/Excel export utility routes directly attached to the student/teacher relations.

### B. Student Bulk Enrollment 
* Facilitated securely via a Google Drive API backend service. Allows downloading high-res folders full of student image maps without blocking the main event loop.
* Local failure caching allows graceful resumes when Drive bandwidth limits trigger.
* End-to-end integration with LBPH retraining triggers after successful imports.

### C. Real-Time Motor Control
* Exposes a `ws://<pi-ip>:8000/robot/control` socket. 
* Encodes `{ "action": "forward", "speed": 100 }` to strict duty-cycle adjustments targeting the left and right wheels for differential track maneuvering.
* Includes dead-man switch timing mechanisms to ensure student collision safety.

### D. Voice Stack
* Configured natively for Deepgram API streaming to bypass the Pi's internal compute delays.
* Integrated tightly with Gemini 2.5 Flash as the online decision core.
* Handles an explicit online/offline fallback cascade (`OfflineLLMService` via lightweight quantization models in `llama.cpp`) when Wi-Fi cuts out in isolated classrooms.
* Encompasses automated dual-language coding capabilities. 

### E. Multi-Agent Knowledge Orchestration (RAG)
To avoid overwhelming the Pi, indexing is kept slim via FAISS context stores in `app/agents/pipeline_agents.py`. Zoro fields a 7-Agent system internally:
1. `QueryUnderstandingAgent`: Intent/Keyword extractions.
2. `RetrieverAgent`: FAISS-backed document scanning.
3. `RerankerAgent`: Hybrid grade+vector distance sorting algorithm.
4. `PersonalizationAgent`: Memory context injection.
5. `SafetyPolicyAgent`: Hard fail-blocks for restricted terminology.
6. `TeacherPersonaAgent`: Structures output around Zoro's 14 pedagogical Socratic rules.
7. `ResponseComposerAgent`: Merges outputs smoothly for Voice-Agent broadcasting.

### F. Classroom Modes Controller
A centralized Redis/memory toggle determines how the `VoiceOrchestrator` answers questions.
* `Idle`: Mic off.
* `Attendance`: Muted processing.
* `Teaching`: Socratic hints deployed heavily.
* `Practice`: Minimal direct assistance, strictly graded.
* `Exam`: Only administrative responses available.

### G. Database & Personalization Schema
A heavy PostgreSQL configuration tracking not just logic, but longitudinal student improvement vectors:
* `users` / `students`: Baseline JWT mapping and Face Label IDs.
* `sessions` / `timetable` / `attendance`: School management constructs.
* `performance`, `interaction_logs`, `practice_attempts`, `topic_mastery`, and `learning_profiles`: Live metadata stores measuring response delays, hit rates, and error topics allowing the `PersonalizationAgent` to dynamically alter instructional strictness.

---

## 5. End-to-End System Flow Summary

1. **Morning Boot:** Zoro turns on via battery payload.
2. **Attendance Initialization:** At 08:30 (Period 1), the `Classroom Mode` flips to `attendance`. Zoro's camera parses the room using Haar cascades and runs fast LBPH verifications, flushing metrics directly to the `attendance` standard table. 
3. **Teaching Hook:** At 08:45, `Mode` transitions to `teaching`. WebSockets open. Face service falls into standby while Voice services activate.
4. **Student Interaction:** "Zoro, I don't understand how diffusion works."
5. **Orchestration:** `VoiceOrchestrator` captures Deepgram STT. `QueryUnderstandingAgent` assesses the intent -> FAISS local indexes. `PersonalizationAgent` checks `topic_mastery` and notices this student struggles heavily with cellular topics. 
6. **Execution:** Context passes securely directly into Gemini 2.5. Zoro structures an encouraging hint rather than a full response according to rule 3 of his Persona.
7. **Motor Adjustment:** A teacher on the same network moves the slider on the React Dashboard. The `motor_service` immediately adjusts the duty-cycles to turn the robot towards the next cluster of desks.

