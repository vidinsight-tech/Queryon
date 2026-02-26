from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional, TypedDict


class LLMMessage(TypedDict):
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class FunctionCallResult:
    """Result of an LLM function/tool call selection."""

    tool_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    raw_response: Optional[str] = None


class BaseLLMClient(ABC):
    @property
    @abstractmethod
    def provider(self) -> str:
        ...

    @abstractmethod
    async def complete(self, prompt: str, *, model: str | None = None) -> str:
        ...

    async def chat(self, messages: List[LLMMessage]) -> str:
        """Send a multi-turn conversation with an optional system message.

        Default implementation concatenates all messages into a single prompt
        and calls ``complete()``.  Override in providers that support native
        multi-turn / system-prompt APIs (OpenAI, Gemini, etc.).
        """
        parts: List[str] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = (msg.get("content") or "").strip()
            if not content:
                continue
            if role == "system":
                # Prepend system context before conversation turns
                parts.insert(0, f"[System instructions]\n{content}\n")
            else:
                parts.append(f"{role}: {content}")
        return await self.complete("\n".join(parts))

    @abstractmethod
    async def test_connection(self) -> bool:
        ...

    async def function_call(
        self,
        prompt: str,
        tools: List[dict],
        *,
        conversation_history: Optional[List[LLMMessage]] = None,
    ) -> Optional[FunctionCallResult]:
        """Ask the LLM to select a tool and extract its arguments.

        Default implementation returns ``None`` (not supported).
        Override in providers that support native function calling.
        """
        return None