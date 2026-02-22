"""
backend.infra.database – PostgreSQL async engine, session, models and repositories.

Public API
──────────
  build_engine, build_session_factory, get_db, init_db, close_engine
  Base, LLM, Embedding, KnowledgeDocument, DocumentChunk (models)
  BaseRepository, LLMRepository, EmbeddingRepository,
  KnowledgeDocumentRepository, DocumentChunkRepository
"""
from backend.infra.database.engine import (
    build_engine,
    build_session_factory,
    close_engine,
    get_db,
    init_db,
)
from backend.infra.database.models import (
    Base,
    DocumentChunk,
    Embedding,
    KnowledgeDocument,
    LLM,
)
from backend.infra.database.repositories import (
    BaseRepository,
    DocumentChunkRepository,
    EmbeddingRepository,
    KnowledgeDocumentRepository,
    LLMRepository,
)

__all__ = [
    "build_engine",
    "build_session_factory",
    "get_db",
    "init_db",
    "close_engine",
    "Base",
    "LLM",
    "Embedding",
    "KnowledgeDocument",
    "DocumentChunk",
    "BaseRepository",
    "LLMRepository",
    "EmbeddingRepository",
    "KnowledgeDocumentRepository",
    "DocumentChunkRepository",
]