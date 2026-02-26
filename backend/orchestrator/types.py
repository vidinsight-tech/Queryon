"""Core data structures for the Orchestrator layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

ConversationTurn = Dict[str, str]
"""A single turn: {"role": "user" | "assistant", "content": "..."}."""


class IntentType(str, Enum):
    """The five possible intent categories."""
    RAG = "rag"
    DIRECT = "direct"
    RULE = "rule"
    TOOL = "tool"
    CHARACTER = "character"


class LowConfidenceStrategy(str, Enum):
    """What to do when classification confidence is below the threshold."""
    FALLBACK = "fallback"
    ASK_USER = "ask_user"


@dataclass
class OrchestratorConfig:
    """User-configurable orchestrator behaviour.

    Fallback policy summary
    -----------------------
    Four distinct scenarios, each with its own config field:

    1. Low confidence  (confidence < min_confidence)
         → low_confidence_strategy: "fallback" uses default_intent,
                                    "ask_user" returns a clarification prompt.

    2. Intent disabled (classified intent not in enabled_intents)
         → always falls back to default_intent (no separate override needed).

    3. RAG unavailable (Qdrant unreachable at startup; no RAG handler registered)
         → when_rag_unavailable: "direct" silently routes to DirectHandler,
                                  "ask_user" returns a service-unavailable prompt.

    4. RAG returned empty (handler ran but found no matching documents)
         → fallback_to_direct: True routes to DirectHandler,
                                False returns an empty/no-answer response.
    """

    enabled_intents: List[IntentType] = field(
        default_factory=lambda: list(IntentType),
    )
    default_intent: IntentType = IntentType.RAG
    """Intent to use when classification confidence is too low (low_confidence_strategy=fallback)
    or when the classified intent is not in enabled_intents."""

    rules_first: bool = True
    fallback_to_direct: bool = True
    """Scenario 4 — when RAG handler runs but returns no answer, fall back to DirectHandler."""

    when_rag_unavailable: str = "direct"
    """Scenario 3 — what to do when the RAG service was not configured at startup.
    Accepted values: "direct" (route to DirectHandler), "ask_user" (return a clarification prompt)."""

    min_confidence: float = 0.7
    low_confidence_strategy: LowConfidenceStrategy = LowConfidenceStrategy.FALLBACK
    """Scenario 1 — what to do when classification confidence < min_confidence."""

    embedding_confidence_threshold: float = 0.85

    classification_prompt_override: Optional[str] = None

    llm_timeout_seconds: Optional[float] = 60.0
    """Timeout for LLM calls (classification, direct answer, rule matching). None = no timeout."""

    max_conversation_turns: int = 10
    """Max number of turns (user+assistant pairs) to include in context for classification. 0 = no history."""

    character_system_prompt: Optional[str] = None
    """When set, enables character mode: the orchestrator uses this as the LLM system prompt
    and routes all non-FAQ messages through CharacterHandler (LLM-driven natural conversation).
    FAQ standalone rules still fire instantly via keyword matching."""

    appointment_fields: List[Dict[str, Any]] = field(default_factory=list)
    """Configurable appointment fields for the chatbot to collect.
    Each entry: {"key": str, "label": str, "question": str, "required": bool, "options": list[str] (optional)}
    When "options" is set, the LLM is constrained to use only one of those values for that field.
    Standard keys: name, surname, phone, email, event_date, service, location, artist.
    Extra keys are stored in Appointment.extra_fields."""

    bot_name: str = "Assistant"
    """Display name for the bot persona."""

    order_mode_enabled: bool = False
    """When True, the chatbot also collects order information via order_fields."""

    order_fields: List[Dict[str, Any]] = field(default_factory=list)
    """Configurable order fields for the chatbot to collect.
    Each entry: {"key": str, "label": str, "question": str, "required": bool, "options": list[str] (optional)}
    When "options" is set, the LLM is constrained to use only one of those values.
    Extra keys are stored in Order.extra_fields."""

    restrictions: Optional[str] = None
    """Behavioral restrictions — topics or actions the bot must never discuss.
    Appended to the system prompt as a hard prohibition block."""

    appointment_webhook_url: Optional[str] = None
    """When set, Queryon POSTs signed JSON events here on every appointment
    create/update/cancel.  Events are signed with appointment_webhook_secret
    using HMAC-SHA256 in the ``X-Queryon-Signature: sha256=<hex>`` header."""

    appointment_webhook_secret: Optional[str] = None
    """Shared secret used to sign outbound events (HMAC-SHA256) and to
    verify inbound webhook calls (X-Webhook-Secret header).
    Treat like a password — never expose in logs."""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON file persistence."""
        return {
            "enabled_intents": [i.value for i in self.enabled_intents],
            "default_intent": self.default_intent.value,
            "rules_first": self.rules_first,
            "fallback_to_direct": self.fallback_to_direct,
            "when_rag_unavailable": self.when_rag_unavailable,
            "min_confidence": self.min_confidence,
            "low_confidence_strategy": self.low_confidence_strategy.value,
            "embedding_confidence_threshold": self.embedding_confidence_threshold,
            "classification_prompt_override": self.classification_prompt_override,
            "llm_timeout_seconds": self.llm_timeout_seconds,
            "max_conversation_turns": self.max_conversation_turns,
            "character_system_prompt": self.character_system_prompt,
            "appointment_fields": self.appointment_fields,
            "bot_name": self.bot_name,
            "order_mode_enabled": self.order_mode_enabled,
            "order_fields": self.order_fields,
            "restrictions": self.restrictions,
            "appointment_webhook_url": self.appointment_webhook_url,
            "appointment_webhook_secret": self.appointment_webhook_secret,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]] = None) -> "OrchestratorConfig":
        """Load from a dict (e.g. JSON file). Missing keys use defaults."""
        if not data:
            return cls()
        try:
            default_intent = IntentType(str(data.get("default_intent", "rag")))
        except ValueError:
            default_intent = IntentType.RAG
        try:
            low_conf = LowConfidenceStrategy(
                str(data.get("low_confidence_strategy", "fallback"))
            )
        except ValueError:
            low_conf = LowConfidenceStrategy.FALLBACK
        timeout = data.get("llm_timeout_seconds")
        if timeout is not None:
            try:
                timeout = float(timeout)
            except (TypeError, ValueError):
                timeout = 60.0
        raw_intents = data.get("enabled_intents")
        if raw_intents is not None:
            enabled_intents: List[IntentType] = []
            for i in raw_intents:
                try:
                    enabled_intents.append(IntentType(str(i)))
                except ValueError:
                    pass
            if not enabled_intents:
                enabled_intents = list(IntentType)
        else:
            enabled_intents = list(IntentType)
        prompt_override: Optional[str] = data.get("classification_prompt_override") or None
        raw_when_rag = str(data.get("when_rag_unavailable") or "direct").strip()
        when_rag_unavailable = raw_when_rag if raw_when_rag in ("direct", "ask_user") else "direct"
        return cls(
            enabled_intents=enabled_intents,
            default_intent=default_intent,
            rules_first=bool(data.get("rules_first", True)),
            fallback_to_direct=bool(data.get("fallback_to_direct", True)),
            when_rag_unavailable=when_rag_unavailable,
            min_confidence=float(data.get("min_confidence", 0.7)),
            low_confidence_strategy=low_conf,
            embedding_confidence_threshold=float(
                data.get("embedding_confidence_threshold", 0.85)
            ),
            classification_prompt_override=prompt_override,
            llm_timeout_seconds=timeout,
            max_conversation_turns=int(data.get("max_conversation_turns", 10)),
            character_system_prompt=data.get("character_system_prompt") or None,
            appointment_fields=data.get("appointment_fields") or [],
            bot_name=str(data.get("bot_name") or "Assistant"),
            order_mode_enabled=bool(data.get("order_mode_enabled", False)),
            order_fields=data.get("order_fields") or [],
            restrictions=data.get("restrictions") or None,
            appointment_webhook_url=data.get("appointment_webhook_url") or None,
            appointment_webhook_secret=data.get("appointment_webhook_secret") or None,
        )


@dataclass
class ClassificationResult:
    """Output of an intent classifier."""

    intent: IntentType
    confidence: float = 1.0
    reasoning: Optional[str] = None
    classifier_layer: Optional[str] = None  # "pre", "embedding", "llm", "cache"
    thinking: Optional[str] = None  # CoT scratchpad (LLM layer only)


@dataclass
class OrchestratorMetrics:
    """Timing and cost metrics for a single orchestrator call."""

    classification_ms: float = 0.0
    handler_ms: float = 0.0
    total_ms: float = 0.0
    llm_calls_count: int = 0
    fallback_used: bool = False
    classifier_layer: Optional[str] = None


@dataclass
class OrchestratorResult:
    """Final output returned by the orchestrator."""

    query: str
    intent: IntentType
    answer: Optional[str] = None
    sources: List[Any] = field(default_factory=list)
    rule_matched: Optional[str] = None
    tool_called: Optional[str] = None
    classification: Optional[ClassificationResult] = None
    metrics: Optional[OrchestratorMetrics] = None
    needs_clarification: bool = False
    fallback_used: bool = False
    fallback_from_intent: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
