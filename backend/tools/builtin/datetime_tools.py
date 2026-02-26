"""Built-in date/time tools — no external API required."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from backend.orchestrator.handlers.tool_handler import ToolDefinition


async def get_current_time(timezone: str = "UTC") -> Dict[str, Any]:
    """Return the current time in the given IANA timezone."""
    try:
        tz = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
        timezone = "UTC"
    now = datetime.now(tz)
    return {
        "time": now.strftime("%H:%M:%S"),
        "timezone": timezone,
        "iso": now.isoformat(),
        "hour": now.hour,
        "minute": now.minute,
    }


async def get_current_date(
    timezone: str = "UTC",
    format: str = "%Y-%m-%d",
) -> Dict[str, Any]:
    """Return the current date in the given IANA timezone."""
    try:
        tz = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("UTC")
        timezone = "UTC"
    now = datetime.now(tz)
    return {
        "date": now.strftime(format),
        "day_of_week": now.strftime("%A"),
        "day": now.day,
        "month": now.month,
        "year": now.year,
        "timezone": timezone,
        "iso": now.date().isoformat(),
    }


DATETIME_TOOLS = [
    ToolDefinition(
        name="get_current_time",
        description=(
            "Get the current time. Use when the user asks about the current time, "
            "what time it is, or the time in a specific timezone."
        ),
        parameters={
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": (
                        "IANA timezone name, e.g. 'Europe/Istanbul', 'America/New_York', 'UTC'. "
                        "Defaults to UTC if not specified."
                    ),
                }
            },
            "required": [],
        },
        handler=get_current_time,
    ),
    ToolDefinition(
        name="get_current_date",
        description=(
            "Get the current date. Use when the user asks about today's date, "
            "the day of the week, or the current month/year."
        ),
        parameters={
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": "IANA timezone name, e.g. 'Europe/Istanbul'. Defaults to UTC.",
                },
                "format": {
                    "type": "string",
                    "description": "strftime format string, e.g. '%d/%m/%Y'. Defaults to '%Y-%m-%d'.",
                },
            },
            "required": [],
        },
        handler=get_current_date,
    ),
]
