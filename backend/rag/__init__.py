"""
RAG: parsing, chunking, embedding, search, reranking, and pipeline.

Usage::

    # Document processing
    from backend.rag import RAGDocService
    svc = RAGDocService()
    chunks = svc.parse_and_chunk("/path/to/file.pdf")

    # Full pipeline via RAGService (backend.services.rag_service)
    from backend.services import RAGService
"""
from backend.rag.context import ContextAssembler
from backend.rag.embedder import Embedder
from backend.rag.hybrid_search import HybridSearcher
from backend.rag.pipeline import RAGPipeline
from backend.rag.query_rewriter import QueryRewriter
from backend.rag.reranker import LLMReranker
from backend.rag.search import SemanticSearcher
from backend.rag.service import RAGDocService
from backend.rag.types import (
    AssembledContext,
    Chunk,
    FileChunkInfo,
    FileInfo,
    IngestionResult,
    ParsedContent,
    PipelineConfig,
    PipelineResult,
    SearchResult,
)

__all__ = [
    "RAGDocService",
    "ParsedContent",
    "Chunk",
    "SearchResult",
    "AssembledContext",
    "PipelineConfig",
    "PipelineResult",
    "IngestionResult",
    "FileInfo",
    "FileChunkInfo",
    "Embedder",
    "SemanticSearcher",
    "HybridSearcher",
    "LLMReranker",
    "QueryRewriter",
    "ContextAssembler",
    "RAGPipeline",
]
