"""Google Gemini LLM provider: BaseLLMClient implementation + registry builder."""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from google import genai

from backend.clients.llm.base import BaseLLMClient, FunctionCallResult, LLMMessage

logger = logging.getLogger(__name__)


class GeminiLLMClient(BaseLLMClient):
    """Google Gemini LLM client (gemini-2.0-flash, gemini-1.5-pro, etc.)."""

    def __init__(
        self,
        model: str = "gemini-2.0-flash",
        *,
        api_key: Optional[str] = None,
    ) -> None:
        self._model = model
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self._client = genai.Client(api_key=resolved_key)

    @property
    def provider(self) -> str:
        return "gemini"

    async def complete(self, prompt: str, *, model: Optional[str] = None) -> str:
        response = await self._client.aio.models.generate_content(
            model=model or self._model,
            contents=prompt,
        )
        return response.text or ""

    async def chat(self, messages: List[Dict[str, Any]]) -> str:
        """Native multi-turn chat with system-instruction support."""
        from google.genai import types as genai_types

        system_parts: List[str] = []
        history: List[Dict[str, Any]] = []

        for msg in messages:
            role = msg.get("role", "user")
            content = (msg.get("content") or "").strip()
            if not content:
                continue
            if role == "system":
                system_parts.append(content)
            elif role == "assistant":
                history.append({"role": "model", "parts": [content]})
            else:
                history.append({"role": "user", "parts": [content]})

        cfg_kwargs: Dict[str, Any] = {}
        if system_parts:
            cfg_kwargs["system_instruction"] = "\n\n".join(system_parts)

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=history,
            config=genai_types.GenerateContentConfig(**cfg_kwargs) if cfg_kwargs else None,
        )
        return response.text or ""

    async def function_call(
        self,
        prompt: str,
        tools: List[dict],
        *,
        conversation_history: Optional[List[LLMMessage]] = None,
    ) -> Optional[FunctionCallResult]:
        """Prompt-based tool selection fallback for Gemini."""
        if not tools:
            return None

        tool_list = json.dumps(tools, ensure_ascii=False, indent=2)
        extraction_prompt = (
            "You are a tool dispatcher. Given the available tools and the user's request, "
            "select the most appropriate tool and extract its arguments.\n\n"
            f"Available tools (JSON schema):\n{tool_list}\n\n"
            f"User request: {prompt}\n\n"
            "Respond with ONLY a JSON object in this exact format:\n"
            '{"tool_name": "<name>", "arguments": {<key-value pairs>}}\n'
            'If no tool matches, respond with: {"tool_name": null, "arguments": {}}'
        )

        try:
            raw = await self.complete(extraction_prompt)
        except Exception as exc:
            logger.error("GeminiLLMClient.function_call failed: %s", exc)
            return None

        # Strip markdown fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
        raw = re.sub(r"\s*```$", "", raw.strip())

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("GeminiLLMClient.function_call: could not parse JSON: %r", raw)
            return None

        tool_name = parsed.get("tool_name")
        if not tool_name:
            return None

        return FunctionCallResult(
            tool_name=tool_name,
            arguments=parsed.get("arguments") or {},
            raw_response=raw,
        )

    async def test_connection(self) -> bool:
        try:
            await self.complete("Say OK", model=self._model)
            return True
        except Exception:
            return False


def gemini_builder(config: Dict[str, Any]) -> GeminiLLMClient:
    return GeminiLLMClient(
        model=config.get("model", "gemini-2.0-flash"),
        api_key=config.get("api_key"),
    )
