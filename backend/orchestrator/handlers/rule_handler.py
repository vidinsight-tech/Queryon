"""RuleHandler: match user queries against deterministic rules."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from backend.orchestrator.handlers.base import BaseHandler
from backend.orchestrator.types import ConversationTurn, IntentType, OrchestratorResult

if TYPE_CHECKING:
    from backend.clients.llm.base import BaseLLMClient
    from backend.orchestrator.rules.engine import RuleEngine

logger = logging.getLogger(__name__)


class RuleHandler(BaseHandler):
    """Try keyword match, then optionally LLM-based match."""

    def __init__(
        self,
        engine: "RuleEngine",
        llm: Optional["BaseLLMClient"] = None,
        *,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        self._engine = engine
        self._llm = llm
        self._timeout_seconds = timeout_seconds

    async def handle(
        self,
        query: str,
        *,
        conversation_history: Optional[List[ConversationTurn]] = None,
        **kwargs: object,
    ) -> OrchestratorResult:
        if self._llm is not None:
            match = await self._engine.match_with_llm(
                query, self._llm, timeout_seconds=self._timeout_seconds,
            )
        else:
            match = self._engine.match(query)

        if match is None:
            return OrchestratorResult(
                query=query,
                intent=IntentType.RULE,
                answer=None,
            )

        logger.info("RuleHandler: matched rule '%s' (id=%s)", match.rule.name, match.rule.id)
        meta: Dict[str, Any] = {}
        if match.next_flow_context is not None:
            meta["next_flow_context"] = match.next_flow_context.to_dict()
        return OrchestratorResult(
            query=query,
            intent=IntentType.RULE,
            answer=match.rendered_answer,
            rule_matched=match.rule.name,
            metadata=meta,
        )
