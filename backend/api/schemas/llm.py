"""Pydantic schemas for LLM CRUD API.

Config shape follows backend.clients.llm.config.LLMConfig (model, api_key, base_url, etc.).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class LLMConfigSchema(BaseModel):
    """Config payload for an LLM (provider-specific). Typically: model, api_key, base_url, temperature, max_tokens."""

    model: str = Field(..., description="Model name (e.g. gpt-4o-mini, gemini-2.0-flash)")
    api_key: Optional[str] = Field(None, description="Provider API key")
    base_url: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    extra: Optional[Dict[str, Any]] = None


class LLMCreateSchema(BaseModel):
    """Create a new LLM record (user-configured provider + key)."""

    name: str = Field(..., min_length=1, max_length=255)
    provider: str = Field(..., min_length=1, max_length=64, description="e.g. openai, gemini")
    config: Dict[str, Any] = Field(..., description="Full LLMConfig-style dict: model, api_key, base_url, ...")
    is_active: bool = True


class LLMUpdateSchema(BaseModel):
    """Partial update for an LLM."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    provider: Optional[str] = Field(None, min_length=1, max_length=64)
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class LLMResponseSchema(BaseModel):
    """LLM record as returned by the API."""

    id: UUID
    name: str
    provider: str
    config: Dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
