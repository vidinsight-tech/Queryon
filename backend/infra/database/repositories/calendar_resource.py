"""CalendarResource repository: CRUD and list by resource_name / calendar_type."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.database.models.calendar_resource import CalendarResource
from backend.infra.database.repositories.base import BaseRepository


class CalendarResourceRepository(BaseRepository[CalendarResource]):
    model = CalendarResource

    async def list_all(
        self,
        *,
        resource_name: Optional[str] = None,
        calendar_type: Optional[str] = None,
        active_only: bool = False,
        skip: int = 0,
        limit: int = 100,
    ) -> List[CalendarResource]:
        stmt = select(CalendarResource).order_by(CalendarResource.name).offset(skip).limit(limit)
        if resource_name is not None:
            stmt = stmt.where(CalendarResource.resource_name == resource_name)
        if calendar_type is not None:
            stmt = stmt.where(CalendarResource.calendar_type == calendar_type)
        if active_only:
            stmt = stmt.where(CalendarResource.is_active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_resource_name(self, resource_name: str) -> List[CalendarResource]:
        return await self.list_all(resource_name=resource_name, active_only=True, limit=50)
