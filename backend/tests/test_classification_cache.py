"""Unit tests for ClassificationCache."""
from __future__ import annotations

import time
import unittest

from backend.orchestrator.classifiers.cache import ClassificationCache
from backend.orchestrator.types import ClassificationResult, IntentType


class TestClassificationCache(unittest.TestCase):
    def test_put_and_get(self) -> None:
        cache = ClassificationCache(max_size=10, ttl_seconds=60)
        result = ClassificationResult(intent=IntentType.RAG, confidence=0.9)
        cache.put("same query", result)
        got = cache.get("same query")
        self.assertIsNotNone(got)
        self.assertEqual(got.intent, IntentType.RAG)
        self.assertEqual(got.confidence, 0.9)
        self.assertEqual(got.classifier_layer, "cache")

    def test_get_miss_returns_none(self) -> None:
        cache = ClassificationCache()
        self.assertIsNone(cache.get("unknown query"))

    def test_key_normalized_lowercase(self) -> None:
        cache = ClassificationCache(ttl_seconds=60)
        cache.put("Hello World", ClassificationResult(intent=IntentType.DIRECT))
        self.assertIsNotNone(cache.get("hello world"))

    def test_ttl_expiry(self) -> None:
        cache = ClassificationCache(max_size=10, ttl_seconds=0)
        cache.put("q", ClassificationResult(intent=IntentType.RAG))
        time.sleep(0.01)
        self.assertIsNone(cache.get("q"))

    def test_max_size_eviction(self) -> None:
        cache = ClassificationCache(max_size=2, ttl_seconds=3600)
        cache.put("a", ClassificationResult(intent=IntentType.RAG))
        cache.put("b", ClassificationResult(intent=IntentType.RAG))
        cache.put("c", ClassificationResult(intent=IntentType.RAG))
        self.assertEqual(cache.size, 2)
        self.assertIsNone(cache.get("a"))
        self.assertIsNotNone(cache.get("b"))
        self.assertIsNotNone(cache.get("c"))

    def test_clear(self) -> None:
        cache = ClassificationCache()
        cache.put("x", ClassificationResult(intent=IntentType.RULE))
        cache.clear()
        self.assertEqual(cache.size, 0)
        self.assertIsNone(cache.get("x"))
