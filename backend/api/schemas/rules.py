"""Pydantic v2 schemas for the Rules API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RuleResponse(BaseModel):
    id: UUID
    name: str
    description: str
    trigger_patterns: List[str]
    response_template: str
    variables: Dict[str, Any]
    priority: int
    is_active: bool
    flow_id: Optional[str] = None
    step_key: Optional[str] = None
    required_step: Optional[str] = None
    next_steps: Optional[Dict[str, Any]] = None
    conditions: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RuleCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="")
    trigger_patterns: List[str] = Field(..., min_length=1)
    response_template: str = Field(..., min_length=1)
    variables: Dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=0, ge=0, le=1000)
    is_active: bool = True
    # Flow fields (optional)
    flow_id: Optional[str] = Field(default=None, max_length=64)
    step_key: Optional[str] = Field(default=None, max_length=64)
    required_step: Optional[str] = Field(default=None, max_length=64)
    next_steps: Optional[Dict[str, Any]] = None
    # Condition fields (optional)
    conditions: Optional[Dict[str, Any]] = None


class RulePatchRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    trigger_patterns: Optional[List[str]] = None
    response_template: Optional[str] = None
    variables: Optional[Dict[str, Any]] = None
    priority: Optional[int] = Field(default=None, ge=0, le=1000)
    is_active: Optional[bool] = None
    flow_id: Optional[str] = Field(default=None, max_length=64)
    step_key: Optional[str] = Field(default=None, max_length=64)
    required_step: Optional[str] = Field(default=None, max_length=64)
    next_steps: Optional[Dict[str, Any]] = None
    conditions: Optional[Dict[str, Any]] = None


class FlowResponse(BaseModel):
    flow_id: str
    rules: List[RuleResponse]


class RuleTreeResponse(BaseModel):
    standalone_rules: List[RuleResponse]
    flows: List[FlowResponse]
