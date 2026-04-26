"""
Zoro AI Robot - RAG Service Wrapper
Thin client over your existing RAG retrieval backend.
Zoro calls your pipeline; it does NOT run embeddings locally.
"""

import logging
from typing import Optional

import httpx
from app.core.config import settings

logger = logging.getLogger("zoro.rag_svc")


class RAGService:
    """
    Interface to your existing RAG system.
    Endpoint contract (adapt to your actual API):
      POST /rag/retrieve   { query, subject, top_k }
      → { context: str, sources: [...] }
    """

    def __init__(self, base_url: Optional[str] = None):
        self._base_url = (base_url or settings.RAG_SERVICE_URL).rstrip("/")
        self._timeout = 8.0

    async def retrieve(
        self,
        query: str,
        subject: Optional[str] = None,
        top_k: int = 3,
    ) -> str:
        """
        Retrieve relevant context for a query.
        Returns the concatenated context string for injection into Zoro's prompt.
        """
        payload = {"query": query, "subject": subject, "top_k": top_k}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/rag/retrieve", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data.get("context", "")
        except httpx.HTTPStatusError as exc:
            logger.error(f"RAG retrieve failed [{exc.response.status_code}]: {exc}")
            return ""
        except httpx.RequestError as exc:
            logger.error(f"RAG service unreachable: {exc}")
            return ""

    async def retrieve_with_sources(
        self,
        query: str,
        subject: Optional[str] = None,
        top_k: int = 3,
    ) -> dict:
        """
        Retrieve context AND source metadata.
        Returns dict with keys: context (str), sources (list).
        """
        payload = {"query": query, "subject": subject, "top_k": top_k}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/rag/retrieve", json=payload)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.error(f"RAG retrieve_with_sources failed: {exc}")
            return {"context": "", "sources": []}

