"""Embedder: wraps BaseEmbeddingClient with batching, L2 normalisation, and dimension checks."""
from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, List, Optional

from backend.core.exceptions import ConfigurationError

if TYPE_CHECKING:
    from backend.clients.embedding import BaseEmbeddingClient

logger = logging.getLogger(__name__)

_DEFAULT_BATCH = 64


class Embedder:
    """Batch embed texts via any BaseEmbeddingClient, optionally normalise.

    Exposes the underlying client's ``model_name`` and ``dimension`` so that
    callers can record which model produced the embeddings and validate that
    the collection vector size matches.
    """

    def __init__(
        self,
        client: "BaseEmbeddingClient",
        *,
        batch_size: int = _DEFAULT_BATCH,
        normalize: bool = True,
        expected_dimension: Optional[int] = None,
    ) -> None:
        self._client = client
        self._batch_size = batch_size
        self._normalize = normalize

        if expected_dimension is not None and client.dimension != expected_dimension:
            raise ConfigurationError(
                f"Embedding model '{client.model_name}' produces {client.dimension}-d vectors "
                f"but the vector store expects {expected_dimension}-d. "
                f"Change QDRANT_VECTOR_SIZE or use a matching embedding model.",
            )

    @property
    def model_name(self) -> str:
        return self._client.model_name

    @property
    def dimension(self) -> int:
        return self._client.dimension

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        vectors: List[List[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            batch_vecs = await self._client.embed(batch)
            if self._normalize:
                batch_vecs = [_l2_normalize(v) for v in batch_vecs]
            vectors.extend(batch_vecs)
        return vectors

    async def embed_query(self, text: str) -> List[float]:
        vecs = await self.embed_texts([text])
        return vecs[0]


def _l2_normalize(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if norm < 1e-12:
        return vec
    return [x / norm for x in vec]
