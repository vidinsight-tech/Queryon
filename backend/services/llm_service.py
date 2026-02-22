"""LLM + database: get client by id, create, delete."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from uuid import UUID

from backend.clients.llm.registry import LLMRegistry, default_registry
from backend.infra.database.repositories import LLMRepository

if TYPE_CHECKING:
    from backend.clients.llm.base import BaseLLMClient
    from backend.infra.database.models import LLM
    from sqlalchemy.ext.asyncio import AsyncSession


class LLMService:
    """LLM kayıtları ve client üretimi. Session + registry kullanır."""

    def __init__(
        self,
        session: "AsyncSession",
        registry: Optional[LLMRegistry] = None,
    ) -> None:
        self._session = session
        self._repo = LLMRepository(session)
        self._registry = registry if registry is not None else default_registry

    async def get_client(self, llm_id: UUID) -> Optional[BaseLLMClient]:
        """DB'den LLM kaydını alır, ilgili client'ı döner. Yoksa None."""
        llm = await self._repo.get_by_id(llm_id)
        if llm is None:
            return None
        return self._registry.build(llm.provider, dict(llm.config))

    async def create(
        self,
        name: str,
        provider: str,
        config: dict,
        *,
        is_active: bool = True,
    ) -> LLM:
        """Yeni LLM kaydı oluşturur. config örn. LLMConfig.to_dict()."""
        return await self._repo.create_llm(name, provider, config, is_active=is_active)

    async def delete(self, llm_id: UUID) -> bool:
        """LLM kaydını siler. Silindi mi True/False."""
        return await self._repo.delete_llm(llm_id)
