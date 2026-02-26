"""Pydantic schemas for Calendar Resources API (per-resource Google connection)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CalendarResourceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    resource_type: str = Field(default="artist", max_length=64)
    resource_name: Optional[str] = Field(None, max_length=255)
    calendar_type: str = Field(default="internal", max_length=32)
    color: Optional[str] = Field(None, max_length=32)
    timezone: Optional[str] = Field(None, max_length=64)
    working_hours: Dict[str, Any] = Field(default_factory=dict)
    service_durations: Dict[str, Any] = Field(default_factory=dict)
    calendar_id: Optional[str] = Field(None, max_length=512)
    ical_url: Optional[str] = None
    is_active: bool = True


class CalendarResourceCreate(CalendarResourceBase):
    """Create a calendar resource. For Google, set calendar_type=google and calendar_id (and optionally credentials via connect-google)."""
    pass


class CalendarResourceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    resource_type: Optional[str] = Field(None, max_length=64)
    resource_name: Optional[str] = Field(None, max_length=255)
    calendar_type: Optional[str] = Field(None, max_length=32)
    color: Optional[str] = Field(None, max_length=32)
    timezone: Optional[str] = Field(None, max_length=64)
    working_hours: Optional[Dict[str, Any]] = None
    service_durations: Optional[Dict[str, Any]] = None
    calendar_id: Optional[str] = Field(None, max_length=512)
    ical_url: Optional[str] = None
    is_active: Optional[bool] = None


class CalendarResourceResponse(BaseModel):
    id: UUID
    name: str
    resource_type: str
    resource_name: Optional[str]
    calendar_type: str
    color: Optional[str]
    timezone: Optional[str]
    working_hours: Dict[str, Any]
    service_durations: Dict[str, Any]
    calendar_id: Optional[str]
    ical_url: Optional[str]
    has_credentials: bool = False
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConnectGoogleRequest(BaseModel):
    calendar_id: str = Field(..., min_length=1, max_length=512)
    credentials_json: Optional[str] = Field(None, description="Service account JSON; omit to use global tool_config credentials.")
