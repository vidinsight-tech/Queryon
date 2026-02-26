"""Layer 2: embedding-based intent classifier — uses cosine similarity against
prototype queries per intent type.  Fast (~5-15 ms) and LLM-free.
"""
from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Dict, List, Optional

from backend.orchestrator.types import ClassificationResult, IntentType

if TYPE_CHECKING:
    from backend.rag.embedder import Embedder

logger = logging.getLogger(__name__)

_DEFAULT_EXAMPLES: Dict[IntentType, List[str]] = {
    IntentType.RAG: [
        "Dokümanlarda bu konu hakkında ne yazıyor?",
        "Bilgi tabanında bu konuyla ilgili bilgi var mı?",
        "Yüklenen dosyalara göre cevap ver.",
        "What does the documentation say about this?",
        "Search the knowledge base for this topic.",
    ],
    IntentType.DIRECT: [
        "Python'da list comprehension nasıl yazılır?",
        "Merhaba, nasılsın?",
        "Bu cümleyi İngilizce'ye çevir.",
        "Özet çıkar.",
        "What is the capital of France?",
        "Explain quantum computing simply.",
    ],
    IntentType.RULE: [
        "Randevu almak istiyorum.",
        "Çalışma saatleriniz nedir?",
        "Fiyat listesi nedir?",
        "İletişim bilgileriniz nelerdir?",
        "What are your business hours?",
    ],
    IntentType.TOOL: [
        "Bu veriyi analiz et.",
        "Grafik oluştur.",
        "Veritabanını sorgula.",
        "Run this query.",
        "Execute the report.",
    ],
}


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a < 1e-12 or norm_b < 1e-12:
        return 0.0
    return dot / (norm_a * norm_b)


class EmbeddingClassifier:
    """Classify intent by comparing the query embedding against prototype embeddings.

    Prototypes are built once via ``build_prototypes()`` and reused for every call.
    """

    def __init__(self, embedder: "Embedder") -> None:
        self._embedder = embedder
        self._prototypes: Dict[IntentType, List[List[float]]] = {}
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    async def build_prototypes(
        self,
        examples: Optional[Dict[IntentType, List[str]]] = None,
    ) -> None:
        """Embed example queries for each intent type."""
        examples = examples or _DEFAULT_EXAMPLES
        for intent, texts in examples.items():
            vecs = await self._embedder.embed_texts(texts)
            self._prototypes[intent] = vecs
        self._ready = True
        logger.info(
            "EmbeddingClassifier: built prototypes for %d intents (%d total examples)",
            len(self._prototypes),
            sum(len(v) for v in self._prototypes.values()),
        )

    async def classify(self, query: str) -> ClassificationResult:
        if not self._ready:
            return ClassificationResult(
                intent=IntentType.DIRECT,
                confidence=0.0,
                reasoning="prototypes not built",
                classifier_layer="embedding",
            )

        try:
            q_vec = await self._embedder.embed_query(query)
        except Exception as exc:
            logger.warning("EmbeddingClassifier: embed_query failed: %s", exc)
            return ClassificationResult(
                intent=IntentType.DIRECT,
                confidence=0.0,
                reasoning=f"embedding error: {exc}",
                classifier_layer="embedding",
            )

        # Compute mean cosine similarity per intent (more stable than global max)
        intent_scores: Dict[IntentType, float] = {}
        for intent, proto_vecs in self._prototypes.items():
            scores = [_cosine_similarity(q_vec, pv) for pv in proto_vecs]
            intent_scores[intent] = sum(scores) / len(scores)

        sorted_intents = sorted(intent_scores.items(), key=lambda x: x[1], reverse=True)
        best_intent, best_score = sorted_intents[0]
        second_score = sorted_intents[1][1] if len(sorted_intents) > 1 else 0.0
        margin = best_score - second_score

        logger.debug(
            "EmbeddingClassifier: query='%s' → %s (mean=%.4f margin=%.4f)",
            query[:60], best_intent.value, best_score, margin,
        )
        return ClassificationResult(
            intent=best_intent,
            confidence=round(best_score, 4),
            reasoning=f"mean cosine similarity: {best_score:.4f}, margin: {margin:.4f}",
            classifier_layer="embedding",
        )
