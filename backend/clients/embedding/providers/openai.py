"""OpenAI Embedding provider: BaseEmbeddingClient implementation + registry builder."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Union

from openai import AsyncOpenAI

from backend.clients.embedding.base import BaseEmbeddingClient

_MODEL_DIMENSIONS: Dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class OpenAIEmbeddingClient(BaseEmbeddingClient):
    """OpenAI embedding client (text-embedding-3-small, etc.)."""

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self._model = model
        self._dimension = _MODEL_DIMENSIONS.get(model, 1536)
        self._client = AsyncOpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url,
        )

    @property
    def provider(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(
        self,
        text: Union[str, List[str]],
        *,
        model: Optional[str] = None,
    ) -> List[List[float]]:
        inputs = [text] if isinstance(text, str) else text
        response = await self._client.embeddings.create(
            model=model or self._model,
            input=inputs,
        )
        return [item.embedding for item in response.data]

    async def test_connection(self) -> bool:
        try:
            await self.embed("test")
            return True
        except Exception:
            return False


def openai_builder(config: Dict[str, Any]) -> OpenAIEmbeddingClient:
    return OpenAIEmbeddingClient(
        model=config.get("model", "text-embedding-3-small"),
        api_key=config.get("api_key"),
        base_url=config.get("base_url"),
    )
