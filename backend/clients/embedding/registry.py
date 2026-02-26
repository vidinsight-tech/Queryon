"""
Embedding provider registry: map provider name → build client from config dict.
"""
from __future__ import annotations

from typing import Any, Callable, Dict

from .base import BaseEmbeddingClient


class EmbeddingRegistry:
    """Maps provider id to a builder that takes config dict and returns BaseEmbeddingClient."""

    def __init__(self) -> None:
        self._builders: Dict[str, Callable[[Dict[str, Any]], BaseEmbeddingClient]] = {}

    def register(
        self,
        provider: str,
        builder: Callable[[Dict[str, Any]], BaseEmbeddingClient],
    ) -> None:
        """Register a builder for this provider. builder(config_dict) -> BaseEmbeddingClient."""
        self._builders[provider] = builder

    def get(self, provider: str) -> Callable[[Dict[str, Any]], BaseEmbeddingClient] | None:
        """Return the builder for this provider, or None."""
        return self._builders.get(provider)

    def build(self, provider: str, config: Dict[str, Any]) -> BaseEmbeddingClient:
        """Build a client for this provider. Raises KeyError if unknown provider."""
        builder = self._builders.get(provider)
        if builder is None:
            raise KeyError(
                f"Unknown embedding provider: {provider!r}. Registered: {list(self._builders)}"
            )
        return builder(config)


default_registry = EmbeddingRegistry()

from backend.clients.embedding.providers.openai import openai_builder  # noqa: E402
from backend.clients.embedding.providers.gemini import gemini_builder  # noqa: E402

default_registry.register("openai", openai_builder)
default_registry.register("gemini", gemini_builder)
