"""Tests for Orchestrator's conversation-tracked processing and handler context passing."""
from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from backend.orchestrator.orchestrator import Orchestrator
from backend.orchestrator.types import (
    IntentType,
    OrchestratorConfig,
    OrchestratorResult,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestOrchestratorRequiresSessionFactory(unittest.TestCase):
    def test_start_conversation_raises_without_session_factory(self):
        class FakeLLM:
            async def complete(self, prompt):
                return "ok"

        orch = Orchestrator(llm=FakeLLM(), config=OrchestratorConfig())
        with self.assertRaises(RuntimeError):
            _run(orch.start_conversation(platform="cli"))

    def test_end_conversation_raises_without_session_factory(self):
        class FakeLLM:
            async def complete(self, prompt):
                return "ok"

        orch = Orchestrator(llm=FakeLLM(), config=OrchestratorConfig())
        with self.assertRaises(RuntimeError):
            _run(orch.end_conversation(uuid4()))

    def test_process_with_tracking_raises_without_session_factory(self):
        class FakeLLM:
            async def complete(self, prompt):
                return "ok"

        orch = Orchestrator(llm=FakeLLM(), config=OrchestratorConfig())
        with self.assertRaises(RuntimeError):
            _run(orch.process_with_tracking("hello", uuid4()))


class TestOrchestratorPassesHistoryToHandlers(unittest.TestCase):
    def test_handler_receives_conversation_history(self):
        """When process() is called with conversation_history, the handler
        receives it as a keyword argument."""
        received_kwargs = {}

        class FakeHandler:
            async def handle(self, query, **kwargs):
                received_kwargs.update(kwargs)
                return OrchestratorResult(
                    query=query,
                    intent=IntentType.DIRECT,
                    answer="test answer",
                )

        class FakeLLM:
            async def complete(self, prompt):
                return "ok"

        orch = Orchestrator(llm=FakeLLM(), config=OrchestratorConfig())
        orch._handlers[IntentType.DIRECT] = FakeHandler()
        orch._pre_classifier = None
        orch._embedding_classifier = None
        orch._llm_classifier = None

        history = [
            {"role": "user", "content": "merhaba"},
            {"role": "assistant", "content": "selam"},
        ]
        result = _run(orch.process("nasılsın", conversation_history=history))
        self.assertEqual(result.answer, "test answer")
        self.assertEqual(received_kwargs.get("conversation_history"), history)


class TestDirectHandlerBuildsPrompt(unittest.TestCase):
    def test_build_prompt_without_history(self):
        from backend.orchestrator.handlers.direct_handler import DirectHandler
        prompt = DirectHandler._build_prompt("hello", None)
        self.assertEqual(prompt, "hello")

    def test_build_prompt_with_history(self):
        from backend.orchestrator.handlers.direct_handler import DirectHandler
        history = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
        ]
        prompt = DirectHandler._build_prompt("q2", history)
        self.assertIn("user: q1", prompt)
        self.assertIn("assistant: a1", prompt)
        self.assertIn("user: q2", prompt)


class TestRAGHandlerEnrichesQuery(unittest.TestCase):
    def test_enrich_without_history(self):
        from backend.orchestrator.handlers.rag_handler import RAGHandler
        result = RAGHandler._enrich_query("test query", None)
        self.assertEqual(result, "test query")

    def test_enrich_with_history(self):
        from backend.orchestrator.handlers.rag_handler import RAGHandler
        history = [
            {"role": "user", "content": "proje hakkında bilgi ver"},
            {"role": "assistant", "content": "proje X hakkında bilgi..."},
        ]
        result = RAGHandler._enrich_query("daha fazla detay", history)
        self.assertIn("Previous conversation:", result)
        self.assertIn("proje hakkında bilgi ver", result)
        self.assertIn("Current question: daha fazla detay", result)

    def test_enrich_limits_to_last_4_turns(self):
        from backend.orchestrator.handlers.rag_handler import RAGHandler
        history = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        result = RAGHandler._enrich_query("latest", history)
        self.assertNotIn("msg0", result)
        self.assertIn("msg9", result)


class TestGetLastIntent(unittest.TestCase):
    def test_returns_intent_when_service_returns_string(self):
        from backend.orchestrator.orchestrator import Orchestrator
        mock_svc = MagicMock()
        mock_svc.get_last_assistant_intent = AsyncMock(return_value="rag")
        result = _run(Orchestrator._get_last_intent(mock_svc, uuid4()))
        self.assertEqual(result, IntentType.RAG)

    def test_returns_none_when_service_returns_none(self):
        from backend.orchestrator.orchestrator import Orchestrator
        mock_svc = MagicMock()
        mock_svc.get_last_assistant_intent = AsyncMock(return_value=None)
        result = _run(Orchestrator._get_last_intent(mock_svc, uuid4()))
        self.assertIsNone(result)

    def test_returns_none_when_service_returns_invalid_intent(self):
        from backend.orchestrator.orchestrator import Orchestrator
        mock_svc = MagicMock()
        mock_svc.get_last_assistant_intent = AsyncMock(return_value="invalid")
        result = _run(Orchestrator._get_last_intent(mock_svc, uuid4()))
        self.assertIsNone(result)


class TestGetConversationHistory(unittest.TestCase):
    def test_returns_empty_for_missing_conversation(self):
        fake_session = MagicMock()
        fake_sf = MagicMock()

        class FakeContext:
            async def __aenter__(self):
                return fake_session
            async def __aexit__(self, *args):
                pass

        fake_sf.return_value = FakeContext()

        class FakeLLM:
            async def complete(self, prompt):
                return "ok"

        orch = Orchestrator(
            llm=FakeLLM(),
            config=OrchestratorConfig(),
            session_factory=fake_sf,
        )

        with patch("backend.services.conversation_service.ConversationService") as mock_cls:
            mock_svc = MagicMock()
            mock_svc.get_conversation = AsyncMock(return_value=None)
            mock_cls.return_value = mock_svc

            result = _run(orch.get_conversation_history(uuid4()))
            self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
