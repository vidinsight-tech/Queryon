"""Tools router: list, enable/disable, configure tools."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.dependencies import get_session
import json

from backend.api.schemas.tools import (
    GoogleCalendarOAuthRequest,
    ToolPatchRequest,
    ToolResponse,
    WebhookCreateRequest,
    WebhookTestRequest,
    WebhookTestResponse,
    WebhookUpdateRequest,
)
from backend.infra.database.models.tool_config import ToolConfig

router = APIRouter(prefix="/tools", tags=["tools"])


def _registry_tools(request: Request) -> list:
    """Read registered tools from app.state.tool_registry if available."""
    registry = getattr(request.app.state, "tool_registry", None)
    if registry is None:
        return []
    return [registry.get(name) for name in registry.names]


@router.get("", response_model=List[ToolResponse])
async def list_tools(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """List all tools: builtin (from registry) merged with DB config rows."""
    # Fetch DB configs keyed by name
    result = await session.execute(select(ToolConfig))
    db_configs = {tc.name: tc for tc in result.scalars().all()}

    tools_out = []
    for tool_def in _registry_tools(request):
        if tool_def is None:
            continue
        db_cfg = db_configs.get(tool_def.name)
        tools_out.append(
            ToolResponse(
                name=tool_def.name,
                description=tool_def.description,
                parameters=tool_def.parameters,
                is_builtin=True,
                enabled=db_cfg.enabled if db_cfg else True,
            )
        )

    # Also include DB-only entries (custom tools not in registry)
    registered_names = {t.name for t in tools_out}
    for name, db_cfg in db_configs.items():
        if name not in registered_names and not db_cfg.is_builtin:
            tools_out.append(
                ToolResponse(
                    name=db_cfg.name,
                    description=db_cfg.description or "",
                    parameters=db_cfg.parameters or {},
                    is_builtin=False,
                    enabled=db_cfg.enabled,
                )
            )

    return tools_out


@router.post("/webhook", response_model=ToolResponse, status_code=status.HTTP_201_CREATED)
async def create_webhook_tool(
    body: WebhookCreateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Create a custom webhook tool and hot-register it into the live registry."""
    registry = getattr(request.app.state, "tool_registry", None)

    # Check for name collision in registry and DB
    if registry and body.name in registry.names:
        raise HTTPException(status_code=409, detail=f"Tool '{body.name}' already exists")
    existing = await session.execute(select(ToolConfig).where(ToolConfig.name == body.name))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Tool '{body.name}' already exists")

    credentials = json.dumps({
        "url": body.url,
        "method": body.method,
        "headers": body.headers or {},
        "auth_token": body.auth_token,
    })
    db_cfg = ToolConfig(
        name=body.name,
        description=body.description,
        parameters=body.parameters or {},
        is_builtin=False,
        enabled=body.enabled,
        credentials=credentials,
    )
    session.add(db_cfg)
    await session.flush()

    # Hot-register into live registry
    if registry is not None:
        try:
            from backend.tools.builtin.webhook_tool import make_webhook_tool
            tool_def = make_webhook_tool(
                name=body.name,
                description=body.description,
                parameters=body.parameters,
                credentials_json=credentials,
            )
            registry.register(tool_def)
            if not body.enabled:
                registry.disable(body.name)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("create_webhook_tool: registration failed: %s", exc)

    return ToolResponse(
        name=db_cfg.name,
        description=db_cfg.description or "",
        parameters=db_cfg.parameters or {},
        is_builtin=False,
        enabled=db_cfg.enabled,
    )


@router.put("/webhook/{tool_name}", response_model=ToolResponse)
async def update_webhook_tool(
    tool_name: str,
    body: WebhookUpdateRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Update a custom webhook tool and re-register it in the live registry."""
    result = await session.execute(
        select(ToolConfig).where(ToolConfig.name == tool_name)
    )
    db_cfg = result.scalar_one_or_none()
    if db_cfg is None:
        raise HTTPException(status_code=404, detail="Webhook tool not found")
    if db_cfg.is_builtin:
        raise HTTPException(status_code=403, detail="Cannot update a builtin tool via this endpoint")

    # Parse existing credentials and merge updates
    try:
        existing_creds = json.loads(db_cfg.credentials or "{}")
    except (json.JSONDecodeError, ValueError):
        existing_creds = {}

    if body.url is not None:
        existing_creds["url"] = body.url
    if body.method is not None:
        existing_creds["method"] = body.method
    if body.headers is not None:
        existing_creds["headers"] = body.headers
    if body.auth_token is not None:
        existing_creds["auth_token"] = body.auth_token

    new_credentials = json.dumps(existing_creds)

    if body.description is not None:
        db_cfg.description = body.description
    if body.parameters is not None:
        db_cfg.parameters = body.parameters
    if body.enabled is not None:
        db_cfg.enabled = body.enabled
    db_cfg.credentials = new_credentials
    await session.flush()

    # Re-register in live registry
    registry = getattr(request.app.state, "tool_registry", None)
    if registry is not None:
        try:
            from backend.tools.builtin.webhook_tool import make_webhook_tool
            tool_def = make_webhook_tool(
                name=tool_name,
                description=db_cfg.description or "",
                parameters=db_cfg.parameters or None,
                credentials_json=new_credentials,
            )
            registry.register(tool_def)
            if db_cfg.enabled:
                registry.enable(tool_name)
            else:
                registry.disable(tool_name)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("update_webhook_tool: re-registration failed: %s", exc)

    return ToolResponse(
        name=db_cfg.name,
        description=db_cfg.description or "",
        parameters=db_cfg.parameters or {},
        is_builtin=False,
        enabled=db_cfg.enabled,
    )


@router.post("/{tool_name}/test", response_model=WebhookTestResponse)
async def test_tool(
    tool_name: str,
    body: WebhookTestRequest,
    request: Request,
):
    """Fire a tool handler directly with the supplied kwargs and return the raw result.

    Useful for admins to verify a webhook tool works before enabling it for the bot.
    """
    registry = getattr(request.app.state, "tool_registry", None)
    if registry is None:
        raise HTTPException(status_code=503, detail="Tool registry not available")

    tool_def = registry.get(tool_name)
    if tool_def is None:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found in registry")

    try:
        result = await tool_def.handler(**body.kwargs)
        return WebhookTestResponse(ok=True, result=result)
    except Exception as exc:
        return WebhookTestResponse(ok=False, error=str(exc))


@router.patch("/{tool_name}", response_model=ToolResponse)
async def patch_tool(
    tool_name: str,
    body: ToolPatchRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(ToolConfig).where(ToolConfig.name == tool_name)
    )
    db_cfg = result.scalar_one_or_none()

    # Create DB row if this is a known builtin with no config yet
    registry = getattr(request.app.state, "tool_registry", None)
    tool_def = registry.get(tool_name) if registry else None

    if db_cfg is None:
        if tool_def is None:
            raise HTTPException(status_code=404, detail="Tool not found")
        db_cfg = ToolConfig(
            name=tool_name,
            description=tool_def.description,
            parameters=tool_def.parameters,
            enabled=True,
            is_builtin=True,
        )
        session.add(db_cfg)

    if body.enabled is not None:
        db_cfg.enabled = body.enabled
        registry = getattr(request.app.state, "tool_registry", None)
        if registry is not None:
            if body.enabled:
                registry.enable(tool_name)
            else:
                registry.disable(tool_name)
    if body.description is not None:
        db_cfg.description = body.description
    await session.flush()

    return ToolResponse(
        name=db_cfg.name,
        description=db_cfg.description or (tool_def.description if tool_def else ""),
        parameters=db_cfg.parameters or (tool_def.parameters if tool_def else {}),
        is_builtin=db_cfg.is_builtin,
        enabled=db_cfg.enabled,
    )


@router.delete("/{tool_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool(
    tool_name: str,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(ToolConfig).where(ToolConfig.name == tool_name)
    )
    db_cfg = result.scalar_one_or_none()
    if db_cfg is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    if db_cfg.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete a builtin tool. Use PATCH to disable it.",
        )
    await session.delete(db_cfg)


@router.post("/google-calendar/oauth", status_code=status.HTTP_200_OK)
async def configure_google_calendar(
    body: GoogleCalendarOAuthRequest,
    session: AsyncSession = Depends(get_session),
):
    """Store Google Calendar service-account or OAuth credentials."""
    result = await session.execute(
        select(ToolConfig).where(ToolConfig.name == "check_calendar_availability")
    )
    db_cfg = result.scalar_one_or_none()
    if db_cfg is None:
        db_cfg = ToolConfig(
            name="check_calendar_availability",
            is_builtin=True,
            enabled=True,
        )
        session.add(db_cfg)
    db_cfg.credentials = body.credentials_json
    await session.flush()
    return {"ok": True, "message": "Google Calendar credentials stored."}
