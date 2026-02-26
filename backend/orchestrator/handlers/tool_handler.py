"""ToolHandler: LLM function-calling dispatcher."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, List, Optional

from backend.orchestrator.handlers.base import BaseHandler
from backend.orchestrator.types import IntentType, OrchestratorResult

if TYPE_CHECKING:
    from backend.clients.llm.base import BaseLLMClient

logger = logging.getLogger(__name__)


@dataclass
class ToolDefinition:
    """Schema for a callable tool."""

    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    handler: Optional[Callable[..., Awaitable[Any]]] = None


class ToolRegistry:
    """Registry of available tools."""

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}
        self._disabled: set = set()

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool
        logger.info("ToolRegistry: registered tool '%s'", tool.name)

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def enable(self, name: str) -> None:
        self._disabled.discard(name)
        logger.info("ToolRegistry: enabled tool '%s'", name)

    def disable(self, name: str) -> None:
        self._disabled.add(name)
        logger.info("ToolRegistry: disabled tool '%s'", name)

    def is_enabled(self, name: str) -> bool:
        return name not in self._disabled

    @property
    def names(self) -> List[str]:
        """All registered tool names regardless of enabled state."""
        return list(self._tools.keys())

    def get_descriptions(self) -> List[str]:
        """Descriptions for enabled tools only (used by LLM classifier)."""
        return [
            f"{t.name}: {t.description}"
            for t in self._tools.values()
            if t.name not in self._disabled
        ]

    def get_schema_for_llm(self) -> List[dict]:
        """OpenAI function-calling schema for enabled tools only."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in self._tools.values()
            if t.name not in self._disabled
        ]


class ToolHandler(BaseHandler):
    """Handler that uses LLM function-calling to select and execute a tool,
    then synthesises a natural-language answer from the tool result.
    """

    def __init__(
        self,
        registry: Optional[ToolRegistry] = None,
        llm: Optional["BaseLLMClient"] = None,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        self._registry = registry or ToolRegistry()
        self._llm = llm
        self._timeout = timeout_seconds

    async def handle(
        self,
        query: str,
        *,
        conversation_history: Optional[List[Any]] = None,
        **kwargs: object,
    ) -> OrchestratorResult:
        # ── Step 1: ask LLM which tool to call ──
        tool_schemas = self._registry.get_schema_for_llm()
        if self._llm is None or not tool_schemas:
            return OrchestratorResult(
                query=query,
                intent=IntentType.TOOL,
                answer="Tool support is not configured.",
                metadata={"available_tools": self._registry.names},
            )
        fc_result = await self._llm.function_call(
            query,
            tool_schemas,
            conversation_history=conversation_history,
        )

        if fc_result is None or not fc_result.tool_name:
            return OrchestratorResult(
                query=query,
                intent=IntentType.TOOL,
                answer="I couldn't determine which tool to use for your request.",
                metadata={"available_tools": self._registry.names},
            )

        tool_def = self._registry.get(fc_result.tool_name)
        if tool_def is None or tool_def.handler is None:
            return OrchestratorResult(
                query=query,
                intent=IntentType.TOOL,
                answer=f"Tool '{fc_result.tool_name}' is registered but not executable.",
                tool_called=fc_result.tool_name,
            )

        # ── Step 2: execute the tool ──
        try:
            tool_result = await tool_def.handler(**fc_result.arguments)
        except TypeError as exc:
            logger.error(
                "ToolHandler: tool '%s' called with bad arguments %s: %s",
                fc_result.tool_name, fc_result.arguments, exc,
            )
            return OrchestratorResult(
                query=query,
                intent=IntentType.TOOL,
                answer=f"Tool call failed (invalid arguments): {exc}",
                tool_called=fc_result.tool_name,
            )
        except Exception as exc:
            logger.error("ToolHandler: tool '%s' raised: %s", fc_result.tool_name, exc)
            return OrchestratorResult(
                query=query,
                intent=IntentType.TOOL,
                answer=f"Tool execution failed: {exc}",
                tool_called=fc_result.tool_name,
            )

        # ── Step 3: synthesise a natural-language answer ──
        tool_result_str = json.dumps(tool_result, ensure_ascii=False, default=str)
        synthesis_prompt = (
            f"The user asked: {query}\n"
            f"The tool '{fc_result.tool_name}' returned the following result:\n"
            f"{tool_result_str}\n\n"
            "Based on this result, provide a concise and helpful answer to the user. "
            "Respond in the same language the user used."
        )

        try:
            coro = self._llm.complete(synthesis_prompt)
            if self._timeout is not None:
                answer = await asyncio.wait_for(coro, timeout=self._timeout)
            else:
                answer = await coro
        except asyncio.TimeoutError:
            logger.warning(
                "ToolHandler: synthesis timed out after %.1fs — returning raw result",
                self._timeout,
            )
            answer = f"Tool result: {tool_result_str}"
        except Exception as exc:
            logger.error("ToolHandler: synthesis LLM call failed: %s", exc)
            answer = f"Tool result: {tool_result_str}"

        logger.info(
            "ToolHandler: tool='%s' args=%s → answer generated",
            fc_result.tool_name, fc_result.arguments,
        )

        return OrchestratorResult(
            query=query,
            intent=IntentType.TOOL,
            answer=answer,
            tool_called=fc_result.tool_name,
            metadata={
                "tool_name": fc_result.tool_name,
                "tool_arguments": fc_result.arguments,
                "tool_result": tool_result,
            },
        )
