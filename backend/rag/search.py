"""SemanticSearcher: embed query → Qdrant search → SearchResult list."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional

from backend.rag.types import SearchResult

if TYPE_CHECKING:
    from qdrant_client.models import Filter

    from backend.infra.vectorstore.client import QdrantManager
    from backend.rag.embedder import Embedder

logger = logging.getLogger(__name__)


class SemanticSearcher:
    """Embed a query then search Qdrant for the top-k similar chunks."""

    def __init__(
        self,
        embedder: "Embedder",
        qdrant: "QdrantManager",
        collection: str,
    ) -> None:
        self._embedder = embedder
        self._qdrant = qdrant
        self._collection = collection

    async def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        score_threshold: float = 0.72,
        query_filter: Optional["Filter"] = None,
    ) -> List[SearchResult]:
        vector = await self._embedder.embed_query(query)
        hits = await self._qdrant.search(
            collection=self._collection,
            query_vector=vector,
            query_filter=query_filter,
            limit=top_k,
            score_threshold=score_threshold,
        )
        results: List[SearchResult] = []
        for hit in hits:
            payload = hit.payload or {}
            results.append(
                SearchResult(
                    chunk_id=str(payload.get("chunk_id", hit.id)),
                    document_id=str(payload.get("document_id", "")),
                    content=str(payload.get("content", "")),
                    score=hit.score,
                    chunk_index=int(payload.get("chunk_index", 0)),
                    title=str(payload.get("title", "")),
                    source_type=str(payload.get("source_type", "")),
                    token_count=int(payload.get("token_count", 0)),
                    metadata={k: v for k, v in payload.items() if k not in ("content", "chunk_id", "document_id", "chunk_index", "title", "source_type", "token_count")},
                )
            )
        logger.debug("SemanticSearcher returned %d results for query length=%d", len(results), len(query))
        return results
