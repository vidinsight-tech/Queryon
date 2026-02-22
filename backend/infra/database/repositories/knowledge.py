"""Repositories for KnowledgeDocument and DocumentChunk."""
from __future__ import annotations

from typing import ClassVar, List, Optional
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.infra.database.models.knowledge import DocumentChunk, KnowledgeDocument
from backend.infra.database.repositories.base import BaseRepository


class KnowledgeDocumentRepository(BaseRepository[KnowledgeDocument]):
    model: ClassVar[type] = KnowledgeDocument

    async def list_active(self, skip: int = 0, limit: int = 100) -> List[KnowledgeDocument]:
        stmt = (
            select(KnowledgeDocument)
            .where(KnowledgeDocument.is_active.is_(True))
            .offset(skip)
            .limit(limit)
            .order_by(KnowledgeDocument.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_with_chunks(self, doc_id: UUID) -> Optional[KnowledgeDocument]:
        stmt = (
            select(KnowledgeDocument)
            .where(KnowledgeDocument.id == doc_id)
            .options(selectinload(KnowledgeDocument.chunks))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def set_active(self, doc_id: UUID, active: bool) -> bool:
        stmt = (
            update(KnowledgeDocument)
            .where(KnowledgeDocument.id == doc_id)
            .values(is_active=active)
        )
        result = await self.session.execute(stmt)
        return (result.rowcount or 0) > 0

    async def search_by_title(self, query: str, limit: int = 20) -> List[KnowledgeDocument]:
        stmt = (
            select(KnowledgeDocument)
            .where(KnowledgeDocument.title.ilike(f"%{query}%"))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class DocumentChunkRepository(BaseRepository[DocumentChunk]):
    model: ClassVar[type] = DocumentChunk

    async def get_by_document(self, document_id: UUID) -> List[DocumentChunk]:
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_vector_ids(self, vector_ids: List[str]) -> List[DocumentChunk]:
        if not vector_ids:
            return []
        stmt = select(DocumentChunk).where(DocumentChunk.vector_id.in_(vector_ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_document(self, document_id: UUID) -> int:
        stmt = delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        result = await self.session.execute(stmt)
        return result.rowcount or 0

    async def count_by_document(self, document_id: UUID) -> int:
        from sqlalchemy import func
        stmt = (
            select(func.count())
            .select_from(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
