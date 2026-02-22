"""DirectHandler: plain LLM response without RAG context."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Dict, List, Optional

from backend.orchestrator.handlers.base import BaseHandler
from backend.orchestrator.types import ConversationTurn, IntentType, OrchestratorResult

if TYPE_CHECKING:
    from backend.clients.llm.base import BaseLLMClient

logger = logging.getLogger(__name__)


class DirectHandler(BaseHandler):
    """Send the query directly to the LLM and return the answer."""

    def __init__(self, llm: "BaseLLMClient", *, timeout_seconds: Optional[float] = None) -> None:
        self._llm = llm
        self._timeout_seconds = timeout_seconds

    async def handle(
        self,
        query: str,
        *,
        conversation_history: Optional[List[ConversationTurn]] = None,
        **kwargs: object,
    ) -> OrchestratorResult:
        prompt = self._build_prompt(query, conversation_history)
        try:
            coro = self._llm.complete(prompt)
            if self._timeout_seconds is not None and self._timeout_seconds > 0:
                coro = asyncio.wait_for(coro, timeout=self._timeout_seconds)
            answer = await coro
        except asyncio.TimeoutError:
            logger.warning("DirectHandler: LLM call timed out (%.0fs)", self._timeout_seconds or 0)
            return OrchestratorResult(
                query=query,
                intent=IntentType.DIRECT,
                answer=None,
                metadata={"error": "timeout"},
            )
        except Exception as exc:
            logger.error("DirectHandler: LLM call failed: %s", exc)
            return OrchestratorResult(
                query=query,
                intent=IntentType.DIRECT,
                answer=None,
                metadata={"error": str(exc)},
            )

        return OrchestratorResult(
            query=query,
            intent=IntentType.DIRECT,
            answer=answer,
        )

    @staticmethod
    def _build_prompt(
        query: str,
        history: Optional[List[ConversationTurn]],
    ) -> str:
        if not history:
            return query
        lines = []
        for turn in history:
            role = turn.get("role", "user")
            content = (turn.get("content") or "").strip()
            if content:
                lines.append(f"{role}: {content}")
        lines.append(f"user: {query}")
        return "\n".join(lines)
