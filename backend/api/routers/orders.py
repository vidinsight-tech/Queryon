"""Orders API: list, get, update status, delete."""
from __future__ import annotations

import uuid
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_session
from backend.services.order_service import OrderService

router = APIRouter(prefix="/orders", tags=["orders"])

_VALID_STATUSES = {"pending", "confirmed", "cancelled"}


# ── Schemas ───────────────────────────────────────────────────────────────────

class OrderResponse(BaseModel):
    id: str
    conversation_id: Optional[str] = None
    status: str
    contact_name: Optional[str] = None
    contact_surname: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None
    summary: Optional[str] = None
    extra_fields: Dict[str, Any] = {}
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class OrderStatusUpdate(BaseModel):
    status: str


class OrderUpdateRequest(BaseModel):
    status: Optional[str] = None
    contact_name: Optional[str] = None
    contact_surname: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None


# ── Helper ────────────────────────────────────────────────────────────────────

def _to_schema(o) -> OrderResponse:
    return OrderResponse(
        id=str(o.id),
        conversation_id=str(o.conversation_id) if o.conversation_id else None,
        status=o.status,
        contact_name=o.contact_name,
        contact_surname=o.contact_surname,
        contact_phone=o.contact_phone,
        contact_email=o.contact_email,
        notes=o.notes,
        summary=o.summary,
        extra_fields=o.extra_fields or {},
        created_at=o.created_at.isoformat() if o.created_at else None,
        updated_at=o.updated_at.isoformat() if o.updated_at else None,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[OrderResponse])
async def list_orders(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
):
    """List orders, optionally filtered by status."""
    if status and status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use one of: {_VALID_STATUSES}")
    svc = OrderService(session)
    items = await svc.list_orders(status=status, skip=skip, limit=limit)
    return [_to_schema(o) for o in items]


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    svc = OrderService(session)
    order = await svc.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return _to_schema(order)


@router.patch("/{order_id}", response_model=OrderResponse)
async def update_order_status(
    order_id: uuid.UUID,
    body: OrderStatusUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update the status of an order (confirmed / cancelled / pending)."""
    if body.status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use one of: {_VALID_STATUSES}")
    svc = OrderService(session)
    order = await svc.update_status(order_id, body.status)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    await session.commit()
    return _to_schema(order)


@router.put("/{order_id}", response_model=OrderResponse)
async def update_order(
    order_id: uuid.UUID,
    body: OrderUpdateRequest,
    session: AsyncSession = Depends(get_session),
):
    """Full update of an order."""
    svc = OrderService(session)
    order = await svc.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    if body.status and body.status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use one of: {_VALID_STATUSES}")

    update_data: Dict[str, Any] = {}
    for field_name in ("status", "contact_name", "contact_surname", "contact_phone", "contact_email", "notes"):
        val = getattr(body, field_name)
        if val is not None:
            update_data[field_name] = val

    if not update_data:
        return _to_schema(order)

    updated = await svc.update_order(order_id, update_data)
    if updated is None:
        raise HTTPException(status_code=404, detail="Order not found")
    await session.commit()
    return _to_schema(updated)


@router.delete("/{order_id}", status_code=204)
async def delete_order(
    order_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    svc = OrderService(session)
    ok = await svc.delete_order(order_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Order not found")
    await session.commit()
