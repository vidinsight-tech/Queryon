"""Parser arayüzü: dosya/bytes → ParsedContent."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Union

from backend.rag.types import ParsedContent

PathOrBytes = Union[str, Path, bytes]


class BaseParser(ABC):
    """Tek dosya tipi: extract → ParsedContent (tek format)."""

    @property
    @abstractmethod
    def supported_extensions(self) -> tuple[str, ...]:
        """Desteklenen uzantılar: 'pdf', 'docx' vb."""

    @property
    def source_type(self) -> str:
        """Kaynak tipi (ParsedContent.source_type)."""
        exts = self.supported_extensions
        return exts[0] if exts else "unknown"

    @abstractmethod
    def extract(self, source: PathOrBytes, filename_hint: str | None = None) -> ParsedContent:
        """Kaynaktan metni çıkarır. Hata için core.exceptions.ExtractionError."""
