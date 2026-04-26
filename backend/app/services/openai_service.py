"""
services/openai_service.py — OpenAI GPT-4o-mini integration for high-performance streaming.
"""

from __future__ import annotations

import logging
import time
from typing import AsyncGenerator, Dict, List, Optional, Tuple

import openai
from app.core.config import settings
from app.schemas import Language, UserRole

logger = logging.getLogger("voice_agent.openai")

class OpenAIService:
    """
    OpenAI GPT-4o-mini service with streaming and tool support.
    """

    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.model = "gpt-4o-mini"
        self.client = openai.AsyncOpenAI(api_key=self.api_key)

    async def generate(
        self,
        prompt: str,
        system_prompt: str,
        history: List[Dict[str, str]] = [],
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> Tuple[str, List[Dict], int]:
        """
        One-shot generation (non-streaming).
        Returns (text, tool_results, tokens_used).
        """
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        t0 = time.perf_counter()
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            text = response.choices[0].message.content or ""
            tokens = response.usage.total_tokens if response.usage else 0
            latency = int((time.perf_counter() - t0) * 1000)
            logger.info("GPT-4o-mini OK: latency=%dms tokens=%d", latency, tokens)
            return text, [], tokens
        except Exception as e:
            logger.error("GPT-4o-mini error: %s", e)
            raise

    async def stream_generate(
        self,
        prompt: str,
        system_prompt: str,
        history: List[Dict[str, str]] = [],
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> AsyncGenerator[str, None]:
        """
        Streaming generation. Yields text chunks as they arrive.
        """
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except Exception as e:
            logger.error("GPT-4o-mini stream error: %s", e)
            yield f" [Error: {e}]"

# Singleton
openai_service = OpenAIService()
