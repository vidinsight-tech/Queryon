"""Generic async repository for SQLAlchemy 2.0."""
from __future__ import annotations

from typing import Any, ClassVar, Generic, List, Optional, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    model: ClassVar[type]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, id: UUID) -> Optional[ModelT]:
        return await self.session.get(self.model, id)  # type: ignore[return-value]

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[ModelT]:
        stmt = select(self.model).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())  # type: ignore[return-value]

    async def exists(self, id: UUID) -> bool:
        from sqlalchemy import literal_column
        pk_col = list(self.model.__table__.primary_key.columns)[0]
        stmt = select(literal_column("1")).where(pk_col == id).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar() is not None

    async def count(self) -> int:
        from sqlalchemy import func
        stmt = select(func.count()).select_from(self.model)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def create(self, data: dict[str, Any]) -> ModelT:
        instance = self.model(**data)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance  # type: ignore[return-value]

    async def update(self, id: UUID, data: dict[str, Any]) -> Optional[ModelT]:
        instance = await self.get_by_id(id)
        if instance is None:
            return None
        for attr, value in data.items():
            setattr(instance, attr, value)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance  # type: ignore[return-value]

    async def upsert(self, lookup: dict[str, Any], defaults: dict[str, Any]) -> tuple[ModelT, bool]:
        from sqlalchemy import and_
        model_cls = self.model
        conditions = [getattr(model_cls, k) == v for k, v in lookup.items()]
        stmt = select(model_cls).where(and_(*conditions)).limit(1)
        result = await self.session.execute(stmt)
        instance = result.scalar_one_or_none()
        if instance is not None:
            return instance, False  # type: ignore[return-value]
        instance = await self.create({**lookup, **defaults})
        return instance, True  # type: ignore[return-value]

    async def delete(self, id: UUID) -> bool:
        instance = await self.get_by_id(id)
        if instance is None:
            return False
        await self.session.delete(instance)
        await self.session.flush()
        return True

    async def bulk_create(self, items: List[dict[str, Any]]) -> List[ModelT]:
        instances = [self.model(**d) for d in items]
        self.session.add_all(instances)
        await self.session.flush()
        for inst in instances:
            await self.session.refresh(inst)
        return instances  # type: ignore[return-value]
