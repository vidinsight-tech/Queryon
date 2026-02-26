"""Layer 3: LLM-based intent classifier — most accurate, highest latency."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import TYPE_CHECKING, List, Optional

from backend.orchestrator.types import (
    ClassificationResult,
    ConversationTurn,
    IntentType,
    OrchestratorConfig,
)

if TYPE_CHECKING:
    from backend.clients.llm.base import BaseLLMClient
    from backend.orchestrator.rules.engine import FlowContext

logger = logging.getLogger(__name__)

_CLASSIFICATION_PROMPT = """\
You are an intent classifier. Think step-by-step through the query, then output your classification.

Intent categories:
1. "rag"    — The user needs information from uploaded documents / knowledge base.
2. "direct" — General knowledge, conversation, translation, summarisation (no documents needed).
3. "rule"   — The message matches one of the fixed rules listed below.
4. "tool"   — An external tool or function should be invoked.

{rules_section}
{tools_section}
{context_section}

Current user message: "{query}"

Think through the following inside <thinking> tags (be concise, 2–4 sentences):
- What is the user asking or trying to do?
- Does the message match any listed rule? If yes, which one?
- Is a tool call required? If yes, which tool?
- Does the user need information from uploaded documents?
- Or is this general conversation / knowledge the LLM can answer directly?

Confidence calibration guide:
- 0.95–1.0: Very clear match, only one intent makes sense.
- 0.80–0.94: Strong match, minor ambiguity possible.
- 0.65–0.79: Probable match but another intent is plausible.
- 0.50–0.64: Uncertain — two intents are nearly equally likely.
- Below 0.50: Very unclear; prefer the most conservative guess.

Then output ONLY the JSON on a new line (no markdown):
<thinking>
[your reasoning here]
</thinking>
{{"intent": "<rag|direct|rule|tool>", "confidence": <0.0-1.0>, "reasoning": "<one sentence summary>"}}
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
        flow_ctx: Optional["FlowContext"] = None,
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
        if last_intent is not None:
            context_section += f"(Previous reply was from intent: {last_intent.value}. If this is a follow-up, prefer the same intent.)\n\n"

        if flow_ctx is not None and flow_ctx.active:
            step = flow_ctx.current_step or "unknown"
            collected_info = ""
            if flow_ctx.data:
                fields = ", ".join(
                    f"{k}={v!r}"
                    for k, v in list(flow_ctx.data.items())[:5]
                )
                collected_info = f", collected={{{fields}}}"
            context_section += (
                f"(User is currently inside a multi-step flow: "
                f"flow_id='{flow_ctx.flow_id}', step='{step}'{collected_info}. "
                f"Prefer 'rule' if the message is a response to the current flow step.)\n\n"
            )

        prompt_template = self._config.classification_prompt_override or _CLASSIFICATION_PROMPT
        fmt_vars = dict(
            rules_section=rules_section,
            tools_section=tools_section,
            context_section=context_section,
            query=query,
        )
        try:
            prompt = prompt_template.format(**fmt_vars)
        except (KeyError, IndexError):
            # Custom prompt is missing one or more expected placeholders — fall
            # back to the default template so the classifier never hard-crashes.
            logger.warning(
                "LLMClassifier: classification_prompt_override is missing expected "
                "placeholders; falling back to the default template."
            )
            prompt = _CLASSIFICATION_PROMPT.format(**fmt_vars)

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
        # ── 1. Extract <thinking> block ──────────────────────────────────────
        thinking: Optional[str] = None
        m = re.search(r"<thinking>(.*?)</thinking>", raw, re.DOTALL)
        if m:
            thinking = m.group(1).strip()
            json_candidate = raw[m.end():].strip()
        else:
            json_candidate = raw.strip()

        # ── 2. Strip markdown fences ─────────────────────────────────────────
        if json_candidate.startswith("```"):
            lines = json_candidate.splitlines()
            json_candidate = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            ).strip()

        # ── 3. Parse JSON ────────────────────────────────────────────────────
        data: dict = {}
        try:
            data = json.loads(json_candidate)
        except json.JSONDecodeError:
            # Fallback: find the first {...} containing "intent" anywhere in raw
            fallback = re.search(r'\{[^{}]*"intent"[^{}]*\}', raw, re.DOTALL)
            if fallback:
                try:
                    data = json.loads(fallback.group())
                except json.JSONDecodeError:
                    pass
            if not data:
                logger.warning("LLMClassifier: could not parse JSON from: %s", raw[:300])
                return ClassificationResult(
                    intent=IntentType.DIRECT,
                    confidence=0.0,
                    reasoning="JSON parse error",
                    classifier_layer="llm",
                    thinking=thinking,
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
            thinking=thinking,
        )
