"""TXT parser. UTF-8, fallback latin-1."""
from __future__ import annotations

from pathlib import Path
from typing import Union

from backend.core.exceptions import ExtractionError
from backend.rag.parsers.base import BaseParser, PathOrBytes
from backend.rag.types import ParsedContent


class TxtParser(BaseParser):
    @property
    def supported_extensions(self) -> tuple[str, ...]:
        return ("txt", "text")

    def extract(self, source: PathOrBytes, filename_hint: str | None = None) -> ParsedContent:
        if isinstance(source, bytes):
            text = self._decode(source)
        else:
            path = Path(source)
            try:
                text = self._decode(path.read_bytes())
            except OSError as e:
                raise ExtractionError(f"TXT okunamadı: {path}", cause=e) from e
        return ParsedContent(text=text, source_type="txt", metadata={})

    def _decode(self, raw: bytes) -> str:
        for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        raise ExtractionError("TXT encoding çözülemedi (utf-8, cp1252, latin-1 denendi).")
