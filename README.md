# AI Teacher Robot Backend

Production-ready FastAPI backend for an AI-powered classroom attendance system running on **Raspberry Pi Zero 2 W**.

- **Face detection**: OpenCV Haar Cascade (default) or MobileNet SSD
- **Face recognition**: OpenCV LBPH (`cv2.face.LBPHFaceRecognizer`) — CPU-only, Pi-friendly
- **Database**: PostgreSQL via SQLAlchemy 2.x async + asyncpg
- **Auth**: JWT (HS256) + bcrypt password hashing
- **Exports**: CSV and Excel (.xlsx)

---

## Project Structure

```
ai_teacher_robot_backend/
├── app/
│   ├── main.py                   # FastAPI app factory + lifespan
│   ├── core/
│   │   ├── config.py             # All settings (Pydantic BaseSettings)
│   │   ├── database.py           # Async engine, session factory, Base
│   │   └── security.py          # JWT + bcrypt helpers
│   ├── models/
│   │   └── models.py             # SQLAlchemy ORM models
│   ├── schemas/
│   │   ├── student.py            # Pydantic request/response models
│   │   ├── attendance.py
│   │   └── timetable.py
│   ├── api/endpoints/
│   │   ├── students.py           # Enrollment endpoints
│   │   ├── attendance.py         # Mark, query, export
│   │   ├── timetable.py          # Upload + current-period lookup
│   │   └── robot.py              # Robot automation (start/stop/scan)
│   ├── services/
│   │   └── face_service.py       # Singleton detector + LBPH recognizer
│   └── utils/
│       ├── image_processing.py   # OpenCV helpers
│       └── helpers.py            # CSV/Excel, session IDs, time utils
├── migrations/                   # Alembic migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial_schema.py
├── .env                          # Environment config (DO NOT commit secrets)
├── alembic.ini
├── requirements.txt
└── run.sh                        # One-command startup
```

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.10 or 3.11 |
| PostgreSQL | 13+ |
| RAM | 512 MB (Pi Zero 2 W) |

---

## Quick Start

### 1. Clone and enter the project

```bash
cd ai_teacher_robot_backend
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

> **Pi Zero 2 W note**: OpenCV compilation can take 20–30 minutes. Use the pre-built wheel `opencv-contrib-python-headless` to avoid compiling from source.

### 4. Configure environment

Edit `.env` and set at minimum:

```env
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/attendance_db
SYNC_DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/attendance_db
SECRET_KEY=<long-random-hex-string>
```

Generate a secret key:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 5. Create the database

```bash
createdb attendance_db   # or use psql
```

### 6. Run migrations

```bash
alembic upgrade head
```

### 7. Start the server

```bash
./run.sh           # production (1 worker)
./run.sh --dev     # development (auto-reload)
```

API is available at `http://10.241.73.235:8000`  
Interactive docs: `http://10.241.73.235:8000/docs`

---

## Authentication

All endpoints (except `/health`, `/`, `/auth/token`) require a JWT bearer token.

**Get a token:**

```bash
curl -X POST http://10.241.73.235:8000/auth/token \
  -d "username=admin&password=admin123"
```

Response:
```json
{ "access_token": "<jwt>", "token_type": "bearer" }
```

Use the token in all subsequent requests:
```
Authorization: Bearer <jwt>
```

> Change the demo password by editing `_DEMO_PASSWORD_HASH` in `app/main.py` or wiring up a proper users table.

---

## API Reference

### Students

| Method | Path | Description |
|---|---|---|
| `POST` | `/students/enroll` | Enroll one student (multipart: fields + 1–5 images) |
| `POST` | `/students/bulk-enroll` | Bulk enroll (JSON with base64 images) |
| `GET` | `/students/` | Paginated student list |

**Single enroll example:**

```bash
curl -X POST http://localhost:8000/students/enroll \
  -H "Authorization: Bearer <token>" \
  -F "student_id=S1001" \
  -F "name=Aarav Kumar" \
  -F "class_section=10-A" \
  -F "images=@photo1.jpg" \
  -F "images=@photo2.jpg"
```

**Bulk enroll example (JSON):**

```json
{
  "students": [
    {
      "student_id": "S1002",
      "name": "Priya Sharma",
      "class_section": "10-A",
      "images_b64": ["<base64_jpeg_1>", "<base64_jpeg_2>"]
    }
  ]
}
```

---

### Timetable

| Method | Path | Description |
|---|---|---|
| `POST` | `/timetable/upload` | Replace timetable for class+day |
| `GET` | `/timetable/current?class_section=10-A` | Get the currently active period |

**Upload example:**

```json
{
  "entries": [
    {
      "class_section": "10-A",
      "day_of_week": "monday",
      "period_number": 1,
      "subject": "Mathematics",
      "teacher_id": "T001",
      "start_time": "08:00:00",
      "end_time": "08:45:00"
    }
  ]
}
```

---

### Attendance

| Method | Path | Description |
|---|---|---|
| `POST` | `/attendance/mark` | Mark one student (face image or student_id) |
| `GET` | `/attendance/today` | Today's records (filter by class/session) |
| `GET` | `/attendance/report` | Historical records with filters |
| `GET` | `/attendance/export/csv` | Download CSV |
| `GET` | `/attendance/export/excel` | Download XLSX |

**Mark by face image:**

```bash
curl -X POST "http://localhost:8000/attendance/mark?session_id=2024-06-01_10-A_P1" \
  -H "Authorization: Bearer <token>" \
  -F "face_image=@frame.jpg"
```

**Mark by student_id (no image):**

```bash
curl -X POST "http://localhost:8000/attendance/mark?session_id=2024-06-01_10-A_P1&student_id=S1001" \
  -H "Authorization: Bearer <token>"
```

**Export CSV:**

```bash
curl "http://localhost:8000/attendance/export/csv?date=2024-06-01&class_section=10-A" \
  -H "Authorization: Bearer <token>" \
  -o attendance.csv
```

---

### Robot Automation

| Method | Path | Description |
|---|---|---|
| `GET` | `/robot/status` | Current mode, session, scan count |
| `POST` | `/robot/start` | Enter classroom, begin scanning |
| `POST` | `/robot/stop` | Leave classroom, mark session complete |
| `POST` | `/robot/scan` | Submit one camera frame for detection |

**Typical robot flow:**

```bash
# 1. Enter classroom
curl -X POST http://localhost:8000/robot/start \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"class_section": "10-A"}'

# 2. Scan frames in a loop
while true; do
  curl -X POST http://localhost:8000/robot/scan \
    -H "Authorization: Bearer <token>" \
    -F "face_image=@current_frame.jpg"
  sleep 0.5
done

# 3. Leave classroom
curl -X POST http://localhost:8000/robot/stop \
  -H "Authorization: Bearer <token>"
```

The scan loop can also be driven by the robot's on-board code. The backend
auto-completes the session when no new faces are detected for
`ROBOT_NO_NEW_FACE_TIMEOUT_SEC` seconds.

---

## Face Recognition Details

### Detection Models

| Model | Config value | Speed | Notes |
|---|---|---|---|
| Haar Cascade | `haar` | Fastest | Default; best for Pi Zero 2 W |
| MobileNet SSD | `mobilenet` | Moderate | Better accuracy; needs model files |

### LBPH Threshold

`LBPH_THRESHOLD` (default `80.0`):
- `confidence < threshold` → **known** student
- `confidence ≥ threshold` → **unknown** (not stored)

Lower values = stricter matching. Tune per classroom lighting.

### Incremental Training

The LBPH model supports incremental updates:
- New students can be enrolled without retraining from scratch.
- The model file (`lbph_model.yml`) and label map (`label_map.json`) are always kept in sync.
- If training fails mid-way, the previous model + label map are automatically restored.

---

## Attendance Logic

| Scenario | Status |
|---|---|
| Detected within `GRACE_MINUTES` after period start | `present` |
| Detected after grace period | `late` |
| Not detected during the entire session | `absent` (not stored; absent = missing record) |
| Already marked in this session | `already_marked` (no duplicate written) |
| Unknown face | Not stored; logged for audit |

**Session ID format:** `YYYY-MM-DD_<class_section>_P<period_number>`  
Example: `2024-06-01_10-A_P3`

---

## Performance Notes (Pi Zero 2 W)

- **1 Uvicorn worker** – set in `run.sh`. More workers waste RAM.
- **Models loaded once** – at startup via `FaceService.startup()`. Never reloaded per request.
- **Max 2 faces per frame** – controlled by `MAX_FACES_PER_FRAME`.
- **Resize to 320 px width** before detection – reduces CPU load dramatically.
- **Grayscale early** – detection and recognition both run on grayscale images.
- **Sequential bulk enrollment** – avoids memory spikes from parallel OpenCV calls.

---

## Database Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Roll back the last migration
alembic downgrade -1

# Generate a new migration after changing models
alembic revision --autogenerate -m "add_new_column"

# Show current revision
alembic current
```

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://...` | Async DB URL for runtime |
| `SYNC_DATABASE_URL` | `postgresql+psycopg2://...` | Sync DB URL for Alembic |
| `SECRET_KEY` | *(required)* | JWT signing key |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `480` | 8-hour school day |
| `DETECTION_MODEL` | `haar` | `haar` or `mobilenet` |
| `LBPH_THRESHOLD` | `80.0` | Recognition confidence cutoff |
| `MAX_IMAGE_WIDTH` | `320` | Resize cap before detection |
| `MAX_FACES_PER_FRAME` | `2` | CPU cap per frame |
| `GRACE_MINUTES` | `10` | Present window after period start |
| `ROBOT_NO_NEW_FACE_TIMEOUT_SEC` | `30` | Auto-complete trigger |
| `ROBOT_MAX_SCANS` | `200` | Infinite-loop guard |
| `ROBOT_VOICE_COOLDOWN_SEC` | `2.5` | Voice message rate limit |

---

## Health Check

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "app": "AI Teacher Robot Backend",
  "version": "1.0.0",
  "face_model_trained": false,
  "detection_model": "haar"
}
```

`face_model_trained` becomes `true` after the first student is enrolled.

---

## Security Checklist

- [ ] Change `SECRET_KEY` to a random 32-byte hex string
- [ ] Replace demo admin credentials in `app/main.py`
- [ ] Set `API_KEY` in `.env` if using robot header-key auth
- [ ] Restrict `CORS` `allow_origins` to known frontend/robot IPs
- [ ] Run PostgreSQL with a dedicated low-privilege user
- [ ] Do NOT commit `.env` to version control (add to `.gitignore`)

---

## License

MIT – see LICENSE file.

# 🤖 Zoro2026 — Hybrid AI Voice Agent

A production-ready, low-latency, multilingual AI voice agent for an Intelligent Teacher Robot, designed to run on a **Raspberry Pi Zero 2 W** in a real classroom.

---

## Architecture Overview

```
Microphone
    │
    ▼
┌───────────────────────────────────────────────────────────────┐
│                   Voice Orchestrator                          │
│                                                               │
│  Audio → VAD → STT (Deepgram Nova-3) → LLM → TTS → Speaker  │
│                          │                                    │
│                   ┌──────┴──────┐                            │
│                   │   ONLINE    │  OFFLINE                   │
│                   │   Gemini    │  llama.cpp (Phi-3 Q4)      │
│                   │   2.5 Flash │  + Piper TTS               │
│                   └─────────────┘                            │
│                          │                                    │
│               PostgreSQL Attendance DB                        │
│               Face Recognition WS Sync                        │
└───────────────────────────────────────────────────────────────┘
```

### Fallback Chain
```
Gemini OK + Deepgram OK  →  ONLINE  (primary)
Gemini OK + Deepgram TTS fail  →  PARTIAL (Gemini + Piper)
Gemini timeout/offline  →  OFFLINE (llama.cpp + Piper)
All fail  →  TEXT ONLY (display on screen)
```

---

## Project Structure

```
voice_agent/
├── app/
│   ├── main.py                     ← FastAPI entry point
│   ├── config.py                   ← All settings via env vars
│   ├── schemas/__init__.py         ← Pydantic data models
│   ├── routers/
│   │   └── voice_attendance.py     ← REST + WebSocket endpoints
│   ├── services/
│   │   ├── voice_orchestrator.py   ← CENTRAL pipeline coordinator
│   │   ├── deepgram_service.py     ← STT + TTS + Voice Agent API
│   │   ├── gemini_service.py       ← Gemini 2.5 Flash + tool calling
│   │   ├── offline_llm_service.py  ← llama.cpp + canned responses
│   │   ├── attendance_tool.py      ← Read-only PostgreSQL tools
│   │   └── face_voice_sync.py      ← Blur filter + vote tracker + TTS
│   └── utils/
│       └── audio_utils.py          ← VAD, PCM, Piper, sounddevice
├── requirements.txt
├── .env.example
└── README.md
```

---

## Raspberry Pi Zero 2 W Setup Guide

### 1. OS Setup

```bash
# Flash Raspberry Pi OS Lite (64-bit) — use Pi Imager
# Enable SSH, set hostname: teacherbot.local

# After boot:
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv python3-pip \
    libportaudio2 portaudio19-dev \
    libopenblas-dev libatlas-base-dev \
    alsa-utils git build-essential cmake
```

### 2. Python Environment

```bash
cd /home/pi
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip wheel

cd /home/pi/voice_agent
pip install -r requirements.txt

# For uvloop (faster async on Pi):
pip install uvloop
```

### 3. Deepgram Setup

```bash
# No local installation needed — pure API calls via httpx
# Just set DEEPGRAM_API_KEY in .env

# Test STT:
python3 -c "
import asyncio
from app.services.deepgram_service import deepgram_stt
# ... test call
print('Deepgram OK')
"
```

### 4. Piper Tamil TTS Setup

```bash
# Install Piper binary
cd /tmp
wget https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_armv7l.tar.gz
tar -xzf piper_armv7l.tar.gz
sudo cp piper /usr/local/bin/piper
sudo chmod +x /usr/local/bin/piper

# Download Tamil voice
sudo mkdir -p /opt/piper
cd /opt/piper

# Tamil (medium quality)
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/ta/ta_IN/coqui/medium/ta_IN-coqui-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/ta/ta_IN/coqui/medium/ta_IN-coqui-medium.onnx.json

# English (for teacher mode)
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json

# Test:
echo "வணக்கம்" | piper --model /opt/piper/ta_IN-coqui-medium.onnx --output_file /tmp/test.wav
aplay /tmp/test.wav
```

### 5. Offline LLM Setup (Phi-3 Mini Q4)

```bash
sudo mkdir -p /opt/models

# Download Phi-3 Mini Q4 (1.8 GB — fits in Pi Zero 2W's 512 MB RAM with mmap)
wget https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q4.gguf \
    -O /opt/models/phi3-mini-q4.gguf

# Install llama-cpp-python (ARM build, no GPU)
CMAKE_ARGS="-DLLAMA_NATIVE=off -DLLAMA_AVX=off -DLLAMA_AVX2=off" \
pip install llama-cpp-python --no-binary llama-cpp-python
```

### 6. Microphone + Speaker Config

```bash
# List devices
aplay -l    # playback
arecord -l  # capture

# Set default in /etc/asound.conf:
cat << 'EOF' | sudo tee /etc/asound.conf
pcm.!default {
    type asym
    playback.pcm "plughw:0,0"
    capture.pcm "plughw:1,0"
}
ctl.!default {
    type hw
    card 0
}
EOF

# Test microphone:
arecord -d 3 -r 16000 -c 1 -f S16_LE /tmp/test_mic.wav
aplay /tmp/test_mic.wav
```

### 7. PostgreSQL Setup

```bash
sudo apt install -y postgresql postgresql-contrib
sudo -u postgres psql << 'SQL'
CREATE USER robot WITH PASSWORD 'yourpassword';
CREATE DATABASE school_db OWNER robot;
\c school_db
CREATE TABLE students (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    roll_number   VARCHAR(20)  UNIQUE NOT NULL,
    class_section VARCHAR(10)  NOT NULL,
    created_at    TIMESTAMP DEFAULT NOW()
);
CREATE TABLE periods (
    id         SERIAL PRIMARY KEY,
    name       VARCHAR(50) NOT NULL,
    start_time TIME        NOT NULL,
    end_time   TIME        NOT NULL,
    day_of_week INT        -- 0=Mon … 6=Sun, NULL=all days
);
CREATE TABLE attendance (
    id              SERIAL PRIMARY KEY,
    student_id      INT  NOT NULL REFERENCES students(id),
    period_id       INT  NOT NULL REFERENCES periods(id),
    attendance_date DATE NOT NULL DEFAULT CURRENT_DATE,
    status          VARCHAR(20) NOT NULL DEFAULT 'absent',
    marked_at       TIMESTAMP,
    marked_by       VARCHAR(50) DEFAULT 'face_recognition',
    UNIQUE (student_id, period_id, attendance_date)
);
-- Indexes for fast queries
CREATE INDEX idx_att_date   ON attendance(attendance_date);
CREATE INDEX idx_att_student ON attendance(student_id, attendance_date);
CREATE INDEX idx_att_period  ON attendance(period_id, attendance_date);
GRANT SELECT ON ALL TABLES IN SCHEMA public TO robot;
SQL
```

### 8. Running the Service

```bash
cd /home/pi/voice_agent
cp .env.example .env
nano .env   # fill in your API keys

source ../venv/bin/activate
python -m app.main

# Or with uvicorn directly:
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1

# Systemd service (auto-start on boot):
sudo tee /etc/systemd/system/teacherbot.service << 'EOF'
[Unit]
Description=TeacherBot Voice Agent
After=network.target postgresql.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/voice_agent
ExecStart=/home/pi/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
Restart=on-failure
RestartSec=5
Environment=PYTHONPATH=/home/pi/voice_agent

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable teacherbot
sudo systemctl start teacherbot
sudo journalctl -fu teacherbot
```

---

## API Usage

### REST — Voice Query
```bash
# Text query
curl -X POST http://teacherbot.local:8000/voice/query \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess-001",
    "text_query": "Who is absent today in class 10A?",
    "user_role": "teacher",
    "class_section": "10A"
  }'

# Audio query (base64 WAV)
AUDIO_B64=$(base64 -w 0 /tmp/query.wav)
curl -X POST http://teacherbot.local:8000/voice/query \
  -d "{\"session_id\":\"s1\",\"audio_b64\":\"$AUDIO_B64\"}"
```

### WebSocket — Streaming Pipeline
```javascript
const ws = new WebSocket("ws://teacherbot.local:8000/voice/stream/sess-001?role=student&lang=ta");

ws.onopen = () => {
  ws.send(JSON.stringify({ type: "session_start", payload: { class_section: "10A" } }));
};

// Send PCM audio chunks (16-bit, mono, 16 kHz)
mediaRecorder.ondataavailable = (e) => ws.send(e.data);

ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  if (msg.type === "transcript_final") console.log("You said:", msg.payload.text);
  if (msg.type === "llm_chunk") appendText(msg.payload.text);
  if (msg.type === "tts_chunk") playAudio(atob(msg.payload.data_b64));
};
```

### Face Event
```bash
curl -X POST http://teacherbot.local:8000/voice/face-event \
  -H "Content-Type: application/json" \
  -d '{
    "event": {
      "student_id": 42,
      "student_name": "Ubaith",
      "confidence": 0.87,
      "period_id": 2,
      "class_section": "10A",
      "blur_score": 120.5
    },
    "speak": true,
    "language": "mixed"
  }'
```

---

## Low-Latency Optimisation Tips

### Audio Pipeline
- Use 20 ms VAD frames (webrtcvad) — reject silence before sending to Deepgram
- Trim silence from start/end of audio with `trim_silence()`
- Stream PCM directly; avoid WAV container overhead on the hot path
- Set `DG_STT_ENDPOINTING=400` — 400 ms silence → end of utterance

### Gemini
- Set `GEMINI_TIMEOUT_S=8.0` — fall back promptly if API is slow
- Use streaming (`stream_generate`) so TTS can start before LLM finishes
- Pre-fetch attendance data in parallel with first LLM token if possible
- Limit `GEMINI_MAX_TOKENS=512` — voice responses should be short

### TTS
- Start TTS on the **first sentence boundary** (`.!?`) of LLM output
- Deepgram Aura first-byte latency: ~200-400 ms; Piper on Pi: ~800-1500 ms
- Cache frequently spoken phrases (e.g., period names, student names)

### System (Pi Zero 2W)
```bash
# Use performance governor
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# Disable swap (reduce SD card wear, improves latency)
sudo systemctl disable dphys-swapfile
sudo dphys-swapfile swapoff

# Set GPU memory to minimum (robot has no display)
echo "gpu_mem=16" | sudo tee -a /boot/config.txt

# Increase Pi clock (if cooling is adequate)
echo "arm_freq=1000" | sudo tee -a /boot/config.txt
```

### Network
- Use Ethernet over WiFi when possible (30-50 ms latency reduction)
- If WiFi: use 5 GHz band, position AP close to robot

---

## Noise Handling + Classroom Tuning

### Microphone
- Use a directional (cardioid) USB microphone aimed at students
- Place mic 30-50 cm from the speaker zone
- Hardware noise cancellation: Jabra Speak or ReSpeaker USB mic array

### VAD Tuning (in .env)
```
AUDIO_VAD_AGGRESSIVENESS=2   # 0=least, 3=most aggressive filtering
```
Higher values filter more background noise but may clip quiet voices.

### Deepgram STT
- `DG_STT_LANGUAGE=en-IN` — trained on Indian English accent
- `DG_STT_SMART_FORMAT=true` — formats numbers, dates naturally
- `DG_STT_ENDPOINTING=400` — tunable silence threshold

### For Tamil
- Switch `DG_STT_LANGUAGE=ta-IN` at runtime (per language detection)
- Deepgram Nova-3 supports Tamil; accuracy may vary — Piper offline is more reliable for TTS

---

## Integration Points

### Attendance System
- `attendance_tool.py` connects to shared PostgreSQL
- Three read-only tools exposed to Gemini via function calling
- Face recognition service marks attendance via its own writer; voice agent reads only

### RAG Tutor
- Add a `rag_tool` to `GEMINI_TOOL_DEFINITIONS` in `attendance_tool.py`
- The tool queries your vector DB (pgvector / Chroma)
- Gemini auto-calls it when it detects curriculum / lesson questions

### Personalised Learning Module
- Extend `ConversationSession` with `student_profile: Dict`
- Load profile from DB at session start (learning style, weak subjects)
- Pass profile as additional context in Gemini system prompt

---

## Gemini Function-Calling Tool Definitions

Defined in `attendance_tool.py → GEMINI_TOOL_DEFINITIONS`.

| Tool | Purpose |
|------|---------|
| `get_student_attendance` | Individual student's attendance by name or ID |
| `get_class_attendance` | Full class present/absent list for a period |
| `get_today_summary` | Class summary: percentage, perfect attendance, chronic absences |

---

## System Prompts

### English — Teacher Mode
> "Class 10A has 28 out of 32 students present today, giving an attendance rate of 87.5 percent."

### Tamil — Student Mode
> "உங்களுக்கு இன்று 4 பீரியட்டில் வருகை உள்ளது, 2 பீரியட்டில் absent ஆ இருந்தீங்க."

Full prompts in `gemini_service.py → SYSTEM_PROMPT_TEACHER_EN / SYSTEM_PROMPT_STUDENT_TA`.

---

## Health & Monitoring

```bash
# Full health check
curl http://teacherbot.local:8000/health

# Voice pipeline health
curl http://teacherbot.local:8000/voice/health

# Session info
curl http://teacherbot.local:8000/voice/session/sess-001
```

---

## Security Notes

- All DB operations are **read-only** — no SQL injection risk
- API keys loaded from `.env` — never commit `.env` to git
- Audio is not stored (privacy-conscious pipeline)
- Rate limiting: 60 requests/minute per IP
- CORS: restrict `allow_origins` to robot's subnet in production
- WebSocket: add token auth for production deployment

# Zoro AI Robot — Integration Layer

**Classroom robot integration layer for Raspberry Pi Zero 2 W.**  
Real-time WebSocket motor control + FastAPI backend + teacher behavior system.  
Integrates cleanly with your existing attendance, RAG, personalization, and database modules.

---

## Architecture Overview

```
Laptop Browser (index.html / app.js)
        │  WebSocket (20 FPS motion commands)
        │  REST (mode switch, status)
        ▼
┌─────────────────────────────────────────┐
│         FastAPI (app/main.py)           │
│  /api/robot/ws/control  ←── WebSocket  │
│  /api/robot/status      ←── REST       │
│  /api/mode/switch        ←── REST      │
└────────────┬────────────────────────────┘
             │
    ┌────────┴────────┐
    │                 │
MotorService    RobotStateService
(GPIO/PWM)      (mode + context)
    │                 │
TB6612FNG       TeacherBehaviorService
(hardware)           │
              ┌──────┴──────────────┐
              │   Integration       │
              │   Wrappers          │
              ├─────────────────────┤
              │ AttendanceService   │──► Your Attendance Backend
              │ RAGService          │──► Your RAG Pipeline
              │ PersonalizationSvc  │──► Your Personalization Engine
              │ VoiceEventInterface │──► Your STT/LLM/TTS Backend
              └─────────────────────┘
```

---

## What This Repo Contains

| File | Purpose |
|---|---|
| `app/main.py` | FastAPI app, lifecycle, mounts web UI |
| `app/core/config.py` | All env-driven settings (GPIO pins, URLs, timeouts) |
| `app/core/security.py` | Optional API key guard |
| `app/api/endpoints/robot_control.py` | WebSocket control + REST stop/start/status |
| `app/api/endpoints/mode.py` | Mode switch REST endpoint |
| `app/services/motor_service.py` | TB6612FNG GPIO/PWM differential drive |
| `app/services/robot_state_service.py` | Current mode, active student, shared state |
| `app/services/teacher_behavior_service.py` | Zoro's teacher persona + prompt building |
| `app/services/integrations/attendance_service.py` | HTTP wrapper → your attendance backend |
| `app/services/integrations/rag_service.py` | HTTP wrapper → your RAG pipeline |
| `app/services/integrations/personalization_service.py` | HTTP wrapper → your personalization engine |
| `app/services/integrations/voice_event_interface.py` | Contract to your STT/LLM/TTS backend |
| `app/utils/helpers.py` | Clamp, rate-limit, retry utilities |
| `web/index.html` | Laptop control UI |
| `web/app.js` | WebSocket client, keyboard input, mode buttons |
| `requirements.txt` | Pi-friendly dependencies |
| `run.sh` | Startup script with safety trap |

**Not included (your existing modules):**
- Database / PostgreSQL schema
- Attendance marking logic internals
- Personalization engine internals
- RAG retrieval internals
- STT / LLM / TTS pipeline

---

## Hardware Wiring (TB6612FNG)

```
12V Battery ──────────────────────► VM  (motor voltage)
12V Battery ──► Buck (12V→5V) ────► Pi  (5V via USB or GPIO pin 2/4)
GND ──────────────────────────────► GND (common ground Pi + driver)

Raspberry Pi Zero 2 W (BCM pins) → TB6612FNG
──────────────────────────────────────────────
GPIO 17  ──► AIN1   (Motor A direction 1)
GPIO 27  ──► AIN2   (Motor A direction 2)
GPIO 18  ──► PWMA   (Motor A speed — hardware PWM)
GPIO 22  ──► BIN1   (Motor B direction 1)
GPIO 23  ──► BIN2   (Motor B direction 2)
GPIO 13  ──► PWMB   (Motor B speed — hardware PWM)
GPIO 24  ──► STBY   (driver enable — pulled HIGH to run)
3.3V     ──► VCC    (logic power for driver)

TB6612FNG Motor outputs:
  AO1, AO2 ──► Left  motors (2x DC, wired in parallel)
  BO1, BO2 ──► Right motors (2x DC, wired in parallel)
```

> **Safety rules enforced in code:**
> - Motors are never powered from the Pi's 5V rail.
> - STBY is pulled LOW on shutdown (disables driver).
> - Emergency stop is called on every WebSocket disconnect.
> - Watchdog stops motors if no command arrives within 0.5 s.

---

## Quick Start

### 1. Clone / copy this repo onto the Pi

```bash
scp -r zoro_ai_robot/ pi@<PI_IP>:~/
ssh pi@<PI_IP>
cd zoro_ai_robot
```

### 2. Create virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
nano .env
```

Key settings to update:

```dotenv
# Your existing service URLs
ATTENDANCE_SERVICE_URL=http://localhost:8001
RAG_SERVICE_URL=http://localhost:8002
PERSONALIZATION_SERVICE_URL=http://localhost:8003
AI_BACKEND_URL=http://localhost:8004

# GPIO pins (defaults match wiring table above)
MOTOR_A_IN1=17
MOTOR_A_IN2=27
MOTOR_A_PWM=18
MOTOR_B_IN1=22
MOTOR_B_IN2=23
MOTOR_B_PWM=13
MOTOR_STBY=24
```

### 4. Start Zoro

```bash
chmod +x run.sh
./run.sh
```

### 5. Open the control panel on your laptop

Navigate to `http://<PI_IP>:8000` in any browser.  
Enter the Pi's IP in the connection field and click **Connect**.

---

## Real-Time Control Protocol

### WebSocket endpoint
```
ws://<PI_IP>:8000/api/robot/ws/control
```

### Client → Server (send at ~20 FPS)
```json
{
  "forward":  true,
  "backward": false,
  "left":     false,
  "right":    true,
  "speed":    70
}
```

### Server → Client (acknowledgement)
```json
{
  "ok":          true,
  "left_speed":  70,
  "right_speed": 42,
  "mode":        "teaching"
}
```

### Differential drive rules
| Command | Left wheel | Right wheel |
|---|---|---|
| Forward | +speed | +speed |
| Backward | −speed | −speed |
| Turn left (moving) | +speed × 0.6 | +speed |
| Turn right (moving) | +speed | +speed × 0.6 |
| Pivot left (stopped) | −speed | +speed |
| Pivot right (stopped) | +speed | −speed |
| Stop (Space) | 0 | 0 |

### Watchdog
Motors stop automatically if no WebSocket frame arrives within **0.5 seconds**.  
Configure via `MOTOR_WATCHDOG_TIMEOUT` in `.env`.

---

## REST API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/robot/status` | Robot state, speed, mode |
| `POST` | `/api/robot/stop` | Emergency stop all motors |
| `POST` | `/api/robot/startstop` | `{"action": "start"}` or `"stop"` |
| `POST` | `/api/mode/switch` | `{"mode": "teaching", "context": {...}}` |
| `GET` | `/api/mode/current` | Returns current mode |
| `GET` | `/api/mode/list` | Returns all valid modes |
| `WS` | `/api/robot/ws/control` | Real-time motor control |

Interactive docs available at `http://<PI_IP>:8000/docs`.

---

## Zoro's Behavior Modes

| Mode | Movement | Speech style | Hints |
|---|---|---|---|
| `attendance` | Slow / patrol | Brief confirmation | N/A |
| `teaching` | Can move | Step-by-step, guided questions | RAG context used |
| `practice` | Can move | Encouraging, Socratic | Small hints only |
| `exam` | Stationary | Strict, minimal | None |
| `idle` | Stopped | Silent unless addressed | N/A |

Mode is switched via the web UI buttons or `POST /api/mode/switch`.

---

## Integration Contracts

### Your services must expose these endpoints:

**Attendance Backend** (`ATTENDANCE_SERVICE_URL`)
```
POST /attendance/mark         { student_id, period_id, timestamp }
GET  /attendance/status       ?student_id=&period_id=
GET  /attendance/period/{id}/roll
```

**RAG Service** (`RAG_SERVICE_URL`)
```
POST /rag/retrieve            { query, subject, top_k }
→ { context: str, sources: [...] }
```

**Personalization Service** (`PERSONALIZATION_SERVICE_URL`)
```
GET  /personalization/profile/{student_id}
POST /personalization/update  { student_id, mode, query, response, subject }
```

**AI Backend** (`AI_BACKEND_URL`) — your STT/LLM/TTS pipeline
```
POST /voice/respond           { system_prompt, message, student_id, session_id }
→ { text: str, audio_url: str|null, metadata: {} }

POST /voice/tts               { text, tts_only: true }
→ { audio_url: str }
```

---

## Performance Notes (Pi Zero 2 W)

- **Single Uvicorn worker** — Pi Zero 2 W has 4 cores but limited RAM (512 MB).
- **No AI inference on-device** — all LLM/TTS/STT calls go to your separate backend.
- **Async throughout** — no blocking calls in the event loop.
- **PWM at 1 kHz** — adequate for DC motor control, not audibly noisy.
- **WebSocket at 20 FPS** — sufficient for smooth control, CPU-friendly.

For hardware PWM (lower CPU usage), consider switching to `pigpio` and updating `motor_service.py` accordingly.

---

## Development (non-Pi host)

On a Mac/Linux dev machine without GPIO, `RPi.GPIO` import fails gracefully and the motor service runs in **simulation mode** — all commands are logged but no GPIO calls are made. Everything else (WebSocket, REST, mode switching, service wrappers) runs normally.

```bash
DEBUG=true ./run.sh
```

---

## File Structure

```
zoro_ai_robot/
├── app/
│   ├── main.py                          # FastAPI app + lifespan
│   ├── core/
│   │   ├── config.py                    # All settings (env-driven)
│   │   └── security.py                  # API key guard
│   ├── api/
│   │   └── endpoints/
│   │       ├── robot_control.py         # WS + REST motor control
│   │       └── mode.py                  # Mode switching REST
│   ├── services/
│   │   ├── motor_service.py             # GPIO/PWM TB6612FNG driver
│   │   ├── robot_state_service.py       # Mode + context state
│   │   ├── teacher_behavior_service.py  # Zoro's persona + prompts
│   │   └── integrations/
│   │       ├── attendance_service.py    # → your attendance backend
│   │       ├── rag_service.py           # → your RAG pipeline
│   │       ├── personalization_service.py # → your personalization engine
│   │       └── voice_event_interface.py # → your STT/LLM/TTS backend
│   └── utils/
│       └── helpers.py                   # Clamp, retry, logging utils
├── web/
│   ├── index.html                       # Laptop control panel UI
│   └── app.js                           # WS client + keyboard input
├── requirements.txt
├── run.sh
└── README.md
```
