"""Layer 3: LLM-based intent classifier — most accurate, highest latency."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, List, Optional

from backend.orchestrator.types import (
    ClassificationResult,
    ConversationTurn,
    IntentType,
    OrchestratorConfig,
)

if TYPE_CHECKING:
    from backend.clients.llm.base import BaseLLMClient

logger = logging.getLogger(__name__)

_CLASSIFICATION_PROMPT = """\
You are an intent classifier. Analyse the user message and choose EXACTLY ONE category:

1. "rag"    — The user needs information from uploaded documents / knowledge base.
2. "direct" — General knowledge, conversation, translation, summarisation (no knowledge base needed).
3. "rule"   — The message matches one of the fixed rules listed below.
4. "tool"   — An external tool or function should be invoked.

{rules_section}
{tools_section}
{context_section}

Current user message: "{query}"

Respond with ONLY valid JSON (no markdown, no explanation):
{{"intent": "<rag|direct|rule|tool>", "confidence": <0.0-1.0>, "reasoning": "<one sentence>"}}
"""


class LLMClassifier:
    """Ask the LLM to classify user intent.  Used as the last resort when
    faster classifiers are not confident enough.
    """

    def __init__(self, llm: "BaseLLMClient", config: OrchestratorConfig) -> None:
        self._llm = llm
        self._config = config

    async def classify(
        self,
        query: str,
        *,
        rule_descriptions: Optional[List[str]] = None,
        tool_descriptions: Optional[List[str]] = None,
        conversation_history: Optional[List[ConversationTurn]] = None,
        last_intent: Optional[IntentType] = None,
    ) -> ClassificationResult:
        rules_section = ""
        if rule_descriptions:
            rules_section = "Active rules:\n" + "\n".join(f"- {d}" for d in rule_descriptions)
        else:
            rules_section = "Active rules: (none)"

        tools_section = ""
        if tool_descriptions:
            tools_section = "Available tools:\n" + "\n".join(f"- {d}" for d in tool_descriptions)
        else:
            tools_section = "Available tools: (none)"

        context_section = ""
        if conversation_history:
            lines = []
            for t in conversation_history:
                role = t.get("role", "user")
                content = (t.get("content") or "").strip()
                if content:
                    lines.append(f"{role}: {content[:200]}")
            if lines:
                context_section = "Recent conversation:\n" + "\n".join(lines) + "\n\n"
        if last_intent is not None and context_section:
            context_section += f"(Previous reply was from intent: {last_intent.value}. If this is a follow-up, prefer the same intent.)\n\n"

        prompt_template = self._config.classification_prompt_override or _CLASSIFICATION_PROMPT
        prompt = prompt_template.format(
            rules_section=rules_section,
            tools_section=tools_section,
            context_section=context_section,
            query=query,
        )

        try:
            coro = self._llm.complete(prompt)
            if self._config.llm_timeout_seconds is not None and self._config.llm_timeout_seconds > 0:
                coro = asyncio.wait_for(coro, timeout=self._config.llm_timeout_seconds)
            raw = await coro
            return self._parse(raw)
        except asyncio.TimeoutError:
            logger.warning("LLMClassifier: classification timed out (%.0fs)", self._config.llm_timeout_seconds or 0)
            return ClassificationResult(
                intent=self._config.default_intent,
                confidence=0.0,
                reasoning="LLM timeout",
                classifier_layer="llm",
            )
        except Exception as exc:
            logger.error("LLMClassifier: classification failed: %s", exc)
            return ClassificationResult(
                intent=self._config.default_intent,
                confidence=0.0,
                reasoning=f"LLM error: {exc}",
                classifier_layer="llm",
            )

    @staticmethod
    def _parse(raw: str) -> ClassificationResult:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            ).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("LLMClassifier: could not parse JSON: %s", cleaned[:200])
            return ClassificationResult(
                intent=IntentType.DIRECT,
                confidence=0.0,
                reasoning="JSON parse error",
                classifier_layer="llm",
            )

        raw_intent = str(data.get("intent", "direct")).lower().strip()
        try:
            intent = IntentType(raw_intent)
        except ValueError:
            intent = IntentType.DIRECT

        confidence = float(data.get("confidence", 0.5))
        confidence = max(0.0, min(confidence, 1.0))
        reasoning = str(data.get("reasoning", ""))

        return ClassificationResult(
            intent=intent,
            confidence=confidence,
            reasoning=reasoning,
            classifier_layer="llm",
        )
