"""FileService: API-facing document lifecycle management.

Handles file upload (bytes), parsing, chunking, embedding, storage (PG + Qdrant),
listing, detail view, and deletion.

The embedding model identity is recorded on every document so the system can
detect model mismatches later.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from backend.core.exceptions import NotFoundError, UnsupportedFileTypeError, ValidationError
from backend.infra.database.repositories.knowledge import (
    DocumentChunkRepository,
    KnowledgeDocumentRepository,
)
from backend.infra.vectorstore.collections import build_chunk_payload, ensure_collection_exists
from backend.rag.embedder import Embedder
from backend.rag.service import RAGDocService
from backend.rag.types import FileChunkInfo, FileInfo, IngestionResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from backend.clients.embedding import BaseEmbeddingClient
    from backend.config import QdrantConfig
    from backend.infra.database.models.knowledge import KnowledgeDocument
    from backend.infra.vectorstore.client import QdrantManager

logger = logging.getLogger(__name__)

_MIME_MAP: Dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "txt": "text/plain",
}

_ALLOWED_EXTENSIONS = frozenset(RAGDocService.supported_extensions())


class FileService:
    """Manage document files: upload, list, get, delete.

    The ``embedding_client`` is validated against ``qdrant_config.vector_size``
    at construction time.  Its ``model_name`` and ``dimension`` are stored on
    every ingested document so the system can enforce model consistency.

    Usage::

        svc = FileService(session, qdrant, embedding_client, qdrant_config=cfg)
        result = await svc.upload(file_bytes, filename="report.pdf", title="Q4")
        files  = await svc.list_files()
        info   = await svc.get_file(doc_id)
        ok     = await svc.delete_file(doc_id)
    """

    def __init__(
        self,
        session: "AsyncSession",
        qdrant: "QdrantManager",
        embedding_client: "BaseEmbeddingClient",
        *,
        qdrant_config: Optional["QdrantConfig"] = None,
        doc_service: Optional[RAGDocService] = None,
        embedder_batch_size: int = 64,
        embedder_normalize: bool = True,
    ) -> None:
        self._session = session
        self._qdrant = qdrant
        self._qdrant_config = qdrant_config
        self._doc_repo = KnowledgeDocumentRepository(session)
        self._chunk_repo = DocumentChunkRepository(session)
        self._doc_svc = doc_service or RAGDocService()

        expected_dim = qdrant_config.vector_size if qdrant_config else None
        self._embedder = Embedder(
            embedding_client,
            batch_size=embedder_batch_size,
            normalize=embedder_normalize,
            expected_dimension=expected_dim,
        )
        self._collection: Optional[str] = None

    async def _ensure_collection(self) -> str:
        if self._collection is None:
            self._collection = await ensure_collection_exists(self._qdrant, self._qdrant_config)
        return self._collection

    # ── Upload ──

    async def upload(
        self,
        file_bytes: bytes,
        filename: str,
        *,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
        language: Optional[str] = None,
        content_type: Optional[str] = None,
        chunk_method: str = "token",
        meta: Optional[Dict[str, Any]] = None,
        **chunk_kwargs: object,
    ) -> IngestionResult:
        """Accept raw file bytes from an API upload and process end-to-end.

        Steps: validate → parse → chunk → embed → store (PG + Qdrant).
        The embedding model name and dimension are saved on the document record.
        """
        ext = self._validate_extension(filename)
        resolved_title = title or Path(filename).stem
        resolved_ct = content_type or _MIME_MAP.get(ext, "application/octet-stream")
        file_size = len(file_bytes)
        collection = await self._ensure_collection()

        try:
            parsed = self._doc_svc.parse(file_bytes, filename_hint=filename)
        except Exception as exc:
            logger.error("FileService.upload: parse failed file=%s: %s", filename, exc)
            return IngestionResult(
                document_id="",
                title=resolved_title,
                chunk_count=0,
                source_type=ext,
                success=False,
                error=str(exc),
            )

        chunks = self._doc_svc.chunk(parsed, method=chunk_method, **chunk_kwargs)
        if not chunks:
            return IngestionResult(
                document_id="",
                title=resolved_title,
                chunk_count=0,
                source_type=parsed.source_type,
                success=False,
                error="No chunks produced from file content.",
            )

        doc_record = await self._doc_repo.create({
            "title": resolved_title,
            "source_type": parsed.source_type,
            "file_name": filename,
            "file_size": file_size,
            "content_type": resolved_ct,
            "embedding_model": self._embedder.model_name,
            "embedding_dimension": self._embedder.dimension,
            "raw_char_count": len(parsed.text),
            "chunk_count": len(chunks),
            "tags": tags,
            "language": language,
            "meta": meta,
        })
        doc_id = doc_record.id

        texts = [c.content for c in chunks]
        vectors = await self._embedder.embed_texts(texts)

        from qdrant_client.models import PointStruct

        points: List[PointStruct] = []
        db_chunk_records: List[dict] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        for idx, (chunk, vector) in enumerate(zip(chunks, vectors)):
            vector_id = str(uuid.uuid4())
            chunk_db_id = uuid.uuid4()
            db_chunk_records.append({
                "id": chunk_db_id,
                "document_id": doc_id,
                "chunk_index": idx,
                "content": chunk.content,
                "token_count": chunk.token_count or None,
                "vector_id": vector_id,
            })
            payload = build_chunk_payload(
                document_id=doc_id,
                chunk_id=chunk_db_id,
                chunk_index=idx,
                content=chunk.content,
                title=resolved_title,
                source_type=parsed.source_type,
                created_at=now_iso,
                tags=tags,
                language=language,
                token_count=chunk.token_count or None,
            )
            points.append(PointStruct(id=vector_id, vector=vector, payload=payload))

        await self._chunk_repo.bulk_create(db_chunk_records)
        await self._qdrant.upsert_points(collection, points)
        await self._session.commit()

        logger.info("FileService: uploaded file='%s' doc_id=%s model=%s chunks=%d", filename, doc_id, self._embedder.model_name, len(chunks))
        return IngestionResult(
            document_id=str(doc_id),
            title=resolved_title,
            chunk_count=len(chunks),
            source_type=parsed.source_type,
        )

    # ── List ──

    async def list_files(
        self,
        *,
        active_only: bool = True,
        skip: int = 0,
        limit: int = 50,
    ) -> List[FileInfo]:
        """Return a paginated list of documents."""
        if active_only:
            docs = await self._doc_repo.list_active(skip=skip, limit=limit)
        else:
            docs = await self._doc_repo.get_all(skip=skip, limit=limit)
        return [self._to_file_info(d) for d in docs]

    async def search_files(self, query: str, *, limit: int = 20) -> List[FileInfo]:
        """Search documents by title (case-insensitive LIKE)."""
        docs = await self._doc_repo.search_by_title(query, limit=limit)
        return [self._to_file_info(d) for d in docs]

    # ── Get ──

    async def get_file(self, document_id: uuid.UUID) -> FileInfo:
        """Return document metadata. Raises NotFoundError if absent."""
        doc = await self._doc_repo.get_by_id(document_id)
        if doc is None:
            raise NotFoundError(f"Document {document_id} not found.")
        return self._to_file_info(doc)

    async def get_file_with_chunks(
        self,
        document_id: uuid.UUID,
    ) -> tuple[FileInfo, List[FileChunkInfo]]:
        """Return document metadata together with all its chunks."""
        doc = await self._doc_repo.get_with_chunks(document_id)
        if doc is None:
            raise NotFoundError(f"Document {document_id} not found.")
        file_info = self._to_file_info(doc)
        chunk_infos = [
            FileChunkInfo(
                id=str(c.id),
                document_id=str(c.document_id),
                chunk_index=c.chunk_index,
                content=c.content,
                token_count=c.token_count,
                vector_id=c.vector_id,
            )
            for c in sorted(doc.chunks, key=lambda c: c.chunk_index)
        ]
        return file_info, chunk_infos

    # ── Delete ──

    async def delete_file(self, document_id: uuid.UUID) -> bool:
        """Delete a document and its chunks from PG and Qdrant."""
        db_chunks = await self._chunk_repo.get_by_document(document_id)
        if db_chunks:
            vector_ids = [c.vector_id for c in db_chunks]
            collection = await self._ensure_collection()
            await self._qdrant.delete_points(collection, vector_ids)

        deleted = await self._doc_repo.delete(document_id)
        if deleted:
            await self._session.commit()
            logger.info("FileService: deleted doc_id=%s (%d vectors removed)", document_id, len(db_chunks))
        return deleted

    # ── Update metadata ──

    async def update_file(
        self,
        document_id: uuid.UUID,
        *,
        title: Optional[str] = None,
        tags: Optional[List[str]] = None,
        language: Optional[str] = None,
        is_active: Optional[bool] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> FileInfo:
        """Update editable metadata fields of a document."""
        updates: Dict[str, Any] = {}
        if title is not None:
            updates["title"] = title
        if tags is not None:
            updates["tags"] = tags
        if language is not None:
            updates["language"] = language
        if is_active is not None:
            updates["is_active"] = is_active
        if meta is not None:
            updates["meta"] = meta
        if not updates:
            raise ValidationError("No fields provided for update.")

        doc = await self._doc_repo.update(document_id, updates)
        if doc is None:
            raise NotFoundError(f"Document {document_id} not found.")
        await self._session.commit()
        return self._to_file_info(doc)

    # ── Helpers ──

    @staticmethod
    def _validate_extension(filename: str) -> str:
        ext = Path(filename).suffix.lstrip(".").lower()
        if not ext:
            raise UnsupportedFileTypeError(f"No file extension found in '{filename}'.")
        if ext not in _ALLOWED_EXTENSIONS:
            raise UnsupportedFileTypeError(
                f"File type '.{ext}' is not supported. Allowed: {', '.join(sorted(_ALLOWED_EXTENSIONS))}",
            )
        return ext

    @staticmethod
    def _to_file_info(doc: "KnowledgeDocument") -> FileInfo:
        created = doc.created_at.isoformat() if doc.created_at else None
        updated = doc.updated_at.isoformat() if doc.updated_at else None
        return FileInfo(
            id=str(doc.id),
            title=doc.title,
            file_name=doc.file_name,
            source_type=doc.source_type,
            file_size=doc.file_size,
            content_type=doc.content_type,
            embedding_model=doc.embedding_model,
            embedding_dimension=doc.embedding_dimension,
            raw_char_count=doc.raw_char_count,
            chunk_count=doc.chunk_count,
            tags=doc.tags,
            language=doc.language,
            is_active=doc.is_active,
            created_at=created,
            updated_at=updated,
        )

    @staticmethod
    def supported_types() -> List[str]:
        """Return the list of accepted file extensions."""
        return sorted(_ALLOWED_EXTENSIONS)
