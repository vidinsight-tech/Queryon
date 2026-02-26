"""Repositories for Conversation, Message, and MessageEvent."""
from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.infra.database.models.conversation import (
    Conversation,
    Message,
    MessageEvent,
)
from backend.infra.database.repositories.base import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    model: ClassVar[type] = Conversation

    async def start(
        self,
        *,
        platform: str = "cli",
        channel_id: Optional[str] = None,
        contact_phone: Optional[str] = None,
        contact_email: Optional[str] = None,
        contact_name: Optional[str] = None,
        contact_username: Optional[str] = None,
        contact_meta: Optional[Dict[str, Any]] = None,
        llm_id: Optional[UUID] = None,
        embedding_id: Optional[UUID] = None,
    ) -> Conversation:
        return await self.create({
            "platform": platform,
            "channel_id": channel_id,
            "contact_phone": contact_phone,
            "contact_email": contact_email,
            "contact_name": contact_name,
            "contact_username": contact_username,
            "contact_meta": contact_meta,
            "llm_id": llm_id,
            "embedding_id": embedding_id,
            "status": "active",
            "message_count": 0,
        })

    async def close(self, conversation_id: UUID) -> bool:
        stmt = (
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(status="closed", updated_at=func.now())
        )
        result = await self.session.execute(stmt)
        return (result.rowcount or 0) > 0

    async def get_with_messages(
        self,
        conversation_id: UUID,
        *,
        last_n: Optional[int] = None,
    ) -> Optional[Conversation]:
        """Load conversation with its messages.

        If *last_n* is set the relationship is loaded eagerly and then
        sliced in Python (SQLAlchemy selectinload doesn't support LIMIT).
        """
        stmt = (
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .options(selectinload(Conversation.messages))
        )
        result = await self.session.execute(stmt)
        conv = result.scalar_one_or_none()
        if conv is not None and last_n is not None and last_n > 0:
            conv.messages = conv.messages[-last_n:]
        return conv

    async def list_active(
        self,
        *,
        platform: Optional[str] = None,
        limit: int = 50,
    ) -> List[Conversation]:
        stmt = select(Conversation).where(Conversation.status == "active")
        if platform:
            stmt = stmt.where(Conversation.platform == platform)
        stmt = stmt.order_by(Conversation.last_message_at.desc().nulls_last()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_recent(
        self,
        *,
        status: Optional[str] = None,
        limit: int = 100,
        skip: int = 0,
    ) -> List[Conversation]:
        """List conversations ordered by most-recently active, any status."""
        stmt = select(Conversation)
        if status:
            stmt = stmt.where(Conversation.status == status)
        stmt = (
            stmt.order_by(Conversation.last_message_at.desc().nulls_last())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def increment_message_count(self, conversation_id: UUID) -> None:
        stmt = (
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(
                message_count=Conversation.message_count + 1,
                last_message_at=func.now(),
                updated_at=func.now(),
            )
        )
        await self.session.execute(stmt)

    async def update_flow_state(
        self,
        conversation_id: UUID,
        flow_state: Optional[Dict[str, Any]],
    ) -> None:
        """Set or clear the multi-step flow state on a conversation."""
        stmt = (
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(flow_state=flow_state, updated_at=func.now())
        )
        await self.session.execute(stmt)

    async def get_flow_state(
        self, conversation_id: UUID,
    ) -> Optional[Dict[str, Any]]:
        stmt = (
            select(Conversation.flow_state)
            .where(Conversation.id == conversation_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_by_channel(
        self, platform: str, channel_id: str,
    ) -> Optional[Conversation]:
        stmt = (
            select(Conversation)
            .where(
                Conversation.platform == platform,
                Conversation.channel_id == channel_id,
                Conversation.status == "active",
            )
            .order_by(Conversation.last_message_at.desc().nulls_last())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class MessageRepository(BaseRepository[Message]):
    model: ClassVar[type] = Message

    async def add_user_message(
        self,
        conversation_id: UUID,
        content: str,
    ) -> Message:
        return await self.create({
            "conversation_id": conversation_id,
            "role": "user",
            "content": content,
        })

    async def add_assistant_message(
        self,
        conversation_id: UUID,
        content: str,
        *,
        intent: Optional[str] = None,
        confidence: Optional[float] = None,
        classifier_layer: Optional[str] = None,
        rule_matched: Optional[str] = None,
        tool_called: Optional[str] = None,
        fallback_used: bool = False,
        needs_clarification: bool = False,
        total_ms: Optional[float] = None,
        llm_calls_count: int = 0,
        sources: Optional[Any] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
        thinking: Optional[str] = None,
        reasoning: Optional[str] = None,
    ) -> Message:
        # Merge thinking/reasoning/tool_called into extra_metadata so they are
        # persisted without requiring a schema migration.
        meta: Dict[str, Any] = dict(extra_metadata or {})
        if thinking:
            meta["thinking"] = thinking
        if reasoning:
            meta["reasoning"] = reasoning
        if tool_called:
            meta["tool_called"] = tool_called
        return await self.create({
            "conversation_id": conversation_id,
            "role": "assistant",
            "content": content,
            "intent": intent,
            "confidence": confidence,
            "classifier_layer": classifier_layer,
            "rule_matched": rule_matched,
            "fallback_used": fallback_used,
            "needs_clarification": needs_clarification,
            "total_ms": total_ms,
            "llm_calls_count": llm_calls_count,
            "sources": sources,
            "extra_metadata": meta if meta else None,
        })

    async def get_recent(
        self,
        conversation_id: UUID,
        limit: int = 20,
    ) -> List[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_with_events(self, message_id: UUID) -> Optional[Message]:
        stmt = (
            select(Message)
            .where(Message.id == message_id)
            .options(selectinload(Message.events))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class MessageEventRepository(BaseRepository[MessageEvent]):
    model: ClassVar[type] = MessageEvent

    async def log_event(
        self,
        message_id: UUID,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> MessageEvent:
        return await self.create({
            "message_id": message_id,
            "event_type": event_type,
            "data": data,
        })

    async def log_events_bulk(
        self,
        message_id: UUID,
        events: List[Dict[str, Any]],
    ) -> List[MessageEvent]:
        items = [
            {"message_id": message_id, "event_type": e["event_type"], "data": e.get("data")}
            for e in events
        ]
        return await self.bulk_create(items)

    async def get_by_message(self, message_id: UUID) -> List[MessageEvent]:
        stmt = (
            select(MessageEvent)
            .where(MessageEvent.message_id == message_id)
            .order_by(MessageEvent.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
