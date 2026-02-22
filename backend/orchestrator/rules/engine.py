"""RuleEngine: deterministic keyword/regex matching with optional LLM fallback."""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from backend.orchestrator.rules.models import OrchestratorRule

if TYPE_CHECKING:
    from backend.clients.llm.base import BaseLLMClient

logger = logging.getLogger(__name__)

_LLM_RULE_MATCH_PROMPT = (
    "You are a rule matcher. Given the user message and a list of rules, "
    "determine which rule (if any) best matches the user's intent.\n\n"
    "Rules:\n{rules}\n\n"
    "User message: \"{query}\"\n\n"
    "If a rule matches, respond with ONLY the JSON: "
    '{{\"rule_id\": \"<id>\", \"confidence\": 0.0-1.0}}\n'
    "If no rule matches, respond with: "
    '{{\"rule_id\": null, \"confidence\": 0.0}}'
)

_REGEX_PREFIX = "r:"


_WILDCARD = "*"


@dataclass
class FlowContext:
    """Snapshot of the user's current position inside a multi-step flow."""
    flow_id: Optional[str] = None
    current_step: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    selections: Dict[str, str] = field(default_factory=dict)
    """Maps step_key → user's raw answer at that step."""

    @property
    def active(self) -> bool:
        return self.flow_id is not None

    def to_dict(self) -> Optional[Dict[str, Any]]:
        if not self.active:
            return None
        return {
            "flow_id": self.flow_id,
            "current_step": self.current_step,
            "data": self.data,
            "selections": self.selections,
        }

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]) -> "FlowContext":
        if not d:
            return cls()
        return cls(
            flow_id=d.get("flow_id"),
            current_step=d.get("current_step"),
            data=d.get("data") or {},
            selections=d.get("selections") or {},
        )


@dataclass
class RuleMatchResult:
    """Extended match result that carries flow-transition metadata."""
    rule: OrchestratorRule
    rendered_answer: str
    next_flow_context: Optional[FlowContext] = None


class RuleEngine:
    """Match user queries against deterministic rules.

    Rules are checked in priority-descending order.  Trigger patterns are
    either plain substring matches or regex patterns (prefixed with ``r:``).

    When a ``FlowContext`` is provided, flow-bound rules for the current step
    are evaluated first; standalone rules follow if no flow rule matched.
    """

    def __init__(self, rules: List[OrchestratorRule]) -> None:
        self._rules = sorted(rules, key=lambda r: r.priority, reverse=True)
        self._compiled: dict[str, re.Pattern[str]] = {}
        for rule in self._rules:
            for pat in rule.trigger_patterns:
                if pat.startswith(_REGEX_PREFIX):
                    expr = pat[len(_REGEX_PREFIX):]
                    try:
                        self._compiled[pat] = re.compile(expr, re.IGNORECASE)
                    except re.error as exc:
                        logger.warning("Invalid regex in rule %s: %s (%s)", rule.id, pat, exc)

    @property
    def rules(self) -> List[OrchestratorRule]:
        return list(self._rules)

    @property
    def keywords(self) -> set[str]:
        """All plain-text (non-regex) trigger keywords, lowercased."""
        kws: set[str] = set()
        for rule in self._rules:
            if not rule.is_active:
                continue
            for pat in rule.trigger_patterns:
                if not pat.startswith(_REGEX_PREFIX):
                    kws.add(pat.lower())
        return kws

    # ── Primary match (keyword/regex, flow-aware) ──────────────────

    def match(
        self,
        query: str,
        *,
        flow_ctx: Optional[FlowContext] = None,
    ) -> Optional[RuleMatchResult]:
        """Keyword/regex match — deterministic, no LLM call.

        When *flow_ctx* is active the engine first tries rules belonging to
        the current flow + step.  If nothing matches inside the flow, it also
        checks standalone (non-flow) rules so the user can still trigger
        global commands (e.g. "iptal" to cancel).
        """
        if flow_ctx and flow_ctx.active:
            result = self._match_flow_entry_by_choice(query, flow_ctx)
            if result is not None:
                return result
            result = self._match_flow_rules(query, flow_ctx)
            if result is not None:
                return result
            result = self._match_standalone_rules(query)
            if result is not None:
                return result
            return None

        result = self._match_standalone_rules(query)
        if result is not None:
            return result
        result = self._match_flow_entry_rules(query)
        return result

    # ── LLM-assisted match (unchanged signature, flow-aware) ───────

    async def match_with_llm(
        self,
        query: str,
        llm: "BaseLLMClient",
        *,
        confidence_threshold: float = 0.7,
        timeout_seconds: Optional[float] = None,
        flow_ctx: Optional[FlowContext] = None,
    ) -> Optional[RuleMatchResult]:
        """Try keyword match first, then ask the LLM to pick a rule."""
        result = self.match(query, flow_ctx=flow_ctx)
        if result is not None:
            return result

        active = [r for r in self._rules if r.is_active and not r.is_flow_rule]
        if not active:
            return None

        rules_text = "\n".join(
            f"- id={r.id} | name=\"{r.name}\" | description=\"{r.description}\""
            for r in active
        )
        prompt = _LLM_RULE_MATCH_PROMPT.format(rules=rules_text, query=query)
        try:
            coro = llm.complete(prompt)
            if timeout_seconds is not None and timeout_seconds > 0:
                coro = asyncio.wait_for(coro, timeout=timeout_seconds)
            raw = await coro
            parsed = json.loads(raw.strip())
            rule_id_str = parsed.get("rule_id")
            confidence = float(parsed.get("confidence", 0))
        except asyncio.TimeoutError:
            logger.warning("RuleEngine: LLM rule matching timed out (%.0fs)", timeout_seconds or 0)
            return None
        except Exception as exc:
            logger.warning("RuleEngine: LLM rule matching failed: %s", exc)
            return None

        if not rule_id_str or confidence < confidence_threshold:
            return None

        matched = next((r for r in active if str(r.id) == rule_id_str), None)
        if matched is None:
            logger.debug("RuleEngine: LLM returned unknown rule_id %s", rule_id_str)
            return None

        logger.debug("RuleEngine: LLM matched rule '%s' (confidence=%.2f)", matched.name, confidence)
        return RuleMatchResult(
            rule=matched,
            rendered_answer=self._render(matched),
            next_flow_context=self._build_next_ctx(matched, query),
        )

    # ── Internal matching helpers ──────────────────────────────────

    def _match_standalone_rules(self, query: str) -> Optional[RuleMatchResult]:
        """Match against rules that are NOT part of any flow."""
        q_lower = query.lower()
        for rule in self._rules:
            if not rule.is_active or rule.is_flow_rule:
                continue
            if self._patterns_hit(rule, query, q_lower):
                return RuleMatchResult(
                    rule=rule,
                    rendered_answer=self._render(rule),
                )
        return None

    def _match_flow_entry_rules(self, query: str) -> Optional[RuleMatchResult]:
        """Match flow entry-point rules (flow_id set, required_step is NULL)."""
        q_lower = query.lower()
        for rule in self._rules:
            if not rule.is_active or not rule.is_flow_rule:
                continue
            if rule.required_step is not None:
                continue
            if self._patterns_hit(rule, query, q_lower):
                return RuleMatchResult(
                    rule=rule,
                    rendered_answer=self._render(rule),
                    next_flow_context=self._build_next_ctx(rule, query),
                )
        return None

    def _match_flow_rules(
        self, query: str, flow_ctx: FlowContext,
    ) -> Optional[RuleMatchResult]:
        """Match rules gated by the user's current flow + step."""
        q_lower = query.lower()
        for rule in self._rules:
            if not rule.is_active or not rule.is_flow_rule:
                continue
            if rule.flow_id != flow_ctx.flow_id:
                continue
            if rule.required_step != flow_ctx.current_step:
                continue
            if self._patterns_hit(rule, query, q_lower):
                return RuleMatchResult(
                    rule=rule,
                    rendered_answer=self._render(rule),
                    next_flow_context=self._build_next_ctx(rule, query, flow_ctx),
                )
        return None

    def _match_flow_entry_by_choice(
        self, query: str, flow_ctx: FlowContext,
    ) -> Optional[RuleMatchResult]:
        """When the user is inside a flow and the previous step had next_steps,
        resolve the choice to the next step's entry rule.

        Supports wildcard ``"*"`` as a catch-all fallback in next_steps.
        """
        parent_rules = [
            r for r in self._rules
            if r.is_active
            and r.flow_id == flow_ctx.flow_id
            and r.step_key == flow_ctx.current_step
            and r.next_steps
        ]
        if not parent_rules:
            return None

        q_lower = query.strip().lower()
        q_words = set(q_lower.split())
        for parent in parent_rules:
            next_steps: Dict[str, str] = parent.next_steps or {}
            wildcard_target: Optional[str] = next_steps.get(_WILDCARD)

            for choice, target_step in next_steps.items():
                if choice == _WILDCARD:
                    continue
                if self._choice_matches(choice, q_lower, q_words):
                    return self._resolve_choice_target(
                        query, flow_ctx, parent, target_step,
                    )

            if wildcard_target is not None:
                return self._resolve_choice_target(
                    query, flow_ctx, parent, wildcard_target,
                )
        return None

    @staticmethod
    def _choice_matches(
        choice: str, q_lower: str, q_words: set[str],
    ) -> bool:
        """Check whether the user's query matches a choice key.

        Short choices (<=2 chars, e.g. "A", "1") require exact or whole-word
        match to avoid false positives like "a" in "merhaba".
        Longer choices use substring matching.
        """
        c_lower = choice.lower()
        if len(c_lower) <= 2:
            return c_lower in q_words or c_lower == q_lower
        return c_lower in q_lower

    def _resolve_choice_target(
        self,
        query: str,
        flow_ctx: FlowContext,
        parent_rule: OrchestratorRule,
        target_step: str,
    ) -> Optional[RuleMatchResult]:
        """Build a RuleMatchResult for a resolved choice transition."""
        target_rule = self._find_step_rule(
            flow_ctx.flow_id, target_step,  # type: ignore[arg-type]
        )
        if target_rule is None:
            return None

        new_selections = {
            **flow_ctx.selections,
            flow_ctx.current_step or "": query.strip(),
        }
        new_ctx: Optional[FlowContext] = None
        if target_rule.next_steps:
            new_ctx = FlowContext(
                flow_id=flow_ctx.flow_id,
                current_step=target_step,
                data={**flow_ctx.data, "last_query": query.strip()},
                selections=new_selections,
            )
        return RuleMatchResult(
            rule=target_rule,
            rendered_answer=self._render(target_rule),
            next_flow_context=new_ctx,
        )

    def _find_step_rule(self, flow_id: str, step_key: str) -> Optional[OrchestratorRule]:
        """Find the highest-priority rule for a specific step in a flow."""
        for rule in self._rules:
            if (
                rule.is_active
                and rule.flow_id == flow_id
                and rule.step_key == step_key
            ):
                return rule
        return None

    def _patterns_hit(
        self, rule: OrchestratorRule, query: str, q_lower: str,
    ) -> bool:
        for pat in rule.trigger_patterns:
            if pat == _WILDCARD:
                return True
            if pat.startswith(_REGEX_PREFIX):
                compiled = self._compiled.get(pat)
                if compiled and compiled.search(query):
                    return True
            else:
                if pat.lower() in q_lower:
                    return True
        return False

    # ── Flow context builder ───────────────────────────────────────

    @staticmethod
    def _build_next_ctx(
        rule: OrchestratorRule,
        query: str,
        prev_ctx: Optional[FlowContext] = None,
    ) -> Optional[FlowContext]:
        if not rule.is_flow_rule:
            return None
        if rule.next_steps:
            prev_selections = prev_ctx.selections if prev_ctx else {}
            new_selections = {**prev_selections}
            if prev_ctx and prev_ctx.current_step:
                new_selections[prev_ctx.current_step] = query.strip()
            return FlowContext(
                flow_id=rule.flow_id,
                current_step=rule.step_key,
                data={**(prev_ctx.data if prev_ctx else {}), "last_query": query},
                selections=new_selections,
            )
        return None

    # ── Template rendering ─────────────────────────────────────────

    _SAFE_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

    @staticmethod
    def _render(rule: OrchestratorRule) -> str:
        """Substitute variables into the response template.

        Only placeholders matching {identifier} are replaced, using values from
        *variables*. This avoids format-string injection (e.g. {0.__class__}).
        """
        variables = rule.variables or {}
        if not variables:
            return rule.response_template

        def repl(match: re.Match[str]) -> str:
            key = match.group(1)
            if key in variables:
                return str(variables[key])
            return match.group(0)

        return RuleEngine._SAFE_PLACEHOLDER.sub(repl, rule.response_template)
