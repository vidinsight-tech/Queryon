"""CalendarBlock ORM: time blocks on a calendar resource (booked, blocked, break, buffer)."""

import datetime as _dt
import uuid
from typing import Optional

from sqlalchemy import Date, ForeignKey, Index, String, Time, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.infra.database.models.base import Base, TimestampMixin, _uuid_pk


class CalendarBlock(Base, TimestampMixin):
    """
    A time block on a CalendarResource's internal calendar.
    block_type: "booked" | "blocked" | "break" | "buffer"
    """

    __tablename__ = "calendar_blocks"
    __table_args__ = (
        Index("ix_calendar_blocks_calendar_date", "calendar_resource_id", "date"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    calendar_resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("calendar_resources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date: Mapped[_dt.date] = mapped_column(Date, nullable=False)
    start_time: Mapped[_dt.time] = mapped_column(Time, nullable=False)
    end_time: Mapped[_dt.time] = mapped_column(Time, nullable=False)
    block_type: Mapped[str] = mapped_column(String(32), nullable=False, default="booked")
    appointment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="SET NULL"),
        nullable=True,
    )
    label: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
