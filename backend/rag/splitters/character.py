"""Karakter bazlı bölücü: sabit karakter sayısı + overlap."""
from __future__ import annotations

from backend.rag.types import Chunk

from .base import BaseSplitter


class CharacterSplitter(BaseSplitter):
    """Metni karakter sayısına göre böler. Çıktı tek format: Chunk."""

    def __init__(self, chunk_size: int = 500, overlap: int = 50) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def split(self, text: str, metadata: dict | None = None) -> list[Chunk]:
        if not text or not text.strip():
            return []
        meta = metadata or {}
        pieces = []
        start = 0
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            content = text[start:end]
            if content.strip():
                pieces.append(content)
            start = end - self.overlap if end < len(text) else len(text)
        return self._chunks_from_pieces(pieces, meta, token_count_fn=lambda _: 0)
