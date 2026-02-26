"""EmbeddingModelConfigRepository – create/delete/list embedding models by provider; config as JSON."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.database.models.embedding_model_config import EmbeddingModelConfig
from backend.infra.database.repositories.base import BaseRepository


class EmbeddingModelConfigRepository(BaseRepository[EmbeddingModelConfig]):
    model = EmbeddingModelConfig

    async def create_embedding_model(
        self,
        name: str,
        provider: str,
        config: Dict[str, Any],
        *,
        is_active: bool = True,
    ) -> EmbeddingModelConfig:
        """Create a new embedding model instance. config should include model, api_key, etc."""
        return await self.create(
            {
                "name": name,
                "provider": provider,
                "config": config,
                "is_active": is_active,
            }
        )

    async def delete_embedding_model(self, id: UUID) -> bool:
        """Delete an embedding model by id. Returns True if deleted, False if not found."""
        return await self.delete(id)

    async def get_by_id(self, id: UUID) -> Optional[EmbeddingModelConfig]:
        return await super().get_by_id(id)

    async def list_all(
        self,
        *,
        active_only: bool = False,
        provider: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[EmbeddingModelConfig]:
        """List all embedding models, optionally filtered by provider and/or active."""
        stmt = (
            select(EmbeddingModelConfig)
            .order_by(EmbeddingModelConfig.provider, EmbeddingModelConfig.created_at)
            .offset(skip)
            .limit(limit)
        )
        if active_only:
            stmt = stmt.where(EmbeddingModelConfig.is_active.is_(True))
        if provider is not None:
            stmt = stmt.where(EmbeddingModelConfig.provider == provider)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def set_active(self, id: UUID, is_active: bool) -> Optional[EmbeddingModelConfig]:
        """Toggle is_active for an embedding model."""
        return await self.update(id, {"is_active": is_active})

    async def update(self, id: UUID, data: Dict[str, Any]) -> Optional[EmbeddingModelConfig]:
        """Update fields for an embedding model."""
        return await super().update(id, data)
