"""RAGPipeline: rewrite → search → rerank → assemble → answer."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional

from backend.rag.context import ContextAssembler
from backend.rag.types import PipelineConfig, PipelineResult, SearchResult

if TYPE_CHECKING:
    from backend.clients.llm import BaseLLMClient
    from backend.rag.hybrid_search import HybridSearcher
    from backend.rag.query_rewriter import QueryRewriter
    from backend.rag.reranker import LLMReranker
    from backend.rag.search import SemanticSearcher

logger = logging.getLogger(__name__)

_ANSWER_PROMPT = (
    "Answer the user's question using ONLY the provided context. "
    "If the context does not contain enough information, say so clearly. "
    "Cite sources using [Source: ...] references where applicable.\n\n"
    "Context:\n{context}\n\n"
    "Question: {question}\n\n"
    "Answer:"
)


class RAGPipeline:
    """Full retrieval-augmented generation pipeline.

    Components are injected once; per-query behaviour is controlled
    via PipelineConfig passed to ``run()``.
    """

    def __init__(
        self,
        searcher: "SemanticSearcher",
        *,
        hybrid_searcher: Optional["HybridSearcher"] = None,
        reranker: Optional["LLMReranker"] = None,
        query_rewriter: Optional["QueryRewriter"] = None,
        llm: Optional["BaseLLMClient"] = None,
    ) -> None:
        self._searcher = searcher
        self._hybrid = hybrid_searcher
        self._reranker = reranker
        self._rewriter = query_rewriter
        self._llm = llm

    async def run(
        self,
        query: str,
        config: Optional[PipelineConfig] = None,
        *,
        generate_answer: bool = True,
    ) -> PipelineResult:
        cfg = config or PipelineConfig()
        result = PipelineResult(query=query)

        search_query = await self._maybe_rewrite(query, cfg)
        if search_query != query:
            result.rewritten_query = search_query

        results = await self._search(search_query, cfg)
        results = await self._maybe_rerank(search_query, results, cfg)
        result.results = results

        assembler = ContextAssembler(max_tokens=cfg.max_context_tokens)
        result.context = assembler.assemble(results)

        if generate_answer and self._llm and result.context.text:
            result.answer = await self._generate_answer(query, result.context.text)

        logger.info(
            "Pipeline: query='%s' results=%d ctx_tokens=%d answered=%s",
            query[:60], len(results),
            result.context.total_tokens,
            bool(result.answer),
        )
        return result

    # ── internal steps ──

    async def _maybe_rewrite(self, query: str, cfg: PipelineConfig) -> str:
        if cfg.rewrite_query and self._rewriter:
            rewritten = await self._rewriter.rewrite(query)
            logger.debug("Rewritten: '%s' → '%s'", query[:60], rewritten[:60])
            return rewritten
        return query

    async def _search(self, query: str, cfg: PipelineConfig) -> List[SearchResult]:
        if cfg.hybrid_search and self._hybrid:
            self._hybrid._keyword_weight = cfg.hybrid_keyword_weight
            return await self._hybrid.search(
                query, top_k=cfg.top_k, score_threshold=cfg.score_threshold,
            )
        return await self._searcher.search(
            query, top_k=cfg.top_k, score_threshold=cfg.score_threshold,
        )

    async def _maybe_rerank(
        self, query: str, results: List[SearchResult], cfg: PipelineConfig,
    ) -> List[SearchResult]:
        if cfg.rerank and self._reranker and results:
            return await self._reranker.rerank(query, results)
        return results

    async def _generate_answer(self, question: str, context: str) -> Optional[str]:
        prompt = _ANSWER_PROMPT.format(context=context, question=question)
        try:
            return await self._llm.complete(prompt)  # type: ignore[union-attr]
        except Exception as exc:
            logger.error("Answer generation failed: %s", exc)
            return None
