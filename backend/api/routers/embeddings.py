"""Embedding model CRUD API: list, create, update, delete user-configured embedding models.

No embedding model is required at startup. Add one here and it takes effect immediately (no restart).
Active embedding models can be wired to the RAG pipeline via the /rag/config endpoint.
"""
from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.api.dependencies import get_session
from backend.api.schemas.embedding_model import (
    EmbeddingModelCreateSchema,
    EmbeddingModelResponseSchema,
    EmbeddingModelUpdateSchema,
)
from backend.infra.database.repositories.embedding_model_config import EmbeddingModelConfigRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/embeddings", tags=["embeddings"])


async def _hot_reload_if_active(request: Request, embedding_model, session) -> None:
    """If the embedding model is active, log the activation. RAG rebuild is done via PUT /rag/config."""
    if not embedding_model.is_active:
        return
    logger.info(
        "Embedding model activated: name=%s provider=%s — use PUT /api/v1/rag/config to wire it to RAG",
        embedding_model.name,
        embedding_model.provider,
    )


def _to_response(embedding_model) -> EmbeddingModelResponseSchema:
    return EmbeddingModelResponseSchema(
        id=embedding_model.id,
        name=embedding_model.name,
        provider=embedding_model.provider,
        config=embedding_model.config or {},
        is_active=embedding_model.is_active,
        created_at=embedding_model.created_at,
        updated_at=embedding_model.updated_at,
    )


@router.get("", response_model=List[EmbeddingModelResponseSchema])
async def list_embedding_models(
    active_only: bool = False,
    provider: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    session=Depends(get_session),
):
    """List embedding models. Use active_only=true to filter active ones."""
    repo = EmbeddingModelConfigRepository(session)
    items = await repo.list_all(active_only=active_only, provider=provider, skip=skip, limit=limit)
    return [_to_response(item) for item in items]


@router.get("/{embedding_model_id}", response_model=EmbeddingModelResponseSchema)
async def get_embedding_model(embedding_model_id: UUID, session=Depends(get_session)):
    """Get a single embedding model by id."""
    repo = EmbeddingModelConfigRepository(session)
    item = await repo.get_by_id(embedding_model_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Embedding model not found")
    return _to_response(item)


@router.post("", response_model=EmbeddingModelResponseSchema, status_code=201)
async def create_embedding_model(
    body: EmbeddingModelCreateSchema,
    request: Request,
    session=Depends(get_session),
):
    """Create a new embedding model (provider + config with api_key). Takes effect when wired to RAG."""
    repo = EmbeddingModelConfigRepository(session)
    item = await repo.create_embedding_model(
        name=body.name,
        provider=body.provider,
        config=body.config,
        is_active=body.is_active,
    )
    await _hot_reload_if_active(request, item, session)
    return _to_response(item)


@router.patch("/{embedding_model_id}", response_model=EmbeddingModelResponseSchema)
async def update_embedding_model(
    embedding_model_id: UUID,
    body: EmbeddingModelUpdateSchema,
    request: Request,
    session=Depends(get_session),
):
    """Update an embedding model (name, provider, config, is_active). Only provided fields are updated."""
    repo = EmbeddingModelConfigRepository(session)
    item = await repo.get_by_id(embedding_model_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Embedding model not found")
    data = body.model_dump(exclude_unset=True)
    if data:
        updated = await repo.update(embedding_model_id, data)
        await _hot_reload_if_active(request, updated, session)
        return _to_response(updated)
    return _to_response(item)


@router.delete("/{embedding_model_id}", status_code=204)
async def delete_embedding_model(embedding_model_id: UUID, session=Depends(get_session)):
    """Delete an embedding model. Update RAG config if this was the active embedding model."""
    repo = EmbeddingModelConfigRepository(session)
    ok = await repo.delete_embedding_model(embedding_model_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Embedding model not found")
