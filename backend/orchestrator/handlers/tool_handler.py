"""ToolHandler: placeholder for future tool/function calling support."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from backend.orchestrator.handlers.base import BaseHandler
from backend.orchestrator.types import IntentType, OrchestratorResult

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

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool
        logger.info("ToolRegistry: registered tool '%s'", tool.name)

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    @property
    def names(self) -> List[str]:
        return list(self._tools.keys())

    def get_descriptions(self) -> List[str]:
        return [f"{t.name}: {t.description}" for t in self._tools.values()]

    def get_schema_for_llm(self) -> List[dict]:
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
        ]


class ToolHandler(BaseHandler):
    """Placeholder handler — returns a 'not yet supported' message."""

    def __init__(self, registry: Optional[ToolRegistry] = None) -> None:
        self._registry = registry or ToolRegistry()

    async def handle(
        self,
        query: str,
        *,
        conversation_history: Optional[List[Any]] = None,
        **kwargs: object,
    ) -> OrchestratorResult:
        return OrchestratorResult(
            query=query,
            intent=IntentType.TOOL,
            answer="Tool desteği henüz aktif değil.",
            metadata={"available_tools": self._registry.names},
        )
