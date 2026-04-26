"""
Zoro AI Robot - Motor Service
TB6612FNG or L298N differential drive control via RPi.GPIO / pigpio.
Safe for Raspberry Pi Zero 2 W.

Safety contract:
  - Motors are NEVER powered from the Pi 5V rail.
  - Common ground between Pi and motor driver is assumed.
  - Emergency stop is always called on disconnect / shutdown.
  - STBY (if using TB6612FNG) disables the driver physically when not in use.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from app.core.config import settings

logger = logging.getLogger("zoro.motor")

# ── Try to import GPIO library; fall back to stub for dev on non-Pi hosts ────
try:
    import RPi.GPIO as GPIO

    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    logger.warning("RPi.GPIO not available — running in SIMULATION mode.")


@dataclass
class MotorState:
    left_speed: int = 0  # -100 to 100 (negative = reverse)
    right_speed: int = 0
    motors_enabled: bool = False

    @property
    def is_moving(self) -> bool:
        return self.left_speed != 0 or self.right_speed != 0


class MotorService:
    """
    Controls two motor channels (A = left, B = right) on a TB6612FNG.

    PWM duty cycle maps linearly to speed 0-100 %.
    Negative speed values reverse the motor direction.
    """

    def __init__(self):
        self._state = MotorState()
        self._pwm_a: Optional[object] = None
        self._pwm_b: Optional[object] = None
        self._lock = asyncio.Lock()

    # ── Lifecycle ────────────────────────────────────────────────────────────

    async def initialize(self):
        """Set up GPIO pins and PWM channels."""
        if not GPIO_AVAILABLE:
            logger.info("[SIM] Motor GPIO initialization skipped.")
            self._state.motors_enabled = True  # sim always enabled
            return

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        pins = [
            settings.MOTOR_A_IN1,
            settings.MOTOR_A_IN2,
            settings.MOTOR_B_IN1,
            settings.MOTOR_B_IN2,
        ]
        if hasattr(settings, "MOTOR_STBY") and settings.MOTOR_STBY is not None:
            pins.append(settings.MOTOR_STBY)
            
        GPIO.setup(pins, GPIO.OUT)
        GPIO.setup(settings.MOTOR_A_PWM, GPIO.OUT)
        GPIO.setup(settings.MOTOR_B_PWM, GPIO.OUT)

        # Start PWM at 0 % duty
        self._pwm_a = GPIO.PWM(settings.MOTOR_A_PWM, settings.PWM_FREQUENCY)
        self._pwm_b = GPIO.PWM(settings.MOTOR_B_PWM, settings.PWM_FREQUENCY)
        self._pwm_a.start(0)
        self._pwm_b.start(0)

        # Assert STBY high to enable driver (if applicable)
        if hasattr(settings, "MOTOR_STBY") and settings.MOTOR_STBY is not None:
            GPIO.output(settings.MOTOR_STBY, GPIO.HIGH)
        self._state.motors_enabled = True
        logger.info("GPIO and PWM initialized. Motor driver enabled.")

    async def cleanup(self):
        """Release GPIO resources."""
        if not GPIO_AVAILABLE:
            return
        await self.emergency_stop()
        if self._pwm_a:
            self._pwm_a.stop()
        if self._pwm_b:
            self._pwm_b.stop()
        GPIO.cleanup()
        logger.info("GPIO cleaned up.")

    # ── Public motor API ─────────────────────────────────────────────────────

    async def enable_motors(self):
        """Assert STBY high (if used) — driver active."""
        async with self._lock:
            if GPIO_AVAILABLE and hasattr(settings, "MOTOR_STBY") and settings.MOTOR_STBY is not None:
                GPIO.output(settings.MOTOR_STBY, GPIO.HIGH)
            self._state.motors_enabled = True
            logger.info("Motor driver enabled.")

    async def disable_motors(self):
        """Pull STBY low (if used) — driver off (coasts / high-Z)."""
        async with self._lock:
            if GPIO_AVAILABLE and hasattr(settings, "MOTOR_STBY") and settings.MOTOR_STBY is not None:
                GPIO.output(settings.MOTOR_STBY, GPIO.LOW)
            self._state.motors_enabled = False
            logger.info("Motor driver disabled.")

    async def control_motors(self, left_speed: int, right_speed: int):
        """
        Set motor speeds.
        left_speed, right_speed: integers in [-100, 100].
        Positive = forward, negative = reverse, 0 = stop.
        """
        left_speed = max(-100, min(100, int(left_speed)))
        right_speed = max(-100, min(100, int(right_speed)))

        async with self._lock:
            if not self._state.motors_enabled:
                return

            self._apply_motor("A", left_speed)
            self._apply_motor("B", right_speed)
            self._state.left_speed = left_speed
            self._state.right_speed = right_speed

    async def emergency_stop(self):
        """Immediately stop both motors (brake mode)."""
        async with self._lock:
            self._brake_motor("A")
            self._brake_motor("B")
            self._state.left_speed = 0
            self._state.right_speed = 0

    def get_state(self) -> dict:
        return {
            "left_speed": self._state.left_speed,
            "right_speed": self._state.right_speed,
            "motors_enabled": self._state.motors_enabled,
            "is_moving": self._state.is_moving,
        }

    # ── Private helpers ──────────────────────────────────────────────────────

    def _apply_motor(self, channel: str, speed: int):
        """
        Set direction and PWM duty for one motor channel.
        channel: "A" (left) | "B" (right)
        speed: -100 to 100
        """
        if not GPIO_AVAILABLE:
            logger.debug(f"[SIM] Motor {channel} speed={speed}")
            return

        duty = abs(speed)

        if channel == "A":
            in1, in2, pwm = settings.MOTOR_A_IN1, settings.MOTOR_A_IN2, self._pwm_a
        else:
            in1, in2, pwm = settings.MOTOR_B_IN1, settings.MOTOR_B_IN2, self._pwm_b

        if speed > 0:  # forward
            GPIO.output(in1, GPIO.HIGH)
            GPIO.output(in2, GPIO.LOW)
        elif speed < 0:  # reverse
            GPIO.output(in1, GPIO.LOW)
            GPIO.output(in2, GPIO.HIGH)
        else:  # coast
            GPIO.output(in1, GPIO.LOW)
            GPIO.output(in2, GPIO.LOW)

        pwm.ChangeDutyCycle(duty)

    def _brake_motor(self, channel: str):
        """Hard brake: both IN pins high, PWM 100 %."""
        if not GPIO_AVAILABLE:
            logger.debug(f"[SIM] Motor {channel} BRAKE")
            return

        if channel == "A":
            in1, in2, pwm = settings.MOTOR_A_IN1, settings.MOTOR_A_IN2, self._pwm_a
        else:
            in1, in2, pwm = settings.MOTOR_B_IN1, settings.MOTOR_B_IN2, self._pwm_b

        GPIO.output(in1, GPIO.HIGH)
        GPIO.output(in2, GPIO.HIGH)
        pwm.ChangeDutyCycle(0)

