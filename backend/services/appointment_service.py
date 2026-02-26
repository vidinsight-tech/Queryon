"""AppointmentService: create and manage appointments from chatbot conversations."""
from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.sql import func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.database.models.appointment import Appointment
from backend.infra.database.repositories.appointment import AppointmentRepository

logger = logging.getLogger(__name__)

# Standard field keys that map directly to Appointment columns
_STANDARD_KEYS = {
    "name": "contact_name",
    "surname": "contact_surname",
    "phone": "contact_phone",
    "email": "contact_email",
    "service": "service",
    "event_type": "service",
    "location": "location",
    "artist": "artist",
    "event_date": "event_date",
    "event_time": "event_time",
    "notes": "notes",
    "summary": "summary",
}


class AppointmentService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = AppointmentRepository(session)

    async def _generate_appt_number(self) -> str:
        """Generate a sequential reference number like RND-2026-0001."""
        year = _dt.date.today().year
        stmt = (
            select(func.max(Appointment.appt_number))
            .where(Appointment.appt_number.like(f"RND-{year}-%"))
        )
        max_val = (await self._repo.session.execute(stmt)).scalar()
        seq = int(max_val.split("-")[-1]) + 1 if max_val else 1
        return f"RND-{year}-{seq:04d}"

    async def create_from_flow_state(
        self,
        conversation_id: Optional[UUID],
        appt_dict: Dict[str, Any],
        fields_config: Optional[List[Dict[str, Any]]] = None,
    ) -> Appointment:
        """Create an Appointment record from the chatbot's collected flow state.

        Standard keys (name, surname, phone, email, service, location, artist,
        event_date, notes, summary) are mapped to dedicated columns.
        Any other keys are stored in ``extra_fields``.
        """
        data: Dict[str, Any] = {
            "conversation_id": conversation_id,
            "status": "pending",
            "extra_fields": {},
        }
        for key, value in appt_dict.items():
            if key in ("confirmed", "saved", "appointment_id", "appt_number", "active_mode"):
                continue
            if value == "__skip__":
                continue
            col = _STANDARD_KEYS.get(key)
            if col:
                data[col] = value
            else:
                data["extra_fields"][key] = value

        data["appt_number"] = await self._generate_appt_number()

        appt = await self._repo.create(data)
        logger.info(
            "AppointmentService: created appointment %s (%s) for conversation %s",
            appt.id, appt.appt_number, conversation_id,
        )
        return appt

    async def reschedule_by_number(
        self,
        appt_number: str,
        requesting_conversation_id: UUID,
        updates: Dict[str, Any],
    ) -> Tuple[Optional[Appointment], str]:
        """Reschedule an appointment by reference number, verifying ownership.

        Returns (appointment, outcome) where outcome is one of:
        "ok" | "not_found" | "unauthorized" | "already_cancelled"
        """
        appt = await self._repo.get_by_appt_number(appt_number)
        if appt is None:
            return None, "not_found"
        if appt.status == "cancelled":
            return appt, "already_cancelled"

        if not self._is_authorized(appt, requesting_conversation_id):
            from backend.infra.database.repositories.conversation import ConversationRepository
            conv_repo = ConversationRepository(self._repo.session)
            req_conv = await conv_repo.get_by_id(requesting_conversation_id)
            appt_conv = await conv_repo.get_by_id(appt.conversation_id) if appt.conversation_id else None

            if not self._check_channel_ownership(req_conv, appt_conv):
                return None, "unauthorized"

        # Map chatbot field names to DB column names
        _field_map = {
            "event_date": "event_date",
            "event_time": "event_time",
            "artist": "artist",
            "service": "service",
        }
        db_updates = {_field_map.get(k, k): v for k, v in updates.items() if k in _field_map}
        if not db_updates:
            return appt, "ok"

        updated = await self._repo.update(appt.id, db_updates)
        logger.info(
            "AppointmentService: rescheduled appointment %s (%s) fields=%s",
            appt.id, appt_number, list(db_updates.keys()),
        )
        return updated, "ok"

    async def cancel_by_number(
        self,
        appt_number: str,
        requesting_conversation_id: UUID,
    ) -> Tuple[Optional[Appointment], str]:
        """Cancel an appointment by reference number, verifying ownership.

        Returns (appointment, outcome) where outcome is one of:
        "ok" | "not_found" | "unauthorized" | "already_cancelled"
        """
        appt = await self._repo.get_by_appt_number(appt_number)
        if appt is None:
            return None, "not_found"
        if appt.status == "cancelled":
            return appt, "already_cancelled"

        if not self._is_authorized(appt, requesting_conversation_id):
            from backend.infra.database.repositories.conversation import ConversationRepository
            conv_repo = ConversationRepository(self._repo.session)
            req_conv = await conv_repo.get_by_id(requesting_conversation_id)
            appt_conv = await conv_repo.get_by_id(appt.conversation_id) if appt.conversation_id else None

            if not self._check_channel_ownership(req_conv, appt_conv):
                return None, "unauthorized"

        updated = await self._repo.update_status(appt.id, "cancelled")
        return updated, "ok"

    @staticmethod
    def _is_authorized(appt: Appointment, requesting_conversation_id: UUID) -> bool:
        """Fast-path: same conversation always has permission."""
        return appt.conversation_id is not None and appt.conversation_id == requesting_conversation_id

    @staticmethod
    def _check_channel_ownership(req_conv, appt_conv) -> bool:
        """Cross-conversation ownership: same platform + same non-null channel_id."""
        if req_conv is None or appt_conv is None:
            return False
        if req_conv.channel_id is None or appt_conv.channel_id is None:
            return False
        return (
            req_conv.channel_id == appt_conv.channel_id
            and req_conv.platform == appt_conv.platform
        )

    async def list_appointments(
        self,
        *,
        status: Optional[str] = None,
        search: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Appointment]:
        return await self._repo.list_all(
            status=status,
            search=search,
            date_from=date_from,
            date_to=date_to,
            skip=skip,
            limit=limit,
        )

    async def get_appointment(self, id: UUID) -> Optional[Appointment]:
        return await self._repo.get_by_id(id)

    async def update_status(self, id: UUID, status: str) -> Optional[Appointment]:
        return await self._repo.update_status(id, status)

    async def update_appointment(self, id: UUID, data: Dict[str, Any]) -> Optional[Appointment]:
        return await self._repo.update(id, data)

    async def delete_appointment(self, id: UUID) -> bool:
        return await self._repo.delete(id)
