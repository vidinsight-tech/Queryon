"""Unit tests for Orchestrator: rules_first path and result shape."""
from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from uuid import uuid4

from backend.orchestrator.types import (
    IntentType,
    LowConfidenceStrategy,
    OrchestratorConfig,
    OrchestratorResult,
)


class TestOrchestratorRulesFirst(unittest.TestCase):
    """Test that rules_first uses keyword-only match and returns immediately."""

    def test_rules_first_returns_rule_result_without_llm(self) -> None:
        """When rule_engine.match(query) returns a match, process() returns that
        result with classifier_layer='rules_first' and no handler/LLM is invoked.
        """
        from backend.orchestrator.orchestrator import Orchestrator

        from backend.orchestrator.rules.engine import RuleMatchResult

        fake_rule = SimpleNamespace(
            id=uuid4(),
            name="FakeRule",
            description="",
            trigger_patterns=[],
            response_template="",
            variables={},
            priority=0,
            is_active=True,
            flow_id=None,
            step_key=None,
            required_step=None,
            next_steps=None,
            is_flow_rule=False,
        )

        class FakeRuleEngine:
            def match(self, query: str, *, flow_ctx=None):
                return RuleMatchResult(
                    rule=fake_rule,
                    rendered_answer="Cevap: sabit metin",
                )

            @property
            def rules(self):
                return [fake_rule]

            @property
            def keywords(self):
                return set()

        class FakeLLM:
            async def complete(self, prompt: str, *, model=None):
                raise AssertionError("LLM should not be called in rules_first path")

        orch = Orchestrator(
            llm=FakeLLM(),
            config=OrchestratorConfig(rules_first=True),
            rule_engine=FakeRuleEngine(),
        )
        # initialize not needed for rules_first path
        result = asyncio.get_event_loop().run_until_complete(
            orch.process("randevu al")
        )

        self.assertIsInstance(result, OrchestratorResult)
        self.assertEqual(result.intent, IntentType.RULE)
        self.assertEqual(result.rule_matched, "FakeRule")
        self.assertEqual(result.answer, "Cevap: sabit metin")
        self.assertIsNotNone(result.metrics)
        self.assertEqual(result.metrics.classifier_layer, "rules_first")


class TestOrchestratorResultShape(unittest.TestCase):
    def test_orchestrator_result_has_expected_fields(self) -> None:
        from backend.orchestrator.types import OrchestratorResult

        r = OrchestratorResult(
            query="test",
            intent=IntentType.DIRECT,
            answer="ok",
        )
        self.assertEqual(r.query, "test")
        self.assertEqual(r.intent, IntentType.DIRECT)
        self.assertEqual(r.answer, "ok")
        self.assertEqual(r.sources, [])
        self.assertIsNone(r.rule_matched)
        self.assertFalse(r.fallback_used)
        self.assertFalse(r.needs_clarification)


class TestOrchestratorConfigPersistence(unittest.TestCase):
    def test_to_dict_roundtrip(self) -> None:
        cfg = OrchestratorConfig(
            min_confidence=0.8,
            llm_timeout_seconds=30.0,
            max_conversation_turns=5,
            rules_first=False,
            low_confidence_strategy=LowConfidenceStrategy.ASK_USER,
        )
        data = cfg.to_dict()
        self.assertEqual(data["min_confidence"], 0.8)
        self.assertEqual(data["llm_timeout_seconds"], 30.0)
        self.assertEqual(data["max_conversation_turns"], 5)
        self.assertEqual(data["rules_first"], False)
        self.assertEqual(data["low_confidence_strategy"], "ask_user")
        loaded = OrchestratorConfig.from_dict(data)
        self.assertEqual(loaded.min_confidence, cfg.min_confidence)
        self.assertEqual(loaded.llm_timeout_seconds, cfg.llm_timeout_seconds)
        self.assertEqual(loaded.max_conversation_turns, cfg.max_conversation_turns)
        self.assertEqual(loaded.rules_first, cfg.rules_first)
        self.assertEqual(loaded.low_confidence_strategy, cfg.low_confidence_strategy)

    def test_from_dict_empty_uses_defaults(self) -> None:
        cfg = OrchestratorConfig.from_dict(None)
        self.assertEqual(cfg.min_confidence, 0.7)
        self.assertEqual(cfg.rules_first, True)
        cfg2 = OrchestratorConfig.from_dict({})
        self.assertEqual(cfg2.min_confidence, 0.7)
