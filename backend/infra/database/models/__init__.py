"""
backend.infra.database.models – SQLAlchemy 2.0 ORM models.

Exports Base, mixins, and all model classes.
"""
from backend.infra.database.models.base import Base, TimestampMixin, _uuid_pk
from backend.infra.database.models.conversation import Conversation, Message, MessageEvent
from backend.infra.database.models.embedding import Embedding
from backend.infra.database.models.embedding_model_config import EmbeddingModelConfig
from backend.infra.database.models.knowledge import DocumentChunk, KnowledgeDocument
from backend.infra.database.models.llm import LLM
from backend.infra.database.models.tool_config import OrchestratorConfigModel, RagConfigModel, ToolConfig
from backend.infra.database.models.appointment import Appointment
from backend.infra.database.models.calendar_block import CalendarBlock
from backend.infra.database.models.calendar_resource import CalendarResource
from backend.infra.database.models.order import Order

__all__ = [
    "Base",
    "TimestampMixin",
    "_uuid_pk",
    "LLM",
    "Embedding",
    "EmbeddingModelConfig",
    "KnowledgeDocument",
    "DocumentChunk",
    "Conversation",
    "Message",
    "MessageEvent",
    "OrchestratorConfigModel",
    "RagConfigModel",
    "ToolConfig",
    "Appointment",
    "CalendarBlock",
    "CalendarResource",
    "Order",
]
