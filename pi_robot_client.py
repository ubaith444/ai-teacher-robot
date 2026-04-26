import asyncio
import json
import logging
import tkinter as tk
from threading import Thread

import cv2
import numpy as np
import pyaudio
import websockets


# ==========================================
# 0. VISUAL FACE (HDMI DISPLAY)
# ==========================================
class RobotFace:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Zoro AI Face")
        self.root.attributes("-fullscreen", True)
        self.root.configure(bg="black")

        self.canvas = tk.Canvas(self.root, bg="black", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.screen_w = self.root.winfo_screenwidth()
        self.screen_h = self.root.winfo_screenheight()

        # Colors (Neon Cyan/Blue)
        self.color = "#00f2ff"
        self.state = "idle"

        self.draw_face()
        self.blink_loop()

    def draw_face(self):
        self.canvas.delete("all")
        mid_x = self.screen_w // 2
        mid_y = self.screen_h // 2

        if self.state == "idle":
            # Two Large Friendly Eyes
            self.canvas.create_oval(
                mid_x - 200,
                mid_y - 100,
                mid_x - 50,
                mid_y + 100,
                fill=self.color,
                outline=self.color,
                tags="eye_l",
            )
            self.canvas.create_oval(
                mid_x + 50,
                mid_y - 100,
                mid_x + 200,
                mid_y + 100,
                fill=self.color,
                outline=self.color,
                tags="eye_r",
            )
        elif self.state == "listening":
            # Pulsing Circular Eyes
            self.canvas.create_oval(
                mid_x - 180,
                mid_y - 80,
                mid_x - 70,
                mid_y + 30,
                fill=self.color,
                outline="white",
                width=5,
                tags="eye_l",
            )
            self.canvas.create_oval(
                mid_x + 70,
                mid_y - 80,
                mid_x + 180,
                mid_y + 30,
                fill=self.color,
                outline="white",
                width=5,
                tags="eye_r",
            )
        elif self.state == "speaking":
            # Moving Waveform Mouth
            self.canvas.create_oval(
                mid_x - 150,
                mid_y - 120,
                mid_x - 50,
                mid_y - 20,
                fill=self.color,
                tags="eye_l",
            )
            self.canvas.create_oval(
                mid_x + 50,
                mid_y - 120,
                mid_x + 150,
                mid_y - 20,
                fill=self.color,
                tags="eye_r",
            )
            # Mouth line
            self.canvas.create_rectangle(
                mid_x - 100,
                mid_y + 100,
                mid_x + 100,
                mid_y + 110,
                fill=self.color,
                tags="mouth",
            )

    def set_state(self, state):
        self.state = state
        self.root.after(0, self.draw_face)

    def blink_loop(self):
        if self.state == "idle":
            self.canvas.itemconfig("eye_l", state="hidden")
            self.canvas.itemconfig("eye_r", state="hidden")
            self.root.after(
                200, lambda: self.canvas.itemconfig("eye_l", state="normal")
            )
            self.root.after(
                200, lambda: self.canvas.itemconfig("eye_r", state="normal")
            )
        self.root.after(3000, self.blink_loop)

    def start(self):
        self.root.mainloop()


# Global Face Instance
face = None


def run_face():
    global face
    face = RobotFace()
    face.start()


# Start UI in background
Thread(target=run_face, daemon=True).start()

# Try import RPi.GPIO (Will only work on the Raspberry Pi)
try:
    import RPi.GPIO as GPIO

    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False

# ==========================================
# CONFIGURATION
# ==========================================
LAPTOP_IP = "localhost"
LAPTOP_WS_URL = f"ws://{LAPTOP_IP}:8000/api/voice/stream/zoro2026-session"
LAPTOP_VIDEO_WS_URL = f"ws://{LAPTOP_IP}:8000/api/attendance/video-stream"
MANUAL_MIC_ID = None  # Set this to an ID from list_audio.py if auto-detection fails


# Audio Settings
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PiRobot")

# Initialize Audio
audio = pyaudio.PyAudio()

# --- SMART USB MIC & SPEAKER PICKER ---
mic_index = MANUAL_MIC_ID
speaker_index = None

logger.info("[SCAN] Scanning for Audio Devices...")
for i in range(audio.get_device_count()):
    info = audio.get_device_info_by_index(i)
    name_up = info["name"].upper()

    # MIC PICKER
    if info["maxInputChannels"] > 0:
        logger.info(f"|-- Found Input ID {i}: {info['name']}")
        if any(k in name_up for k in ["USB", "PNP", "GENERIC", "EXTERNAL"]):
            if mic_index is None:
                mic_index = i
                logger.info(f" >>> Mic Match: {info['name']} (ID {i})")

    # SPEAKER PICKER
    if info["maxOutputChannels"] > 0:
        logger.info(f"|-- Found Output ID {i}: {info['name']}")
        if any(k in name_up for k in ["USB", "PNP", "GENERIC", "EXTERNAL", "AUDIO"]):
            if speaker_index is None:
                speaker_index = i
                logger.info(f" >>> Speaker Match: {info['name']} (ID {i})")

# 1. Open Mic Stream
try:
    mic_stream = audio.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        input_device_index=mic_index,
        frames_per_buffer=CHUNK,
    )
    logger.info(f"[MIC] Stream active on ID {mic_index}")
except Exception as e:
    logger.error(f"[MIC] Failed to open: {e}")
    exit(1)

# 2. Open Speaker Stream (with fallback for sample rate)
speaker_stream = None
for s_rate in [RATE, 44100, 48000]:
    try:
        speaker_stream = audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=s_rate,
            output=True,
            output_device_index=speaker_index,
            frames_per_buffer=CHUNK,
        )
        logger.info(f"[SPEAKER] Active on ID {speaker_index} at {s_rate}Hz")
        # Update global RATE if it changed for the speaker (needs resampling in logic)
        # For now, we assume 16k works on at least one device
        break
    except Exception:
        continue

if not speaker_stream:
    logger.error("[SPEAKER] Could not find a compatible output device.")
    exit(1)

# ==========================================
# 0. HARDWARE - L298N MOTOR DRIVER
# ==========================================
MOTOR_EN_A = 18
MOTOR_IN1 = 17
MOTOR_IN2 = 27
MOTOR_IN3 = 22
MOTOR_IN4 = 23
MOTOR_EN_B = 13
PWM_FREQ = 1000

pwd_a = None
pwd_b = None

if GPIO_AVAILABLE:
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(
        [MOTOR_EN_A, MOTOR_IN1, MOTOR_IN2, MOTOR_IN3, MOTOR_IN4, MOTOR_EN_B], GPIO.OUT
    )

    pwd_a = GPIO.PWM(MOTOR_EN_A, PWM_FREQ)
    pwd_b = GPIO.PWM(MOTOR_EN_B, PWM_FREQ)
    pwd_a.start(0)
    pwd_b.start(0)


def set_motors(left_speed, right_speed):
    """Speed ranging from -100 to 100"""
    if not GPIO_AVAILABLE:
        # logger.info(f"[SIM MOTOR] Left: {left_speed}, Right: {right_speed}")
        return

    # Left Channel (Motor A)
    if left_speed > 0:
        GPIO.output(MOTOR_IN1, GPIO.HIGH)
        GPIO.output(MOTOR_IN2, GPIO.LOW)
    elif left_speed < 0:
        GPIO.output(MOTOR_IN1, GPIO.LOW)
        GPIO.output(MOTOR_IN2, GPIO.HIGH)
    else:
        GPIO.output(MOTOR_IN1, GPIO.LOW)
        GPIO.output(MOTOR_IN2, GPIO.LOW)
    pwd_a.ChangeDutyCycle(abs(left_speed))

    # Right Channel (Motor B)
    if right_speed > 0:
        GPIO.output(MOTOR_IN3, GPIO.HIGH)
        GPIO.output(MOTOR_IN4, GPIO.LOW)
    elif right_speed < 0:
        GPIO.output(MOTOR_IN3, GPIO.LOW)
        GPIO.output(MOTOR_IN4, GPIO.HIGH)
    else:
        GPIO.output(MOTOR_IN3, GPIO.LOW)
        GPIO.output(MOTOR_IN4, GPIO.LOW)
    pwd_b.ChangeDutyCycle(abs(right_speed))


# ==========================================
# 1. VIDEO STREAMING
# ==========================================
async def video_websocket_loop():
    while True:
        try:
            async with websockets.connect(LAPTOP_VIDEO_WS_URL) as ws:
                cap = cv2.VideoCapture(0)
                if not cap.isOpened():
                    logger.error(
                        "[VIDEO] Could not open camera. Check connection or permissions."
                    )
                    break  # Stop trying if hardware is missing

                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
                logger.info("[VIDEO] Camera Stream Active.")
                try:
                    while cap.isOpened():
                        ret, frame = cap.read()
                        if not ret:
                            logger.warning("[VIDEO] Failed to grab frame.")
                            break
                        _, buffer = cv2.imencode(
                            ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70]
                        )
                        await ws.send(buffer.tobytes())
                        await asyncio.sleep(0.1)
                finally:
                    cap.release()
        except Exception as e:
            logger.error(f"[VIDEO] Stream Error: {e}")
            await asyncio.sleep(5)


# ==========================================
# 2. VOICE & INTERRUPT LOGIC
# ==========================================
is_playing = False


async def send_audio(websocket):
    global is_playing
    while True:
        try:
            data = mic_stream.read(CHUNK, exception_on_overflow=False)

            # --- BARGE-IN (INTERRUPT) DETECTION ---
            audio_data = np.frombuffer(data, dtype=np.int16)
            peak = np.max(np.abs(audio_data))

            if peak > 2000:  # We are speaking
                if face:
                    face.set_state("listening")
            elif not is_playing:
                if face:
                    face.set_state("idle")

            if is_playing and peak > 5000:  # High threshold
                logger.info("[AUDIO] Barge-in! Interrupting playback.")
                is_playing = False
                # Server will see new audio and auto-interrupt

            await websocket.send(data)
            await asyncio.sleep(0.01)
        except Exception:
            break


async def receive_audio(websocket):
    global is_playing
    while True:
        try:
            message = await websocket.recv()
            if isinstance(message, bytes):
                is_playing = True
                if face:
                    face.set_state("speaking")
                speaker_stream.write(message)
                # After writing a chunk, check if there's more.
                # If not, set back to idle after a short delay
                if face:
                    face.root.after(
                        500, lambda: face.set_state("idle") if not is_playing else None
                    )
            else:
                data = json.loads(message)
                if data.get("type") == "interrupt":
                    is_playing = False
                    if face:
                        face.set_state("idle")
                elif "motor" in data:
                    cmd = data["motor"]
                    if cmd == "forward":
                        set_motors(80, 80)
                    elif cmd == "backward":
                        set_motors(-80, -80)
                    elif cmd == "left":
                        set_motors(-60, 60)
                    elif cmd == "right":
                        set_motors(60, -60)
                    elif cmd == "stop":
                        set_motors(0, 0)
        except Exception:
            break


async def audio_websocket_loop():
    while True:
        try:
            logger.info(f"Connecting to AI Brain at {LAPTOP_WS_URL}...")
            async with websockets.connect(LAPTOP_WS_URL) as websocket:
                logger.info("[WS] Connected! High-Performance Pipeline Active.")
                await asyncio.gather(send_audio(websocket), receive_audio(websocket))
        except Exception as e:
            logger.error(f"Brain connection lost. Retrying... ({e})")
            await asyncio.sleep(5)


async def main():
    await asyncio.gather(audio_websocket_loop(), video_websocket_loop())


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
        if GPIO_AVAILABLE:
            set_motors(0, 0)
            GPIO.cleanup()
