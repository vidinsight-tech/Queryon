"""Layer 1: keyword/pattern-based pre-classifier — no LLM calls, <1 ms."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

from backend.orchestrator.types import ClassificationResult, IntentType

logger = logging.getLogger(__name__)

_DEFAULT_RAG_SIGNALS = [
    "dosyada", "belgede", "dokümanda", "dosyaya göre", "kaynağa göre",
    "ne yazıyor", "hangi dokümanda", "yüklenen", "bilgi tabanı",
    "in the document", "according to the file", "knowledge base",
]


class PreClassifier:
    """Fast deterministic classifier using keyword sets.

    Returns a ``ClassificationResult`` when confident, or ``None``
    to hand off to the next classification layer.
    """

    def __init__(
        self,
        rule_keywords: Set[str],
        *,
        rag_signals: Optional[List[str]] = None,
        tool_triggers: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        self._rule_keywords = {kw.lower() for kw in rule_keywords}
        self._rag_signals = [s.lower() for s in (rag_signals or _DEFAULT_RAG_SIGNALS)]
        self._tool_triggers = {
            name: [t.lower() for t in triggers]
            for name, triggers in (tool_triggers or {}).items()
        }

    def try_classify(self, query: str) -> Optional[ClassificationResult]:
        q_lower = query.lower()

        for kw in self._rule_keywords:
            if kw in q_lower:
                logger.debug("PreClassifier: matched rule keyword '%s'", kw)
                return ClassificationResult(
                    intent=IntentType.RULE,
                    confidence=0.95,
                    reasoning=f"keyword match: {kw}",
                    classifier_layer="pre",
                )

        for tool_name, triggers in self._tool_triggers.items():
            for t in triggers:
                if t in q_lower:
                    logger.debug("PreClassifier: matched tool trigger '%s' for %s", t, tool_name)
                    return ClassificationResult(
                        intent=IntentType.TOOL,
                        confidence=0.90,
                        reasoning=f"tool trigger: {t} → {tool_name}",
                        classifier_layer="pre",
                    )

        for signal in self._rag_signals:
            if signal in q_lower:
                logger.debug("PreClassifier: matched RAG signal '%s'", signal)
                return ClassificationResult(
                    intent=IntentType.RAG,
                    confidence=0.85,
                    reasoning=f"RAG signal: {signal}",
                    classifier_layer="pre",
                )

        return None
