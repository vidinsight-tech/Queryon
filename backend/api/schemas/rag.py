"""Pydantic schemas for RAG configuration."""
from __future__ import annotations
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class RagConfigSchema(BaseModel):
    """Which LLM and embedding model are wired to the RAG pipeline."""
    llm_id: Optional[UUID] = None
    embedding_model_id: Optional[UUID] = None
