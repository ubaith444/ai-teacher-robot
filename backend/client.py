import asyncio
import json
import logging

import cv2
import pyaudio
import websockets

# ==========================================
# CONFIGURATION
# ==========================================
LAPTOP_IP = "localhost"
WS_BASE = f"http://{LAPTOP_IP}:8000/api"
VOICE_WS_URL = f"ws://{LAPTOP_IP}:8000/api/voice/stream/zoro2026-session"
VIDEO_WS_URL = f"ws://{LAPTOP_IP}:8000/api/attendance/video-stream"

# Audio Settings
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ZoroClient")

audio = pyaudio.PyAudio()

# --- SMART MIC PICKER ---
mic_index = None
print("\n[SCAN] SCANNING AUDIO DEVICES...")
for i in range(audio.get_device_count()):
    info = audio.get_device_info_by_index(i)
    if info["maxInputChannels"] > 0:
        print(f"[MIC] ID {i}: {info['name']}")
        if "USB" in info["name"] and mic_index is None:
            mic_index = i

if mic_index is not None:
    print(f"[SUCCESS] Auto-selected USB Mic at ID {mic_index}")

mic_stream = None
for i in range(audio.get_device_count()):
    try:
        current_idx = mic_index if mic_index is not None else i
        info = audio.get_device_info_by_index(current_idx)
        if info["maxInputChannels"] > 0:
            mic_stream = audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                input_device_index=current_idx,
                frames_per_buffer=CHUNK,
            )
            print(f"[SUCCESS] Mic working on ID {current_idx}!")
            break
    except Exception:
        mic_index = None
        continue

if not mic_stream:
    print("[ERROR] NO WORKING MICROPHONE FOUND!")
    exit(1)

# Speaker stream for raw PCM
speaker_stream = audio.open(
    format=FORMAT, channels=CHANNELS, rate=RATE, output=True, frames_per_buffer=CHUNK
)

# ==========================================
# 1. VIDEO STREAMING
# ==========================================
cap = cv2.VideoCapture(0)
has_camera = cap.isOpened()


async def stream_video():
    if not has_camera:
        return
    while True:
        try:
            async with websockets.connect(VIDEO_WS_URL) as ws:
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    _, buffer = cv2.imencode(
                        ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 50]
                    )
                    await ws.send(buffer.tobytes())
                    await asyncio.sleep(0.1)
        except Exception:
            await asyncio.sleep(5)


# ==========================================
# 2. VOICE AGENT (PCM STREAMING)
# ==========================================
async def stream_voice():
    while True:
        try:
            logger.info(f"Connecting Voice to {VOICE_WS_URL}...")
            async with websockets.connect(VOICE_WS_URL) as ws:
                logger.info("[VOICE] Full-Duplex Voice Active.")

                async def send_mic():
                    while True:
                        try:
                            data = mic_stream.read(CHUNK, exception_on_overflow=False)
                            await ws.send(data)
                            await asyncio.sleep(0.01)
                        except Exception:
                            break

                async def receive_speaker():
                    while True:
                        try:
                            msg = await ws.recv()
                            if isinstance(msg, bytes):
                                speaker_stream.write(msg)
                            else:
                                data = json.loads(msg)
                                if data.get("type") == "llm_chunk":
                                    print(f"[ZORO] Zoro: {data.get('text')}")
                        except Exception:
                            break

                await asyncio.gather(send_mic(), receive_speaker())
        except Exception as e:
            logger.error(f"Voice Error: {e}. Retrying...")
            await asyncio.sleep(5)


async def main():
    await asyncio.gather(stream_video(), stream_voice())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down.")
    finally:
        mic_stream.stop_stream()
        mic_stream.close()
        speaker_stream.stop_stream()
        speaker_stream.close()
        audio.terminate()
