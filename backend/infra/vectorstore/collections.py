"""Payload schema, collection setup, payload builder."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from uuid import UUID

from backend.infra.vectorstore.client import QdrantManager

if TYPE_CHECKING:
    from backend.config import QdrantConfig

logger = logging.getLogger(__name__)

KNOWLEDGE_BASE_COLLECTION = "knowledge_base"


class PayloadField:
    DOCUMENT_ID = "document_id"
    CHUNK_ID = "chunk_id"
    CHUNK_INDEX = "chunk_index"
    CONTENT = "content"
    TITLE = "title"
    SOURCE_TYPE = "source_type"
    TAGS = "tags"
    LANGUAGE = "language"
    CREATED_AT = "created_at"
    TOKEN_COUNT = "token_count"


CHUNK_PAYLOAD_SCHEMA: Dict[str, str] = {
    PayloadField.DOCUMENT_ID: "keyword",
    PayloadField.CHUNK_ID: "keyword",
    PayloadField.CHUNK_INDEX: "integer",
    PayloadField.CONTENT: "text",
    PayloadField.TITLE: "keyword",
    PayloadField.SOURCE_TYPE: "keyword",
    PayloadField.TAGS: "keyword",
    PayloadField.LANGUAGE: "keyword",
    PayloadField.CREATED_AT: "datetime",
    PayloadField.TOKEN_COUNT: "integer",
}


async def ensure_collection_exists(
    manager: QdrantManager,
    config: Optional["QdrantConfig"] = None,
    *,
    vector_size: Optional[int] = None,
    distance: Optional[str] = None,
    collection_name: Optional[str] = None,
) -> str:
    if config is None:
        from backend.config import load_qdrant_config
        config = load_qdrant_config()
    name = collection_name or config.collection_name
    if await manager.collection_exists(name):
        logger.debug("Collection '%s' already exists.", name)
        return name
    size = vector_size if vector_size is not None else config.vector_size
    dist = distance or config.distance
    logger.info("Creating collection '%s' vector_size=%d distance=%s", name, size, dist)
    await manager.create_collection(name, vector_size=size, distance=dist)
    await _create_payload_indexes(name, manager)
    logger.info("Collection '%s' ready.", name)
    return name


async def _create_payload_indexes(name: str, manager: QdrantManager) -> None:
    try:
        from qdrant_client.models import PayloadSchemaType
    except ImportError:
        logger.warning("Payload index creation skipped (qdrant_client)")
        return
    type_map = {
        "keyword": PayloadSchemaType.KEYWORD,
        "integer": PayloadSchemaType.INTEGER,
        "datetime": PayloadSchemaType.DATETIME,
        "text": PayloadSchemaType.TEXT,
    }
    for field_name, field_type_str in CHUNK_PAYLOAD_SCHEMA.items():
        schema_type = type_map.get(field_type_str)
        if schema_type is None:
            continue
        try:
            await manager._client.create_payload_index(collection_name=name, field_name=field_name, field_schema=schema_type)
        except Exception as exc:
            logger.warning("Failed to create payload index '%s' on '%s': %s", field_name, name, exc)


def build_chunk_payload(
    document_id: UUID,
    chunk_id: UUID,
    chunk_index: int,
    content: str,
    title: str,
    source_type: str,
    created_at: str,
    tags: Optional[List[str]] = None,
    language: Optional[str] = None,
    token_count: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        PayloadField.DOCUMENT_ID: str(document_id),
        PayloadField.CHUNK_ID: str(chunk_id),
        PayloadField.CHUNK_INDEX: chunk_index,
        PayloadField.CONTENT: content,
        PayloadField.TITLE: title,
        PayloadField.SOURCE_TYPE: source_type,
        PayloadField.CREATED_AT: created_at,
        PayloadField.TAGS: tags or [],
    }
    if language:
        payload[PayloadField.LANGUAGE] = language
    if token_count is not None:
        payload[PayloadField.TOKEN_COUNT] = token_count
    if extra:
        payload.update(extra)
    return payload
