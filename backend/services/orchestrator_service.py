"""OrchestratorService: build a fully-wired Orchestrator from DB state."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from backend.orchestrator.orchestrator import Orchestrator
from backend.orchestrator.rules.engine import RuleEngine
from backend.orchestrator.rules.repository import RuleRepository
from backend.orchestrator.types import OrchestratorConfig

if TYPE_CHECKING:
    from backend.clients.llm.base import BaseLLMClient
    from backend.orchestrator.handlers.tool_handler import ToolRegistry
    from backend.rag.embedder import Embedder
    from backend.services.rag_service import RAGService
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

logger = logging.getLogger(__name__)


class OrchestratorService:
    """Factory that loads rules from the database and constructs a ready-to-use
    ``Orchestrator`` instance.
    """

    @staticmethod
    async def build(
        session: "AsyncSession",
        llm_client: "BaseLLMClient",
        *,
        rag_service: Optional["RAGService"] = None,
        embedder: Optional["Embedder"] = None,
        config: Optional[OrchestratorConfig] = None,
        tool_registry: Optional["ToolRegistry"] = None,
        session_factory: Optional["async_sessionmaker[AsyncSession]"] = None,
    ) -> Orchestrator:
        rule_repo = RuleRepository(session)
        db_rules = await rule_repo.list_active()
        rule_engine = RuleEngine(db_rules) if db_rules else None

        orch = Orchestrator(
            llm=llm_client,
            config=config or OrchestratorConfig(),
            rag_service=rag_service,
            rule_engine=rule_engine,
            embedder=embedder,
            tool_registry=tool_registry,
            session_factory=session_factory,
        )
        await orch.initialize()

        logger.info(
            "OrchestratorService: built orchestrator with %d rules, RAG=%s, "
            "embedder=%s, tools=%s, tracking=%s",
            len(db_rules),
            rag_service is not None,
            embedder is not None,
            tool_registry.names if tool_registry else [],
            session_factory is not None,
        )
        return orch
