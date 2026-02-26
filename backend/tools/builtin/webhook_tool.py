"""Webhook tool factory: creates purpose-specific HTTP tools from admin config.

Each webhook tool is registered in the ToolRegistry with a custom name and
description so the LLM can invoke it by intent (e.g. ``check_stock``,
``send_sms``) rather than having to craft a raw ``http_request`` call.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def make_webhook_tool(
    name: str,
    description: str,
    parameters: Optional[Dict[str, Any]],
    credentials_json: str,
):
    """Build and return a :class:`~backend.orchestrator.handlers.tool_handler.ToolDefinition`.

    Parameters
    ----------
    name:
        Snake-case tool name visible to the LLM (e.g. ``check_stock``).
    description:
        Human/LLM-readable description of what the tool does.
    parameters:
        JSON Schema dict describing the tool's input parameters, or None for
        a parameter-free tool.
    credentials_json:
        JSON string with keys: ``url`` (required), ``method`` (default POST),
        ``headers`` (optional dict), ``auth_token`` (optional bearer token).
    """
    from backend.orchestrator.handlers.tool_handler import ToolDefinition

    try:
        creds = json.loads(credentials_json)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"Invalid credentials_json for webhook tool '{name}': {exc}") from exc

    url: str = creds.get("url", "")
    method: str = str(creds.get("method") or "POST").upper()
    extra_headers: Dict[str, str] = creds.get("headers") or {}
    auth_token: Optional[str] = creds.get("auth_token") or None

    if not url:
        raise ValueError(f"Webhook tool '{name}' credentials_json must include 'url'")

    schema = parameters or {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def _handler(**kwargs: Any) -> Dict[str, Any]:
        import aiohttp

        headers: Dict[str, str] = {"Content-Type": "application/json", **extra_headers}
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"

        try:
            async with aiohttp.ClientSession() as http_session:
                if method in ("GET", "DELETE"):
                    resp = await http_session.request(
                        method, url, params=kwargs, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
                    )
                else:
                    resp = await http_session.request(
                        method, url, json=kwargs, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
                    )
                body_text = await resp.text()
                content_type = resp.content_type or ""
                return {
                    "status_code": resp.status,
                    "body": body_text[:4000],
                    "content_type": content_type,
                    "url": str(resp.url),
                }
        except Exception as exc:
            logger.warning("WebhookTool '%s' failed: %s", name, exc)
            return {"error": str(exc)}

    return ToolDefinition(
        name=name,
        description=description,
        parameters=schema,
        handler=_handler,
    )
