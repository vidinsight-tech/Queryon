"""LLMRepository – create/delete/list LLMs by provider; config as JSON (LLMConfig)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.database.models import LLM
from backend.infra.database.repositories.base import BaseRepository


class LLMRepository(BaseRepository[LLM]):
    model = LLM

    async def create_llm(
        self,
        name: str,
        provider: str,
        config: Dict[str, Any],
        *,
        is_active: bool = True,
    ) -> LLM:
        """Create a new LLM instance. config should match LLMConfig.to_dict()."""
        return await self.create(
            {
                "name": name,
                "provider": provider,
                "config": config,
                "is_active": is_active,
            }
        )

    async def delete_llm(self, id: UUID) -> bool:
        """Delete an LLM by id. Returns True if deleted, False if not found."""
        return await self.delete(id)

    async def get_by_id(self, id: UUID) -> Optional[LLM]:
        return await super().get_by_id(id)

    async def list_by_provider(
        self,
        provider: str,
        *,
        active_only: bool = True,
        skip: int = 0,
        limit: int = 100,
    ) -> List[LLM]:
        """List LLMs for a given provider, optionally only active."""
        stmt = (
            select(LLM)
            .where(LLM.provider == provider)
            .order_by(LLM.created_at)
            .offset(skip)
            .limit(limit)
        )
        if active_only:
            stmt = stmt.where(LLM.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(
        self,
        *,
        active_only: bool = False,
        provider: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[LLM]:
        """List all LLMs, optionally filtered by provider and/or active."""
        stmt = select(LLM).order_by(LLM.provider, LLM.created_at).offset(skip).limit(limit)
        if active_only:
            stmt = stmt.where(LLM.is_active.is_(True))
        if provider is not None:
            stmt = stmt.where(LLM.provider == provider)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def set_active(self, id: UUID, is_active: bool) -> Optional[LLM]:
        """Toggle is_active for an LLM."""
        return await self.update(id, {"is_active": is_active})

    async def update_config(self, id: UUID, config: Dict[str, Any]) -> Optional[LLM]:
        """Update only the config JSON for an LLM."""
        return await self.update(id, {"config": config})
