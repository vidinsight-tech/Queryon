"""Core data structures for the Orchestrator layer."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

ConversationTurn = Dict[str, str]
"""A single turn: {"role": "user" | "assistant", "content": "..."}."""


class IntentType(str, Enum):
    """The four possible intent categories."""
    RAG = "rag"
    DIRECT = "direct"
    RULE = "rule"
    TOOL = "tool"


class LowConfidenceStrategy(str, Enum):
    """What to do when classification confidence is below the threshold."""
    FALLBACK = "fallback"
    ASK_USER = "ask_user"


@dataclass
class OrchestratorConfig:
    """User-configurable orchestrator behaviour."""

    enabled_intents: List[IntentType] = field(
        default_factory=lambda: list(IntentType),
    )
    default_intent: IntentType = IntentType.RAG
    rules_first: bool = True
    fallback_to_direct: bool = True

    min_confidence: float = 0.7
    low_confidence_strategy: LowConfidenceStrategy = LowConfidenceStrategy.FALLBACK
    embedding_confidence_threshold: float = 0.85

    classification_prompt_override: Optional[str] = None

    llm_timeout_seconds: Optional[float] = 60.0
    """Timeout for LLM calls (classification, direct answer, rule matching). None = no timeout."""

    max_conversation_turns: int = 10
    """Max number of turns (user+assistant pairs) to include in context for classification. 0 = no history."""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for JSON file persistence."""
        return {
            "default_intent": self.default_intent.value,
            "rules_first": self.rules_first,
            "fallback_to_direct": self.fallback_to_direct,
            "min_confidence": self.min_confidence,
            "low_confidence_strategy": self.low_confidence_strategy.value,
            "embedding_confidence_threshold": self.embedding_confidence_threshold,
            "llm_timeout_seconds": self.llm_timeout_seconds,
            "max_conversation_turns": self.max_conversation_turns,
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
        return cls(
            default_intent=default_intent,
            rules_first=bool(data.get("rules_first", True)),
            fallback_to_direct=bool(data.get("fallback_to_direct", True)),
            min_confidence=float(data.get("min_confidence", 0.7)),
            low_confidence_strategy=low_conf,
            embedding_confidence_threshold=float(
                data.get("embedding_confidence_threshold", 0.85)
            ),
            llm_timeout_seconds=timeout,
            max_conversation_turns=int(data.get("max_conversation_turns", 10)),
        )


@dataclass
class ClassificationResult:
    """Output of an intent classifier."""

    intent: IntentType
    confidence: float = 1.0
    reasoning: Optional[str] = None
    classifier_layer: Optional[str] = None  # "pre", "embedding", "llm", "cache"


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
    metadata: Dict[str, Any] = field(default_factory=dict)
