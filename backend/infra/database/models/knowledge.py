"""KnowledgeDocument + DocumentChunk ORM models."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.infra.database.models.base import Base, TimestampMixin, _uuid_pk


class KnowledgeDocument(Base, TimestampMixin):
    """A document ingested into the knowledge base."""

    __tablename__ = "knowledge_documents"
    __table_args__ = (
        Index("ix_kd_source_type", "source_type"),
        Index("ix_kd_is_active", "is_active"),
        Index("ix_kd_title", "title"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)

    file_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    embedding_model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    embedding_dimension: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    raw_char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    tags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    meta: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    chunks: Mapped[List["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"KnowledgeDocument(id={self.id!r}, title={self.title!r})"


class DocumentChunk(Base, TimestampMixin):
    """A chunk belonging to a KnowledgeDocument with a pointer into Qdrant."""

    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_dc_document_id", "document_id"),
        Index("ix_dc_vector_id", "vector_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    vector_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    meta: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    document: Mapped["KnowledgeDocument"] = relationship(
        "KnowledgeDocument",
        back_populates="chunks",
    )

    def __repr__(self) -> str:
        return f"DocumentChunk(id={self.id!r}, doc={self.document_id!r}, idx={self.chunk_index})"
