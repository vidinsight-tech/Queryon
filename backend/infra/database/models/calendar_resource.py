"""Calendar resource ORM: per-artist/per-resource calendar with optional Google connection."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.database.models.base import Base, TimestampMixin, _uuid_pk


class CalendarResource(Base, TimestampMixin):
    """
    One calendar source (artist, room, equipment).
    calendar_type: "internal" | "google" | "ical"
    For Google: calendar_id + optional credentials (else uses global tool_config).
    """

    __tablename__ = "calendar_resources"
    __table_args__ = (
        Index("ix_calendar_resources_resource_name", "resource_name"),
        Index("ix_calendar_resources_calendar_type", "calendar_type"),
        Index("ix_calendar_resources_is_active", "is_active"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False, default="artist")
    resource_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    calendar_type: Mapped[str] = mapped_column(String(32), nullable=False, default="internal")
    color: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    working_hours: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    service_durations: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    calendar_id: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    ical_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    credentials: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
