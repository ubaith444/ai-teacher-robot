"""
app/utils/image_processing.py
──────────────────────────────
Low-level image helpers used by face_service and enrollment endpoints.
All operations are CPU-only OpenCV calls; optimised for Raspberry Pi Zero 2 W.

Pipeline summary (per frame)
─────────────────────────────
1. bytes_to_bgr / b64_to_bgr → decode raw input
2. resize_to_max_width         → cap width at MAX_IMAGE_WIDTH (320 px)
3. to_gray                     → single-channel for LBPH
4. normalise_face_roi          → fixed-size + histogram equalisation
5. bbox_to_dict                → canonical {x, y, w, h} output
"""

from __future__ import annotations

import base64
import io
from typing import Optional, Tuple

import cv2
import numpy as np
import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)


# ── Decode helpers ─────────────────────────────────────────────────────────────

def bytes_to_bgr(raw: bytes) -> Optional[np.ndarray]:
    """
    Decode raw image bytes (JPEG, PNG, BMP, …) into a BGR ndarray.
    Returns None if OpenCV cannot decode the data (corrupt / unsupported format).
    """
    if not raw:
        return None
    try:
        arr = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return img  # None if decoding fails
    except Exception as exc:
        log.warning("image_processing.bytes_to_bgr.failed", error=str(exc))
        return None


def b64_to_bgr(encoded: str) -> Optional[np.ndarray]:
    """
    Decode a base64-encoded image string into a BGR ndarray.
    Strips 'data:image/...;base64,' data-URI prefixes automatically.
    """
    if not encoded:
        return None
    try:
        if "," in encoded:
            encoded = encoded.split(",", 1)[1]
        raw = base64.b64decode(encoded)
        return bytes_to_bgr(raw)
    except Exception as exc:
        log.warning("image_processing.b64_to_bgr.failed", error=str(exc))
        return None


# ── Resize ─────────────────────────────────────────────────────────────────────

def resize_to_max_width(
    img: np.ndarray,
    max_width: int = settings.MAX_IMAGE_WIDTH,
) -> np.ndarray:
    """
    Proportionally resize *img* so its width ≤ *max_width*.
    Returns the original array unchanged if already within bounds.
    Uses INTER_AREA for high-quality downscaling on Pi hardware.
    """
    h, w = img.shape[:2]
    if w <= max_width:
        return img
    scale = max_width / w
    new_w = max_width
    new_h = int(h * scale)
    return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)


# ── Grayscale ──────────────────────────────────────────────────────────────────

def to_gray(img: np.ndarray) -> np.ndarray:
    """
    Convert a BGR image to grayscale.
    Returns the image unchanged if it is already single-channel.
    """
    if img.ndim == 2 or img.shape[2] == 1:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


# ── LBPH normalisation ─────────────────────────────────────────────────────────

def normalise_face_roi(
    gray_roi: np.ndarray,
    target_size: Tuple[int, int] = (100, 100),
) -> np.ndarray:
    """
    Resize a grayscale face ROI to a fixed size and apply histogram
    equalisation to compensate for lighting variation.

    LBPH doesn't require a fixed size but consistent dimensions improve accuracy.
    """
    resized = cv2.resize(gray_roi, target_size, interpolation=cv2.INTER_AREA)
    return cv2.equalizeHist(resized)


# ── Frame preprocessing pipeline ───────────────────────────────────────────────

def preprocess_frame(raw_bytes: bytes) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """
    Full preprocessing from raw bytes → (bgr, gray) ready for detection.

    Steps: decode → resize to MAX_IMAGE_WIDTH → grayscale.
    Returns None if the bytes cannot be decoded.
    """
    bgr = bytes_to_bgr(raw_bytes)
    if bgr is None:
        log.warning("preprocess_frame.decode_failed")
        return None
    bgr = resize_to_max_width(bgr)
    gray = to_gray(bgr)
    return bgr, gray


def preprocess_bgr(bgr: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Preprocessing for an already-decoded BGR image.
    Returns (resized_bgr, gray).
    """
    bgr = resize_to_max_width(bgr)
    gray = to_gray(bgr)
    return bgr, gray


# ── Bounding box helpers ───────────────────────────────────────────────────────

def bbox_to_dict(x: int, y: int, w: int, h: int) -> dict:
    """Convert a bounding box tuple to the canonical {x, y, w, h} dict."""
    return {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}


def extract_face_roi(gray: np.ndarray, bbox: dict) -> np.ndarray:
    """
    Slice the face ROI from a grayscale image.
    *bbox* must contain keys 'x', 'y', 'w', 'h'.
    """
    x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
    return gray[y : y + h, x : x + w]


# ── Encode back to bytes ───────────────────────────────────────────────────────

def bgr_to_jpeg_bytes(bgr: np.ndarray, quality: int = 80) -> bytes:
    """Encode a BGR ndarray to JPEG bytes (for storage or forwarding)."""
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("cv2.imencode failed — cannot convert image to JPEG.")
    return buf.tobytes()


# ── Validation ─────────────────────────────────────────────────────────────────

def validate_image_file(raw: bytes, max_bytes: int = 5 * 1024 * 1024) -> Optional[str]:
    """
    Validate raw image bytes for enrollment.

    Returns:
        None if valid, or an error message string.
    """
    if not raw:
        return "Empty file."
    if len(raw) > max_bytes:
        return f"File too large ({len(raw) // 1024} KB > {max_bytes // 1024} KB max)."
    bgr = bytes_to_bgr(raw)
    if bgr is None:
        return "File could not be decoded as an image (corrupt or unsupported format)."
    return None
