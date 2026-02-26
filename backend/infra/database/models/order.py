"""Order ORM model."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.database.models.base import Base, TimestampMixin


class Order(Base, TimestampMixin):
    """An order created when the chatbot collects all required order info."""

    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Link to conversation (nullable — conv may be deleted later)
    conversation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Order lifecycle
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    # pending | confirmed | cancelled

    # Contact info
    contact_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact_surname: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Freeform note + LLM-generated summary
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Any admin-configured extra fields (key→value)
    extra_fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
