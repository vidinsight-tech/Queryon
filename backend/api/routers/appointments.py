"""Appointments API: list, get, update status/fields, reschedule, delete."""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select as _select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_session
from backend.infra.database.repositories import CalendarBlockRepository
from backend.services.appointment_service import AppointmentService
from backend.services.appointment_webhook_service import dispatch as _webhook_dispatch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/appointments", tags=["appointments"])

_VALID_STATUSES = {"pending", "confirmed", "cancelled"}


# ── Schemas ───────────────────────────────────────────────────────────────────

class LinkedBlockInfo(BaseModel):
    block_id: str
    resource_name: str
    date: str
    start_time: str
    end_time: str


class AppointmentResponse(BaseModel):
    id: str
    conversation_id: Optional[str] = None
    appt_number: Optional[str] = None
    status: str
    service: Optional[str] = None
    location: Optional[str] = None
    artist: Optional[str] = None
    event_date: Optional[str] = None
    event_time: Optional[str] = None
    contact_name: Optional[str] = None
    contact_surname: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None
    summary: Optional[str] = None
    extra_fields: Dict[str, Any] = {}
    calendar_block: Optional[LinkedBlockInfo] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AppointmentStatusUpdate(BaseModel):
    status: str


class AppointmentUpdateRequest(BaseModel):
    status: Optional[str] = None
    service: Optional[str] = None
    location: Optional[str] = None
    artist: Optional[str] = None
    event_date: Optional[str] = None
    event_time: Optional[str] = None
    contact_name: Optional[str] = None
    contact_surname: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    notes: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _to_schema(a, calendar_block: Optional[LinkedBlockInfo] = None) -> AppointmentResponse:
    return AppointmentResponse(
        id=str(a.id),
        conversation_id=str(a.conversation_id) if a.conversation_id else None,
        appt_number=a.appt_number,
        status=a.status,
        service=a.service,
        location=a.location,
        artist=a.artist,
        event_date=a.event_date,
        event_time=a.event_time,
        contact_name=a.contact_name,
        contact_surname=a.contact_surname,
        contact_phone=a.contact_phone,
        contact_email=a.contact_email,
        notes=a.notes,
        summary=a.summary,
        extra_fields=a.extra_fields or {},
        calendar_block=calendar_block,
        created_at=a.created_at.isoformat() if a.created_at else None,
        updated_at=a.updated_at.isoformat() if a.updated_at else None,
    )


async def _get_block_for_appointment(
    session: AsyncSession, appointment_id: uuid.UUID
) -> Optional[LinkedBlockInfo]:
    """Query the linked CalendarBlock for a single appointment."""
    from backend.infra.database.models.calendar_block import CalendarBlock as _CB
    from backend.infra.database.models.calendar_resource import CalendarResource as _CR

    stmt = (
        _select(_CB, _CR.name)
        .join(_CR, _CB.calendar_resource_id == _CR.id)
        .where(_CB.appointment_id == appointment_id)
        .limit(1)
    )
    result = await session.execute(stmt)
    row = result.first()
    if row is None:
        return None
    block, resource_name = row
    return LinkedBlockInfo(
        block_id=str(block.id),
        resource_name=resource_name or "",
        date=str(block.date),
        start_time=str(block.start_time),
        end_time=str(block.end_time),
    )


async def _get_blocks_for_appointments(
    session: AsyncSession, appointment_ids: List[uuid.UUID]
) -> Dict[uuid.UUID, LinkedBlockInfo]:
    """Batch-fetch calendar blocks for multiple appointments in one query."""
    if not appointment_ids:
        return {}
    from backend.infra.database.models.calendar_block import CalendarBlock as _CB
    from backend.infra.database.models.calendar_resource import CalendarResource as _CR

    stmt = (
        _select(_CB, _CR.name)
        .join(_CR, _CB.calendar_resource_id == _CR.id)
        .where(_CB.appointment_id.in_(appointment_ids))
    )
    result = await session.execute(stmt)
    blocks: Dict[uuid.UUID, LinkedBlockInfo] = {}
    for block, resource_name in result.all():
        if block.appointment_id not in blocks:
            blocks[block.appointment_id] = LinkedBlockInfo(
                block_id=str(block.id),
                resource_name=resource_name or "",
                date=str(block.date),
                start_time=str(block.start_time),
                end_time=str(block.end_time),
            )
    return blocks


async def _delete_google_event_for_appointment(
    session: AsyncSession,
    appointment,
) -> None:
    """Delete the linked Google Calendar event, if any. Swallows 404 silently."""
    extra = appointment.extra_fields or {}
    event_id = extra.get("_google_event_id")
    if not event_id:
        return

    try:
        from backend.infra.database.repositories import CalendarResourceRepository
        cal_repo = CalendarResourceRepository(session)
        resources = await cal_repo.list_by_resource_name(appointment.artist or "")
        if not resources:
            return
        resource = resources[0]
        if resource.calendar_type != "google":
            return

        creds_json = resource.credentials
        if not creds_json:
            from backend.infra.database.models.tool_config import ToolConfig
            result = await session.execute(
                _select(ToolConfig).where(ToolConfig.name == "check_calendar_availability")
            )
            row = result.scalar_one_or_none()
            creds_json = row.credentials if row and row.credentials else None

        if not creds_json:
            return

        cal_id = resource.calendar_id or "primary"

        try:
            from backend.tools.builtin.google_calendar import _build_service
        except ImportError:
            return

        gcal_service = _build_service(creds_json)

        def _sync_delete() -> None:
            try:
                gcal_service.events().delete(calendarId=cal_id, eventId=event_id).execute()
            except Exception as _e:
                msg = str(_e)
                if "404" in msg or "notFound" in msg.lower():
                    pass  # Already deleted — that's fine
                else:
                    raise

        await asyncio.get_event_loop().run_in_executor(None, _sync_delete)
        logger.info("appointments: deleted Google Calendar event %s", event_id)
    except Exception as exc:
        logger.warning("appointments: could not delete Google Calendar event: %s", exc)


class InboundWebhookPayload(BaseModel):
    """Payload accepted by the inbound webhook endpoint.

    All fields except appt_number are optional — only provided fields are updated.
    """
    appt_number: str
    status: Optional[str] = None
    event_date: Optional[str] = None
    event_time: Optional[str] = None
    artist: Optional[str] = None
    service: Optional[str] = None
    location: Optional[str] = None
    notes: Optional[str] = None
    contact_name: Optional[str] = None
    contact_surname: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None


async def _get_webhook_config(session: AsyncSession):
    """Load webhook URL and secret from OrchestratorConfig."""
    from sqlalchemy import select as _sel
    from backend.infra.database.models.tool_config import OrchestratorConfigModel
    from backend.orchestrator.types import OrchestratorConfig
    result = await session.execute(_sel(OrchestratorConfigModel).where(OrchestratorConfigModel.id == 1))
    row = result.scalar_one_or_none()
    if row is None:
        return None, None
    cfg = OrchestratorConfig.from_dict(row.config_json)
    return cfg.appointment_webhook_url, cfg.appointment_webhook_secret


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[AppointmentResponse])
async def list_appointments(
    status: Optional[str] = None,
    search: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    skip: int = 0,
    limit: int = 100,
    session: AsyncSession = Depends(get_session),
):
    """List appointments, optionally filtered by status, ref-number search, or date range."""
    if status and status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use one of: {_VALID_STATUSES}")
    svc = AppointmentService(session)
    items = await svc.list_appointments(
        status=status, search=search, date_from=date_from, date_to=date_to,
        skip=skip, limit=limit,
    )
    blocks = await _get_blocks_for_appointments(session, [a.id for a in items])
    return [_to_schema(a, blocks.get(a.id)) for a in items]


# NOTE: must be registered BEFORE /{appointment_id} so FastAPI doesn't treat
# "export" as a UUID path segment.
@router.get("/export")
async def export_appointments_csv(
    status: Optional[str] = None,
    search: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
):
    """Download appointments as CSV with current filters applied."""
    if status and status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use one of: {_VALID_STATUSES}")
    svc = AppointmentService(session)
    items = await svc.list_appointments(
        status=status, search=search, date_from=date_from, date_to=date_to,
        skip=0, limit=10_000,
    )

    _CSV_FIELDS = [
        "appt_number", "status",
        "contact_name", "contact_surname", "contact_phone", "contact_email",
        "service", "location", "artist",
        "event_date", "event_time", "notes", "created_at",
    ]

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=_CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for a in items:
        writer.writerow({
            "appt_number": a.appt_number or "",
            "status": a.status,
            "contact_name": a.contact_name or "",
            "contact_surname": a.contact_surname or "",
            "contact_phone": a.contact_phone or "",
            "contact_email": a.contact_email or "",
            "service": a.service or "",
            "location": a.location or "",
            "artist": a.artist or "",
            "event_date": a.event_date or "",
            "event_time": a.event_time or "",
            "notes": a.notes or "",
            "created_at": a.created_at.isoformat() if a.created_at else "",
        })

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=appointments.csv"},
    )


@router.post("/webhook/inbound", response_model=AppointmentResponse)
async def inbound_webhook(
    payload: InboundWebhookPayload,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Receive appointment updates from external systems.

    Security: the caller must include the shared secret in the
    ``X-Webhook-Secret`` header.  The value is compared with
    ``appointment_webhook_secret`` from OrchestratorConfig using
    ``hmac.compare_digest`` (constant-time) to prevent timing attacks.

    On success the updated appointment is returned.
    """
    import hmac as _hmac

    webhook_url, webhook_secret = await _get_webhook_config(session)

    if not webhook_secret:
        raise HTTPException(status_code=503, detail="Webhook not configured")

    provided_secret = request.headers.get("X-Webhook-Secret", "")
    if not provided_secret or not _hmac.compare_digest(webhook_secret, provided_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    svc = AppointmentService(session)
    appt = await svc._repo.get_by_appt_number(payload.appt_number)
    if appt is None:
        raise HTTPException(status_code=404, detail="Appointment not found")

    update_data: Dict[str, Any] = {}
    for field_name in (
        "status", "event_date", "event_time", "artist", "service",
        "location", "notes", "contact_name", "contact_surname",
        "contact_phone", "contact_email",
    ):
        val = getattr(payload, field_name)
        if val is not None:
            update_data[field_name] = val

    if payload.status and payload.status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use one of: {_VALID_STATUSES}")

    if not update_data:
        block = await _get_block_for_appointment(session, appt.id)
        return _to_schema(appt, block)

    updated = await svc.update_appointment(appt.id, update_data)
    if updated is None:
        raise HTTPException(status_code=404, detail="Appointment not found")

    await session.commit()

    event = "appointment.cancelled" if payload.status == "cancelled" else "appointment.updated"
    asyncio.create_task(_webhook_dispatch(event, updated, webhook_url, webhook_secret))

    block = await _get_block_for_appointment(session, appt.id)
    return _to_schema(updated, block)


@router.get("/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    appointment_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    svc = AppointmentService(session)
    appt = await svc.get_appointment(appointment_id)
    if appt is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    block = await _get_block_for_appointment(session, appointment_id)
    return _to_schema(appt, block)


@router.get("/{appointment_id}/block", response_model=Optional[LinkedBlockInfo])
async def get_appointment_block(
    appointment_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Return the linked CalendarBlock info for this appointment, or null."""
    return await _get_block_for_appointment(session, appointment_id)


@router.patch("/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment_status(
    appointment_id: uuid.UUID,
    body: AppointmentStatusUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update the status of an appointment (confirmed / cancelled / pending)."""
    if body.status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use one of: {_VALID_STATUSES}")
    svc = AppointmentService(session)
    appt = await svc.update_status(appointment_id, body.status)
    if appt is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    # Free the artist's calendar slot when the appointment is cancelled.
    if body.status == "cancelled":
        block_repo = CalendarBlockRepository(session)
        deleted = await block_repo.delete_by_appointment_id(appointment_id)
        if deleted:
            logger.info(
                "appointments: freed %d calendar block(s) for cancelled appointment %s",
                deleted, appointment_id,
            )
        # Also delete the linked Google Calendar event
        await _delete_google_event_for_appointment(session, appt)
    await session.commit()

    # Outbound webhook
    wh_url, wh_secret = await _get_webhook_config(session)
    event = "appointment.cancelled" if body.status == "cancelled" else "appointment.updated"
    asyncio.create_task(_webhook_dispatch(event, appt, wh_url, wh_secret))

    return _to_schema(appt)


@router.put("/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    appointment_id: uuid.UUID,
    body: AppointmentUpdateRequest,
    session: AsyncSession = Depends(get_session),
):
    """Full update / reschedule of an appointment."""
    svc = AppointmentService(session)
    appt = await svc.get_appointment(appointment_id)
    if appt is None:
        raise HTTPException(status_code=404, detail="Appointment not found")

    block_repo = CalendarBlockRepository(session)

    # Validate status if provided
    if body.status and body.status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Use one of: {_VALID_STATUSES}")

    # If cancelling: free blocks + delete Google event first
    if body.status == "cancelled" and appt.status != "cancelled":
        await block_repo.delete_by_appointment_id(appointment_id)
        await _delete_google_event_for_appointment(session, appt)

    # Build update payload from non-None fields
    update_data: Dict[str, Any] = {}
    for field_name in (
        "status", "service", "location", "artist",
        "event_date", "event_time",
        "contact_name", "contact_surname", "contact_phone", "contact_email", "notes",
    ):
        val = getattr(body, field_name)
        if val is not None:
            update_data[field_name] = val

    if not update_data:
        block = await _get_block_for_appointment(session, appointment_id)
        return _to_schema(appt, block)

    # Reschedule check: any of artist / event_date / event_time changed
    is_reschedule = (
        body.status != "cancelled"
        and any(
            update_data.get(k) is not None and update_data.get(k) != getattr(appt, k)
            for k in ("artist", "event_date", "event_time")
        )
    )

    if is_reschedule:
        # Conflict guard: block if new slot overlaps an existing calendar block
        new_artist = update_data.get("artist") or appt.artist
        new_date = update_data.get("event_date") or appt.event_date
        new_time = update_data.get("event_time") or appt.event_time
        if new_artist and new_date and new_time:
            from backend.services.availability_service import AvailabilityService
            has_conflict = await AvailabilityService(session).check_conflict(
                artist_name=new_artist,
                event_date_str=new_date,
                event_time_str=new_time,
                service_name=update_data.get("service") or appt.service,
                exclude_appointment_id=appointment_id,
            )
            if has_conflict:
                raise HTTPException(status_code=409, detail="conflict")

        # Delete old calendar block and Google event before saving new slot
        await block_repo.delete_by_appointment_id(appointment_id)
        await _delete_google_event_for_appointment(session, appt)

    updated = await svc.update_appointment(appointment_id, update_data)
    if updated is None:
        raise HTTPException(status_code=404, detail="Appointment not found")

    await session.flush()

    # Create new calendar block after reschedule
    if is_reschedule:
        from backend.orchestrator.orchestrator import Orchestrator
        appt_dict_for_block: Dict[str, Any] = {
            "artist": updated.artist,
            "event_date": updated.event_date,
            "event_time": updated.event_time,
            "service": updated.service,
        }
        try:
            await Orchestrator._create_calendar_block_for_appointment(
                session, updated, appt_dict_for_block,
            )
        except Exception as exc:
            logger.warning("appointments: could not create new calendar block on reschedule: %s", exc)

    await session.commit()

    # Outbound webhook
    wh_url, wh_secret = await _get_webhook_config(session)
    wh_event = "appointment.cancelled" if update_data.get("status") == "cancelled" else "appointment.updated"
    asyncio.create_task(_webhook_dispatch(wh_event, updated, wh_url, wh_secret))

    block = await _get_block_for_appointment(session, appointment_id)
    return _to_schema(updated, block)


@router.delete("/{appointment_id}", status_code=204)
async def delete_appointment(
    appointment_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    svc = AppointmentService(session)
    # Load appointment first to grab extra_fields (Google event ID)
    appt = await svc.get_appointment(appointment_id)
    if appt is None:
        raise HTTPException(status_code=404, detail="Appointment not found")
    # Free calendar blocks before deleting the appointment row.
    block_repo = CalendarBlockRepository(session)
    await block_repo.delete_by_appointment_id(appointment_id)
    # Delete the linked Google Calendar event
    await _delete_google_event_for_appointment(session, appt)
    ok = await svc.delete_appointment(appointment_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Appointment not found")
    await session.commit()
