"""EmbeddingModelConfig ORM model — user-managed embedding model instances."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.database.models.base import Base, TimestampMixin, _uuid_pk


class EmbeddingModelConfig(Base, TimestampMixin):
    """User-created embedding model instance: provider + config (JSON).

    config holds: model, api_key, base_url, dimension, extra.
    """

    __tablename__ = "embedding_model_configs"
    __table_args__ = (
        Index("ix_emb_model_configs_provider", "provider"),
        Index("ix_emb_model_configs_is_active", "is_active"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"EmbeddingModelConfig(id={self.id!r}, name={self.name!r}, provider={self.provider!r})"
