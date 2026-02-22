"""
Embedding clients: base, config, registry.

Provider kaydı: default_registry.register(provider, builder).
DB ile kullanım: backend.services.EmbeddingService.
"""
from .base import BaseEmbeddingClient
from .config import EmbeddingConfig
from .registry import EmbeddingRegistry, default_registry

__all__ = [
    "BaseEmbeddingClient",
    "EmbeddingConfig",
    "EmbeddingRegistry",
    "default_registry",
]
