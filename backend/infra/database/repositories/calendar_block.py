"""CalendarBlock repository: list/create/delete blocks for a calendar resource."""
from __future__ import annotations

import datetime as _dt
from typing import List, Optional
from uuid import UUID

from sqlalchemy import delete as sa_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.database.models.calendar_block import CalendarBlock
from backend.infra.database.repositories.base import BaseRepository


class CalendarBlockRepository(BaseRepository[CalendarBlock]):
    model = CalendarBlock

    async def list_for_date(
        self,
        calendar_resource_id: UUID,
        date: _dt.date,
    ) -> List[CalendarBlock]:
        stmt = (
            select(CalendarBlock)
            .where(CalendarBlock.calendar_resource_id == calendar_resource_id)
            .where(CalendarBlock.date == date)
            .order_by(CalendarBlock.start_time)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_range(
        self,
        calendar_resource_id: UUID,
        start_date: _dt.date,
        end_date: _dt.date,
    ) -> List[CalendarBlock]:
        stmt = (
            select(CalendarBlock)
            .where(CalendarBlock.calendar_resource_id == calendar_resource_id)
            .where(CalendarBlock.date >= start_date)
            .where(CalendarBlock.date <= end_date)
            .order_by(CalendarBlock.date, CalendarBlock.start_time)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_appointment_id(self, appointment_id: UUID) -> int:
        """Delete all blocks linked to the given appointment.

        Returns the number of rows deleted.
        Called when an appointment is cancelled or permanently deleted so
        the artist's calendar slot is freed immediately.

        ``synchronize_session=False`` is required for async sessions: bulk
        DML bypasses the ORM identity map, so we tell SQLAlchemy not to try
        to evaluate / fetch the affected objects from its cache.
        """
        stmt = (
            sa_delete(CalendarBlock)
            .where(CalendarBlock.appointment_id == appointment_id)
            .execution_options(synchronize_session=False)
        )
        result = await self.session.execute(stmt)
        return result.rowcount
