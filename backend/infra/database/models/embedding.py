"""
Embedding model: user-managed embedding instances from providers (backend.clients.embedding).

Stores provider id, display name, and full config as JSON (EmbeddingConfig).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.database.models.base import Base, TimestampMixin, _uuid_pk


class Embedding(Base, TimestampMixin):
    """
    User-created embedding instance: provider + config (JSON).

    config holds the full EmbeddingConfig payload (model, api_key, base_url, extra, etc.).
    """

    __tablename__ = "embeddings"
    __table_args__ = (
        Index("ix_embeddings_provider", "provider"),
        Index("ix_embeddings_is_active", "is_active"),
        Index("ix_embeddings_name", "name"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
    )
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
        return f"Embedding(id={self.id!r}, name={self.name!r}, provider={self.provider!r})"
