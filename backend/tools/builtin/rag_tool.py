"""Built-in RAG/knowledge base lookup tool."""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from backend.orchestrator.handlers.tool_handler import ToolDefinition

logger = logging.getLogger(__name__)


def build_rag_tool(rag_service: Any) -> ToolDefinition:
    """Build a knowledge-base search tool bound to the given RAGService."""

    async def search_knowledge_base(
        query: str,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """Search the internal knowledge base and return relevant chunks."""
        try:
            results = await rag_service.search(query, top_k=top_k)
        except Exception as exc:
            logger.error("search_knowledge_base: error: %s", exc)
            return {"error": str(exc), "results": []}

        return {
            "results": [
                {
                    "title": getattr(r, "title", ""),
                    "content_preview": (getattr(r, "content", "") or "")[:500],
                    "score": getattr(r, "score", 0.0),
                    "document_id": str(getattr(r, "document_id", "")),
                    "chunk_index": getattr(r, "chunk_index", 0),
                }
                for r in results
            ],
            "query": query,
            "total": len(results),
        }

    return ToolDefinition(
        name="search_knowledge_base",
        description=(
            "Search the internal knowledge base for information. Use when the user "
            "asks about documents, files, or specific knowledge stored in the system."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to look up in the knowledge base.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of results to return (default 5).",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
        handler=search_knowledge_base,
    )
