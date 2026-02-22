"""RAGHandler: delegates to the existing RAGService."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List, Optional

from backend.orchestrator.handlers.base import BaseHandler
from backend.orchestrator.types import ConversationTurn, IntentType, OrchestratorResult

if TYPE_CHECKING:
    from backend.services.rag_service import RAGService

logger = logging.getLogger(__name__)


class RAGHandler(BaseHandler):
    """Wrap ``RAGService.ask()`` and return an ``OrchestratorResult``."""

    def __init__(self, rag_service: "RAGService") -> None:
        self._rag = rag_service

    async def handle(
        self,
        query: str,
        *,
        conversation_history: Optional[List[ConversationTurn]] = None,
        **kwargs: object,
    ) -> OrchestratorResult:
        enriched_query = self._enrich_query(query, conversation_history)
        try:
            pipeline_result = await self._rag.ask(enriched_query)
        except Exception as exc:
            logger.error("RAGHandler: RAG pipeline failed: %s", exc)
            return OrchestratorResult(
                query=query,
                intent=IntentType.RAG,
                answer=None,
                metadata={"error": str(exc)},
            )

        sources = []
        if pipeline_result.context and pipeline_result.context.sources:
            sources = [
                {
                    "title": sr.title,
                    "document_id": sr.document_id,
                    "chunk_index": sr.chunk_index,
                    "score": sr.score,
                }
                for sr in pipeline_result.context.sources
            ]

        return OrchestratorResult(
            query=query,
            intent=IntentType.RAG,
            answer=pipeline_result.answer,
            sources=sources,
        )

    @staticmethod
    def _enrich_query(
        query: str,
        history: Optional[List[ConversationTurn]],
    ) -> str:
        """Prepend recent conversation turns so the RAG pipeline can resolve
        pronouns and follow-up references (e.g. 'onun hakkında daha fazla bilgi ver').
        """
        if not history:
            return query
        context_lines = []
        for turn in history[-4:]:
            role = turn.get("role", "user")
            content = (turn.get("content") or "").strip()
            if content:
                context_lines.append(f"{role}: {content[:200]}")
        if not context_lines:
            return query
        return (
            "Previous conversation:\n"
            + "\n".join(context_lines)
            + f"\n\nCurrent question: {query}"
        )
