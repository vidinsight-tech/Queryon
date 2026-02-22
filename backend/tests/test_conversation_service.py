"""Unit tests for ConversationService with mocked repositories."""
from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

from backend.orchestrator.types import (
    ClassificationResult,
    IntentType,
    OrchestratorMetrics,
    OrchestratorResult,
)
from backend.services.conversation_service import ConversationService


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
        "contact_meta": None,
        "status": "active",
        "llm_id": None,
        "embedding_id": None,
        "message_count": 0,
        "last_message_at": None,
        "messages": [],
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _fake_message(**kwargs):
    defaults = {
        "id": uuid4(),
        "conversation_id": uuid4(),
        "role": "user",
        "content": "test",
        "intent": None,
        "confidence": None,
        "classifier_layer": None,
        "rule_matched": None,
        "fallback_used": False,
        "needs_clarification": False,
        "total_ms": None,
        "llm_calls_count": 0,
        "sources": None,
        "extra_metadata": None,
        "events": [],
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestConversationServiceStartClose(unittest.TestCase):
    def test_start_conversation(self):
        session = MagicMock()
        svc = ConversationService(session)
        conv = _fake_conversation()
        svc._conv_repo.start = AsyncMock(return_value=conv)

        result = _run(svc.start_conversation(platform="web", contact_email="a@b.com"))
        self.assertEqual(result.id, conv.id)
        self.assertEqual(result.platform, "cli")
        svc._conv_repo.start.assert_awaited_once()
        call_kwargs = svc._conv_repo.start.call_args
        self.assertEqual(call_kwargs.kwargs["platform"], "web")
        self.assertEqual(call_kwargs.kwargs["contact_email"], "a@b.com")

    def test_close_conversation(self):
        session = MagicMock()
        svc = ConversationService(session)
        svc._conv_repo.close = AsyncMock(return_value=True)

        cid = uuid4()
        ok = _run(svc.close_conversation(cid))
        self.assertTrue(ok)
        svc._conv_repo.close.assert_awaited_once_with(cid)


class TestConversationServiceMessages(unittest.TestCase):
    def test_record_user_message(self):
        session = MagicMock()
        svc = ConversationService(session)
        msg = _fake_message(role="user", content="hello")
        svc._msg_repo.add_user_message = AsyncMock(return_value=msg)
        svc._conv_repo.increment_message_count = AsyncMock()

        cid = uuid4()
        result = _run(svc.record_user_message(cid, "hello"))
        self.assertEqual(result.role, "user")
        self.assertEqual(result.content, "hello")
        svc._conv_repo.increment_message_count.assert_awaited_once_with(cid)

    def test_record_assistant_message(self):
        session = MagicMock()
        svc = ConversationService(session)
        msg = _fake_message(role="assistant", content="answer")
        svc._msg_repo.add_assistant_message = AsyncMock(return_value=msg)
        svc._event_repo.log_events_bulk = AsyncMock(return_value=[])
        svc._conv_repo.increment_message_count = AsyncMock()

        orch_result = OrchestratorResult(
            query="test",
            intent=IntentType.RAG,
            answer="answer",
            classification=ClassificationResult(
                intent=IntentType.RAG,
                confidence=0.95,
                classifier_layer="llm",
            ),
            metrics=OrchestratorMetrics(
                classification_ms=10.0,
                handler_ms=50.0,
                total_ms=60.0,
                llm_calls_count=2,
            ),
            rule_matched=None,
            fallback_used=False,
            sources=[{"title": "doc1"}],
        )

        cid = uuid4()
        result = _run(svc.record_assistant_message(cid, orch_result))
        self.assertEqual(result.role, "assistant")
        svc._msg_repo.add_assistant_message.assert_awaited_once()
        call_kwargs = svc._msg_repo.add_assistant_message.call_args
        self.assertEqual(call_kwargs.kwargs["intent"], "rag")
        self.assertAlmostEqual(call_kwargs.kwargs["confidence"], 0.95)
        self.assertEqual(call_kwargs.kwargs["llm_calls_count"], 2)
        svc._event_repo.log_events_bulk.assert_awaited_once()


class TestConversationServiceHistory(unittest.TestCase):
    def test_get_history_as_turns(self):
        session = MagicMock()
        svc = ConversationService(session)
        messages = [
            _fake_message(role="user", content="q1"),
            _fake_message(role="assistant", content="a1"),
            _fake_message(role="user", content="q2"),
            _fake_message(role="assistant", content="a2"),
        ]
        svc._msg_repo.get_recent = AsyncMock(return_value=messages)

        cid = uuid4()
        turns = _run(svc.get_history_as_turns(cid, max_turns=5))
        self.assertEqual(len(turns), 4)
        self.assertEqual(turns[0]["role"], "user")
        self.assertEqual(turns[0]["content"], "q1")
        self.assertEqual(turns[-1]["role"], "assistant")
        svc._msg_repo.get_recent.assert_awaited_once_with(cid, limit=10)

    def test_get_last_assistant_intent_none_when_no_messages(self):
        session = MagicMock()
        svc = ConversationService(session)
        svc._msg_repo.get_recent = AsyncMock(return_value=[])
        cid = uuid4()
        self.assertIsNone(_run(svc.get_last_assistant_intent(cid)))

    def test_get_last_assistant_intent_returns_most_recent_assistant(self):
        session = MagicMock()
        svc = ConversationService(session)
        messages = [
            _fake_message(role="assistant", content="a1", intent="rag"),
            _fake_message(role="user", content="q2"),
            _fake_message(role="assistant", content="a2", intent="direct"),
        ]
        svc._msg_repo.get_recent = AsyncMock(return_value=messages)
        cid = uuid4()
        self.assertEqual(_run(svc.get_last_assistant_intent(cid)), "direct")

    def test_get_last_assistant_intent_none_when_only_user_messages(self):
        session = MagicMock()
        svc = ConversationService(session)
        svc._msg_repo.get_recent = AsyncMock(
            return_value=[_fake_message(role="user", content="q1")],
        )
        cid = uuid4()
        self.assertIsNone(_run(svc.get_last_assistant_intent(cid)))


class TestBuildEventsFromResult(unittest.TestCase):
    def test_events_from_full_result(self):
        result = OrchestratorResult(
            query="test",
            intent=IntentType.RULE,
            answer="response",
            classification=ClassificationResult(
                intent=IntentType.RULE,
                confidence=0.99,
                classifier_layer="pre",
                reasoning="keyword match",
            ),
            metrics=OrchestratorMetrics(
                classification_ms=2.0,
                handler_ms=1.0,
                total_ms=3.0,
                llm_calls_count=0,
            ),
            rule_matched="appointment_rule",
            fallback_used=False,
            sources=[],
        )
        events = ConversationService._build_events_from_result(result)
        event_types = [e["event_type"] for e in events]
        self.assertIn("classification_result", event_types)
        self.assertIn("rule_matched", event_types)
        self.assertIn("metrics", event_types)
        self.assertNotIn("fallback_triggered", event_types)

    def test_events_from_fallback_result(self):
        result = OrchestratorResult(
            query="test",
            intent=IntentType.DIRECT,
            answer="fallback answer",
            classification=ClassificationResult(
                intent=IntentType.RAG,
                confidence=0.8,
                classifier_layer="llm",
            ),
            metrics=OrchestratorMetrics(total_ms=100.0),
            fallback_used=True,
            needs_clarification=True,
        )
        events = ConversationService._build_events_from_result(result)
        event_types = [e["event_type"] for e in events]
        self.assertIn("fallback_triggered", event_types)
        self.assertIn("low_confidence", event_types)

    def test_events_empty_when_no_classification(self):
        result = OrchestratorResult(
            query="test",
            intent=IntentType.DIRECT,
            answer="ok",
        )
        events = ConversationService._build_events_from_result(result)
        self.assertEqual(len(events), 0)


if __name__ == "__main__":
    unittest.main()
