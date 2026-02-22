"""Qdrant vector store for RAG."""
from backend.infra.vectorstore.client import QdrantManager, close_qdrant_manager, get_qdrant_manager
from backend.infra.vectorstore.collections import (
    KNOWLEDGE_BASE_COLLECTION,
    PayloadField,
    build_chunk_payload,
    ensure_collection_exists,
)
from backend.infra.vectorstore.query import extract_chunk_ids, extract_content, search_chunks

__all__ = [
    "QdrantManager",
    "get_qdrant_manager",
    "close_qdrant_manager",
    "KNOWLEDGE_BASE_COLLECTION",
    "ensure_collection_exists",
    "build_chunk_payload",
    "PayloadField",
    "search_chunks",
    "extract_chunk_ids",
    "extract_content",
]
