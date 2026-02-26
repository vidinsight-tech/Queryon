"""
LLM provider registry: map provider name -> build client from config dict.

Register your provider, then use the registry (or factory) to build clients from DB config.
"""
from __future__ import annotations

from typing import Any, Callable, Dict

from backend.clients.llm.base import BaseLLMClient


class LLMRegistry:
    """Maps provider id to a builder that takes config dict and returns BaseLLMClient."""

    def __init__(self) -> None:
        self._builders: Dict[str, Callable[[Dict[str, Any]], BaseLLMClient]] = {}

    def register(self, provider: str, builder: Callable[[Dict[str, Any]], BaseLLMClient]) -> None:
        """Register a builder for this provider. builder(config_dict) -> BaseLLMClient."""
        self._builders[provider] = builder

    def get(self, provider: str) -> Callable[[Dict[str, Any]], BaseLLMClient] | None:
        """Return the builder for this provider, or None."""
        return self._builders.get(provider)

    def build(self, provider: str, config: Dict[str, Any]) -> BaseLLMClient:
        """Build a client for this provider with the given config. Raises KeyError if unknown provider."""
        builder = self._builders.get(provider)
        if builder is None:
            raise KeyError(f"Unknown LLM provider: {provider!r}. Registered: {list(self._builders)}")
        return builder(config)


# Default registry with all built-in providers pre-registered.
default_registry = LLMRegistry()

from backend.clients.llm.providers.openai import openai_builder  # noqa: E402
from backend.clients.llm.providers.gemini import gemini_builder  # noqa: E402

default_registry.register("openai", openai_builder)
default_registry.register("gemini", gemini_builder)