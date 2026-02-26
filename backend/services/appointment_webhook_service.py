"""AppointmentWebhookService: outbound HMAC-signed webhook dispatcher.

Outbound security model
-----------------------
Every event is signed with HMAC-SHA256 using ``appointment_webhook_secret``.
The resulting hex digest is sent in the ``X-Queryon-Signature: sha256=<hex>``
header so the receiving server can verify authenticity.

Typical verification (Python):
    import hashlib, hmac
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(expected, received_sig.removeprefix("sha256="))

Events fired
------------
- ``appointment.created``  — new appointment saved from chatbot
- ``appointment.updated``  — status or fields changed (admin or chat reschedule)
- ``appointment.cancelled`` — status set to "cancelled"
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10


def _build_payload(event: str, appointment) -> Dict[str, Any]:
    """Serialize an Appointment ORM object into a flat webhook payload dict."""
    import datetime as _dt
    ts = _dt.datetime.utcnow().isoformat() + "Z"
    return {
        "event": event,
        "timestamp": ts,
        "data": {
            "id": str(appointment.id),
            "appt_number": appointment.appt_number,
            "status": appointment.status,
            "contact_name": appointment.contact_name,
            "contact_surname": appointment.contact_surname,
            "contact_phone": appointment.contact_phone,
            "contact_email": appointment.contact_email,
            "service": appointment.service,
            "location": appointment.location,
            "artist": appointment.artist,
            "event_date": appointment.event_date,
            "event_time": appointment.event_time,
            "notes": appointment.notes,
            "extra_fields": appointment.extra_fields or {},
            "created_at": appointment.created_at.isoformat() if appointment.created_at else None,
        },
    }


def _sign(body: bytes, secret: str) -> str:
    """Return ``sha256=<hex>`` HMAC signature for *body* using *secret*."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


async def dispatch(
    event: str,
    appointment,
    webhook_url: Optional[str],
    webhook_secret: Optional[str],
) -> None:
    """Fire-and-forget: POST a signed JSON event to *webhook_url*.

    Silently drops the event if URL or secret is missing.
    Never raises — logs warnings on failure.
    """
    if not webhook_url or not webhook_secret:
        return

    payload = _build_payload(event, appointment)
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    signature = _sign(body, webhook_secret)

    try:
        import httpx
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                webhook_url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Queryon-Signature": signature,
                    "X-Queryon-Event": event,
                },
            )
            if resp.status_code >= 400:
                logger.warning(
                    "AppointmentWebhook: %s → %s returned HTTP %d",
                    event, webhook_url, resp.status_code,
                )
            else:
                logger.info(
                    "AppointmentWebhook: %s dispatched → %s (%d)",
                    event, webhook_url, resp.status_code,
                )
    except ImportError:
        # httpx not installed — fall back to stdlib urllib
        import urllib.request
        req = urllib.request.Request(
            webhook_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Queryon-Signature": signature,
                "X-Queryon-Event": event,
            },
            method="POST",
        )
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, urllib.request.urlopen, req)
            logger.info("AppointmentWebhook: %s dispatched (urllib) → %s", event, webhook_url)
        except Exception as exc:
            logger.warning("AppointmentWebhook: %s failed (urllib): %s", event, exc)
    except Exception as exc:
        logger.warning("AppointmentWebhook: %s → %s failed: %s", event, webhook_url, exc)


def verify_inbound(body: bytes, secret: str, provided_sig: str) -> bool:
    """Verify that *provided_sig* matches the HMAC of *body* with *secret*.

    *provided_sig* may be bare hex or ``sha256=<hex>``.
    Uses ``hmac.compare_digest`` to prevent timing attacks.
    """
    if not secret:
        return False
    clean = provided_sig.removeprefix("sha256=") if provided_sig.startswith("sha256=") else provided_sig
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, clean)
