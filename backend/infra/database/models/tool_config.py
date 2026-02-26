"""ORM models for orchestrator config persistence and tool configuration."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.database.models.base import Base, TimestampMixin, _uuid_pk


class OrchestratorConfigModel(Base, TimestampMixin):
    """Single-row table that persists the active OrchestratorConfig as JSON.

    Always use id=1 as the single row. Use upsert semantics on write.
    """

    __tablename__ = "orchestrator_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    config_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )


class ToolConfig(Base, TimestampMixin):
    """Persisted configuration and credentials for a registered tool.

    Builtin tools are seeded by the registry builder. Custom tools are
    created via the API.  Credentials (e.g. Google Calendar service-account
    JSON) are stored as plaintext here — add encryption at rest in production.
    """

    __tablename__ = "tool_configs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parameters: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    credentials: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # encrypted JSON for OAuth / service accounts
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RagConfigModel(Base):
    """Single-row table (id=1) that stores which LLM and embedding model are wired to RAG."""

    __tablename__ = "rag_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    llm_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    embedding_model_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
