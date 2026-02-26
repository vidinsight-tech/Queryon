"""Pydantic v2 schemas for the Orchestrator Config API."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class OrchestratorConfigSchema(BaseModel):
    # ── Bot identity ───────────────────────────────────────────────
    bot_name: str = "Assistant"
    character_system_prompt: Optional[str] = None

    # ── Intent routing ─────────────────────────────────────────────
    enabled_intents: List[Literal["rag", "direct", "rule", "tool", "character"]] = [
        "rag", "direct", "rule", "tool"
    ]
    default_intent: Literal["rag", "direct", "rule", "tool"] = "rag"
    """Used when: confidence < min_confidence (strategy=fallback) or intent is disabled."""

    rules_first: bool = True

    # ── Fallback policy ────────────────────────────────────────────
    fallback_to_direct: bool = True
    """Scenario 4: RAG handler ran but returned no answer → fall back to direct."""

    when_rag_unavailable: Literal["direct", "ask_user"] = "direct"
    """Scenario 3: RAG service not configured at startup (Qdrant unreachable).
    'direct' silently routes to the LLM. 'ask_user' returns a service-unavailable message."""

    # ── Confidence / classification ────────────────────────────────
    min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    low_confidence_strategy: Literal["fallback", "ask_user"] = "fallback"
    """Scenario 1: confidence < min_confidence.
    'fallback' uses default_intent. 'ask_user' asks for clarification."""

    embedding_confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    classification_prompt_override: Optional[str] = None

    # ── Performance ────────────────────────────────────────────────
    llm_timeout_seconds: Optional[float] = Field(default=60.0, ge=0.0)
    max_conversation_turns: int = Field(default=10, ge=0, le=100)

    # ── Modes ──────────────────────────────────────────────────────
    appointment_fields: List[Dict[str, Any]] = []
    order_mode_enabled: bool = False
    order_fields: List[Dict[str, Any]] = []

    # ── Behavioral restrictions ─────────────────────────────────────
    restrictions: Optional[str] = None

    # ── Webhook integration ─────────────────────────────────────────
    appointment_webhook_url: Optional[str] = None
    """URL to POST signed appointment events to (outbound). Leave blank to disable."""

    appointment_webhook_secret: Optional[str] = None
    """Shared HMAC secret. Used to sign outbound payloads and verify inbound calls."""
