from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypedDict, Literal, Sequence


class LLMMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


class BaseLLMClient(ABC):
    @property
    @abstractmethod
    def provider(self) -> str:
        ...

    @abstractmethod
    async def complete(self, prompt: str, *, model: str | None = None) -> str:
        ...

    @abstractmethod
    async def test_connection(self) -> bool:
        ...