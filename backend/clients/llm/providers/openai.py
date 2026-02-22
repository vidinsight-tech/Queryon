"""OpenAI LLM provider: BaseLLMClient implementation + registry builder."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from openai import AsyncOpenAI

from backend.clients.llm.base import BaseLLMClient


class OpenAILLMClient(BaseLLMClient):
    """OpenAI-compatible LLM client (GPT-4o, GPT-4o-mini, etc.)."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = AsyncOpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url,
        )

    @property
    def provider(self) -> str:
        return "openai"

    async def complete(self, prompt: str, *, model: Optional[str] = None) -> str:
        kwargs: Dict[str, Any] = {
            "model": model or self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self._temperature,
        }
        if self._max_tokens is not None:
            kwargs["max_tokens"] = self._max_tokens
        response = await self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    async def test_connection(self) -> bool:
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False


def openai_builder(config: Dict[str, Any]) -> OpenAILLMClient:
    return OpenAILLMClient(
        model=config.get("model", "gpt-4o-mini"),
        api_key=config.get("api_key"),
        base_url=config.get("base_url"),
        temperature=float(config.get("temperature", 0.0)),
        max_tokens=config.get("max_tokens"),
    )
