"""
backend.infra.database.models – SQLAlchemy 2.0 ORM models.

Exports Base, mixins, and all model classes.
"""
from backend.infra.database.models.base import Base, TimestampMixin, _uuid_pk
from backend.infra.database.models.conversation import Conversation, Message, MessageEvent
from backend.infra.database.models.embedding import Embedding
from backend.infra.database.models.knowledge import DocumentChunk, KnowledgeDocument
from backend.infra.database.models.llm import LLM

__all__ = [
    "Base",
    "TimestampMixin",
    "_uuid_pk",
    "LLM",
    "Embedding",
    "KnowledgeDocument",
    "DocumentChunk",
    "Conversation",
    "Message",
    "MessageEvent",
]
