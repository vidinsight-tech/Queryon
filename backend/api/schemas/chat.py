"""Pydantic v2 schemas for the Chat API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=8000)
    conversation_id: Optional[UUID] = None


class SourceSchema(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    score: Optional[float] = None
    document_id: Optional[str] = None
    chunk_index: Optional[int] = None


class ChatResponse(BaseModel):
    answer: str
    intent: str
    confidence: Optional[float] = None
    classifier_layer: Optional[str] = None
    rule_matched: Optional[str] = None
    tool_called: Optional[str] = None
    fallback_used: bool = False
    fallback_from_intent: Optional[str] = None
    needs_clarification: bool = False
    sources: List[SourceSchema] = []
    total_ms: Optional[float] = None
    conversation_id: UUID
    thinking: Optional[str] = None
    reasoning: Optional[str] = None


class ConversationCreateRequest(BaseModel):
    platform: str = Field(default="web", max_length=32)
    contact_name: Optional[str] = Field(default=None, max_length=255)
    contact_email: Optional[str] = Field(default=None, max_length=255)
    contact_phone: Optional[str] = Field(default=None, max_length=32)


class ConversationResponse(BaseModel):
    conversation_id: UUID


class MessageSchema(BaseModel):
    id: UUID
    role: str
    content: str
    intent: Optional[str] = None
    confidence: Optional[float] = None
    classifier_layer: Optional[str] = None
    rule_matched: Optional[str] = None
    tool_called: Optional[str] = None
    fallback_used: bool = False
    total_ms: Optional[float] = None
    thinking: Optional[str] = None
    reasoning: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationHistoryResponse(BaseModel):
    conversation_id: UUID
    messages: List[MessageSchema]


class ConversationListItem(BaseModel):
    """Summary row for the admin conversation list view."""
    conversation_id: UUID
    platform: str
    status: str
    message_count: int
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    last_message_at: Optional[datetime] = None
    created_at: datetime
