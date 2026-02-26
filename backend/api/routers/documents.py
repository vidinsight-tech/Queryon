"""Documents API: upload files, list, get details, delete from knowledge base."""
from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_session
from backend.core.exceptions import NotFoundError, UnsupportedFileTypeError
from backend.infra.database.repositories.knowledge import (
    DocumentChunkRepository,
    KnowledgeDocumentRepository,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class DocumentResponse(BaseModel):
    id: str
    title: str
    file_name: Optional[str] = None
    source_type: str
    file_size: Optional[int] = None
    embedding_model: Optional[str] = None
    embedding_dimension: Optional[int] = None
    raw_char_count: int = 0
    chunk_count: int = 0
    tags: Optional[List[str]] = None
    language: Optional[str] = None
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DocumentUploadResponse(BaseModel):
    document_id: str
    title: str
    chunk_count: int
    source_type: str
    success: bool
    error: Optional[str] = None


class DocumentUpdateRequest(BaseModel):
    title: Optional[str] = None
    tags: Optional[List[str]] = None
    language: Optional[str] = None
    is_active: Optional[bool] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _doc_response(doc) -> DocumentResponse:
    created = doc.created_at.isoformat() if doc.created_at else None
    updated = doc.updated_at.isoformat() if doc.updated_at else None
    return DocumentResponse(
        id=str(doc.id),
        title=doc.title,
        file_name=doc.file_name,
        source_type=doc.source_type,
        file_size=doc.file_size,
        embedding_model=doc.embedding_model,
        embedding_dimension=doc.embedding_dimension,
        raw_char_count=doc.raw_char_count or 0,
        chunk_count=doc.chunk_count or 0,
        tags=doc.tags,
        language=doc.language,
        is_active=doc.is_active,
        created_at=created,
        updated_at=updated,
    )


def _require_embed_client(request: Request):
    """Only called by upload — list/get/delete/update do NOT need an embedding model."""
    client = getattr(request.app.state, "embed_client", None)
    if client is None:
        raise HTTPException(
            status_code=503,
            detail="No embedding model configured. Go to RAG → Save & Apply first.",
        )
    return client


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[DocumentResponse])
async def list_documents(
    active_only: bool = True,
    skip: int = 0,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    """List all ingested documents. No embedding model required."""
    repo = KnowledgeDocumentRepository(session)
    if active_only:
        docs = await repo.list_active(skip=skip, limit=limit)
    else:
        docs = await repo.get_all(skip=skip, limit=limit)
    return [_doc_response(d) for d in docs]


@router.get("/supported-types")
async def supported_types():
    """Return the list of supported upload file types."""
    from backend.services.file_service import FileService
    return {"types": FileService.supported_types()}


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Get metadata for a single document."""
    repo = KnowledgeDocumentRepository(session)
    doc = await repo.get_by_id(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return _doc_response(doc)


@router.post("", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    language: Optional[str] = Form(None),
    session: AsyncSession = Depends(get_session),
):
    """Upload a file (pdf, docx, doc, txt) and ingest it into the knowledge base.
    Requires an embedding model to be configured via the RAG config page.
    """
    from backend.config.qdrant import QdrantConfig
    from backend.infra.vectorstore.client import QdrantManager
    from backend.services.file_service import FileService

    embed_client = _require_embed_client(request)
    qdrant_cfg = QdrantConfig.from_env()
    qdrant = QdrantManager(qdrant_cfg)
    svc = FileService(session, qdrant, embed_client, qdrant_config=qdrant_cfg)

    file_bytes = await file.read()
    parsed_tags = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    try:
        result = await svc.upload(
            file_bytes,
            filename=file.filename or "upload",
            title=title or None,
            tags=parsed_tags,
            language=language or None,
            content_type=file.content_type,
        )
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error("upload_document failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    if not result.success:
        raise HTTPException(status_code=422, detail=result.error or "Ingestion failed")

    return DocumentUploadResponse(
        document_id=result.document_id,
        title=result.title,
        chunk_count=result.chunk_count,
        source_type=result.source_type,
        success=result.success,
        error=result.error,
    )


@router.patch("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: uuid.UUID,
    body: DocumentUpdateRequest,
    session: AsyncSession = Depends(get_session),
):
    """Update document metadata (title, tags, language, is_active)."""
    repo = KnowledgeDocumentRepository(session)
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        doc = await repo.get_by_id(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return _doc_response(doc)
    doc = await repo.update(document_id, updates)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    await session.commit()
    return _doc_response(doc)


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
):
    """Delete a document and its vectors from the knowledge base."""
    from backend.config.qdrant import QdrantConfig
    from backend.infra.vectorstore.client import QdrantManager

    chunk_repo = DocumentChunkRepository(session)
    doc_repo = KnowledgeDocumentRepository(session)

    chunks = await chunk_repo.get_by_document(document_id)
    if chunks:
        vector_ids = [c.vector_id for c in chunks]
        try:
            qdrant_cfg = QdrantConfig.from_env()
            qdrant = QdrantManager(qdrant_cfg)
            collection = qdrant_cfg.collection_name
            await qdrant.delete_points(collection, vector_ids)
        except Exception as exc:
            logger.warning("delete_document: Qdrant delete failed (continuing): %s", exc)

    deleted = await doc_repo.delete(document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    await session.commit()
