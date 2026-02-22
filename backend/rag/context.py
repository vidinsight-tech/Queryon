"""ContextAssembler: build a prompt-ready context from search results."""
from __future__ import annotations

import logging
from typing import Callable, List, Optional, Set

from backend.rag.types import AssembledContext, SearchResult

logger = logging.getLogger(__name__)

_DEFAULT_TOKEN_BUDGET = 3000


def _jaccard(a: str, b: str) -> float:
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


class ContextAssembler:
    """Assemble deduplicated, token-budgeted context from SearchResults."""

    def __init__(
        self,
        *,
        max_tokens: int = _DEFAULT_TOKEN_BUDGET,
        dedup_threshold: float = 0.85,
        token_counter: Optional[Callable[[str], int]] = None,
        cite_sources: bool = True,
    ) -> None:
        self._max_tokens = max_tokens
        self._dedup_threshold = dedup_threshold
        self._count_tokens = token_counter or _approx_tokens
        self._cite_sources = cite_sources

    def assemble(self, results: List[SearchResult]) -> AssembledContext:
        if not results:
            return AssembledContext(text="", sources=[], total_tokens=0, truncated=False)

        deduped = self._deduplicate(results)

        parts: List[str] = []
        used: List[SearchResult] = []
        total = 0
        truncated = False
        for sr in deduped:
            tc = self._count_tokens(sr.content)
            if total + tc > self._max_tokens:
                truncated = True
                break
            if self._cite_sources:
                header = f"[Source: {sr.title or sr.document_id} | chunk {sr.chunk_index}]"
                parts.append(f"{header}\n{sr.content}")
            else:
                parts.append(sr.content)
            used.append(sr)
            total += tc

        text = "\n\n---\n\n".join(parts)
        return AssembledContext(text=text, sources=used, total_tokens=total, truncated=truncated)

    def _deduplicate(self, results: List[SearchResult]) -> List[SearchResult]:
        kept: List[SearchResult] = []
        seen_ids: Set[str] = set()
        for sr in results:
            if sr.chunk_id in seen_ids:
                continue
            if any(_jaccard(sr.content, k.content) >= self._dedup_threshold for k in kept):
                continue
            kept.append(sr)
            seen_ids.add(sr.chunk_id)
        if len(kept) < len(results):
            logger.debug("ContextAssembler: dedup %d → %d", len(results), len(kept))
        return kept


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)
