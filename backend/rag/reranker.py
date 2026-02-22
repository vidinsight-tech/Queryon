"""LLM-based reranker: rescore search results using the LLM."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

from backend.rag.types import SearchResult

if TYPE_CHECKING:
    from backend.clients.llm import BaseLLMClient

logger = logging.getLogger(__name__)

_RERANK_PROMPT_TEMPLATE = (
    "Rate how relevant the following passage is to the query on a scale of 0 to 10.\n"
    "Only respond with a single number, nothing else.\n\n"
    "Query: {query}\n\n"
    "Passage:\n{passage}\n\n"
    "Relevance score (0-10):"
)

_MAX_PASSAGE_CHARS = 2000


class LLMReranker:
    """Rescore SearchResults using a BaseLLMClient for cross-encoder-style scoring."""

    def __init__(self, llm: "BaseLLMClient", *, top_n: int | None = None) -> None:
        self._llm = llm
        self._top_n = top_n

    async def rerank(self, query: str, results: List[SearchResult]) -> List[SearchResult]:
        if not results:
            return []
        scored: List[tuple[float, SearchResult]] = []
        for sr in results:
            passage = sr.content[:_MAX_PASSAGE_CHARS]
            prompt = _RERANK_PROMPT_TEMPLATE.format(query=query, passage=passage)
            try:
                raw = await self._llm.complete(prompt)
                score = _parse_score(raw)
            except Exception as exc:
                logger.warning("Reranker: LLM call failed for chunk %s: %s", sr.chunk_id, exc)
                score = sr.score
            scored.append((score, sr))
        scored.sort(key=lambda t: t[0], reverse=True)
        top_n = self._top_n or len(scored)
        final: List[SearchResult] = []
        for rank_score, sr in scored[:top_n]:
            sr.score = rank_score
            final.append(sr)
        logger.debug("LLMReranker: reranked %d → %d results", len(results), len(final))
        return final


def _parse_score(raw: str) -> float:
    raw = raw.strip()
    for token in raw.split():
        try:
            val = float(token)
            return max(0.0, min(val, 10.0))
        except ValueError:
            continue
    return 0.0
