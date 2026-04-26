"""
app/services/drive_service.py
─────────────────────────────
Google Drive folder ingestion for bulk student enrollment.
Uses 'gdown' for robust downloading of public shared folders.

Supports:
  • Public shared folders (no OAuth required)
  • Flat folder structures (images directly in root)
  • Nested folder structures (one subfolder per student)
  • Sequential processing to minimize RAM usage
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import gdown
import numpy as np
import structlog

log = structlog.get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
BLUR_THRESHOLD = 80.0
TOO_FEW_IMAGES_WARN = 3

# ── Data containers ────────────────────────────────────────────────────────────

@dataclass
class DriveFileInfo:
    path: Path
    name: str
    size_bytes: int = 0
    is_valid_image: bool = False

@dataclass
class StudentImageGroup:
    student_name: str
    folder_id: str
    files: List[DriveFileInfo] = field(default_factory=list)
    valid_image_count: int = 0

@dataclass
class StudentAnalysis:
    student_name: str
    total_files: int = 0
    valid_images: int = 0
    images_with_faces: int = 0
    is_enrollable: bool = False
    warnings: List[str] = field(default_factory=list)

@dataclass
class DatasetReport:
    folder_url: str
    student_count: int = 0
    enrollable_student_count: int = 0
    student_analyses: List[StudentAnalysis] = field(default_factory=list)
    analyzed_at: float = field(default_factory=time.time)

# ── URL Parsing ────────────────────────────────────────────────────────────────

def extract_folder_id(folder_url: str) -> Optional[str]:
    patterns = [
        r"/drive/folders/([a-zA-Z0-9_-]{20,})",
        r"[?&]id=([a-zA-Z0-9_-]{20,})",
    ]
    for pat in patterns:
        m = re.search(pat, folder_url)
        if m:
            return m.group(1)
    return None

# ── Ingestion Logic (gdown powered) ───────────────────────────────────────────

def _sanitise_name(raw: str) -> str:
    # Remove leading class prefixes and common suffixes
    clean = re.sub(r"^[A-Z0-9]+-[A-Z0-9]+_", "", raw)
    clean = re.sub(r"[\s_-]*\(\d+\)$", "", clean)
    return clean.replace("_", " ").strip()

async def discover_students_in_folder(folder_url: str) -> List[StudentImageGroup]:
    """
    Downloads the Drive folder using gdown and parses the local directory.
    Uses run_in_executor to avoid blocking the FastAPI event loop.
    Also supports Local Directory paths for bypassing Drive limits.
    """
    import asyncio
    groups: List[StudentImageGroup] = []
    
    # ── Local File System Fallback ──────────────────────────────
    # Bypasses Google Drive entirely if a local folder path is provided
    try:
        if os.path.exists(folder_url) and os.path.isdir(folder_url):
            log.info("drive.local_folder_detected", path=folder_url)
            root_path = Path(folder_url)
            
            subfolders = [d for d in root_path.iterdir() if d.is_dir() and not d.name.startswith(".")]
            
            if subfolders:
                for sf in subfolders:
                    student_name = _sanitise_name(sf.name)
                    group = StudentImageGroup(student_name=student_name, folder_id=sf.name)
                    for f in sf.iterdir():
                        if f.is_file() and f.suffix.lower() in VALID_EXTENSIONS:
                            group.files.append(DriveFileInfo(path=f, name=f.name, size_bytes=f.stat().st_size, is_valid_image=True))
                            group.valid_image_count += 1
                    if group.files:
                        groups.append(group)
            else:
                from collections import defaultdict
                flat_groups = defaultdict(list)
                for f in root_path.iterdir():
                    if f.is_file() and f.suffix.lower() in VALID_EXTENSIONS:
                        student_name = _sanitise_name(f.stem)
                        flat_groups[student_name].append(f)
                
                for name, files in flat_groups.items():
                    group = StudentImageGroup(student_name=name, folder_id="root")
                    for f in files:
                        group.files.append(DriveFileInfo(path=f, name=f.name, size_bytes=f.stat().st_size, is_valid_image=True))
                        group.valid_image_count += 1
                    groups.append(group)
            
            return groups
    except Exception as e:
        log.warning("drive.local_fallback_error", error=str(e))
        pass

    # ── Google Drive Download ───────────────────────────────────
    # Create a temporary directory for the download
    temp_dir = tempfile.mkdtemp(prefix="zoro_drive_")
    try:
        def _safe_download():
            import sys
            import io
            from contextlib import redirect_stdout, redirect_stderr
            # Suppress all gdown output to avoid cp1252 charmap Windows crashes
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                return gdown.download_folder(
                    url=folder_url, 
                    output=temp_dir, 
                    quiet=True, 
                    use_cookies=False
                )
        await loop.run_in_executor(None, _safe_download)
    except Exception as e:
        # Google Drive often blocks / errors out on individual files.
        # OR it might be DNS/proxy issues. 
        log.warning("drive.download_interrupted", error=str(e), note="Processing whatever was downloaded.")


    # Walk the downloaded content
    root_path = Path(temp_dir)

    # DEBUG: Log what was actually downloaded
    all_files = list(root_path.rglob("*"))
    log.info("drive.path_scan", count=len(all_files), root=str(root_path))
    for f in all_files[:10]: # Log first 10 for debugging
        log.info("drive.file_found", name=f.name, is_dir=f.is_dir())

        # Check for subfolders (nested structure)
        subfolders = [d for d in root_path.iterdir() if d.is_dir() and not d.name.startswith(".")]
        
        if subfolders:
            for sf in subfolders:
                student_name = _sanitise_name(sf.name)
                group = StudentImageGroup(student_name=student_name, folder_id=sf.name)
                for f in sf.iterdir():
                    if f.is_file() and f.suffix.lower() in VALID_EXTENSIONS:
                        group.files.append(DriveFileInfo(path=f, name=f.name, size_bytes=f.stat().st_size, is_valid_image=True))
                        group.valid_image_count += 1
                if group.files:
                    groups.append(group)
        else:
            # Flat structure
            from collections import defaultdict
            flat_groups = defaultdict(list)
            for f in root_path.iterdir():
                if f.is_file() and f.suffix.lower() in VALID_EXTENSIONS:
                    student_name = _sanitise_name(f.stem)
                    flat_groups[student_name].append(f)
            
            for name, files in flat_groups.items():
                group = StudentImageGroup(student_name=name, folder_id="root")
                for f in files:
                    group.files.append(DriveFileInfo(path=f, name=f.name, size_bytes=f.stat().st_size, is_valid_image=True))
                    group.valid_image_count += 1
                groups.append(group)

        log.info("drive.discovery_complete", students=len(groups), path=temp_dir)
        return groups

# ── Face Detection Helper ─────────────────────────────────────────────────────

def _has_face(img_path: Path) -> bool:
    """Quick face check for analysis."""
    try:
        img = cv2.imread(str(img_path))
        if img is None: return False
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        data_dir = cv2.data.haarcascades
        cascade = cv2.CascadeClassifier(os.path.join(data_dir, "haarcascade_frontalface_default.xml"))
        faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(30, 30))
        return len(faces) > 0
    except:
        return False

# ── Public API ────────────────────────────────────────────────────────────────

async def analyse_drive_dataset(folder_url: str) -> DatasetReport:
    groups = await discover_students_in_folder(folder_url)
    report = DatasetReport(folder_url=folder_url)
    report.student_count = len(groups)
    
    for g in groups:
        analysis = StudentAnalysis(student_name=g.student_name, total_files=len(g.files), valid_images=g.valid_image_count)
        # Check first image for face
        if g.files and _has_face(g.files[0].path):
            analysis.images_with_faces = 1
            analysis.is_enrollable = True
        
        report.student_analyses.append(analysis)
        if analysis.is_enrollable:
            report.enrollable_student_count += 1
            
    return report

async def fetch_student_images(group: StudentImageGroup, max_images: int = 10) -> Tuple[List[np.ndarray], int, int]:
    """Load images from local disk (already downloaded by discovery)."""
    bgr_images = []
    for f in group.files[:max_images]:
        img = cv2.imread(str(f.path))
        if img is not None:
            bgr_images.append(img)
    return bgr_images, len(bgr_images), 0

def cleanup_drive_temp(groups: List[StudentImageGroup]):
    """Clean up the temp directories created during enrollment."""
    if not groups: return
    # Find the parent temp dir from the first file path
    try:
        temp_root = groups[0].files[0].path.parent.parent
        if "zoro_drive_" in temp_root.name:
            shutil.rmtree(temp_root)
            log.info("drive.temp_cleanup_done", path=str(temp_root))
    except:
        pass

