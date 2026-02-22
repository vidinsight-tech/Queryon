"""ConversationService: high-level API for conversation tracking."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import UUID

from backend.infra.database.repositories.conversation import (
    ConversationRepository,
    MessageEventRepository,
    MessageRepository,
)

if TYPE_CHECKING:
    from backend.infra.database.models.conversation import (
        Conversation,
        Message,
        MessageEvent,
    )
    from backend.orchestrator.types import OrchestratorResult
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ConversationService:
    """Manages conversation lifecycle and message persistence.

    Designed to be used by the calling layer (CLI, API) — the
    ``Orchestrator.process()`` signature stays unchanged.
    """

    def __init__(self, session: "AsyncSession") -> None:
        self._session = session
        self._conv_repo = ConversationRepository(session)
        self._msg_repo = MessageRepository(session)
        self._event_repo = MessageEventRepository(session)

    # ── Conversation lifecycle ────────────────────────────────────

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
    ) -> "Conversation":
        conv = await self._conv_repo.start(
            platform=platform,
            channel_id=channel_id,
            contact_phone=contact_phone,
            contact_email=contact_email,
            contact_name=contact_name,
            contact_meta=contact_meta,
            llm_id=llm_id,
            embedding_id=embedding_id,
        )
        logger.info("Conversation started: %s (platform=%s)", conv.id, platform)
        return conv

    async def close_conversation(self, conversation_id: UUID) -> bool:
        ok = await self._conv_repo.close(conversation_id)
        if ok:
            logger.info("Conversation closed: %s", conversation_id)
        return ok

    async def get_conversation(
        self,
        conversation_id: UUID,
        *,
        last_n_messages: Optional[int] = None,
    ) -> Optional["Conversation"]:
        return await self._conv_repo.get_with_messages(
            conversation_id, last_n=last_n_messages,
        )

    async def list_active(
        self,
        *,
        platform: Optional[str] = None,
        limit: int = 50,
    ) -> List["Conversation"]:
        return await self._conv_repo.list_active(platform=platform, limit=limit)

    # ── Message recording ─────────────────────────────────────────

    async def record_user_message(
        self,
        conversation_id: UUID,
        content: str,
    ) -> "Message":
        msg = await self._msg_repo.add_user_message(conversation_id, content)
        await self._conv_repo.increment_message_count(conversation_id)
        logger.debug("User message recorded: %s", msg.id)
        return msg

    async def record_assistant_message(
        self,
        conversation_id: UUID,
        result: "OrchestratorResult",
    ) -> "Message":
        """Persist the orchestrator result as an assistant message with events."""
        metrics = result.metrics
        classification = result.classification

        sources_data = None
        if result.sources:
            sources_data = [
                s if isinstance(s, dict) else str(s) for s in result.sources
            ]

        confidence = classification.confidence if classification else None
        classifier_layer = (
            classification.classifier_layer if classification
            else (metrics.classifier_layer if metrics else None)
        )

        msg = await self._msg_repo.add_assistant_message(
            conversation_id,
            result.answer or "",
            intent=result.intent.value if result.intent else None,
            confidence=confidence,
            classifier_layer=classifier_layer,
            rule_matched=result.rule_matched,
            fallback_used=result.fallback_used,
            needs_clarification=result.needs_clarification,
            total_ms=metrics.total_ms if metrics else None,
            llm_calls_count=metrics.llm_calls_count if metrics else 0,
            sources=sources_data,
            extra_metadata=result.metadata if result.metadata else None,
        )

        events = self._build_events_from_result(result)
        if events:
            await self._event_repo.log_events_bulk(msg.id, events)

        await self._conv_repo.increment_message_count(conversation_id)
        logger.debug("Assistant message recorded: %s (intent=%s)", msg.id, result.intent)
        return msg

    # ── Flow state management ─────────────────────────────────────

    async def get_flow_state(
        self, conversation_id: UUID,
    ) -> Optional[Dict[str, Any]]:
        """Return the raw flow_state dict from the conversation, or None."""
        return await self._conv_repo.get_flow_state(conversation_id)

    async def update_flow_state(
        self,
        conversation_id: UUID,
        flow_state: Optional[Dict[str, Any]],
    ) -> None:
        """Persist a new flow_state (or clear it by passing None)."""
        await self._conv_repo.update_flow_state(conversation_id, flow_state)
        action = "cleared" if flow_state is None else f"set to {flow_state}"
        logger.debug("Flow state %s for conversation %s", action, conversation_id)

    # ── History retrieval (for orchestrator context) ───────────────

    async def get_history_as_turns(
        self,
        conversation_id: UUID,
        max_turns: int = 10,
    ) -> List[Dict[str, str]]:
        """Return the last *max_turns* pairs as ``[{role, content}, ...]``
        suitable for passing to ``Orchestrator.process(conversation_history=...)``.
        """
        limit = max_turns * 2
        messages = await self._msg_repo.get_recent(conversation_id, limit=limit)
        return [
            {"role": m.role, "content": m.content}
            for m in messages
        ]

    async def get_last_assistant_intent(
        self,
        conversation_id: UUID,
    ) -> Optional[str]:
        """Return the intent of the most recent assistant message, or None."""
        messages = await self._msg_repo.get_recent(conversation_id, limit=50)
        for m in reversed(messages):
            if m.role == "assistant" and m.intent:
                return m.intent
        return None

    # ── Event logging ─────────────────────────────────────────────

    async def log_event(
        self,
        message_id: UUID,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> "MessageEvent":
        return await self._event_repo.log_event(message_id, event_type, data)

    # ── Detailed message view ─────────────────────────────────────

    async def get_message_with_events(self, message_id: UUID) -> Optional["Message"]:
        return await self._msg_repo.get_with_events(message_id)

    # ── Internal helpers ──────────────────────────────────────────

    @staticmethod
    def _build_events_from_result(result: "OrchestratorResult") -> List[Dict[str, Any]]:
        """Extract structured events from an OrchestratorResult."""
        events: List[Dict[str, Any]] = []
        classification = result.classification
        metrics = result.metrics

        if classification:
            events.append({
                "event_type": "classification_result",
                "data": {
                    "intent": classification.intent.value,
                    "confidence": classification.confidence,
                    "layer": classification.classifier_layer,
                    "reasoning": classification.reasoning,
                },
            })

        if result.rule_matched:
            events.append({
                "event_type": "rule_matched",
                "data": {"rule_name": result.rule_matched},
            })

        if result.fallback_used:
            events.append({
                "event_type": "fallback_triggered",
                "data": {"from_intent": "rag", "to_intent": "direct"},
            })

        if result.needs_clarification:
            events.append({
                "event_type": "low_confidence",
                "data": {
                    "confidence": classification.confidence if classification else None,
                },
            })

        if result.sources:
            events.append({
                "event_type": "rag_search",
                "data": {"source_count": len(result.sources)},
            })

        if metrics:
            events.append({
                "event_type": "metrics",
                "data": {
                    "classification_ms": metrics.classification_ms,
                    "handler_ms": metrics.handler_ms,
                    "total_ms": metrics.total_ms,
                    "llm_calls_count": metrics.llm_calls_count,
                },
            })

        return events
