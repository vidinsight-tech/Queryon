"""EmbeddingModelService: build embedding client from DB record."""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from backend.clients.embedding.registry import default_registry
from backend.infra.database.repositories.embedding_model_config import EmbeddingModelConfigRepository

if TYPE_CHECKING:
    from backend.clients.embedding.base import BaseEmbeddingClient
    from sqlalchemy.ext.asyncio import AsyncSession


class EmbeddingModelService:
    def __init__(self, session: "AsyncSession") -> None:
        self._session = session
        self._repo = EmbeddingModelConfigRepository(session)

    async def get_client(self, embedding_model_id: UUID) -> Optional["BaseEmbeddingClient"]:
        rec = await self._repo.get_by_id(embedding_model_id)
        if rec is None:
            return None
        try:
            return default_registry.build(rec.provider, dict(rec.config))
        except KeyError:
            return None
