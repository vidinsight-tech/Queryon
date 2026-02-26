"""Pydantic v2 schemas for the Tools API."""
from __future__ import annotations

import re
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ToolResponse(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]
    is_builtin: bool
    enabled: bool


class ToolPatchRequest(BaseModel):
    enabled: Optional[bool] = None
    description: Optional[str] = None


class GoogleCalendarOAuthRequest(BaseModel):
    credentials_json: str = Field(
        ...,
        description="Service account JSON or OAuth token JSON pasted as a string",
    )


_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class WebhookCreateRequest(BaseModel):
    name: str
    description: str
    url: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "POST"
    headers: Optional[Dict[str, str]] = None
    auth_token: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    enabled: bool = True

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError("name must match ^[a-z][a-z0-9_]*$ (snake_case)")
        return v


class WebhookUpdateRequest(BaseModel):
    description: Optional[str] = None
    url: Optional[str] = None
    method: Optional[Literal["GET", "POST", "PUT", "PATCH", "DELETE"]] = None
    headers: Optional[Dict[str, str]] = None
    auth_token: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None


class WebhookTestRequest(BaseModel):
    """Arbitrary kwargs to pass directly to the tool handler."""
    kwargs: Dict[str, Any] = Field(default_factory=dict)


class WebhookTestResponse(BaseModel):
    ok: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
