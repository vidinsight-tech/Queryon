"""Appointment repository."""
from __future__ import annotations

import datetime as _dt
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select

from backend.infra.database.models.appointment import Appointment
from backend.infra.database.repositories.base import BaseRepository


class AppointmentRepository(BaseRepository[Appointment]):
    model = Appointment

    async def list_all(
        self,
        *,
        status: Optional[str] = None,
        search: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Appointment]:
        stmt = select(Appointment).order_by(Appointment.created_at.desc())
        if status:
            stmt = stmt.where(Appointment.status == status)
        if search:
            stmt = stmt.where(Appointment.appt_number.ilike(f"%{search}%"))
        if date_from:
            try:
                df = _dt.datetime.fromisoformat(date_from)
            except ValueError:
                df = _dt.datetime.strptime(date_from, "%Y-%m-%d")
            stmt = stmt.where(Appointment.created_at >= df)
        if date_to:
            try:
                dt_ = _dt.datetime.fromisoformat(date_to)
            except ValueError:
                dt_ = _dt.datetime.strptime(date_to, "%Y-%m-%d")
            # Include the full day
            dt_ = dt_.replace(hour=23, minute=59, second=59)
            stmt = stmt.where(Appointment.created_at <= dt_)
        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_appt_number(self, appt_number: str) -> Optional[Appointment]:
        stmt = select(Appointment).where(Appointment.appt_number == appt_number)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(self, id: UUID, status: str) -> Optional[Appointment]:
        return await self.update(id, {"status": status})
