"""Eski Word .doc metin çıkarma (textract; sistem bağımlılığı olabilir)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Union

from backend.core.exceptions import ExtractionError
from backend.rag.parsers.base import BaseParser, PathOrBytes
from backend.rag.types import ParsedContent


class DocParser(BaseParser):
    @property
    def supported_extensions(self) -> tuple[str, ...]:
        return ("doc",)

    def extract(self, source: PathOrBytes, filename_hint: str | None = None) -> ParsedContent:
        try:
            import textract
        except ImportError as e:
            raise ExtractionError(
                ".doc desteği için 'textract' kurulmalı. Sistem bağımlılıkları gerekebilir.",
                cause=e,
            ) from e

        def to_str(data: bytes | str) -> str:
            if isinstance(data, str):
                return data.strip()
            return data.decode("utf-8", errors="replace").strip()

        if isinstance(source, bytes):
            suffix = Path(filename_hint or "file.doc").suffix or ".doc"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                try:
                    f.write(source)
                    f.flush()
                    text = to_str(textract.process(f.name))
                finally:
                    os.unlink(f.name)
        else:
            path = Path(source)
            if not path.exists():
                raise ExtractionError(f"Dosya bulunamadı: {path}", cause=FileNotFoundError())
            try:
                text = to_str(textract.process(str(path)))
            except Exception as e:
                raise ExtractionError(f".doc okunamadı: {e}", cause=e) from e
        return ParsedContent(text=text, source_type="doc", metadata={})
