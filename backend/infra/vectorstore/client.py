"""Async Qdrant client with retry."""
from __future__ import annotations

import asyncio
import functools
import logging
from typing import TYPE_CHECKING, Any, Callable, List, Optional, TypeVar, cast

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
from qdrant_client.models import (
    Distance,
    Filter,
    PointIdsList,
    PointStruct,
    ScoredPoint,
    UpdateResult,
    VectorParams,
)

from backend.core.exceptions import VectorstoreError

if TYPE_CHECKING:
    from backend.config import QdrantConfig

logger = logging.getLogger(__name__)

_F = TypeVar("_F", bound=Callable[..., Any])
_RETRYABLE = (ResponseHandlingException, asyncio.TimeoutError)
_MAX_RETRIES = 3
_BASE_BACKOFF = 0.5


def _retry(func: _F) -> _F:
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        last_exc: Exception = RuntimeError("unreachable")
        for attempt in range(1, _MAX_RETRIES + 2):
            try:
                return await func(*args, **kwargs)
            except UnexpectedResponse as exc:
                if exc.status_code is not None and exc.status_code < 500:
                    raise
                last_exc = exc
            except _RETRYABLE as exc:
                last_exc = exc
            if attempt <= _MAX_RETRIES:
                delay = min(_BASE_BACKOFF * (2 ** (attempt - 1)), 4.0)
                logger.warning("Qdrant %s attempt %d/%d failed (%s), retry in %.1fs", func.__name__, attempt, _MAX_RETRIES, last_exc, delay)
                await asyncio.sleep(delay)
        raise VectorstoreError(f"Qdrant '{func.__name__}' failed after {_MAX_RETRIES} retries: {last_exc}", cause=last_exc)
    return cast(_F, wrapper)


_manager: Optional["QdrantManager"] = None


def get_qdrant_manager(config: Optional["QdrantConfig"] = None) -> "QdrantManager":
    global _manager
    if _manager is None:
        if config is None:
            from backend.config import load_qdrant_config
            config = load_qdrant_config()
        _manager = QdrantManager(config=config)
    return _manager


async def close_qdrant_manager() -> None:
    global _manager
    if _manager is not None:
        await _manager.close()
        _manager = None
        logger.info("QdrantManager closed.")


class QdrantManager:
    """Async Qdrant wrapper. All methods raise VectorstoreError on failure."""

    def __init__(self, config: Optional["QdrantConfig"] = None, *, url: Optional[str] = None, api_key: Optional[str] = None, timeout: Optional[int] = None) -> None:
        if config is not None:
            self._url = config.url
            self._api_key = config.api_key
            self._timeout = config.timeout
        else:
            from backend.config import load_qdrant_config
            c = load_qdrant_config()
            self._url = url or c.url
            self._api_key = api_key if api_key is not None else c.api_key
            self._timeout = timeout if timeout is not None else c.timeout
        self._client = AsyncQdrantClient(url=self._url, api_key=self._api_key, timeout=self._timeout)
        logger.info("QdrantManager initialised url=%s", self._url)

    async def collection_exists(self, name: str) -> bool:
        try:
            return await self._client.collection_exists(name)
        except (UnexpectedResponse, ResponseHandlingException) as exc:
            raise VectorstoreError(f"Failed to check collection '{name}': {exc}", cause=exc) from exc

    @_retry
    async def create_collection(self, name: str, vector_size: int, distance: str = "Cosine", on_disk_payload: bool = True) -> bool:
        try:
            dist = Distance[distance.upper()]
        except KeyError:
            raise VectorstoreError(f"Invalid distance '{distance}'. Use Cosine, Dot, Euclid.")
        try:
            await self._client.create_collection(collection_name=name, vectors_config=VectorParams(size=vector_size, distance=dist), on_disk_payload=on_disk_payload)
            logger.info("Created collection name=%s vector_size=%d", name, vector_size)
            return True
        except UnexpectedResponse as exc:
            if exc.status_code == 409:
                logger.debug("Collection '%s' already exists.", name)
                return False
            raise VectorstoreError(f"Failed to create collection '{name}': {exc}", cause=exc) from exc

    async def delete_collection(self, name: str) -> bool:
        try:
            result = await self._client.delete_collection(name)
            logger.warning("Deleted collection name=%s", name)
            return result
        except UnexpectedResponse as exc:
            if exc.status_code == 404:
                return False
            raise VectorstoreError(f"Failed to delete collection '{name}': {exc}", cause=exc) from exc

    @_retry
    async def upsert_points(self, collection: str, points: List[PointStruct], wait: bool = True) -> UpdateResult:
        if not points:
            return UpdateResult(operation_id=None, status="completed")  # type: ignore[call-arg]
        try:
            result = await self._client.upsert(collection_name=collection, points=points, wait=wait)
            logger.debug("upsert_points collection=%s count=%d", collection, len(points))
            return result
        except (UnexpectedResponse, ResponseHandlingException) as exc:
            raise VectorstoreError(f"Failed to upsert {len(points)} points into '{collection}': {exc}", cause=exc) from exc

    async def search(self, collection: str, query_vector: List[float], query_filter: Optional[Filter] = None, limit: int = 10, score_threshold: Optional[float] = None, with_payload: bool = True) -> List[ScoredPoint]:
        try:
            response = await self._client.query_points(
                collection_name=collection,
                query=query_vector,
                query_filter=query_filter,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=with_payload,
                with_vectors=False,
            )
            points = list(response.points) if getattr(response, "points", None) is not None else []
            if not points and (limit or score_threshold):
                logger.debug(
                    "search returned 0 points (collection=%s limit=%s score_threshold=%s)",
                    collection, limit, score_threshold,
                )
            return points
        except UnexpectedResponse as exc:
            if exc.status_code == 404:
                raise VectorstoreError(f"Collection '{collection}' does not exist.", cause=exc) from exc
            raise VectorstoreError(f"Search failed in '{collection}': {exc}", cause=exc) from exc
        except (ResponseHandlingException, asyncio.TimeoutError) as exc:
            raise VectorstoreError(f"Search timeout/error in '{collection}': {exc}", cause=exc) from exc

    async def scroll(self, collection: str, scroll_filter: Optional[Filter] = None, limit: int = 100, with_payload: bool = True) -> list:
        try:
            result = await self._client.scroll(collection_name=collection, scroll_filter=scroll_filter, limit=limit, with_payload=with_payload, with_vectors=False)
            return list(result[0]) if result else []
        except (UnexpectedResponse, ResponseHandlingException) as exc:
            raise VectorstoreError(f"Scroll failed in '{collection}': {exc}", cause=exc) from exc

    @_retry
    async def delete_points(self, collection: str, point_ids: List[str], wait: bool = True) -> UpdateResult:
        if not point_ids:
            return UpdateResult(operation_id=None, status="completed")  # type: ignore[call-arg]
        try:
            return await self._client.delete(collection_name=collection, points_selector=PointIdsList(points=point_ids), wait=wait)  # type: ignore[arg-type]
        except (UnexpectedResponse, ResponseHandlingException) as exc:
            raise VectorstoreError(f"Failed to delete points from '{collection}': {exc}", cause=exc) from exc

    async def count_points(self, collection: str, exact: bool = False) -> int:
        try:
            result = await self._client.count(collection_name=collection, exact=exact)
            return result.count
        except (UnexpectedResponse, ResponseHandlingException) as exc:
            raise VectorstoreError(f"Failed to count points in '{collection}': {exc}", cause=exc) from exc

    async def close(self) -> None:
        await self._client.close()
        logger.debug("QdrantManager: client closed.")
