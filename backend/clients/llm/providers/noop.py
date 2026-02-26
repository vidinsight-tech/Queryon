"""No-op LLM client when no provider is configured. Returns a friendly message."""
from __future__ import annotations

from backend.clients.llm.base import BaseLLMClient, FunctionCallResult


_NOOP_MESSAGE = (
    "Dil modeli henüz yapılandırılmadı. Lütfen ayarlardan bir LLM ekleyin "
    "(OpenAI veya Gemini API anahtarı) veya yöneticiyle iletişime geçin."
)


class NoOpLLMClient(BaseLLMClient):
    """Placeholder client when no API key or DB LLM is configured."""

    @property
    def provider(self) -> str:
        return "noop"

    async def complete(self, prompt: str, *, model: str | None = None) -> str:
        return _NOOP_MESSAGE

    async def test_connection(self) -> bool:
        return False

    async def function_call(
        self,
        prompt: str,
        tools: list,
        *,
        conversation_history: list | None = None,
    ) -> FunctionCallResult | None:
        return None
