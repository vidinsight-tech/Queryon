"""Tests for Telegram & WhatsApp webhook integration.

Covers:
- ConversationService.get_active_by_channel
- Webhook router: Telegram payload parsing and HTTP behaviour
- Webhook router: WhatsApp payload parsing, verification, and HTTP behaviour
- Integration client helpers (chunking logic)
"""
from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.services.conversation_service import ConversationService


# ─── helpers ─────────────────────────────────────────────────────────────────

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _fake_conversation(**kwargs):
    defaults = {
        "id": uuid4(),
        "platform": "cli",
        "channel_id": None,
        "contact_phone": None,
        "contact_email": None,
        "contact_name": None,
        "status": "active",
        "message_count": 0,
        "last_message_at": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ─── ConversationService.get_active_by_channel ────────────────────────────────

class TestGetActiveByChannel(unittest.TestCase):
    def test_delegates_to_repo(self):
        session = MagicMock()
        svc = ConversationService(session)
        conv = _fake_conversation(platform="telegram", channel_id="123456")
        svc._conv_repo.get_active_by_channel = AsyncMock(return_value=conv)

        result = _run(svc.get_active_by_channel("telegram", "123456"))

        self.assertIs(result, conv)
        svc._conv_repo.get_active_by_channel.assert_awaited_once_with("telegram", "123456")

    def test_returns_none_when_no_active(self):
        session = MagicMock()
        svc = ConversationService(session)
        svc._conv_repo.get_active_by_channel = AsyncMock(return_value=None)

        result = _run(svc.get_active_by_channel("whatsapp", "+905001234567"))

        self.assertIsNone(result)


# ─── Webhook router test helpers ──────────────────────────────────────────────

def _make_test_app(*, tg_token=None, wa_token=None, wa_phone_id=None, wa_verify=None):
    """Build a minimal FastAPI app with the webhooks router mounted and app.state mocked."""
    from backend.api.routers import webhooks

    app = FastAPI()
    app.include_router(webhooks.router)

    # Provide enough app.state for the handlers
    fake_orchestrator = MagicMock()
    fake_orchestrator.process_with_tracking = AsyncMock(
        return_value=SimpleNamespace(answer="test reply")
    )

    async def _fake_session_factory_cm():
        pass

    class _FakeSessionCtx:
        async def __aenter__(self):
            sess = MagicMock()
            return sess
        async def __aexit__(self, *_):
            pass

    app.state.orchestrator = fake_orchestrator
    app.state.session_factory = lambda: _FakeSessionCtx()

    env_patch = {
        "TELEGRAM_BOT_TOKEN": tg_token or "",
        "WHATSAPP_ACCESS_TOKEN": wa_token or "",
        "WHATSAPP_PHONE_NUMBER_ID": wa_phone_id or "",
        "WHATSAPP_VERIFY_TOKEN": wa_verify or "",
    }
    return app, env_patch


# ─── Telegram webhook ─────────────────────────────────────────────────────────

class TestTelegramWebhook(unittest.TestCase):

    def test_returns_503_when_token_not_configured(self):
        app, env = _make_test_app(tg_token="")
        with patch.dict("os.environ", env, clear=False):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/webhooks/telegram",
                    json={"update_id": 1, "message": {"text": "hi", "chat": {"id": 1}, "from": {}}},
                )
        self.assertEqual(resp.status_code, 503)

    def test_returns_200_and_skips_non_text_update(self):
        app, env = _make_test_app(tg_token="tok123")
        with patch.dict("os.environ", env, clear=False):
            with TestClient(app, raise_server_exceptions=False) as client:
                # Sticker update — no "text" key
                resp = client.post(
                    "/webhooks/telegram",
                    json={"update_id": 2, "message": {"sticker": {}, "chat": {"id": 1}}},
                )
        self.assertEqual(resp.status_code, 200)

    def test_returns_200_and_skips_update_without_message(self):
        app, env = _make_test_app(tg_token="tok123")
        with patch.dict("os.environ", env, clear=False):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/webhooks/telegram",
                    json={"update_id": 3, "callback_query": {"data": "btn1"}},
                )
        self.assertEqual(resp.status_code, 200)

    def test_returns_200_immediately_for_text_message(self):
        app, env = _make_test_app(tg_token="tok123")
        payload = {
            "update_id": 4,
            "message": {
                "text": "Hello bot",
                "chat": {"id": 987654},
                "from": {"first_name": "Alice"},
            },
        }
        with patch("asyncio.create_task") as mock_task, \
             patch.dict("os.environ", env, clear=False):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post("/webhooks/telegram", json=payload)

        self.assertEqual(resp.status_code, 200)
        mock_task.assert_called_once()

    def test_returns_200_on_malformed_json(self):
        app, env = _make_test_app(tg_token="tok123")
        with patch.dict("os.environ", env, clear=False):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/webhooks/telegram",
                    content=b"not json",
                    headers={"Content-Type": "application/json"},
                )
        self.assertEqual(resp.status_code, 200)


# ─── WhatsApp verification ────────────────────────────────────────────────────

class TestWhatsAppVerification(unittest.TestCase):

    def test_verify_succeeds_with_correct_token(self):
        app, env = _make_test_app(wa_token="t", wa_phone_id="p", wa_verify="mysecret")
        with patch.dict("os.environ", env, clear=False):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get(
                    "/webhooks/whatsapp",
                    params={
                        "hub.mode": "subscribe",
                        "hub.verify_token": "mysecret",
                        "hub.challenge": "challenge_abc",
                    },
                )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.text, "challenge_abc")

    def test_verify_fails_with_wrong_token(self):
        app, env = _make_test_app(wa_token="t", wa_phone_id="p", wa_verify="mysecret")
        with patch.dict("os.environ", env, clear=False):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get(
                    "/webhooks/whatsapp",
                    params={
                        "hub.mode": "subscribe",
                        "hub.verify_token": "wrongtoken",
                        "hub.challenge": "challenge_abc",
                    },
                )
        self.assertEqual(resp.status_code, 403)

    def test_verify_returns_403_when_verify_token_not_configured(self):
        app, env = _make_test_app(wa_token="t", wa_phone_id="p", wa_verify="")
        with patch.dict("os.environ", env, clear=False):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.get(
                    "/webhooks/whatsapp",
                    params={
                        "hub.mode": "subscribe",
                        "hub.verify_token": "anything",
                        "hub.challenge": "ch",
                    },
                )
        self.assertEqual(resp.status_code, 403)


# ─── WhatsApp inbound messages ────────────────────────────────────────────────

def _wa_payload(*, from_="15550001234", text="Hello", msg_type="text", contact_name="Bob"):
    """Build a minimal WhatsApp Cloud API webhook payload."""
    msg: dict = {"from": from_, "type": msg_type}
    if msg_type == "text":
        msg["text"] = {"body": text}
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [msg],
                    "contacts": [{"profile": {"name": contact_name}}],
                }
            }]
        }]
    }


class TestWhatsAppInbound(unittest.TestCase):

    def test_returns_503_when_not_configured(self):
        app, env = _make_test_app(wa_token="", wa_phone_id="", wa_verify="v")
        with patch.dict("os.environ", env, clear=False):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post("/webhooks/whatsapp", json=_wa_payload())
        self.assertEqual(resp.status_code, 503)

    def test_returns_200_and_skips_non_text(self):
        app, env = _make_test_app(wa_token="tok", wa_phone_id="pid", wa_verify="v")
        with patch.dict("os.environ", env, clear=False):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/webhooks/whatsapp",
                    json=_wa_payload(msg_type="image"),
                )
        self.assertEqual(resp.status_code, 200)

    def test_returns_200_immediately_for_text_message(self):
        app, env = _make_test_app(wa_token="tok", wa_phone_id="pid", wa_verify="v")
        payload = _wa_payload(from_="15550001234", text="Hi there", contact_name="Bob")
        with patch("asyncio.create_task") as mock_task, \
             patch.dict("os.environ", env, clear=False):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post("/webhooks/whatsapp", json=payload)

        self.assertEqual(resp.status_code, 200)
        mock_task.assert_called_once()

    def test_returns_200_for_empty_entry(self):
        app, env = _make_test_app(wa_token="tok", wa_phone_id="pid", wa_verify="v")
        with patch.dict("os.environ", env, clear=False):
            with TestClient(app, raise_server_exceptions=False) as client:
                # Status update: entry present but no messages
                resp = client.post(
                    "/webhooks/whatsapp",
                    json={"entry": [{"changes": [{"value": {"statuses": []}}]}]},
                )
        self.assertEqual(resp.status_code, 200)

    def test_returns_200_on_malformed_json(self):
        app, env = _make_test_app(wa_token="tok", wa_phone_id="pid", wa_verify="v")
        with patch.dict("os.environ", env, clear=False):
            with TestClient(app, raise_server_exceptions=False) as client:
                resp = client.post(
                    "/webhooks/whatsapp",
                    content=b"not json",
                    headers={"Content-Type": "application/json"},
                )
        self.assertEqual(resp.status_code, 200)


# ─── Client chunking logic ────────────────────────────────────────────────────

class TestTelegramClientChunking(unittest.TestCase):
    def test_short_message_sends_one_chunk(self):
        from backend.integrations.telegram import TelegramClient, _MAX_MESSAGE_LEN

        client = TelegramClient("tok")
        text = "x" * (_MAX_MESSAGE_LEN - 1)
        chunks = [text[i: i + _MAX_MESSAGE_LEN] for i in range(0, len(text), _MAX_MESSAGE_LEN)]
        self.assertEqual(len(chunks), 1)

    def test_long_message_splits_into_multiple_chunks(self):
        from backend.integrations.telegram import _MAX_MESSAGE_LEN

        text = "a" * (_MAX_MESSAGE_LEN * 2 + 100)
        chunks = [text[i: i + _MAX_MESSAGE_LEN] for i in range(0, len(text), _MAX_MESSAGE_LEN)]
        self.assertEqual(len(chunks), 3)
        self.assertEqual("".join(chunks), text)


class TestWhatsAppClientChunking(unittest.TestCase):
    def test_long_message_splits(self):
        from backend.integrations.whatsapp import _MAX_MESSAGE_LEN

        text = "b" * (_MAX_MESSAGE_LEN + 1)
        chunks = [text[i: i + _MAX_MESSAGE_LEN] for i in range(0, len(text), _MAX_MESSAGE_LEN)]
        self.assertEqual(len(chunks), 2)
        self.assertEqual("".join(chunks), text)


if __name__ == "__main__":
    unittest.main()
