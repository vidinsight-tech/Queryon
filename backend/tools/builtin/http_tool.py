"""Built-in HTTP/webhook tool — calls any external URL."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.orchestrator.handlers.tool_handler import ToolDefinition

logger = logging.getLogger(__name__)

_MAX_BODY_CHARS = 4000  # cap response body to avoid LLM context overflow


async def http_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[str] = None,
) -> Dict[str, Any]:
    """Make an HTTP request and return status code + response body."""
    import httpx

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        response = await client.request(
            method=method.upper(),
            url=url,
            headers=headers or {},
            content=body.encode() if body else None,
        )

    return {
        "status_code": response.status_code,
        "body": response.text[:_MAX_BODY_CHARS],
        "content_type": response.headers.get("content-type", ""),
        "url": str(response.url),
    }


HTTP_TOOL = ToolDefinition(
    name="http_request",
    description=(
        "Make an HTTP request to any URL. Use for webhooks, external APIs, "
        "or fetching web content. Returns status code and response body."
    ),
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The fully-qualified URL to request.",
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                "description": "HTTP method. Defaults to GET.",
            },
            "headers": {
                "type": "object",
                "description": "Optional HTTP headers as key-value pairs.",
                "additionalProperties": {"type": "string"},
            },
            "body": {
                "type": "string",
                "description": "Optional request body (string, e.g. JSON).",
            },
        },
        "required": ["url"],
    },
    handler=http_request,
)
