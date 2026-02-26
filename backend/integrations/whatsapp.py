"""WhatsApp Business (Meta Cloud API) client — outbound message sending."""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_GRAPH_URL = "https://graph.facebook.com/v21.0/{phone_number_id}/messages"
_MAX_MESSAGE_LEN = 4096


class WhatsAppClient:
    def __init__(self, access_token: str, phone_number_id: str) -> None:
        self._url = _GRAPH_URL.format(phone_number_id=phone_number_id)
        self._headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

    async def send_message(self, to: str, text: str) -> None:
        """Send *text* to *to* (E.164 phone number), splitting if needed."""
        chunks = [text[i : i + _MAX_MESSAGE_LEN] for i in range(0, len(text), _MAX_MESSAGE_LEN)]
        async with httpx.AsyncClient(timeout=15) as client:
            for chunk in chunks:
                payload = {
                    "messaging_product": "whatsapp",
                    "to": to,
                    "type": "text",
                    "text": {"body": chunk},
                }
                resp = await client.post(self._url, headers=self._headers, json=payload)
                if resp.status_code not in (200, 201):
                    logger.warning(
                        "WhatsAppClient: send failed (to=%s status=%s): %s",
                        to, resp.status_code, resp.text,
                    )
