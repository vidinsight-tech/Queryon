"""Conversation, Message, and MessageEvent ORM models for tracking chat sessions."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.infra.database.models.base import Base, TimestampMixin, _uuid_pk


class Conversation(Base, TimestampMixin):
    """A single chat session with platform and contact information."""

    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_platform", "platform"),
        Index("ix_conversations_status", "status"),
        Index("ix_conversations_channel_id", "channel_id"),
        Index("ix_conversations_contact_phone", "contact_phone"),
        Index("ix_conversations_last_message_at", "last_message_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()

    platform: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="cli",
    )
    """Platform identifier: cli, web, whatsapp, api, etc."""

    channel_id: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True,
    )
    """External channel identifier (e.g. WhatsApp group, web session token)."""

    contact_phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_meta: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
    )
    """Arbitrary contact metadata (avatar url, locale, etc.)."""

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="active",
    )
    """Conversation lifecycle: active | closed | archived."""

    llm_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    embedding_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )

    message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )
    last_message_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    flow_state: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True,
    )
    """Tracks multi-step flow progress.
    Structure: ``{"flow_id": "...", "current_step": "...", "data": {...}}``
    NULL when the user is not inside a flow."""

    messages: Mapped[List["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return (
            f"Conversation(id={self.id!r}, platform={self.platform!r}, "
            f"status={self.status!r}, msgs={self.message_count})"
        )


class Message(Base):
    """A single user or assistant message within a conversation."""

    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_id", "conversation_id"),
        Index("ix_messages_role", "role"),
        Index("ix_messages_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(16), nullable=False,
    )
    """Message author: user | assistant | system."""

    content: Mapped[str] = mapped_column(Text, nullable=False, server_default="")

    # --- assistant-only fields (NULL for user messages) ---
    intent: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    classifier_layer: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    rule_matched: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    needs_clarification: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false",
    )
    total_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    llm_calls_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0",
    )
    sources: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    extra_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages",
    )
    events: Mapped[List["MessageEvent"]] = relationship(
        "MessageEvent",
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="MessageEvent.created_at",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        preview = (self.content or "")[:40]
        return f"Message(id={self.id!r}, role={self.role!r}, content={preview!r})"


class MessageEvent(Base):
    """Granular system action log entry for a message (classification, search, etc.)."""

    __tablename__ = "message_events"
    __table_args__ = (
        Index("ix_message_events_message_id", "message_id"),
        Index("ix_message_events_event_type", "event_type"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="CASCADE"),
        nullable=False,
    )

    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    """Event kind: classification_start, classification_result, rule_matched,
    rag_search, llm_call, fallback_triggered, timeout, error, etc."""

    data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    """Arbitrary payload for this event."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    message: Mapped["Message"] = relationship(
        "Message", back_populates="events",
    )

    def __repr__(self) -> str:
        return f"MessageEvent(id={self.id!r}, type={self.event_type!r})"
