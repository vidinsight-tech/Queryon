"""Calendars API: CRUD for calendar resources and per-resource Google connection."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_session
from backend.api.schemas.calendars import (
    CalendarResourceCreate,
    CalendarResourceResponse,
    CalendarResourceUpdate,
    ConnectGoogleRequest,
)
from backend.infra.database.models.calendar_resource import CalendarResource
from backend.infra.database.models.tool_config import ToolConfig
from backend.infra.database.repositories import CalendarResourceRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/calendars", tags=["calendars"])


def _to_response(r: CalendarResource) -> CalendarResourceResponse:
    return CalendarResourceResponse(
        id=r.id,
        name=r.name,
        resource_type=r.resource_type,
        resource_name=r.resource_name,
        calendar_type=r.calendar_type,
        color=r.color,
        timezone=r.timezone,
        working_hours=r.working_hours or {},
        service_durations=r.service_durations or {},
        calendar_id=r.calendar_id,
        ical_url=r.ical_url,
        has_credentials=bool(r.credentials),
        is_active=r.is_active,
        created_at=r.created_at,
        updated_at=r.updated_at,
    )


@router.get("", response_model=List[CalendarResourceResponse])
async def list_calendars(
    resource_name: Optional[str] = None,
    calendar_type: Optional[str] = None,
    active_only: bool = False,
    skip: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
):
    repo = CalendarResourceRepository(session)
    items = await repo.list_all(
        resource_name=resource_name,
        calendar_type=calendar_type,
        active_only=active_only,
        skip=skip,
        limit=limit,
    )
    return [_to_response(r) for r in items]


@router.get("/by-resource/{resource_name}", response_model=List[CalendarResourceResponse])
async def list_calendars_by_resource(
    resource_name: str,
    session: AsyncSession = Depends(get_session),
):
    """List active calendars for a given resource (e.g. artist name). For bot availability lookup."""
    repo = CalendarResourceRepository(session)
    items = await repo.list_by_resource_name(resource_name)
    return [_to_response(r) for r in items]


@router.get("/{calendar_id}", response_model=CalendarResourceResponse)
async def get_calendar(
    calendar_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    repo = CalendarResourceRepository(session)
    r = await repo.get_by_id(calendar_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Calendar not found")
    return _to_response(r)


@router.post("", response_model=CalendarResourceResponse, status_code=201)
async def create_calendar(
    body: CalendarResourceCreate,
    session: AsyncSession = Depends(get_session),
):
    repo = CalendarResourceRepository(session)
    data = body.model_dump()
    r = await repo.create(data)
    return _to_response(r)


@router.patch("/{calendar_id}", response_model=CalendarResourceResponse)
async def update_calendar(
    calendar_id: UUID,
    body: CalendarResourceUpdate,
    session: AsyncSession = Depends(get_session),
):
    repo = CalendarResourceRepository(session)
    r = await repo.get_by_id(calendar_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Calendar not found")
    data = body.model_dump(exclude_unset=True)
    if data:
        r = await repo.update(calendar_id, data)
    return _to_response(r)


@router.post("/{calendar_id}/connect-google", response_model=CalendarResourceResponse)
async def connect_google(
    calendar_id: UUID,
    body: ConnectGoogleRequest,
    session: AsyncSession = Depends(get_session),
):
    """Set Google Calendar ID and optional per-resource credentials for this calendar."""
    repo = CalendarResourceRepository(session)
    r = await repo.get_by_id(calendar_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Calendar not found")
    update: Dict[str, Any] = {
        "calendar_type": "google",
        "calendar_id": body.calendar_id,
    }
    if body.credentials_json is not None:
        update["credentials"] = body.credentials_json
    r = await repo.update(calendar_id, update)
    return _to_response(r)


async def _get_credentials_for_google(
    session: AsyncSession,
    resource: Optional[CalendarResource],
) -> Optional[str]:
    if resource and resource.credentials:
        return resource.credentials
    result = await session.execute(select(ToolConfig).where(ToolConfig.name == "check_calendar_availability"))
    row = result.scalar_one_or_none()
    if row and row.credentials:
        return row.credentials
    return None


@router.get("/{calendar_id}/test-connection")
async def test_connection(
    calendar_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Test Google Calendar connection for this resource (freebusy query). Returns 200 if OK, 503 on failure."""
    repo = CalendarResourceRepository(session)
    r = await repo.get_by_id(calendar_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Calendar not found")
    if r.calendar_type != "google":
        raise HTTPException(
            status_code=400,
            detail="Test connection is only for calendar_type=google",
        )
    creds_json = await _get_credentials_for_google(session, r)
    if not creds_json:
        raise HTTPException(
            status_code=503,
            detail="No credentials. Set per-resource credentials or configure global Google Calendar in Tools.",
        )
    cal_id = r.calendar_id or "primary"
    try:
        from backend.tools.builtin.google_calendar import _build_service
    except ImportError:
        raise HTTPException(status_code=503, detail="Google Calendar support not installed")
    try:
        service = _build_service(creds_json)
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=1)
        body = {
            "timeMin": now.isoformat(),
            "timeMax": end.isoformat(),
            "items": [{"id": cal_id}],
        }

        def _sync_query():
            return service.freebusy().query(body=body).execute()

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _sync_query)
        calendars = result.get("calendars", {})
        if cal_id not in calendars:
            raise HTTPException(status_code=503, detail=f"Calendar {cal_id} not found or no access")
        return {"ok": True, "calendar_id": cal_id, "message": "Connection successful"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Calendar test_connection failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))


@router.delete("/{calendar_id}", status_code=204)
async def delete_calendar(
    calendar_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    repo = CalendarResourceRepository(session)
    ok = await repo.delete(calendar_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Calendar not found")


# ── Availability ──────────────────────────────────────────────────────────────

@router.get("/{calendar_id}/availability")
async def get_availability(
    calendar_id: UUID,
    date: str,
    service: Optional[str] = None,
    buffer: int = 0,
    session: AsyncSession = Depends(get_session),
):
    """Return available time slots for a calendar resource on a given date (YYYY-MM-DD)."""
    from backend.services.availability_service import AvailabilityService
    import datetime as _dt

    try:
        d = _dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    svc = AvailabilityService(session)
    slots = await svc.get_slots(calendar_id, d, service_name=service, buffer_minutes=buffer)
    return {"date": date, "calendar_id": str(calendar_id), "available_slots": slots}


@router.get("/by-resource/{resource_name}/availability")
async def get_availability_by_resource(
    resource_name: str,
    date: str,
    service: Optional[str] = None,
    buffer: int = 0,
    session: AsyncSession = Depends(get_session),
):
    """Return available time slots for a resource name (e.g. artist) on a given date. Used by bot."""
    from backend.services.availability_service import AvailabilityService
    import datetime as _dt

    try:
        d = _dt.date.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    svc = AvailabilityService(session)
    slots = await svc.get_slots_by_resource_name(resource_name, d, service_name=service, buffer_minutes=buffer)
    return {"date": date, "resource_name": resource_name, "available_slots": slots}


# ── Block CRUD ────────────────────────────────────────────────────────────────

from pydantic import BaseModel, Field  # noqa: E402


class BlockCreateRequest(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD")
    start_time: str = Field(..., description="HH:MM")
    end_time: str = Field(..., description="HH:MM")
    block_type: str = Field(default="blocked", description="booked | blocked | break | buffer")
    label: Optional[str] = None


class BlockResponse(BaseModel):
    id: str
    calendar_resource_id: str
    date: str
    start_time: str
    end_time: str
    block_type: str
    appointment_id: Optional[str] = None
    label: Optional[str] = None
    created_at: Optional[str] = None


def _block_response(b) -> BlockResponse:
    return BlockResponse(
        id=str(b.id),
        calendar_resource_id=str(b.calendar_resource_id),
        date=b.date.isoformat(),
        start_time=b.start_time.strftime("%H:%M"),
        end_time=b.end_time.strftime("%H:%M"),
        block_type=b.block_type,
        appointment_id=str(b.appointment_id) if b.appointment_id else None,
        label=b.label,
        created_at=b.created_at.isoformat() if b.created_at else None,
    )


@router.get("/{calendar_id}/blocks", response_model=List[BlockResponse])
async def list_blocks(
    calendar_id: UUID,
    date: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """List blocks for a calendar. Filter by single date or date range."""
    from backend.infra.database.repositories import CalendarBlockRepository
    import datetime as _dt

    repo = CalendarBlockRepository(session)
    if date:
        try:
            d = _dt.date.fromisoformat(date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date")
        items = await repo.list_for_date(calendar_id, d)
    elif start_date and end_date:
        try:
            sd = _dt.date.fromisoformat(start_date)
            ed = _dt.date.fromisoformat(end_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date")
        items = await repo.list_for_range(calendar_id, sd, ed)
    else:
        import datetime as _dt2
        today = _dt2.date.today()
        items = await repo.list_for_range(calendar_id, today, today + _dt.timedelta(days=30))
    return [_block_response(b) for b in items]


@router.post("/{calendar_id}/blocks", response_model=BlockResponse, status_code=201)
async def create_block(
    calendar_id: UUID,
    body: BlockCreateRequest,
    session: AsyncSession = Depends(get_session),
):
    """Create a manual block (break, holiday, etc.) on a calendar."""
    from backend.infra.database.repositories import CalendarBlockRepository, CalendarResourceRepository
    import datetime as _dt

    cal_repo = CalendarResourceRepository(session)
    r = await cal_repo.get_by_id(calendar_id)
    if r is None:
        raise HTTPException(status_code=404, detail="Calendar not found")

    try:
        d = _dt.date.fromisoformat(body.date)
        st = _dt.datetime.strptime(body.start_time, "%H:%M").time()
        et = _dt.datetime.strptime(body.end_time, "%H:%M").time()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date/time format")

    block_repo = CalendarBlockRepository(session)
    block = await block_repo.create({
        "calendar_resource_id": calendar_id,
        "date": d,
        "start_time": st,
        "end_time": et,
        "block_type": body.block_type,
        "label": body.label,
    })
    return _block_response(block)


@router.delete("/{calendar_id}/blocks/{block_id}", status_code=204)
async def delete_block(
    calendar_id: UUID,
    block_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    from backend.infra.database.repositories import CalendarBlockRepository
    repo = CalendarBlockRepository(session)
    block = await repo.get_by_id(block_id)
    if block is None or block.calendar_resource_id != calendar_id:
        raise HTTPException(status_code=404, detail="Block not found")
    await repo.delete(block_id)
