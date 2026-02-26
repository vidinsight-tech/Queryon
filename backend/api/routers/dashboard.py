"""Dashboard stats endpoint — aggregated counts for the admin home page."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_session
from backend.infra.database.models import (
    Appointment,
    Conversation,
    KnowledgeDocument,
    Order,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


# ── Response schemas ──────────────────────────────────────────────────────────

class StatusCount(BaseModel):
    status: str
    count: int


class RecentConversation(BaseModel):
    id: str
    platform: str
    status: str
    message_count: int
    contact_name: Optional[str] = None
    last_message_at: Optional[datetime] = None
    created_at: datetime


class DashboardStats(BaseModel):
    conversations_total: int
    conversations_active: int
    conversations_today: int
    appointments_by_status: List[StatusCount]
    appointments_total: int
    orders_by_status: List[StatusCount]
    orders_total: int
    documents_active: int
    recent_conversations: List[RecentConversation]


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("", response_model=DashboardStats)
async def get_dashboard_stats(session: AsyncSession = Depends(get_session)):
    """Return aggregated counts for the admin dashboard."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # ── Conversations ─────────────────────────────────────────────────────────
    conv_total_result = await session.execute(
        select(func.count()).select_from(Conversation)
    )
    conversations_total = conv_total_result.scalar_one() or 0

    conv_active_result = await session.execute(
        select(func.count()).select_from(Conversation).where(Conversation.status == "active")
    )
    conversations_active = conv_active_result.scalar_one() or 0

    conv_today_result = await session.execute(
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.created_at >= today_start)
    )
    conversations_today = conv_today_result.scalar_one() or 0

    # ── Appointments ──────────────────────────────────────────────────────────
    appt_rows = await session.execute(
        select(Appointment.status, func.count().label("cnt"))
        .group_by(Appointment.status)
    )
    appointments_by_status = [
        StatusCount(status=row.status, count=row.cnt)
        for row in appt_rows.all()
    ]
    appointments_total = sum(s.count for s in appointments_by_status)

    # ── Orders ────────────────────────────────────────────────────────────────
    order_rows = await session.execute(
        select(Order.status, func.count().label("cnt"))
        .group_by(Order.status)
    )
    orders_by_status = [
        StatusCount(status=row.status, count=row.cnt)
        for row in order_rows.all()
    ]
    orders_total = sum(s.count for s in orders_by_status)

    # ── Documents ─────────────────────────────────────────────────────────────
    docs_result = await session.execute(
        select(func.count())
        .select_from(KnowledgeDocument)
        .where(KnowledgeDocument.is_active == True)  # noqa: E712
    )
    documents_active = docs_result.scalar_one() or 0

    # ── Recent conversations (last 10) ─────────────────────────────────────
    recent_result = await session.execute(
        select(Conversation)
        .order_by(Conversation.last_message_at.desc().nulls_last())
        .limit(10)
    )
    recent_conversations = [
        RecentConversation(
            id=str(c.id),
            platform=c.platform,
            status=c.status,
            message_count=c.message_count,
            contact_name=c.contact_name,
            last_message_at=c.last_message_at,
            created_at=c.created_at,
        )
        for c in recent_result.scalars().all()
    ]

    return DashboardStats(
        conversations_total=conversations_total,
        conversations_active=conversations_active,
        conversations_today=conversations_today,
        appointments_by_status=appointments_by_status,
        appointments_total=appointments_total,
        orders_by_status=orders_by_status,
        orders_total=orders_total,
        documents_active=documents_active,
        recent_conversations=recent_conversations,
    )
