"""LLM provider implementations – auto-register on import."""
from backend.clients.llm.registry import default_registry
from backend.clients.llm.providers.openai import openai_builder
from backend.clients.llm.providers.gemini import gemini_builder

default_registry.register("openai", openai_builder)
default_registry.register("gemini", gemini_builder)
