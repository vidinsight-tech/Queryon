"""Chat router: send messages, manage conversations."""
from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_session
from backend.api.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationCreateRequest,
    ConversationHistoryResponse,
    ConversationListItem,
    ConversationResponse,
    MessageSchema,
    SourceSchema,
)
from backend.services.conversation_service import ConversationService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["chat"])
limiter = Limiter(key_func=get_remote_address)


def _build_orchestrator(request: Request):
    """Access the pre-built orchestrator from app.state."""
    orch = getattr(request.app.state, "orchestrator", None)
    if orch is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Orchestrator not initialised. Check server startup logs.",
        )
    return orch


@router.get("/conversations", response_model=List[ConversationListItem])
async def list_conversations(
    status: Optional[str] = None,
    limit: int = 100,
    skip: int = 0,
    session: AsyncSession = Depends(get_session),
):
    """List recent conversations for the admin panel, ordered by last activity."""
    svc = ConversationService(session)
    convs = await svc.list_recent(status=status, limit=limit, skip=skip)
    return [
        ConversationListItem(
            conversation_id=c.id,
            platform=c.platform,
            status=c.status,
            message_count=c.message_count or 0,
            contact_name=c.contact_name,
            contact_phone=c.contact_phone,
            contact_email=c.contact_email,
            last_message_at=c.last_message_at,
            created_at=c.created_at,
        )
        for c in convs
    ]


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    body: ConversationCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    svc = ConversationService(session)
    conv = await svc.start_conversation(
        platform=body.platform,
        contact_name=body.contact_name,
        contact_email=body.contact_email,
        contact_phone=body.contact_phone,
    )
    return ConversationResponse(conversation_id=conv.id)


@router.post("", response_model=ChatResponse)
@limiter.limit("30/minute")
async def chat(
    request: Request,
    body: ChatRequest,
    session: AsyncSession = Depends(get_session),
):
    orch = _build_orchestrator(request)

    # Create a conversation if none provided, or if the given ID no longer exists.
    # Must commit before calling process_with_tracking — it opens its own session
    # and the new conversation row must be visible to that independent connection.
    svc = ConversationService(session)
    if body.conversation_id is None:
        conv = await svc.start_conversation(platform="web")
        await session.commit()
        conversation_id = conv.id
    else:
        existing = await svc.get_conversation(body.conversation_id)
        if existing is None:
            conv = await svc.start_conversation(platform="web")
            await session.commit()
            conversation_id = conv.id
        else:
            conversation_id = body.conversation_id

    try:
        result = await orch.process_with_tracking(body.query, conversation_id)
    except Exception as exc:
        logger.error("chat: orchestrator error: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))

    sources: List[SourceSchema] = []
    for s in result.sources or []:
        if isinstance(s, dict):
            sources.append(SourceSchema(**{k: v for k, v in s.items() if k in SourceSchema.model_fields}))
        else:
            sources.append(
                SourceSchema(
                    title=getattr(s, "title", None),
                    content=getattr(s, "content", None),
                    score=getattr(s, "score", None),
                    document_id=getattr(s, "document_id", None),
                    chunk_index=getattr(s, "chunk_index", None),
                )
            )

    return ChatResponse(
        answer=result.answer or "",
        intent=result.intent.value if result.intent else "direct",
        confidence=result.classification.confidence if result.classification else None,
        classifier_layer=result.classification.classifier_layer if result.classification else None,
        rule_matched=result.rule_matched,
        tool_called=result.tool_called,
        fallback_used=result.fallback_used,
        fallback_from_intent=result.fallback_from_intent,
        needs_clarification=result.needs_clarification,
        sources=sources,
        total_ms=result.metrics.total_ms if result.metrics else None,
        conversation_id=conversation_id,
        thinking=result.classification.thinking if result.classification else None,
        reasoning=result.classification.reasoning if result.classification else None,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationHistoryResponse)
async def get_conversation_history(
    conversation_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    svc = ConversationService(session)
    conv = await svc.get_conversation(conversation_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = [
        MessageSchema(
            id=m.id,
            role=m.role,
            content=m.content,
            intent=m.intent,
            confidence=m.confidence,
            classifier_layer=m.classifier_layer,
            rule_matched=m.rule_matched,
            tool_called=(m.extra_metadata or {}).get("tool_called"),
            fallback_used=m.fallback_used,
            total_ms=m.total_ms,
            thinking=(m.extra_metadata or {}).get("thinking"),
            reasoning=(m.extra_metadata or {}).get("reasoning"),
            created_at=m.created_at,
        )
        for m in (conv.messages or [])
    ]
    return ConversationHistoryResponse(
        conversation_id=conversation_id,
        messages=messages,
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
async def close_conversation(
    conversation_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    svc = ConversationService(session)
    ok = await svc.close_conversation(conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Conversation not found")
