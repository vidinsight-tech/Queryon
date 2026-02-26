"""Order repository."""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select

from backend.infra.database.models.order import Order
from backend.infra.database.repositories.base import BaseRepository


class OrderRepository(BaseRepository[Order]):
    model = Order

    async def list_all(
        self,
        *,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Order]:
        stmt = select(Order).order_by(Order.created_at.desc())
        if status:
            stmt = stmt.where(Order.status == status)
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(self, id: UUID, status: str) -> Optional[Order]:
        return await self.update(id, {"status": status})
