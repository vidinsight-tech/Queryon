"""Classification cache — avoids repeated LLM calls for identical queries."""
from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import Optional

from backend.orchestrator.types import ClassificationResult

logger = logging.getLogger(__name__)


class ClassificationCache:
    """Simple LRU cache keyed on the exact query string with TTL expiry."""

    def __init__(self, max_size: int = 500, ttl_seconds: int = 3600) -> None:
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._store: OrderedDict[str, tuple[ClassificationResult, float]] = OrderedDict()

    def get(self, query: str) -> Optional[ClassificationResult]:
        key = query.strip().lower()
        entry = self._store.get(key)
        if entry is None:
            return None
        result, ts = entry
        if time.monotonic() - ts > self._ttl:
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        logger.debug("ClassificationCache: hit for '%s'", query[:60])
        return ClassificationResult(
            intent=result.intent,
            confidence=result.confidence,
            reasoning=result.reasoning,
            classifier_layer="cache",
        )

    def put(self, query: str, result: ClassificationResult) -> None:
        key = query.strip().lower()
        self._store[key] = (result, time.monotonic())
        self._store.move_to_end(key)
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)
