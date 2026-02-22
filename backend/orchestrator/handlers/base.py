"""Abstract base handler for all intent handlers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from backend.orchestrator.types import ConversationTurn, OrchestratorResult


class BaseHandler(ABC):
    """Every intent handler implements ``handle()`` and returns a result."""

    @abstractmethod
    async def handle(
        self,
        query: str,
        *,
        conversation_history: Optional[List[ConversationTurn]] = None,
        **kwargs: object,
    ) -> OrchestratorResult:
        ...
