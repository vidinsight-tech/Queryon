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
        self.assertIsNone(r.tool_called)
        self.assertFalse(r.fallback_used)
        self.assertIsNone(r.fallback_from_intent)
        self.assertFalse(r.needs_clarification)

    def test_fallback_fields_default_none(self) -> None:
        """fallback_used=False and fallback_from_intent=None by default."""
        r = OrchestratorResult(query="q", intent=IntentType.RAG)
        self.assertFalse(r.fallback_used)
        self.assertIsNone(r.fallback_from_intent)

    def test_fallback_fields_can_be_set(self) -> None:
        """Verify both fallback fields accept values."""
        r = OrchestratorResult(
            query="q",
            intent=IntentType.DIRECT,
            fallback_used=True,
            fallback_from_intent="rag",
        )
        self.assertTrue(r.fallback_used)
        self.assertEqual(r.fallback_from_intent, "rag")


class TestOrchestratorFallbacks(unittest.TestCase):
    """Verify rule→direct and rag→direct fallback paths set fallback_from_intent."""

    def _make_orch(self, handlers: dict, *, config: "OrchestratorConfig" = None):
        """Build a minimal Orchestrator with stubbed handlers."""
        from backend.orchestrator.orchestrator import Orchestrator

        class FakeLLM:
            async def complete(self, prompt: str, *, model=None):
                return '{"intent": "direct", "confidence": 0.9, "reasoning": "ok"}'

        orch = Orchestrator(
            llm=FakeLLM(),
            config=config or OrchestratorConfig(
                rules_first=False,
                min_confidence=0.0,
                enabled_intents=[IntentType.DIRECT, IntentType.RAG, IntentType.RULE],
            ),
        )
        orch._handlers = handlers
        return orch

    def _make_handler(self, answer: str, intent: "IntentType"):
        """Return a fake handler whose handle() resolves to an OrchestratorResult."""
        result = OrchestratorResult(query="", intent=intent, answer=answer)

        class FakeHandler:
            async def handle(self, query, **kwargs):
                return result

        return FakeHandler()

    def test_rule_to_direct_fallback(self) -> None:
        """When RULE handler returns empty answer, fallback_from_intent='rule'."""
        rule_handler = self._make_handler("", IntentType.RULE)
        direct_handler = self._make_handler("Direct answer", IntentType.DIRECT)

        orch = self._make_orch({
            IntentType.RULE: rule_handler,
            IntentType.DIRECT: direct_handler,
        })

        # Force RULE classification by providing a pre-classified result
        from backend.orchestrator.types import ClassificationResult

        async def _classify(*args, **kwargs):
            return ClassificationResult(
                intent=IntentType.RULE,
                confidence=0.95,
                reasoning="keyword match",
                classifier_layer="pre",
            )

        orch._classify = _classify

        result = asyncio.get_event_loop().run_until_complete(
            orch.process("some query")
        )

        self.assertTrue(result.fallback_used)
        self.assertEqual(result.fallback_from_intent, "rule")
        self.assertEqual(result.intent, IntentType.DIRECT)
        self.assertEqual(result.answer, "Direct answer")

    def test_rag_to_direct_fallback(self) -> None:
        """When RAG handler returns empty answer and fallback_to_direct=True,
        fallback_from_intent='rag'."""
        rag_handler = self._make_handler("", IntentType.RAG)
        direct_handler = self._make_handler("Direct answer", IntentType.DIRECT)

        config = OrchestratorConfig(
            rules_first=False,
            min_confidence=0.0,
            fallback_to_direct=True,
            enabled_intents=[IntentType.DIRECT, IntentType.RAG],
        )
        orch = self._make_orch(
            {IntentType.RAG: rag_handler, IntentType.DIRECT: direct_handler},
            config=config,
        )

        from backend.orchestrator.types import ClassificationResult

        async def _classify(*args, **kwargs):
            return ClassificationResult(
                intent=IntentType.RAG,
                confidence=0.9,
                reasoning="RAG signal",
                classifier_layer="pre",
            )

        orch._classify = _classify

        result = asyncio.get_event_loop().run_until_complete(
            orch.process("belgede ne yazıyor?")
        )

        self.assertTrue(result.fallback_used)
        self.assertEqual(result.fallback_from_intent, "rag")
        self.assertEqual(result.intent, IntentType.DIRECT)

    def test_no_fallback_when_answer_present(self) -> None:
        """When RULE handler returns an answer, no fallback should occur."""
        rule_handler = self._make_handler("Rule answer", IntentType.RULE)
        direct_handler = self._make_handler("Direct answer", IntentType.DIRECT)

        orch = self._make_orch({
            IntentType.RULE: rule_handler,
            IntentType.DIRECT: direct_handler,
        })

        from backend.orchestrator.types import ClassificationResult

        async def _classify(*args, **kwargs):
            return ClassificationResult(
                intent=IntentType.RULE,
                confidence=0.95,
                reasoning="match",
                classifier_layer="pre",
            )

        orch._classify = _classify

        result = asyncio.get_event_loop().run_until_complete(
            orch.process("query")
        )

        self.assertFalse(result.fallback_used)
        self.assertIsNone(result.fallback_from_intent)
        self.assertEqual(result.answer, "Rule answer")


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
