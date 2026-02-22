"""Search helpers for the knowledge_base collection."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional

from qdrant_client.models import ScoredPoint

from backend.core.exceptions import VectorstoreError
from backend.infra.vectorstore.client import QdrantManager
from backend.infra.vectorstore.collections import KNOWLEDGE_BASE_COLLECTION, PayloadField

if TYPE_CHECKING:
    from backend.config import QdrantConfig

logger = logging.getLogger(__name__)

DEFAULT_SIMILARITY_THRESHOLD = 0.72


async def search_chunks(
    qdrant: QdrantManager,
    vector: List[float],
    query_filter: Optional[object] = None,
    limit: int = 10,
    threshold: Optional[float] = None,
    with_payload: bool = True,
    config: Optional["QdrantConfig"] = None,
) -> List[ScoredPoint]:
    if not vector:
        raise VectorstoreError("search_chunks: query vector must not be empty.")
    collection = config.collection_name if config is not None else KNOWLEDGE_BASE_COLLECTION
    score_threshold = threshold if threshold is not None else DEFAULT_SIMILARITY_THRESHOLD
    return await qdrant.search(
        collection=collection,
        query_vector=vector,
        query_filter=query_filter,
        limit=limit,
        score_threshold=score_threshold,
        with_payload=with_payload,
    )


def extract_chunk_ids(hits: List[ScoredPoint]) -> List[str]:
    ids: List[str] = []
    for hit in hits:
        if hit.payload and PayloadField.CHUNK_ID in hit.payload:
            ids.append(str(hit.payload[PayloadField.CHUNK_ID]))
    return ids


def extract_content(hits: List[ScoredPoint]) -> List[str]:
    return [str(hit.payload.get(PayloadField.CONTENT, "")) for hit in hits if hit.payload]
