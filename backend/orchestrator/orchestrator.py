"""Orchestrator: top-level router that classifies intent and dispatches to the
correct handler (RAG, Direct LLM, Rule, or Tool).

Classification uses a three-layer cascade:
  Layer 1  PreClassifier     — keyword/pattern matching     (<1 ms, no LLM)
  Layer 2  EmbeddingClassifier — cosine similarity prototypes (~5 ms, no LLM)
  Layer 3  LLMClassifier     — full LLM classification      (~500 ms)
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import UUID

from backend.orchestrator.classifiers.cache import ClassificationCache
from backend.orchestrator.types import ConversationTurn
from backend.orchestrator.classifiers.pre_classifier import PreClassifier
from backend.orchestrator.handlers.base import BaseHandler
from backend.orchestrator.handlers.direct_handler import DirectHandler
from backend.orchestrator.handlers.rag_handler import RAGHandler
from backend.orchestrator.handlers.rule_handler import RuleHandler
from backend.orchestrator.handlers.tool_handler import ToolHandler, ToolRegistry
from backend.orchestrator.rules.engine import FlowContext
from backend.orchestrator.types import (
    ClassificationResult,
    IntentType,
    LowConfidenceStrategy,
    OrchestratorConfig,
    OrchestratorMetrics,
    OrchestratorResult,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
    from backend.clients.llm.base import BaseLLMClient
    from backend.orchestrator.classifiers.embedding_classifier import EmbeddingClassifier
    from backend.orchestrator.classifiers.llm_classifier import LLMClassifier
    from backend.orchestrator.rules.engine import RuleEngine, RuleMatchResult
    from backend.rag.embedder import Embedder
    from backend.services.rag_service import RAGService

logger = logging.getLogger(__name__)


class Orchestrator:
    """Central entry-point that takes a user query, classifies intent,
    dispatches to the matching handler, and applies fallback logic.

    All heavy components are injected — the orchestrator itself is stateless
    between calls (aside from the classification cache).
    """

    def __init__(
        self,
        llm: "BaseLLMClient",
        config: OrchestratorConfig,
        *,
        rag_service: Optional["RAGService"] = None,
        rule_engine: Optional["RuleEngine"] = None,
        embedder: Optional["Embedder"] = None,
        tool_registry: Optional[ToolRegistry] = None,
        session_factory: Optional["async_sessionmaker[AsyncSession]"] = None,
    ) -> None:
        self._llm = llm
        self._config = config
        self._session_factory = session_factory

        timeout = config.llm_timeout_seconds
        self._handlers: Dict[IntentType, BaseHandler] = {
            IntentType.DIRECT: DirectHandler(llm, timeout_seconds=timeout),
        }
        if rag_service is not None:
            self._handlers[IntentType.RAG] = RAGHandler(rag_service)
        if rule_engine is not None:
            self._handlers[IntentType.RULE] = RuleHandler(
                rule_engine, llm, timeout_seconds=timeout
            )
            self._rule_engine = rule_engine
        else:
            self._rule_engine = None
        self._handlers[IntentType.TOOL] = ToolHandler(tool_registry)

        self._pre_classifier: Optional[PreClassifier] = None
        self._embedding_classifier: Optional["EmbeddingClassifier"] = None
        self._llm_classifier: Optional["LLMClassifier"] = None
        self._cache = ClassificationCache()
        self._embedder = embedder

        self._build_classifiers()

    def _build_classifiers(self) -> None:
        rule_keywords: set[str] = set()
        if self._rule_engine is not None:
            rule_keywords = self._rule_engine.keywords

        self._pre_classifier = PreClassifier(rule_keywords)

        from backend.orchestrator.classifiers.llm_classifier import LLMClassifier
        self._llm_classifier = LLMClassifier(self._llm, self._config)

    async def initialize(self) -> None:
        """Build embedding prototypes.  Call once after construction."""
        if self._embedder is not None:
            from backend.orchestrator.classifiers.embedding_classifier import EmbeddingClassifier
            self._embedding_classifier = EmbeddingClassifier(self._embedder)
            await self._embedding_classifier.build_prototypes()
            logger.info("Orchestrator: embedding classifier initialised")

    async def process(
        self,
        query: str,
        *,
        conversation_history: Optional[List[ConversationTurn]] = None,
        last_intent: Optional[IntentType] = None,
        flow_ctx: Optional[FlowContext] = None,
    ) -> OrchestratorResult:
        """Full orchestration cycle: classify → handle → fallback → return.

        conversation_history: recent turns [{"role":"user"|"assistant","content":"..."}]
        for context-aware classification. last_intent: previous reply's intent (helps follow-ups).
        flow_ctx: multi-step flow state — when active, flow-bound rules are evaluated first.
        """
        t_start = time.monotonic()
        llm_calls = 0

        # ── Step 0: flow-aware rule match (always checked when flow is active) ──
        if flow_ctx and flow_ctx.active and self._rule_engine is not None:
            from backend.orchestrator.rules.engine import RuleMatchResult
            rule_match = self._rule_engine.match(query, flow_ctx=flow_ctx)
            if rule_match is not None:
                return self._build_rule_result(
                    query, rule_match, t_start, layer="flow_rule",
                )

        # ── Step 1: rules_first — keyword-only rule match (no LLM) ──
        if self._config.rules_first and self._rule_engine is not None:
            rule_match = self._rule_engine.match(query, flow_ctx=flow_ctx)
            if rule_match is not None:
                return self._build_rule_result(
                    query, rule_match, t_start, layer="rules_first",
                )

        # ── Step 2: three-layer classification ──
        t_classify = time.monotonic()
        classification = await self._classify(
            query,
            conversation_history=conversation_history,
            last_intent=last_intent,
        )
        classify_ms = (time.monotonic() - t_classify) * 1000
        if classification.classifier_layer == "llm":
            llm_calls += 1

        # ── Step 3: confidence check ──
        if classification.confidence < self._config.min_confidence:
            if self._config.low_confidence_strategy == LowConfidenceStrategy.ASK_USER:
                elapsed = (time.monotonic() - t_start) * 1000
                return OrchestratorResult(
                    query=query,
                    intent=classification.intent,
                    needs_clarification=True,
                    answer="Tam olarak anlayamadım. Lütfen sorunuzu biraz daha açar mısınız?",
                    classification=classification,
                    metrics=OrchestratorMetrics(
                        classification_ms=classify_ms,
                        total_ms=elapsed,
                        llm_calls_count=llm_calls,
                        classifier_layer=classification.classifier_layer,
                    ),
                )
            classification.intent = self._config.default_intent

        # ── Step 4: dispatch to handler ──
        intent = classification.intent
        if intent not in self._handlers:
            intent = self._config.default_intent
        handler = self._handlers.get(intent) or self._handlers[IntentType.DIRECT]

        t_handler = time.monotonic()
        result = await handler.handle(
            query, conversation_history=conversation_history,
        )
        handler_ms = (time.monotonic() - t_handler) * 1000
        if intent in (IntentType.RAG, IntentType.DIRECT):
            llm_calls += 1

        # ── Step 5: fallback ──
        fallback_used = False
        if (
            intent == IntentType.RAG
            and not result.answer
            and self._config.fallback_to_direct
            and IntentType.DIRECT in self._handlers
        ):
            t_fb = time.monotonic()
            result = await self._handlers[IntentType.DIRECT].handle(
                query, conversation_history=conversation_history,
            )
            handler_ms += (time.monotonic() - t_fb) * 1000
            fallback_used = True
            llm_calls += 1
            result.intent = IntentType.DIRECT  # so last_intent reflects actual reply source
            logger.info("Orchestrator: RAG returned no answer → fallback to DIRECT")

        # ── Step 6: assemble metrics ──
        elapsed = (time.monotonic() - t_start) * 1000
        result.classification = classification
        result.fallback_used = fallback_used
        result.metrics = OrchestratorMetrics(
            classification_ms=classify_ms,
            handler_ms=handler_ms,
            total_ms=elapsed,
            llm_calls_count=llm_calls,
            fallback_used=fallback_used,
            classifier_layer=classification.classifier_layer,
        )
        logger.info(
            "Orchestrator: intent=%s confidence=%.2f layer=%s total=%.0fms fallback=%s",
            result.intent.value,
            classification.confidence,
            classification.classifier_layer,
            elapsed,
            fallback_used,
        )
        return result

    # ── Conversation-tracked processing ──────────────────────────

    async def start_conversation(
        self,
        *,
        platform: str = "cli",
        channel_id: Optional[str] = None,
        contact_phone: Optional[str] = None,
        contact_email: Optional[str] = None,
        contact_name: Optional[str] = None,
        contact_meta: Optional[Dict[str, Any]] = None,
        llm_id: Optional[UUID] = None,
        embedding_id: Optional[UUID] = None,
    ) -> UUID:
        """Create a new tracked conversation and return its ID.

        Requires ``session_factory`` to be set at construction time.
        """
        self._require_session_factory()
        from backend.services.conversation_service import ConversationService

        async with self._session_factory() as session:  # type: ignore[misc]
            svc = ConversationService(session)
            conv = await svc.start_conversation(
                platform=platform,
                channel_id=channel_id,
                contact_phone=contact_phone,
                contact_email=contact_email,
                contact_name=contact_name,
                contact_meta=contact_meta,
                llm_id=llm_id,
                embedding_id=embedding_id,
            )
            await session.commit()
            return conv.id

    async def end_conversation(self, conversation_id: UUID) -> bool:
        """Close a tracked conversation."""
        self._require_session_factory()
        from backend.services.conversation_service import ConversationService

        async with self._session_factory() as session:  # type: ignore[misc]
            svc = ConversationService(session)
            ok = await svc.close_conversation(conversation_id)
            await session.commit()
            return ok

    async def process_with_tracking(
        self,
        query: str,
        conversation_id: UUID,
    ) -> OrchestratorResult:
        """Full orchestration cycle with automatic DB persistence.

        1. Load conversation history + flow_state from DB
        2. Derive ``last_intent`` from the most recent assistant message
        3. Call ``process()`` with flow context
        4. Record user + assistant messages (with events) to DB
        5. Persist updated flow_state
        6. Return the ``OrchestratorResult``
        """
        self._require_session_factory()
        from backend.services.conversation_service import ConversationService

        max_turns = max(0, self._config.max_conversation_turns)

        async with self._session_factory() as session:  # type: ignore[misc]
            svc = ConversationService(session)

            conversation_history = await svc.get_history_as_turns(
                conversation_id, max_turns=max_turns,
            )

            last_intent = await self._get_last_intent(svc, conversation_id)

            flow_state_raw = await svc.get_flow_state(conversation_id)
            flow_ctx = FlowContext.from_dict(flow_state_raw)

            await svc.record_user_message(conversation_id, query)
            await session.commit()

        result = await self.process(
            query,
            conversation_history=conversation_history if conversation_history else None,
            last_intent=last_intent,
            flow_ctx=flow_ctx,
        )

        next_flow_dict = result.metadata.get("next_flow_context") if result.metadata else None
        new_flow_ctx = FlowContext.from_dict(next_flow_dict) if next_flow_dict else None

        async with self._session_factory() as session:  # type: ignore[misc]
            svc = ConversationService(session)
            await svc.record_assistant_message(conversation_id, result)

            if result.intent == IntentType.RULE:
                await svc.update_flow_state(
                    conversation_id,
                    new_flow_ctx.to_dict() if new_flow_ctx and new_flow_ctx.active else None,
                )
            await session.commit()

        return result

    async def get_conversation_history(
        self,
        conversation_id: UUID,
        last_n: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve persisted messages for a conversation."""
        self._require_session_factory()
        from backend.services.conversation_service import ConversationService

        async with self._session_factory() as session:  # type: ignore[misc]
            svc = ConversationService(session)
            conv = await svc.get_conversation(
                conversation_id, last_n_messages=last_n,
            )
            if conv is None:
                return []
            return [
                {
                    "id": str(m.id),
                    "role": m.role,
                    "content": m.content,
                    "intent": m.intent,
                    "confidence": m.confidence,
                    "classifier_layer": m.classifier_layer,
                    "rule_matched": m.rule_matched,
                    "fallback_used": m.fallback_used,
                    "total_ms": m.total_ms,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in conv.messages
            ]

    @staticmethod
    def _build_rule_result(
        query: str,
        rule_match: "RuleMatchResult",
        t_start: float,
        *,
        layer: str = "rules_first",
    ) -> OrchestratorResult:
        elapsed = (time.monotonic() - t_start) * 1000
        flow_meta: Dict[str, Any] = {}
        if rule_match.next_flow_context is not None:
            flow_meta["next_flow_context"] = rule_match.next_flow_context.to_dict()
        logger.info(
            "Orchestrator: %s matched → '%s' (%.0f ms)",
            layer, rule_match.rule.name, elapsed,
        )
        return OrchestratorResult(
            query=query,
            intent=IntentType.RULE,
            answer=rule_match.rendered_answer,
            rule_matched=rule_match.rule.name,
            classification=ClassificationResult(
                intent=IntentType.RULE,
                confidence=1.0,
                classifier_layer=layer,
            ),
            metrics=OrchestratorMetrics(
                total_ms=elapsed,
                classifier_layer=layer,
            ),
            metadata=flow_meta if flow_meta else {},
        )

    def _require_session_factory(self) -> None:
        if self._session_factory is None:
            raise RuntimeError(
                "Orchestrator: session_factory is required for conversation tracking. "
                "Pass session_factory when constructing the Orchestrator."
            )

    @staticmethod
    async def _get_last_intent(
        svc: Any,
        conversation_id: UUID,
    ) -> Optional[IntentType]:
        """Read the intent of the most recent assistant message from the DB."""
        intent_str = await svc.get_last_assistant_intent(conversation_id)
        if not intent_str:
            return None
        try:
            return IntentType(intent_str)
        except ValueError:
            return None

    # ── private ──

    async def _classify(
        self,
        query: str,
        *,
        conversation_history: Optional[List[ConversationTurn]] = None,
        last_intent: Optional[IntentType] = None,
    ) -> ClassificationResult:
        """Run the three-layer classification cascade."""

        # Layer 1: PreClassifier (keyword)
        if self._pre_classifier is not None:
            pre = self._pre_classifier.try_classify(query)
            if pre is not None and pre.confidence >= 0.9:
                return pre

        # Layer 2: EmbeddingClassifier
        if self._embedding_classifier is not None and self._embedding_classifier.ready:
            emb = await self._embedding_classifier.classify(query)
            if emb.confidence >= self._config.embedding_confidence_threshold:
                return emb

        # Layer 3: cache → LLM (skip cache when context is present)
        if not conversation_history:
            cached = self._cache.get(query)
            if cached is not None:
                return cached

        if self._llm_classifier is not None:
            max_turns = max(0, self._config.max_conversation_turns)
            history = (
                conversation_history[-max_turns * 2 :]
                if conversation_history and max_turns > 0
                else None
            )
            rule_descs = self._get_rule_descriptions()
            tool_descs = self._get_tool_descriptions()
            result = await self._llm_classifier.classify(
                query,
                rule_descriptions=rule_descs,
                tool_descriptions=tool_descs,
                conversation_history=history,
                last_intent=last_intent,
            )
            if not conversation_history:
                self._cache.put(query, result)
            return result

        return ClassificationResult(
            intent=self._config.default_intent,
            confidence=0.5,
            reasoning="no classifier available",
        )

    def _get_rule_descriptions(self) -> List[str]:
        if self._rule_engine is None:
            return []
        return [
            f"{r.name}: {r.description}"
            for r in self._rule_engine.rules
            if r.is_active
        ]

    def _get_tool_descriptions(self) -> List[str]:
        tool_handler = self._handlers.get(IntentType.TOOL)
        if isinstance(tool_handler, ToolHandler) and tool_handler._registry is not None:
            return tool_handler._registry.get_descriptions()
        return []
