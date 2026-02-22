"""PDF metin çıkarma (pypdf)."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Union

from pypdf import PdfReader

from backend.core.exceptions import ExtractionError
from backend.rag.parsers.base import BaseParser, PathOrBytes
from backend.rag.types import ParsedContent


class PdfParser(BaseParser):
    @property
    def supported_extensions(self) -> tuple[str, ...]:
        return ("pdf",)

    def extract(self, source: PathOrBytes, filename_hint: str | None = None) -> ParsedContent:
        if isinstance(source, bytes):
            stream = BytesIO(source)
        else:
            stream = Path(source)
        try:
            reader = PdfReader(stream)
        except Exception as e:
            raise ExtractionError(f"PDF açılamadı: {e}", cause=e) from e
        parts = []
        for page in reader.pages:
            try:
                t = page.extract_text()
                if t:
                    parts.append(t)
            except Exception:
                continue
        text = "\n".join(parts) if parts else ""
        return ParsedContent(text=text, source_type="pdf", metadata={})
