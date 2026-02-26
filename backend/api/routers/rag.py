"""RAG configuration router: connect LLM + embedding model to the RAG pipeline."""
from __future__ import annotations

import logging
import os
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_session
from backend.api.schemas.rag import RagConfigSchema
from backend.infra.database.models.tool_config import RagConfigModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rag", tags=["rag"])


async def _load_rag_config(session: AsyncSession) -> RagConfigModel:
    result = await session.execute(select(RagConfigModel).where(RagConfigModel.id == 1))
    row = result.scalar_one_or_none()
    if row is None:
        row = RagConfigModel(id=1, llm_id=None, embedding_model_id=None)
    return row


async def _rebuild_rag_service(
    request: Request,
    llm_id: Optional[UUID],
    embedding_model_id: Optional[UUID],
    session: AsyncSession,
) -> None:
    """Build a new RAGService from the given LLM + embedding model IDs and reload the orchestrator."""
    try:
        from backend.config.qdrant import QdrantConfig
        from backend.infra.vectorstore.client import QdrantManager
        from backend.services.rag_service import RAGService
        from backend.services.llm_service import LLMService
        from backend.services.embedding_model_service import EmbeddingModelService

        # Get embedding client
        if embedding_model_id is None:
            logger.info("RAG config: no embedding model set, RAG service disabled")
            request.app.state.rag_service = None
            orch = getattr(request.app.state, "orchestrator", None)
            if orch is not None:
                orch.reload_rag(None)
            return

        embed_client = await EmbeddingModelService(session).get_client(embedding_model_id)
        if embed_client is None:
            raise HTTPException(status_code=400, detail="Embedding model not found or provider unknown")
        request.app.state.embed_client = embed_client

        # Get LLM client (use specified or fall back to app.state.llm_client)
        if llm_id is not None:
            llm_client = await LLMService(session).get_client(llm_id)
            if llm_client is None:
                raise HTTPException(status_code=400, detail="LLM not found or provider unknown")
        else:
            llm_client = getattr(request.app.state, "llm_client", None)

        if llm_client is None or getattr(llm_client, "provider", "") == "noop":
            raise HTTPException(status_code=400, detail="No active LLM configured. Add an LLM first.")

        qdrant_cfg = QdrantConfig.from_env()
        qdrant = QdrantManager(qdrant_cfg)
        rag_service = RAGService(qdrant, embed_client, llm_client, qdrant_config=qdrant_cfg)

        request.app.state.rag_service = rag_service
        orch = getattr(request.app.state, "orchestrator", None)
        if orch is not None:
            orch.reload_rag(rag_service)

        logger.info("RAG service rebuilt: embedding_model_id=%s llm_id=%s", embedding_model_id, llm_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("RAG rebuild failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"RAG rebuild failed: {exc}")


@router.get("/config", response_model=RagConfigSchema)
async def get_rag_config(session: AsyncSession = Depends(get_session)):
    """Get the active RAG configuration."""
    row = await _load_rag_config(session)
    return RagConfigSchema(llm_id=row.llm_id, embedding_model_id=row.embedding_model_id)


@router.put("/config", response_model=RagConfigSchema)
async def update_rag_config(
    body: RagConfigSchema,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Update RAG configuration and immediately rebuild the RAG pipeline."""
    result = await session.execute(select(RagConfigModel).where(RagConfigModel.id == 1))
    row = result.scalar_one_or_none()
    if row is None:
        row = RagConfigModel(id=1, llm_id=body.llm_id, embedding_model_id=body.embedding_model_id)
        session.add(row)
    else:
        row.llm_id = body.llm_id
        row.embedding_model_id = body.embedding_model_id
    await session.flush()
    await _rebuild_rag_service(request, body.llm_id, body.embedding_model_id, session)
    return RagConfigSchema(llm_id=row.llm_id, embedding_model_id=row.embedding_model_id)
