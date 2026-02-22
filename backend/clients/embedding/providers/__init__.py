"""Embedding provider implementations – auto-register on import."""
from backend.clients.embedding.registry import default_registry
from backend.clients.embedding.providers.openai import openai_builder
from backend.clients.embedding.providers.gemini import gemini_builder

default_registry.register("openai", openai_builder)
default_registry.register("gemini", gemini_builder)
