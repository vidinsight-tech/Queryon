"""Google Gemini Embedding provider: BaseEmbeddingClient implementation + registry builder."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Union

from google import genai

from backend.clients.embedding.base import BaseEmbeddingClient

_MODEL_DIMENSIONS: Dict[str, int] = {
    "text-embedding-004": 768,
    "text-embedding-005": 768,
}


class GeminiEmbeddingClient(BaseEmbeddingClient):
    """Google Gemini embedding client (text-embedding-004, etc.)."""

    def __init__(
        self,
        model: str = "text-embedding-004",
        *,
        api_key: Optional[str] = None,
    ) -> None:
        self._model = model
        self._dimension = _MODEL_DIMENSIONS.get(model, 768)
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self._client = genai.Client(api_key=resolved_key)

    @property
    def provider(self) -> str:
        return "gemini"

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
        vectors: List[List[float]] = []
        for single_text in inputs:
            response = await self._client.aio.models.embed_content(
                model=model or self._model,
                contents=single_text,
            )
            vectors.append(list(response.embeddings[0].values))
        return vectors

    async def test_connection(self) -> bool:
        try:
            await self.embed("test")
            return True
        except Exception:
            return False


def gemini_builder(config: Dict[str, Any]) -> GeminiEmbeddingClient:
    return GeminiEmbeddingClient(
        model=config.get("model", "text-embedding-004"),
        api_key=config.get("api_key"),
    )
