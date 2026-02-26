"""Pydantic schemas for messaging channel configuration."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class TelegramConfigRequest(BaseModel):
    token: str = Field(..., min_length=1, description="Telegram bot token from @BotFather")


class WhatsAppConfigRequest(BaseModel):
    access_token: str = Field(..., min_length=1)
    phone_number_id: str = Field(..., min_length=1)
    verify_token: str = Field(..., min_length=1)


class TelegramChannelStatus(BaseModel):
    configured: bool
    masked_token: Optional[str] = None


class WhatsAppChannelStatus(BaseModel):
    configured: bool
    masked_token: Optional[str] = None
    phone_number_id: Optional[str] = None
    verify_token_set: bool = False
    verified_at: Optional[str] = None  # ISO timestamp set when Meta's GET verification succeeds


class ChannelsResponse(BaseModel):
    telegram: TelegramChannelStatus
    whatsapp: WhatsAppChannelStatus
