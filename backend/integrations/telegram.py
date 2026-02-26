"""Telegram Bot API client — outbound message sending."""
from __future__ import annotations

import logging
from typing import Union

import httpx

logger = logging.getLogger(__name__)

_MAX_MESSAGE_LEN = 4096


class TelegramClient:
    BASE = "https://api.telegram.org/bot{token}"

    def __init__(self, token: str) -> None:
        self._base = self.BASE.format(token=token)

    async def send_message(self, chat_id: Union[int, str], text: str) -> None:
        """Send *text* to *chat_id*, splitting into chunks if needed."""
        chunks = [text[i : i + _MAX_MESSAGE_LEN] for i in range(0, len(text), _MAX_MESSAGE_LEN)]
        async with httpx.AsyncClient(timeout=15) as client:
            for chunk in chunks:
                resp = await client.post(
                    f"{self._base}/sendMessage",
                    json={"chat_id": chat_id, "text": chunk},
                )
                if resp.status_code != 200:
                    logger.warning(
                        "TelegramClient: sendMessage failed (chat=%s status=%s): %s",
                        chat_id, resp.status_code, resp.text,
                    )
