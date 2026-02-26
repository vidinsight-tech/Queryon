"""Pydantic schemas for EmbeddingModelConfig CRUD API."""
from __future__ import annotations
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class EmbeddingModelCreateSchema(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    provider: str = Field(..., min_length=1, max_length=64, description="e.g. openai, gemini")
    config: Dict[str, Any] = Field(..., description="model, api_key, base_url, dimension, ...")
    is_active: bool = True


class EmbeddingModelUpdateSchema(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    provider: Optional[str] = Field(None, min_length=1, max_length=64)
    config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class EmbeddingModelResponseSchema(BaseModel):
    id: UUID
    name: str
    provider: str
    config: Dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
