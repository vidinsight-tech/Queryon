"""Google Gemini LLM provider: BaseLLMClient implementation + registry builder."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from google import genai

from backend.clients.llm.base import BaseLLMClient


class GeminiLLMClient(BaseLLMClient):
    """Google Gemini LLM client (gemini-2.0-flash, gemini-1.5-pro, etc.)."""

    def __init__(
        self,
        model: str = "gemini-2.0-flash",
        *,
        api_key: Optional[str] = None,
    ) -> None:
        self._model = model
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self._client = genai.Client(api_key=resolved_key)

    @property
    def provider(self) -> str:
        return "gemini"

    async def complete(self, prompt: str, *, model: Optional[str] = None) -> str:
        response = await self._client.aio.models.generate_content(
            model=model or self._model,
            contents=prompt,
        )
        return response.text or ""

    async def test_connection(self) -> bool:
        try:
            await self.complete("Say OK", model=self._model)
            return True
        except Exception:
            return False


def gemini_builder(config: Dict[str, Any]) -> GeminiLLMClient:
    return GeminiLLMClient(
        model=config.get("model", "gemini-2.0-flash"),
        api_key=config.get("api_key"),
    )
