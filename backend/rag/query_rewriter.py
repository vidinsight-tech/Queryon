"""QueryRewriter: rewrite/expand the user query using an LLM."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from backend.clients.llm import BaseLLMClient

logger = logging.getLogger(__name__)

_REWRITE_PROMPT = (
    "You are a search query optimizer. Given the user query below, rewrite it "
    "as a single, clear, detailed search query that would retrieve the most "
    "relevant documents from a knowledge base. "
    "Resolve pronouns, expand abbreviations, and add relevant context. "
    "Only return the rewritten query, nothing else.\n\n"
    "User query: {query}\n\n"
    "Rewritten query:"
)

_SUBQUERY_PROMPT = (
    "Break the following complex question into 2-4 simpler sub-questions "
    "that together answer the original. Return one sub-question per line, "
    "nothing else.\n\n"
    "Question: {query}\n\n"
    "Sub-questions:"
)

_KEYWORD_PROMPT = (
    "Extract the 3-5 most important search keywords from the following query. "
    "Return them comma-separated, nothing else.\n\n"
    "Query: {query}\n\n"
    "Keywords:"
)


class QueryRewriter:
    """Uses an LLM to rewrite, decompose, or extract keywords from queries."""

    def __init__(self, llm: "BaseLLMClient") -> None:
        self._llm = llm

    async def rewrite(self, query: str) -> str:
        prompt = _REWRITE_PROMPT.format(query=query)
        try:
            result = (await self._llm.complete(prompt)).strip()
            if result:
                logger.debug("QueryRewriter: rewrote query len=%d → %d", len(query), len(result))
                return result
        except Exception as exc:
            logger.warning("QueryRewriter: rewrite failed, returning original: %s", exc)
        return query

    async def decompose(self, query: str) -> List[str]:
        prompt = _SUBQUERY_PROMPT.format(query=query)
        try:
            raw = (await self._llm.complete(prompt)).strip()
            subs = [line.strip().lstrip("0123456789.-) ") for line in raw.splitlines() if line.strip()]
            if subs:
                logger.debug("QueryRewriter: decomposed into %d sub-queries", len(subs))
                return subs
        except Exception as exc:
            logger.warning("QueryRewriter: decompose failed: %s", exc)
        return [query]

    async def extract_keywords(self, query: str) -> List[str]:
        prompt = _KEYWORD_PROMPT.format(query=query)
        try:
            raw = (await self._llm.complete(prompt)).strip()
            keywords = [kw.strip() for kw in raw.split(",") if kw.strip()]
            if keywords:
                return keywords
        except Exception as exc:
            logger.warning("QueryRewriter: keyword extraction failed: %s", exc)
        return [query]
