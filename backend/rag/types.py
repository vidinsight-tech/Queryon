"""Common data structures for the RAG pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ParsedContent:
    """Parser output: single text + metadata."""

    text: str
    source_type: str  # pdf, docx, doc, txt
    metadata: dict = field(default_factory=dict)


@dataclass
class Chunk:
    """Splitter output: one piece of text with index and counts."""

    content: str
    chunk_index: int
    token_count: int = 0
    char_count: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class SearchResult:
    """A single vector search hit enriched with metadata."""

    chunk_id: str
    document_id: str
    content: str
    score: float
    chunk_index: int = 0
    title: str = ""
    source_type: str = ""
    token_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AssembledContext:
    """Output of the ContextAssembler: a ready-to-use prompt context."""

    text: str
    sources: List[SearchResult] = field(default_factory=list)
    total_tokens: int = 0
    truncated: bool = False


@dataclass
class PipelineConfig:
    """Runtime config passed to the RAG pipeline."""

    top_k: int = 10
    score_threshold: float = 0.0  # 0 = accept all; filter by score disabled
    max_context_tokens: int = 3000
    rerank: bool = True
    rewrite_query: bool = True
    hybrid_search: bool = True
    hybrid_keyword_weight: float = 0.3


@dataclass
class PipelineResult:
    """Full result from a RAG pipeline run (retrieval + assembly)."""

    query: str
    rewritten_query: Optional[str] = None
    context: Optional[AssembledContext] = None
    results: List[SearchResult] = field(default_factory=list)
    answer: Optional[str] = None


@dataclass
class IngestionResult:
    """Summary of an ingestion operation."""

    document_id: str
    title: str
    chunk_count: int
    source_type: str
    success: bool = True
    error: Optional[str] = None


@dataclass
class FileInfo:
    """Read-only snapshot of a stored document."""

    id: str
    title: str
    file_name: Optional[str]
    source_type: str
    file_size: Optional[int]
    content_type: Optional[str]
    embedding_model: Optional[str]
    embedding_dimension: Optional[int]
    raw_char_count: int
    chunk_count: int
    tags: Optional[List[str]]
    language: Optional[str]
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class FileChunkInfo:
    """Read-only view of a single stored chunk."""

    id: str
    document_id: str
    chunk_index: int
    content: str
    token_count: Optional[int]
    vector_id: str
