"""Built-in Google Calendar tools.

Supports two credential modes:
  1. Service account JSON (type == "service_account")
  2. OAuth 2.0 user tokens (type == "oauth") — obtained via Google sign-in flow
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from backend.orchestrator.handlers.tool_handler import ToolDefinition

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _build_service(credentials_json: str):
    """Build a Google Calendar API service from credentials JSON.

    Detects credential type automatically:
      - {"type": "service_account", ...}  → service account flow
      - {"type": "oauth", ...}            → user OAuth token flow
    """
    from googleapiclient.discovery import build

    info = json.loads(credentials_json)
    cred_type = info.get("type", "service_account")

    if cred_type == "oauth":
        return _build_service_oauth(info)

    from google.oauth2.service_account import Credentials
    creds = Credentials.from_service_account_info(info, scopes=_SCOPES)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _build_service_oauth(info: Dict[str, Any]):
    """Build Calendar service from OAuth tokens, refreshing if needed."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        token=info.get("access_token"),
        refresh_token=info.get("refresh_token"),
        token_uri=info.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=info.get("client_id"),
        client_secret=info.get("client_secret"),
        scopes=_SCOPES,
    )

    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request
        creds.refresh(Request())
        logger.info("Google OAuth: token refreshed successfully")

    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def build_google_calendar_tools(credentials_json: str) -> List[ToolDefinition]:
    """Return list of Google Calendar ToolDefinitions using the given credentials."""

    async def check_calendar_availability(
        start_time: str,
        end_time: str,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """Check if a calendar is free/busy in a time window (ISO 8601 format)."""
        import asyncio

        def _sync():
            service = _build_service(credentials_json)
            body = {
                "timeMin": start_time,
                "timeMax": end_time,
                "items": [{"id": calendar_id}],
            }
            result = service.freebusy().query(body=body).execute()
            busy = result.get("calendars", {}).get(calendar_id, {}).get("busy", [])
            return busy

        try:
            busy_slots = await asyncio.get_event_loop().run_in_executor(None, _sync)
        except Exception as exc:
            logger.error("check_calendar_availability failed: %s", exc)
            return {"error": str(exc), "available": False, "busy_slots": []}

        return {
            "available": len(busy_slots) == 0,
            "busy_slots": busy_slots,
            "calendar_id": calendar_id,
        }

    async def create_calendar_event(
        title: str,
        start_time: str,
        end_time: str,
        description: str = "",
        attendees: Optional[List[str]] = None,
        calendar_id: str = "primary",
    ) -> Dict[str, Any]:
        """Create a calendar event. Times must be ISO 8601 (e.g. '2025-03-01T10:00:00+03:00')."""
        import asyncio

        def _sync():
            service = _build_service(credentials_json)
            event_body: Dict[str, Any] = {
                "summary": title,
                "description": description,
                "start": {"dateTime": start_time},
                "end": {"dateTime": end_time},
            }
            if attendees:
                event_body["attendees"] = [{"email": a} for a in attendees]
            result = service.events().insert(calendarId=calendar_id, body=event_body).execute()
            return result

        try:
            event = await asyncio.get_event_loop().run_in_executor(None, _sync)
        except Exception as exc:
            logger.error("create_calendar_event failed: %s", exc)
            return {"error": str(exc)}

        return {
            "event_id": event.get("id"),
            "html_link": event.get("htmlLink"),
            "status": event.get("status"),
            "title": event.get("summary"),
        }

    async def list_calendar_events(
        calendar_id: str = "primary",
        max_results: int = 10,
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List upcoming calendar events. Optionally filter by time range (ISO 8601)."""
        import asyncio
        from datetime import datetime, timezone

        def _sync():
            service = _build_service(credentials_json)
            kwargs: Dict[str, Any] = {
                "calendarId": calendar_id,
                "maxResults": max_results,
                "singleEvents": True,
                "orderBy": "startTime",
            }
            if time_min:
                kwargs["timeMin"] = time_min
            else:
                kwargs["timeMin"] = datetime.now(timezone.utc).isoformat()
            if time_max:
                kwargs["timeMax"] = time_max
            result = service.events().list(**kwargs).execute()
            return result.get("items", [])

        try:
            items = await asyncio.get_event_loop().run_in_executor(None, _sync)
        except Exception as exc:
            logger.error("list_calendar_events failed: %s", exc)
            return {"error": str(exc), "events": []}

        events = [
            {
                "id": ev.get("id"),
                "title": ev.get("summary", ""),
                "start": ev.get("start", {}).get("dateTime") or ev.get("start", {}).get("date"),
                "end": ev.get("end", {}).get("dateTime") or ev.get("end", {}).get("date"),
                "description": ev.get("description", ""),
                "attendees": [a["email"] for a in ev.get("attendees", [])],
            }
            for ev in items
        ]
        return {"events": events, "total": len(events)}

    return [
        ToolDefinition(
            name="check_calendar_availability",
            description=(
                "Check if a Google Calendar is free or busy during a time window. "
                "Use when someone asks about availability or free time slots."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "start_time": {"type": "string", "description": "Start time in ISO 8601 format."},
                    "end_time": {"type": "string", "description": "End time in ISO 8601 format."},
                    "calendar_id": {"type": "string", "description": "Calendar ID, default 'primary'."},
                },
                "required": ["start_time", "end_time"],
            },
            handler=check_calendar_availability,
        ),
        ToolDefinition(
            name="create_calendar_event",
            description=(
                "Create a new event on a Google Calendar. "
                "Use when setting an appointment, booking a meeting, or scheduling something."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title."},
                    "start_time": {"type": "string", "description": "Start time in ISO 8601."},
                    "end_time": {"type": "string", "description": "End time in ISO 8601."},
                    "description": {"type": "string", "description": "Optional event description."},
                    "attendees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of attendee email addresses.",
                    },
                    "calendar_id": {"type": "string", "description": "Calendar ID, default 'primary'."},
                },
                "required": ["title", "start_time", "end_time"],
            },
            handler=create_calendar_event,
        ),
        ToolDefinition(
            name="list_calendar_events",
            description=(
                "List upcoming events from a Google Calendar. "
                "Use when someone asks what is scheduled, what events are coming up, etc."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "calendar_id": {"type": "string", "description": "Calendar ID, default 'primary'."},
                    "max_results": {"type": "integer", "description": "Max events to return (default 10)."},
                    "time_min": {"type": "string", "description": "Earliest time filter in ISO 8601."},
                    "time_max": {"type": "string", "description": "Latest time filter in ISO 8601."},
                },
                "required": [],
            },
            handler=list_calendar_events,
        ),
    ]
