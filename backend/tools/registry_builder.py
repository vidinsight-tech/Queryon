"""Build the ToolRegistry from available built-in tools and DB configuration."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from backend.orchestrator.handlers.tool_handler import ToolRegistry
from backend.tools.builtin.datetime_tools import DATETIME_TOOLS
from backend.tools.builtin.http_tool import HTTP_TOOL

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def build_tool_registry(
    *,
    rag_service: Optional[object] = None,
    session: Optional["AsyncSession"] = None,
) -> ToolRegistry:
    """Build and return a fully populated ToolRegistry.

    Always registers:
      - get_current_time
      - get_current_date
      - http_request

    Conditionally registers:
      - search_knowledge_base  (if rag_service is provided)
      - Google Calendar tools  (if credentials are stored in tool_configs table)
    """
    registry = ToolRegistry()

    # Always-on: date/time tools
    for tool in DATETIME_TOOLS:
        registry.register(tool)

    # Always-on: HTTP request tool
    registry.register(HTTP_TOOL)

    # Conditional: RAG knowledge base lookup
    if rag_service is not None:
        from backend.tools.builtin.rag_tool import build_rag_tool
        registry.register(build_rag_tool(rag_service))
        logger.info("registry_builder: search_knowledge_base registered")

    # Conditional: Google Calendar (requires stored credentials)
    # Also: sync enabled/disabled state for all tools from DB
    if session is not None:
        try:
            from sqlalchemy import select
            from backend.infra.database.models.tool_config import ToolConfig

            result = await session.execute(select(ToolConfig))
            db_configs = {tc.name: tc for tc in result.scalars().all()}

            gcal_cfg = db_configs.get("check_calendar_availability")
            if gcal_cfg and gcal_cfg.credentials and gcal_cfg.enabled:
                from backend.tools.builtin.google_calendar import build_google_calendar_tools
                for tool in build_google_calendar_tools(gcal_cfg.credentials):
                    registry.register(tool)
                logger.info("registry_builder: Google Calendar tools registered")

            # Register custom webhook tools from DB (non-builtin rows with credentials)
            builtin_names = set(registry.names)
            for name, tc in db_configs.items():
                if not tc.is_builtin and tc.credentials and name not in builtin_names:
                    try:
                        from backend.tools.builtin.webhook_tool import make_webhook_tool
                        tool = make_webhook_tool(
                            name=tc.name,
                            description=tc.description or "",
                            parameters=tc.parameters or None,
                            credentials_json=tc.credentials,
                        )
                        registry.register(tool)
                        logger.info("registry_builder: webhook tool '%s' registered", name)
                    except Exception as exc:
                        logger.warning(
                            "registry_builder: could not register webhook tool '%s': %s", name, exc
                        )

            # Disable any tool that has a DB row with enabled=False
            for name, tc in db_configs.items():
                if not tc.enabled and name in registry.names:
                    registry.disable(name)
        except Exception as exc:
            logger.warning("registry_builder: could not sync tool enabled states: %s", exc)

    logger.info(
        "registry_builder: built registry with %d tools: %s",
        len(registry.names),
        registry.names,
    )
    return registry
