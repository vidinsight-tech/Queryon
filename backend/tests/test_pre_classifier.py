"""Unit tests for PreClassifier (keyword-based intent layer)."""
from __future__ import annotations

import unittest

from backend.orchestrator.classifiers.pre_classifier import PreClassifier
from backend.orchestrator.types import IntentType


class TestPreClassifier(unittest.TestCase):
    def test_rule_keyword_match(self) -> None:
        pc = PreClassifier(rule_keywords={"randevu", "saat"})
        result = pc.try_classify("Randevu almak istiyorum")
        self.assertIsNotNone(result)
        self.assertEqual(result.intent, IntentType.RULE)
        self.assertGreaterEqual(result.confidence, 0.9)

    def test_rag_signal_match(self) -> None:
        pc = PreClassifier(rule_keywords=set())
        result = pc.try_classify("Dokümanlarda ne yazıyor?")
        self.assertIsNotNone(result)
        self.assertEqual(result.intent, IntentType.RAG)

    def test_tool_trigger_match(self) -> None:
        pc = PreClassifier(
            rule_keywords=set(),
            tool_triggers={"grafik": ["grafik oluştur", "chart"]},
        )
        result = pc.try_classify("grafik oluştur")
        self.assertIsNotNone(result)
        self.assertEqual(result.intent, IntentType.TOOL)

    def test_no_match_returns_none(self) -> None:
        pc = PreClassifier(rule_keywords=set())
        result = pc.try_classify("Merhaba nasılsın")
        self.assertIsNone(result)

    def test_rule_takes_precedence_over_rag_signal(self) -> None:
        pc = PreClassifier(rule_keywords={"randevu"}, rag_signals=["randevu"])
        result = pc.try_classify("randevu saatleri")
        self.assertIsNotNone(result)
        self.assertEqual(result.intent, IntentType.RULE)
