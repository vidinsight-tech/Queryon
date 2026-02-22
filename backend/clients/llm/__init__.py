"""
LLM clients: base, config, registry.

Provider kaydı: default_registry.register(provider, builder).
DB ile kullanım: backend.services.LLMService.
"""
from backend.clients.llm.base import BaseLLMClient, LLMMessage
from backend.clients.llm.config import LLMConfig
from backend.clients.llm.registry import LLMRegistry, default_registry

__all__ = [
    "BaseLLMClient",
    "LLMMessage",
    "LLMConfig",
    "LLMRegistry",
    "default_registry",
]
