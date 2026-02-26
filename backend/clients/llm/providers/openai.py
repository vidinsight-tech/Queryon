"""OpenAI LLM provider: BaseLLMClient implementation + registry builder."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from backend.clients.llm.base import BaseLLMClient, FunctionCallResult, LLMMessage

logger = logging.getLogger(__name__)


class OpenAILLMClient(BaseLLMClient):
    """OpenAI-compatible LLM client (GPT-4o, GPT-4o-mini, etc.)."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._client = AsyncOpenAI(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url,
        )

    @property
    def provider(self) -> str:
        return "openai"

    async def complete(self, prompt: str, *, model: Optional[str] = None) -> str:
        kwargs: Dict[str, Any] = {
            "model": model or self._model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self._temperature,
        }
        if self._max_tokens is not None:
            kwargs["max_tokens"] = self._max_tokens
        response = await self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    async def chat(self, messages: List[Dict[str, Any]]) -> str:
        """Native multi-turn chat with system-prompt support."""
        kwargs: Dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
        }
        if self._max_tokens is not None:
            kwargs["max_tokens"] = self._max_tokens
        response = await self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    async def function_call(
        self,
        prompt: str,
        tools: List[dict],
        *,
        conversation_history: Optional[List[LLMMessage]] = None,
    ) -> Optional[FunctionCallResult]:
        """Use OpenAI native tool calling to select a tool and extract arguments."""
        if not tools:
            return None

        messages: List[Dict[str, Any]] = list(conversation_history or [])
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.0,
            )
        except Exception as exc:
            logger.error("OpenAILLMClient.function_call failed: %s", exc)
            return None

        msg = response.choices[0].message
        if not msg.tool_calls:
            return None

        tc = msg.tool_calls[0]
        try:
            arguments = json.loads(tc.function.arguments)
        except json.JSONDecodeError:
            arguments = {}

        return FunctionCallResult(
            tool_name=tc.function.name,
            arguments=arguments,
            raw_response=tc.function.arguments,
        )

    async def test_connection(self) -> bool:
        try:
            await self._client.models.list()
            return True
        except Exception:
            return False


def openai_builder(config: Dict[str, Any]) -> OpenAILLMClient:
    return OpenAILLMClient(
        model=config.get("model", "gpt-4o-mini"),
        api_key=config.get("api_key"),
        base_url=config.get("base_url"),
        temperature=float(config.get("temperature", 0.0)),
        max_tokens=config.get("max_tokens"),
    )
