"""
LLM model: user-managed LLM instances from providers (backend.clients.llm).

Stores provider id, display name, and full config as JSON (backend.clients.llm.config.LLMConfig).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.database.models.base import Base, TimestampMixin, _uuid_pk


class LLM(Base, TimestampMixin):
    """
    User-created LLM instance: provider + config (JSON).

    config holds the full LLMConfig payload from backend.clients.llm.config
    (model, api_key, base_url, temperature, max_tokens, extra, etc.).
    """

    __tablename__ = "llms"
    __table_args__ = (
        Index("ix_llms_provider", "provider"),
        Index("ix_llms_is_active", "is_active"),
        Index("ix_llms_name", "name"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    """Display name for this LLM instance."""

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    """Provider id (e.g. openai, gemini) from backend.clients.llm."""

    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
    """
    Full LLM config as JSON. Matches backend.clients.llm.config.LLMConfig.to_dict():
    model, api_key, base_url, temperature, max_tokens, extra, etc.
    """

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"LLM(id={self.id!r}, name={self.name!r}, provider={self.provider!r})"
