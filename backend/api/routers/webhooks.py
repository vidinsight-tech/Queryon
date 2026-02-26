"""Public webhook endpoints for Telegram and WhatsApp.

These routes live under /webhooks/ (NOT /api/v1/) so they are intentionally
excluded from the admin API-key middleware — Telegram and WhatsApp do not know
our internal admin key.

Processing is offloaded to an asyncio background task so both handlers return
HTTP 200 immediately, satisfying:
  - WhatsApp: must ack within 20 s
  - Telegram: must ack within 60 s
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from backend.services.conversation_service import ConversationService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# ── Credential helpers — env vars take priority, DB config is fallback ────────

def _telegram_token(request: Optional[Request] = None) -> Optional[str]:
    val = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if val:
        return val
    if request is not None:
        cfg = getattr(request.app.state, "channel_configs", {})
        return cfg.get("telegram", {}).get("token") or None
    return None

def _whatsapp_token(request: Optional[Request] = None) -> Optional[str]:
    val = os.environ.get("WHATSAPP_ACCESS_TOKEN", "").strip()
    if val:
        return val
    if request is not None:
        cfg = getattr(request.app.state, "channel_configs", {})
        return cfg.get("whatsapp", {}).get("access_token") or None
    return None

def _whatsapp_phone_id(request: Optional[Request] = None) -> Optional[str]:
    val = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    if val:
        return val
    if request is not None:
        cfg = getattr(request.app.state, "channel_configs", {})
        return cfg.get("whatsapp", {}).get("phone_number_id") or None
    return None

def _whatsapp_verify_token(request: Optional[Request] = None) -> Optional[str]:
    val = os.environ.get("WHATSAPP_VERIFY_TOKEN", "").strip()
    if val:
        return val
    if request is not None:
        cfg = getattr(request.app.state, "channel_configs", {})
        return cfg.get("whatsapp", {}).get("verify_token") or None
    return None


# ── Shared helper ─────────────────────────────────────────────────────────────

async def _get_or_create_conversation(
    session_factory,
    platform: str,
    channel_id: str,
    contact_name: Optional[str] = None,
    contact_phone: Optional[str] = None,
    contact_username: Optional[str] = None,
) -> UUID:
    async with session_factory() as session:
        svc = ConversationService(session)
        conv = await svc.get_active_by_channel(platform, channel_id)
        if conv is None:
            conv = await svc.start_conversation(
                platform=platform,
                channel_id=channel_id,
                contact_name=contact_name,
                contact_phone=contact_phone,
                contact_username=contact_username,
            )
            await session.commit()
        return conv.id


# ── Background processing ─────────────────────────────────────────────────────

async def _process_and_reply(
    *,
    orchestrator,
    session_factory,
    platform: str,
    channel_id: str,
    query: str,
    contact_name: Optional[str],
    contact_phone: Optional[str],
    contact_username: Optional[str] = None,
    reply_fn,  # async callable (text: str) -> None
) -> None:
    try:
        conversation_id = await _get_or_create_conversation(
            session_factory, platform, channel_id,
            contact_name=contact_name,
            contact_phone=contact_phone,
            contact_username=contact_username,
        )
        result = await orchestrator.process_with_tracking(query, conversation_id)
        answer = result.answer or ""
        await reply_fn(answer)
    except Exception:
        logger.exception("webhooks: error processing %s message from %s", platform, channel_id)


# ── WhatsApp: verification ────────────────────────────────────────────────────

@router.get("/whatsapp")
async def whatsapp_verify(request: Request):
    """Meta webhook verification handshake."""
    verify_token = _whatsapp_verify_token(request)
    if not verify_token:
        return JSONResponse(
            status_code=403,
            content={"detail": "WHATSAPP_VERIFY_TOKEN not configured"},
        )

    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == verify_token:
        logger.info("webhooks: WhatsApp verification succeeded")
        # Record verification timestamp in app.state so the channels API can surface it
        cfg: dict = getattr(request.app.state, "channel_configs", {})
        wa = dict(cfg.get("whatsapp", {}))
        wa["verified_at"] = datetime.now(timezone.utc).isoformat()
        cfg["whatsapp"] = wa
        request.app.state.channel_configs = cfg
        return PlainTextResponse(challenge or "")

    logger.warning("webhooks: WhatsApp verification failed (token mismatch or wrong mode)")
    return JSONResponse(status_code=403, content={"detail": "Verification failed"})


# ── WhatsApp: inbound messages ────────────────────────────────────────────────

@router.post("/whatsapp")
async def whatsapp_inbound(request: Request):
    """Receive WhatsApp Business messages from Meta Cloud API."""
    wa_token = _whatsapp_token(request)
    wa_phone_id = _whatsapp_phone_id(request)
    if not wa_token or not wa_phone_id:
        return JSONResponse(
            status_code=503,
            content={"detail": "WhatsApp integration not configured"},
        )

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        return Response(status_code=200)  # ack even on bad JSON

    try:
        entry = body.get("entry", [])
        if not entry:
            return Response(status_code=200)

        change = entry[0].get("changes", [{}])[0]
        value = change.get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return Response(status_code=200)

        msg = messages[0]
        if msg.get("type") != "text":
            return Response(status_code=200)

        channel_id: str = msg["from"]
        query: str = msg["text"]["body"]

        contacts = value.get("contacts", [])
        contact_name: Optional[str] = None
        if contacts:
            contact_name = contacts[0].get("profile", {}).get("name")
        # For WhatsApp, the sender's phone number (E.164) IS the contact identity
        wa_contact_username: str = channel_id

    except (KeyError, IndexError, TypeError):
        logger.warning("webhooks: WhatsApp payload parse error", exc_info=True)
        return Response(status_code=200)

    orchestrator = getattr(request.app.state, "orchestrator", None)
    session_factory = request.app.state.session_factory

    from backend.integrations.whatsapp import WhatsAppClient
    wa_client = WhatsAppClient(wa_token, wa_phone_id)

    asyncio.create_task(
        _process_and_reply(
            orchestrator=orchestrator,
            session_factory=session_factory,
            platform="whatsapp",
            channel_id=channel_id,
            query=query,
            contact_name=contact_name,
            contact_phone=channel_id,
            contact_username=wa_contact_username,
            reply_fn=lambda text: wa_client.send_message(channel_id, text),
        )
    )

    return Response(status_code=200)


# ── Telegram: inbound updates ─────────────────────────────────────────────────

@router.post("/telegram")
async def telegram_inbound(request: Request):
    """Receive Telegram Update objects from the Bot API."""
    tg_token = _telegram_token(request)
    if not tg_token:
        return JSONResponse(
            status_code=503,
            content={"detail": "Telegram integration not configured"},
        )

    try:
        update: Dict[str, Any] = await request.json()
    except Exception:
        return Response(status_code=200)

    msg = update.get("message")
    if not msg or "text" not in msg:
        return Response(status_code=200)

    try:
        channel_id = str(msg["chat"]["id"])
        query: str = msg["text"]
        from_data = msg.get("from", {})
        contact_name: Optional[str] = from_data.get("first_name")
        tg_username: Optional[str] = from_data.get("username")
        # Store as @username when available; Telegram usernames are unique identifiers
        tg_contact_username: Optional[str] = f"@{tg_username}" if tg_username else None
    except (KeyError, TypeError):
        logger.warning("webhooks: Telegram payload parse error", exc_info=True)
        return Response(status_code=200)

    orchestrator = getattr(request.app.state, "orchestrator", None)
    session_factory = request.app.state.session_factory

    from backend.integrations.telegram import TelegramClient
    tg_client = TelegramClient(tg_token)

    asyncio.create_task(
        _process_and_reply(
            orchestrator=orchestrator,
            session_factory=session_factory,
            platform="telegram",
            channel_id=channel_id,
            query=query,
            contact_name=contact_name,
            contact_phone=None,
            contact_username=tg_contact_username,
            reply_fn=lambda text: tg_client.send_message(channel_id, text),
        )
    )

    return Response(status_code=200)
