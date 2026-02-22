"""Embedding + database: get client by id, create, delete."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from uuid import UUID

from backend.clients.embedding.registry import EmbeddingRegistry, default_registry
from backend.infra.database.repositories import EmbeddingRepository

if TYPE_CHECKING:
    from backend.clients.embedding.base import BaseEmbeddingClient
    from backend.infra.database.models import Embedding
    from sqlalchemy.ext.asyncio import AsyncSession


class EmbeddingService:
    """Embedding kayıtları ve client üretimi. Session + registry kullanır."""

    def __init__(
        self,
        session: "AsyncSession",
        registry: Optional[EmbeddingRegistry] = None,
    ) -> None:
        self._session = session
        self._repo = EmbeddingRepository(session)
        self._registry = registry if registry is not None else default_registry

    async def get_client(self, embedding_id: UUID) -> Optional[BaseEmbeddingClient]:
        """DB'den Embedding kaydını alır, ilgili client'ı döner. Yoksa None."""
        emb = await self._repo.get_by_id(embedding_id)
        if emb is None:
            return None
        return self._registry.build(emb.provider, dict(emb.config))

    async def create(
        self,
        name: str,
        provider: str,
        config: dict,
        *,
        is_active: bool = True,
    ) -> Embedding:
        """Yeni Embedding kaydı oluşturur. config örn. EmbeddingConfig.to_dict()."""
        return await self._repo.create_embedding(name, provider, config, is_active=is_active)

    async def delete(self, embedding_id: UUID) -> bool:
        """Embedding kaydını siler. Silindi mi True/False."""
        return await self._repo.delete_embedding(embedding_id)
