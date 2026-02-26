"""AvailabilityService: compute free time slots from working_hours minus calendar blocks and Google freebusy."""
from __future__ import annotations

import asyncio
import datetime as _dt
import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.database.models.calendar_resource import CalendarResource
from backend.infra.database.models.tool_config import ToolConfig
from backend.infra.database.repositories import CalendarBlockRepository, CalendarResourceRepository

logger = logging.getLogger(__name__)

_DAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class AvailabilityService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._cal_repo = CalendarResourceRepository(session)
        self._block_repo = CalendarBlockRepository(session)

    async def get_slots(
        self,
        calendar_resource_id: UUID,
        date: _dt.date,
        service_name: Optional[str] = None,
        buffer_minutes: int = 0,
    ) -> List[str]:
        """Return available time slots (HH:MM strings) for a given date.

        1. Load calendar resource -> working_hours for the day of week
        2. Compute slot_duration from service_durations or default (60 min)
        3. Generate candidate slots from working_hours intervals
        4. Subtract internal calendar_blocks for that date
        5. If calendar_type=google, also subtract Google Calendar busy times
        6. Return available slot start times
        """
        resource = await self._cal_repo.get_by_id(calendar_resource_id)
        if resource is None:
            return []

        day_name = _DAY_NAMES[date.weekday()]
        working = (resource.working_hours or {}).get(day_name)
        if not working or not working.get("open"):
            return []

        durations = resource.service_durations or {}
        if service_name and service_name in durations:
            slot_duration = int(durations[service_name])
        else:
            slot_duration = int(durations.get("default", 60))
        total_duration = slot_duration + buffer_minutes

        candidates: List[_dt.time] = []
        for interval in working.get("slots", []):
            start_str = interval.get("start", "09:00")
            end_str = interval.get("end", "17:00")
            start = _parse_time(start_str)
            end = _parse_time(end_str)
            if start is None or end is None:
                continue
            cursor = _dt.datetime.combine(date, start)
            end_dt = _dt.datetime.combine(date, end)
            while cursor + _dt.timedelta(minutes=total_duration) <= end_dt:
                candidates.append(cursor.time())
                cursor += _dt.timedelta(minutes=slot_duration)

        if not candidates:
            return []

        # Internal blocks
        blocks = await self._block_repo.list_for_date(calendar_resource_id, date)
        busy_ranges: List[Tuple[_dt.time, _dt.time]] = [(b.start_time, b.end_time) for b in blocks]

        # Google Calendar freebusy (if resource has google calendar)
        if resource.calendar_type == "google":
            google_busy = await self._fetch_google_busy(resource, date)
            busy_ranges.extend(google_busy)

        available = []
        for slot_start in candidates:
            slot_end_dt = _dt.datetime.combine(date, slot_start) + _dt.timedelta(minutes=total_duration)
            slot_end = slot_end_dt.time()
            if not _overlaps_any(slot_start, slot_end, busy_ranges):
                available.append(slot_start.strftime("%H:%M"))

        return available

    async def get_slots_by_resource_name(
        self,
        resource_name: str,
        date: _dt.date,
        service_name: Optional[str] = None,
        buffer_minutes: int = 0,
    ) -> List[str]:
        """Convenience: find first active calendar for resource_name and return slots."""
        resources = await self._cal_repo.list_by_resource_name(resource_name)
        if not resources:
            return []
        return await self.get_slots(resources[0].id, date, service_name, buffer_minutes)

    async def _get_google_credentials(self, resource: CalendarResource) -> Optional[str]:
        """Return per-resource credentials, falling back to global tool_config."""
        if resource.credentials:
            return resource.credentials
        result = await self._session.execute(
            select(ToolConfig).where(ToolConfig.name == "check_calendar_availability")
        )
        row = result.scalar_one_or_none()
        return row.credentials if row and row.credentials else None

    async def _fetch_google_busy(
        self,
        resource: CalendarResource,
        date: _dt.date,
    ) -> List[Tuple[_dt.time, _dt.time]]:
        """Query Google Calendar freebusy for the given date and return busy (start, end) tuples."""
        creds_json = await self._get_google_credentials(resource)
        if not creds_json:
            return []
        cal_id = resource.calendar_id or "primary"
        tz_name = resource.timezone or "Europe/Istanbul"

        try:
            from backend.tools.builtin.google_calendar import _build_service
        except ImportError:
            logger.debug("Google Calendar support not installed")
            return []

        try:
            try:
                from zoneinfo import ZoneInfo
                tz = ZoneInfo(tz_name)
            except Exception:
                tz = _dt.timezone(_dt.timedelta(hours=3))

            day_start = _dt.datetime.combine(date, _dt.time(0, 0), tzinfo=tz)
            day_end = _dt.datetime.combine(date, _dt.time(23, 59, 59), tzinfo=tz)

            service = _build_service(creds_json)
            body = {
                "timeMin": day_start.isoformat(),
                "timeMax": day_end.isoformat(),
                "items": [{"id": cal_id}],
            }

            def _sync():
                return service.freebusy().query(body=body).execute()

            result = await asyncio.get_event_loop().run_in_executor(None, _sync)
            busy_list = result.get("calendars", {}).get(cal_id, {}).get("busy", [])

            ranges: List[Tuple[_dt.time, _dt.time]] = []
            for slot in busy_list:
                try:
                    s = _dt.datetime.fromisoformat(slot["start"]).astimezone(tz).time()
                    e = _dt.datetime.fromisoformat(slot["end"]).astimezone(tz).time()
                    ranges.append((s, e))
                except (KeyError, ValueError):
                    continue
            logger.info("AvailabilityService: Google freebusy for %s on %s: %d busy ranges", cal_id, date, len(ranges))
            return ranges
        except Exception as exc:
            logger.warning("AvailabilityService: Google freebusy failed for %s: %s", resource.name, exc)
            return []


    async def check_conflict(
        self,
        artist_name: str,
        event_date_str: str,
        event_time_str: str,
        service_name: Optional[str] = None,
        exclude_appointment_id: Optional[UUID] = None,
    ) -> bool:
        """Return True if artist_name is already booked at event_date_str/event_time_str.

        Reuses _parse_time, _overlaps_any, and the internal calendar-block store.
        Returns False when data is missing or the resource doesn't exist.
        """
        resources = await self._cal_repo.list_by_resource_name(artist_name)
        if not resources:
            return False
        resource = resources[0]

        from backend.orchestrator.orchestrator import _parse_date_str
        event_date = _parse_date_str(event_date_str)
        start_time = _parse_time(event_time_str)
        if event_date is None or start_time is None:
            return False

        durations = resource.service_durations or {}
        duration = int(durations.get(service_name or "", durations.get("default", 60)))
        end_time = (
            _dt.datetime.combine(event_date, start_time) + _dt.timedelta(minutes=duration)
        ).time()

        blocks = await self._block_repo.list_for_date(resource.id, event_date)
        busy = [
            (b.start_time, b.end_time)
            for b in blocks
            if b.appointment_id != exclude_appointment_id
        ]
        return _overlaps_any(start_time, end_time, busy)


def _parse_time(s: str) -> Optional[_dt.time]:
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return _dt.datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None


def _overlaps_any(
    start: _dt.time,
    end: _dt.time,
    ranges: List[tuple],
) -> bool:
    for busy_start, busy_end in ranges:
        if start < busy_end and end > busy_start:
            return True
    return False
