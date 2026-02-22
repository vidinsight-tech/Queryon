"""
backend.config.qdrant – Qdrant connection and collection config.

Env vars: QDRANT_URL, QDRANT_API_KEY, QDRANT_TIMEOUT, QDRANT_VECTOR_SIZE,
         QDRANT_COLLECTION_NAME, QDRANT_DISTANCE.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

_VALID_DISTANCES = frozenset({"Cosine", "Dot", "Euclid"})


@dataclass(frozen=True)
class QdrantConfig:
    url: str
    api_key: str | None = None
    timeout: int = 30
    vector_size: int = 1536
    collection_name: str = "knowledge_base"
    distance: str = "Cosine"

    def __post_init__(self) -> None:
        url = (self.url or "").strip()
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("QDRANT_URL must start with http:// or https://")
        if not isinstance(self.timeout, int) or self.timeout < 1:
            raise ValueError(f"timeout must be a positive integer, got {self.timeout!r}")
        if not isinstance(self.vector_size, int) or self.vector_size < 1:
            raise ValueError(f"vector_size must be a positive integer, got {self.vector_size!r}")
        if self.distance not in _VALID_DISTANCES:
            raise ValueError(f"distance must be one of {sorted(_VALID_DISTANCES)}, got {self.distance!r}")
        if not self.collection_name or not self.collection_name.strip():
            raise ValueError("collection_name must be a non-empty string")

    @classmethod
    def from_env(cls, **overrides: object) -> QdrantConfig:
        url = str(overrides.get("url") or os.environ.get("QDRANT_URL", "http://localhost:6333")).strip().rstrip("/")
        raw_key = overrides.get("api_key") or os.environ.get("QDRANT_API_KEY")
        api_key = str(raw_key).strip() if raw_key else None
        if api_key == "":
            api_key = None
        timeout = int(overrides.get("timeout") or os.environ.get("QDRANT_TIMEOUT", "30"))
        vector_size = int(overrides.get("vector_size") or os.environ.get("QDRANT_VECTOR_SIZE", "1536"))
        collection_name = str(overrides.get("collection_name") or os.environ.get("QDRANT_COLLECTION_NAME", "knowledge_base")).strip()
        distance = str(overrides.get("distance") or os.environ.get("QDRANT_DISTANCE", "Cosine")).strip()
        return cls(url=url, api_key=api_key, timeout=timeout, vector_size=vector_size, collection_name=collection_name, distance=distance)


def load_qdrant_config(**overrides: object) -> QdrantConfig:
    return QdrantConfig.from_env(**overrides)
