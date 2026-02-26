"""Appointment ORM model."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.database.models.base import Base, TimestampMixin


class Appointment(Base, TimestampMixin):
    """A booking created when the chatbot collects all required contact info."""

    __tablename__ = "appointments"
    __table_args__ = (
        Index("ix_appointments_appt_number", "appt_number", unique=True),
    )

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

    # Booking lifecycle
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    # pending | confirmed | cancelled

    # What the customer wants
    service: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    artist: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    event_date: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    event_time: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Contact info
    contact_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact_surname: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Human-readable reference number (e.g. RND-2026-0001)
    appt_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Freeform note + LLM-generated summary
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Any admin-configured extra fields (key→value)
    extra_fields: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
