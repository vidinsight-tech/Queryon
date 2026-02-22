"""RAGService: takes a user question, runs the RAG pipeline, returns an answer.

Validates at construction time that the embedding model dimension matches
the Qdrant collection vector size, so ingestion and retrieval are always
using compatible vectors.

Usage::

    svc = RAGService(
        qdrant=qdrant_manager,
        embedding_client=emb_client,
        llm_client=llm_client,
        qdrant_config=cfg,
    )
    result = await svc.ask("What were Q4 revenues?")
    print(result.answer, result.context.sources)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional

from backend.infra.vectorstore.collections import ensure_collection_exists
from backend.rag.embedder import Embedder
from backend.rag.hybrid_search import HybridSearcher
from backend.rag.pipeline import RAGPipeline
from backend.rag.query_rewriter import QueryRewriter
from backend.rag.reranker import LLMReranker
from backend.rag.search import SemanticSearcher
from backend.rag.types import PipelineConfig, PipelineResult, SearchResult

if TYPE_CHECKING:
    from backend.clients.embedding import BaseEmbeddingClient
    from backend.clients.llm import BaseLLMClient
    from backend.config import QdrantConfig
    from backend.infra.vectorstore.client import QdrantManager

logger = logging.getLogger(__name__)


class RAGService:
    """Answer user questions using the full RAG pipeline.

    The embedding client's ``dimension`` is checked against
    ``qdrant_config.vector_size`` at init time.  This guarantees
    the same vector space is used for both ingestion and retrieval.

    All heavy components (embedder, searcher, rewriter, reranker) are built
    once during the first ``ask()`` call and reused.
    """

    def __init__(
        self,
        qdrant: "QdrantManager",
        embedding_client: "BaseEmbeddingClient",
        llm_client: "BaseLLMClient",
        *,
        qdrant_config: Optional["QdrantConfig"] = None,
        embedder_batch_size: int = 64,
        embedder_normalize: bool = True,
    ) -> None:
        self._qdrant = qdrant
        self._qdrant_config = qdrant_config
        self._llm = llm_client

        expected_dim = qdrant_config.vector_size if qdrant_config else None
        self._embedder = Embedder(
            embedding_client,
            batch_size=embedder_batch_size,
            normalize=embedder_normalize,
            expected_dimension=expected_dim,
        )
        self._pipeline: Optional[RAGPipeline] = None
        self._collection: Optional[str] = None

    @property
    def embedding_model(self) -> str:
        return self._embedder.model_name

    @property
    def embedding_dimension(self) -> int:
        return self._embedder.dimension

    # ── Public API ──

    async def ask(
        self,
        question: str,
        *,
        config: Optional[PipelineConfig] = None,
    ) -> PipelineResult:
        """Run the full RAG pipeline and return an answer with sources.

        Steps executed (depending on config flags):
            1. Query rewrite  (rewrite_query=True)
            2. Hybrid search  (hybrid_search=True) or semantic search
            3. LLM reranking  (rerank=True)
            4. Context assembly with token budgeting & dedup
            5. LLM answer generation
        """
        pipeline = await self._get_pipeline()
        return await pipeline.run(question, config=config, generate_answer=True)

    async def search(
        self,
        question: str,
        *,
        top_k: int = 10,
        score_threshold: float = 0.72,
    ) -> List[SearchResult]:
        """Search without reranking or answer generation. Returns raw results."""
        cfg = PipelineConfig(
            top_k=top_k,
            score_threshold=score_threshold,
            rerank=False,
            rewrite_query=False,
            hybrid_search=False,
        )
        pipeline = await self._get_pipeline()
        result = await pipeline.run(question, config=cfg, generate_answer=False)
        return result.results

    # ── Internals ──

    async def _get_pipeline(self) -> RAGPipeline:
        if self._pipeline is None:
            collection = await self._ensure_collection()
            self._pipeline = self._build_pipeline(collection)
        return self._pipeline

    async def _ensure_collection(self) -> str:
        if self._collection is None:
            self._collection = await ensure_collection_exists(
                self._qdrant, self._qdrant_config,
            )
        return self._collection

    def _build_pipeline(self, collection: str) -> RAGPipeline:
        searcher = SemanticSearcher(self._embedder, self._qdrant, collection)
        hybrid = HybridSearcher(self._embedder, self._qdrant, collection)
        reranker = LLMReranker(self._llm)
        rewriter = QueryRewriter(self._llm)

        return RAGPipeline(
            searcher=searcher,
            hybrid_searcher=hybrid,
            reranker=reranker,
            query_rewriter=rewriter,
            llm=self._llm,
        )
