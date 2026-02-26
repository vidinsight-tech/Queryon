"""Channels router: configure Telegram and WhatsApp messaging integrations.

Credentials are stored in the ToolConfig table under the special names
`_channel_telegram` and `_channel_whatsapp`.  On startup, main.py loads
them into app.state.channel_configs so the webhook handlers can read them
without hitting the DB on every request.
"""
from __future__ import annotations

import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_session
from backend.api.schemas.channels import (
    ChannelsResponse,
    TelegramChannelStatus,
    TelegramConfigRequest,
    WhatsAppChannelStatus,
    WhatsAppConfigRequest,
)
from backend.infra.database.models.tool_config import ToolConfig

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/channels", tags=["channels"])

_TG_KEY = "_channel_telegram"
_WA_KEY = "_channel_whatsapp"


def _mask(value: str, show: int = 4) -> str:
    """Return value with all but the last *show* characters replaced by *."""
    if len(value) <= show:
        return value
    return "*" * (len(value) - show) + value[-show:]


async def _get_config(session: AsyncSession, name: str) -> ToolConfig | None:
    result = await session.execute(select(ToolConfig).where(ToolConfig.name == name))
    return result.scalar_one_or_none()


def _reload_state(request: Request, platform: str, creds: dict | None) -> None:
    """Update the live app.state.channel_configs dict after a save/delete."""
    configs: dict = getattr(request.app.state, "channel_configs", {})
    if creds is None:
        configs.pop(platform, None)
    else:
        configs[platform] = creds
    request.app.state.channel_configs = configs


# ── GET /channels ─────────────────────────────────────────────────────────────

@router.get("", response_model=ChannelsResponse)
async def get_channels(request: Request, session: AsyncSession = Depends(get_session)):
    """Return the configuration status of both messaging channels."""
    tg_cfg = await _get_config(session, _TG_KEY)
    wa_cfg = await _get_config(session, _WA_KEY)

    # Pick up verified_at from live app.state (set when Meta's GET verification arrives)
    live_wa: dict = getattr(request.app.state, "channel_configs", {}).get("whatsapp", {})

    # Telegram
    if tg_cfg and tg_cfg.credentials:
        try:
            tg_data = json.loads(tg_cfg.credentials)
            tg_status = TelegramChannelStatus(
                configured=True,
                masked_token=_mask(tg_data.get("token", "")),
            )
        except Exception:
            tg_status = TelegramChannelStatus(configured=False)
    else:
        tg_status = TelegramChannelStatus(configured=False)

    # WhatsApp
    if wa_cfg and wa_cfg.credentials:
        try:
            wa_data = json.loads(wa_cfg.credentials)
            wa_status = WhatsAppChannelStatus(
                configured=True,
                masked_token=_mask(wa_data.get("access_token", "")),
                phone_number_id=wa_data.get("phone_number_id"),
                verify_token_set=bool(wa_data.get("verify_token")),
                verified_at=live_wa.get("verified_at"),
            )
        except Exception:
            wa_status = WhatsAppChannelStatus(configured=False)
    else:
        wa_status = WhatsAppChannelStatus(configured=False)

    return ChannelsResponse(telegram=tg_status, whatsapp=wa_status)


# ── PUT /channels/telegram ────────────────────────────────────────────────────

@router.put("/telegram", response_model=TelegramChannelStatus)
async def save_telegram(
    body: TelegramConfigRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    creds = {"token": body.token}
    creds_json = json.dumps(creds)

    row = await _get_config(session, _TG_KEY)
    if row is None:
        session.add(ToolConfig(
            name=_TG_KEY,
            description="Telegram Bot integration credentials",
            credentials=creds_json,
            enabled=True,
            is_builtin=True,
        ))
    else:
        row.credentials = creds_json

    await session.commit()
    _reload_state(request, "telegram", creds)
    logger.info("channels: Telegram config saved")

    return TelegramChannelStatus(
        configured=True,
        masked_token=_mask(body.token),
    )


# ── PUT /channels/whatsapp ────────────────────────────────────────────────────

@router.put("/whatsapp", response_model=WhatsAppChannelStatus)
async def save_whatsapp(
    body: WhatsAppConfigRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    creds = {
        "access_token": body.access_token,
        "phone_number_id": body.phone_number_id,
        "verify_token": body.verify_token,
    }
    creds_json = json.dumps(creds)

    row = await _get_config(session, _WA_KEY)
    if row is None:
        session.add(ToolConfig(
            name=_WA_KEY,
            description="WhatsApp Business integration credentials",
            credentials=creds_json,
            enabled=True,
            is_builtin=True,
        ))
    else:
        row.credentials = creds_json

    await session.commit()
    _reload_state(request, "whatsapp", creds)
    logger.info("channels: WhatsApp config saved")

    return WhatsAppChannelStatus(
        configured=True,
        masked_token=_mask(body.access_token),
        phone_number_id=body.phone_number_id,
        verify_token_set=True,
    )


# ── DELETE /channels/{platform} ───────────────────────────────────────────────

# ── GET /channels/telegram/webhook-info ──────────────────────────────────────

@router.get("/telegram/webhook-info")
async def telegram_webhook_info(session: AsyncSession = Depends(get_session)):
    """Call Telegram getWebhookInfo and return the current registration status."""
    row = await _get_config(session, _TG_KEY)
    if not row or not row.credentials:
        raise HTTPException(status_code=404, detail="Telegram not configured")
    try:
        token = json.loads(row.credentials)["token"]
    except Exception:
        raise HTTPException(status_code=500, detail="Corrupted Telegram credentials")

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"https://api.telegram.org/bot{token}/getWebhookInfo"
        )

    data = resp.json()
    if not data.get("ok"):
        raise HTTPException(
            status_code=502,
            detail=f"Telegram API error: {data.get('description', 'unknown')}",
        )
    info = data.get("result", {})
    return {
        "ok": True,
        "url": info.get("url", ""),
        "has_custom_certificate": info.get("has_custom_certificate", False),
        "pending_update_count": info.get("pending_update_count", 0),
        "last_error_date": info.get("last_error_date"),
        "last_error_message": info.get("last_error_message"),
        "registered": bool(info.get("url")),
    }


# ── POST /channels/telegram/register-webhook ─────────────────────────────────

class RegisterWebhookRequest(BaseModel):
    public_url: str  # e.g. https://abc123.ngrok.io


@router.post("/telegram/register-webhook")
async def telegram_register_webhook(
    body: RegisterWebhookRequest,
    session: AsyncSession = Depends(get_session),
):
    """Call Telegram setWebhook with the given public URL."""
    row = await _get_config(session, _TG_KEY)
    if not row or not row.credentials:
        raise HTTPException(status_code=404, detail="Telegram not configured")
    try:
        token = json.loads(row.credentials)["token"]
    except Exception:
        raise HTTPException(status_code=500, detail="Corrupted Telegram credentials")

    webhook_url = body.public_url.rstrip("/") + "/webhooks/telegram"

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": webhook_url},
        )

    data = resp.json()
    if not data.get("ok"):
        raise HTTPException(
            status_code=502,
            detail=f"Telegram API error: {data.get('description', 'unknown')}",
        )
    logger.info("channels: Telegram webhook registered at %s", webhook_url)
    return {"ok": True, "webhook_url": webhook_url, "description": data.get("description", "")}


# ── GET /channels/whatsapp/test-connection ───────────────────────────────────

@router.get("/whatsapp/test-connection")
async def whatsapp_test_connection(session: AsyncSession = Depends(get_session)):
    """Validate the WhatsApp access token + phone number ID against the Graph API."""
    row = await _get_config(session, _WA_KEY)
    if not row or not row.credentials:
        raise HTTPException(status_code=404, detail="WhatsApp not configured")
    try:
        creds = json.loads(row.credentials)
        access_token = creds["access_token"]
        phone_number_id = creds["phone_number_id"]
    except Exception:
        raise HTTPException(status_code=500, detail="Corrupted WhatsApp credentials")

    url = f"https://graph.facebook.com/v21.0/{phone_number_id}"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    data = resp.json()
    if "error" in data:
        err = data["error"]
        return {
            "ok": False,
            "error_message": err.get("message", "Unknown error"),
            "error_code": err.get("code"),
            "display_phone_number": None,
            "verified_name": None,
        }

    return {
        "ok": True,
        "error_message": None,
        "error_code": None,
        "display_phone_number": data.get("display_phone_number"),
        "verified_name": data.get("verified_name"),
    }


@router.delete("/telegram", status_code=status.HTTP_204_NO_CONTENT)
async def delete_telegram(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    row = await _get_config(session, _TG_KEY)
    if row is None:
        raise HTTPException(status_code=404, detail="Telegram not configured")
    await session.delete(row)
    await session.commit()
    _reload_state(request, "telegram", None)
    logger.info("channels: Telegram config removed")


@router.delete("/whatsapp", status_code=status.HTTP_204_NO_CONTENT)
async def delete_whatsapp(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    row = await _get_config(session, _WA_KEY)
    if row is None:
        raise HTTPException(status_code=404, detail="WhatsApp not configured")
    await session.delete(row)
    await session.commit()
    _reload_state(request, "whatsapp", None)
    logger.info("channels: WhatsApp config removed")
