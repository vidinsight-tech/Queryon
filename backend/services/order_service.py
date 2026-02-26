"""OrderService: create and manage orders from chatbot conversations."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.database.models.order import Order
from backend.infra.database.repositories.order import OrderRepository

logger = logging.getLogger(__name__)

# Standard field keys that map directly to Order columns
_STANDARD_KEYS = {
    "name": "contact_name",
    "surname": "contact_surname",
    "phone": "contact_phone",
    "email": "contact_email",
    "notes": "notes",
    "summary": "summary",
}


class OrderService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = OrderRepository(session)

    async def create_from_flow_state(
        self,
        conversation_id: Optional[UUID],
        order_dict: Dict[str, Any],
        fields_config: Optional[List[Dict[str, Any]]] = None,
    ) -> Order:
        """Create an Order record from the chatbot's collected flow state.

        Standard keys (name, surname, phone, email, notes, summary) are mapped
        to dedicated columns. Any other keys are stored in ``extra_fields``.
        """
        data: Dict[str, Any] = {
            "conversation_id": conversation_id,
            "status": "pending",
            "extra_fields": {},
        }
        for key, value in order_dict.items():
            if key in ("confirmed", "saved", "order_id"):
                continue
            if value == "__skip__":
                continue
            col = _STANDARD_KEYS.get(key)
            if col:
                data[col] = value
            else:
                data["extra_fields"][key] = value

        order = await self._repo.create(data)
        logger.info(
            "OrderService: created order %s for conversation %s",
            order.id, conversation_id,
        )
        return order

    async def list_orders(
        self,
        *,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Order]:
        return await self._repo.list_all(status=status, skip=skip, limit=limit)

    async def get_order(self, id: UUID) -> Optional[Order]:
        return await self._repo.get_by_id(id)

    async def update_status(self, id: UUID, status: str) -> Optional[Order]:
        return await self._repo.update_status(id, status)

    async def update_order(self, id: UUID, data: Dict[str, Any]) -> Optional[Order]:
        return await self._repo.update(id, data)

    async def delete_order(self, id: UUID) -> bool:
        return await self._repo.delete(id)
