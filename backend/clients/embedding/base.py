"""Embedding client interface: text → vector(s)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Union


class BaseEmbeddingClient(ABC):
    """Minimal embedding interface: text or list of texts → list of vectors."""

    @property
    @abstractmethod
    def provider(self) -> str:
        """Provider name (e.g. openai, gemini)."""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Concrete model id (e.g. text-embedding-3-small)."""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Output vector dimension for this model."""
        ...

    @abstractmethod
    async def embed(
        self,
        text: Union[str, List[str]],
        *,
        model: str | None = None,
    ) -> List[List[float]]:
        """Embed one or more texts. Returns one vector per input text."""
        ...

    @abstractmethod
    async def test_connection(self) -> bool:
        """Check that the client can reach the provider. Returns True if OK."""
        ...
