"""EmbeddingRepository – create/delete/list embeddings by provider; config as JSON."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.database.models import Embedding
from backend.infra.database.repositories.base import BaseRepository


class EmbeddingRepository(BaseRepository[Embedding]):
    model = Embedding

    async def create_embedding(
        self,
        name: str,
        provider: str,
        config: Dict[str, Any],
        *,
        is_active: bool = True,
    ) -> Embedding:
        """Create a new Embedding instance. config should match EmbeddingConfig.to_dict()."""
        return await self.create(
            {
                "name": name,
                "provider": provider,
                "config": config,
                "is_active": is_active,
            }
        )

    async def delete_embedding(self, id: UUID) -> bool:
        """Delete an Embedding by id. Returns True if deleted, False if not found."""
        return await self.delete(id)

    async def get_by_id(self, id: UUID) -> Optional[Embedding]:
        return await super().get_by_id(id)

    async def list_by_provider(
        self,
        provider: str,
        *,
        active_only: bool = True,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Embedding]:
        """List embeddings for a given provider."""
        stmt = (
            select(Embedding)
            .where(Embedding.provider == provider)
            .order_by(Embedding.created_at)
            .offset(skip)
            .limit(limit)
        )
        if active_only:
            stmt = stmt.where(Embedding.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(
        self,
        *,
        active_only: bool = False,
        provider: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Embedding]:
        """List all embeddings, optionally filtered by provider and/or active."""
        stmt = (
            select(Embedding)
            .order_by(Embedding.provider, Embedding.created_at)
            .offset(skip)
            .limit(limit)
        )
        if active_only:
            stmt = stmt.where(Embedding.is_active.is_(True))
        if provider is not None:
            stmt = stmt.where(Embedding.provider == provider)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def set_active(self, id: UUID, is_active: bool) -> Optional[Embedding]:
        """Toggle is_active for an embedding."""
        return await self.update(id, {"is_active": is_active})

    async def update_config(self, id: UUID, config: Dict[str, Any]) -> Optional[Embedding]:
        """Update only the config JSON."""
        return await self.update(id, {"config": config})
