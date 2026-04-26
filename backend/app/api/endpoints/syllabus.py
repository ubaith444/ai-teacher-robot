from __future__ import annotations

import os
import shutil
import tempfile
from typing import List

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.core.orchestrator import get_orchestrator
from app.core.security import get_current_user

router = APIRouter(prefix="/syllabus", tags=["Syllabus"])
log = structlog.get_logger(__name__)

class UploadResponse(BaseModel):
    success: bool
    message: str
    docs_loaded: int
    chunks_created: int
    time_seconds: float

@router.post(
    "/upload",
    response_model=UploadResponse,
    summary="Upload a syllabus file (PDF, DOCX, PPTX) for RAG ingestion.",
)
async def upload_syllabus(
    file: UploadFile = File(...),
    _user: str = Depends(get_current_user),
) -> UploadResponse:
    """
    Upload a document, extract text, and ingest it into the RAG vector store.
    Supports: PDF, DOCX, PPTX, TXT, MD, CSV.
    Max size: 50MB (enforced by FastAPI/Nginx if configured, but we check here too).
    """
    # 1. Validate file extension
    ext = os.path.splitext(file.filename)[1].lower()
    allowed = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".txt", ".md", ".csv", ".json"}
    if ext not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type {ext} not supported. Use PDF, DOCX, or PPTX.",
        )

    # 2. Save to temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        try:
            content = await file.read()
            if len(content) > 50 * 1024 * 1024:  # 50MB
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="File too large. Max 50MB allowed.",
                )
            tmp.write(content)
            tmp_path = tmp.name
        except Exception as e:
            log.error("syllabus.upload_failed", error=str(e))
            raise HTTPException(status_code=500, detail="Failed to save uploaded file.")

    # 3. Ingest into Orchestrator
    try:
        orch = get_orchestrator()
        # We need to rename the temp file to the original filename so DocumentLoader can detect subject/grade
        # But tempfile.NamedTemporaryFile usually has a random name.
        # Let's create a temp directory instead.
        temp_dir = tempfile.mkdtemp()
        safe_name = "".join(c for c in file.filename if c.isalnum() or c in "._- ").strip()
        final_path = os.path.join(temp_dir, safe_name)
        shutil.move(tmp_path, final_path)

        result = await orch.ingest_documents(final_path)
        
        # Cleanup temp dir
        shutil.rmtree(temp_dir)

        return UploadResponse(
            success=True,
            message=f"Successfully ingested {file.filename}",
            docs_loaded=result.docs_loaded,
            chunks_created=result.chunks_created,
            time_seconds=result.time_seconds,
        )
    except Exception as e:
        log.error("syllabus.ingestion_failed", error=str(e))
        # Cleanup
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {str(e)}")

@router.get("/stats")
async def get_syllabus_stats(_user: str = Depends(get_current_user)):
    orch = get_orchestrator()
    return orch.get_stats()
