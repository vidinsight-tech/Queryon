"""HybridSearcher: combine semantic + keyword search via Reciprocal Rank Fusion."""
from __future__ import annotations

import logging
import re
from collections import Counter
from typing import TYPE_CHECKING, Dict, List, Optional, Set

from backend.rag.types import SearchResult

if TYPE_CHECKING:
    from qdrant_client.models import Filter

    from backend.infra.vectorstore.client import QdrantManager
    from backend.rag.embedder import Embedder

logger = logging.getLogger(__name__)

_STOP_WORDS: Set[str] = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "shall", "of", "in", "to", "for",
    "with", "on", "at", "from", "by", "about", "as", "into", "through",
    "during", "before", "after", "above", "below", "and", "but", "or",
    "not", "no", "nor", "so", "yet", "both", "each", "this", "that",
    "these", "those", "it", "its",
    "bir", "ve", "ile", "de", "da", "bu", "şu", "o", "ne", "için",
}

_WORD_RE = re.compile(r"[a-zA-ZçğıöşüÇĞİÖŞÜ0-9]+")


class HybridSearcher:
    """Combine semantic vector search with simple BM25-style keyword scoring."""

    def __init__(
        self,
        embedder: "Embedder",
        qdrant: "QdrantManager",
        collection: str,
        *,
        keyword_weight: float = 0.3,
        rrf_k: int = 60,
    ) -> None:
        self._embedder = embedder
        self._qdrant = qdrant
        self._collection = collection
        self._keyword_weight = keyword_weight
        self._rrf_k = rrf_k

    async def search(
        self,
        query: str,
        *,
        top_k: int = 10,
        score_threshold: float = 0.72,
        query_filter: Optional["Filter"] = None,
    ) -> List[SearchResult]:
        vector = await self._embedder.embed_query(query)
        semantic_hits = await self._qdrant.search(
            collection=self._collection,
            query_vector=vector,
            query_filter=query_filter,
            limit=top_k * 2,
            score_threshold=score_threshold,
        )

        all_results: Dict[str, SearchResult] = {}
        semantic_rank: Dict[str, int] = {}
        for rank, hit in enumerate(semantic_hits):
            payload = hit.payload or {}
            cid = str(payload.get("chunk_id", hit.id))
            sr = SearchResult(
                chunk_id=cid,
                document_id=str(payload.get("document_id", "")),
                content=str(payload.get("content", "")),
                score=hit.score,
                chunk_index=int(payload.get("chunk_index", 0)),
                title=str(payload.get("title", "")),
                source_type=str(payload.get("source_type", "")),
                token_count=int(payload.get("token_count", 0)),
            )
            all_results[cid] = sr
            semantic_rank[cid] = rank

        query_tokens = _tokenize(query)
        keyword_scores: Dict[str, float] = {}
        for cid, sr in all_results.items():
            keyword_scores[cid] = _bm25_simple(query_tokens, sr.content)

        keyword_ranked = sorted(keyword_scores.keys(), key=lambda c: keyword_scores[c], reverse=True)
        keyword_rank_map: Dict[str, int] = {cid: i for i, cid in enumerate(keyword_ranked)}

        fused: Dict[str, float] = {}
        for cid in all_results:
            sem_r = semantic_rank.get(cid, len(all_results))
            kw_r = keyword_rank_map.get(cid, len(all_results))
            sem_score = 1.0 / (self._rrf_k + sem_r)
            kw_score = 1.0 / (self._rrf_k + kw_r)
            fused[cid] = (1.0 - self._keyword_weight) * sem_score + self._keyword_weight * kw_score

        ranked = sorted(fused.keys(), key=lambda c: fused[c], reverse=True)[:top_k]
        final: List[SearchResult] = []
        for cid in ranked:
            sr = all_results[cid]
            sr.score = fused[cid]
            final.append(sr)

        logger.debug("HybridSearcher: %d semantic hits fused to %d results", len(semantic_hits), len(final))
        return final


def _tokenize(text: str) -> List[str]:
    return [w.lower() for w in _WORD_RE.findall(text) if w.lower() not in _STOP_WORDS]


def _bm25_simple(query_tokens: List[str], content: str, k1: float = 1.5, b: float = 0.75) -> float:
    doc_tokens = _tokenize(content)
    if not doc_tokens or not query_tokens:
        return 0.0
    dl = len(doc_tokens)
    avgdl = max(dl, 100)
    tf_map: Counter[str] = Counter(doc_tokens)
    score = 0.0
    for qt in query_tokens:
        tf = tf_map.get(qt, 0)
        if tf == 0:
            continue
        numerator = tf * (k1 + 1)
        denominator = tf + k1 * (1 - b + b * dl / avgdl)
        score += numerator / denominator
    return score
