"""LLM CRUD API: list, create, update, delete user-configured LLMs.

No LLM is required at startup. Add one here and it takes effect immediately (no restart).
Active LLMs are hot-reloaded into the running orchestrator and all handlers.
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.api.dependencies import get_session
from backend.api.schemas.llm import LLMCreateSchema, LLMResponseSchema, LLMUpdateSchema
from backend.infra.database.repositories import LLMRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llms", tags=["llms"])


async def _hot_reload_if_active(request: Request, llm, session) -> None:
    """If the LLM is active, rebuild the client and push it into the live orchestrator."""
    if not llm.is_active:
        return
    try:
        from backend.services.llm_service import LLMService
        client = await LLMService(session).get_client(llm.id)
        if client is None:
            return
        request.app.state.llm_client = client
        orch = getattr(request.app.state, "orchestrator", None)
        if orch is not None:
            orch.reload_llm(client)
        logger.info("LLM hot-reloaded: name=%s provider=%s", llm.name, llm.provider)
    except Exception as exc:
        logger.warning("LLM hot-reload failed (non-fatal): %s", exc)


def _to_response(llm) -> LLMResponseSchema:
    return LLMResponseSchema(
        id=llm.id,
        name=llm.name,
        provider=llm.provider,
        config=llm.config or {},
        is_active=llm.is_active,
        created_at=llm.created_at,
        updated_at=llm.updated_at,
    )


@router.get("", response_model=List[LLMResponseSchema])
async def list_llms(
    active_only: bool = False,
    provider: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    session=Depends(get_session),
):
    """List LLMs. Use active_only=true to see only those used when no env key is set."""
    repo = LLMRepository(session)
    items = await repo.list_all(active_only=active_only, provider=provider, skip=skip, limit=limit)
    return [_to_response(llm) for llm in items]


@router.get("/{llm_id}", response_model=LLMResponseSchema)
async def get_llm(llm_id: UUID, session=Depends(get_session)):
    """Get a single LLM by id."""
    repo = LLMRepository(session)
    llm = await repo.get_by_id(llm_id)
    if llm is None:
        raise HTTPException(status_code=404, detail="LLM not found")
    return _to_response(llm)


@router.post("", response_model=LLMResponseSchema, status_code=201)
async def create_llm(body: LLMCreateSchema, request: Request, session=Depends(get_session)):
    """Create a new LLM (provider + config with api_key). Takes effect immediately if is_active=true."""
    repo = LLMRepository(session)
    llm = await repo.create_llm(
        name=body.name,
        provider=body.provider,
        config=body.config,
        is_active=body.is_active,
    )
    await _hot_reload_if_active(request, llm, session)
    return _to_response(llm)


@router.patch("/{llm_id}", response_model=LLMResponseSchema)
async def update_llm(llm_id: UUID, body: LLMUpdateSchema, request: Request, session=Depends(get_session)):
    """Update an LLM (name, provider, config, is_active). Only provided fields are updated. Takes effect immediately."""
    repo = LLMRepository(session)
    llm = await repo.get_by_id(llm_id)
    if llm is None:
        raise HTTPException(status_code=404, detail="LLM not found")
    data = body.model_dump(exclude_unset=True)
    if data:
        updated = await repo.update(llm_id, data)
        await _hot_reload_if_active(request, updated, session)
        return _to_response(updated)
    return _to_response(llm)


@router.delete("/{llm_id}", status_code=204)
async def delete_llm(llm_id: UUID, session=Depends(get_session)):
    """Delete an LLM. Restart backend if this was the active default."""
    repo = LLMRepository(session)
    ok = await repo.delete_llm(llm_id)
    if not ok:
        raise HTTPException(status_code=404, detail="LLM not found")
