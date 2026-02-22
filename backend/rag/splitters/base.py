"""Splitter arayüzü: metin → Chunk listesi (tek format)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable

from backend.rag.types import Chunk


class BaseSplitter(ABC):
    """Tüm splitter'lar aynı çıktıyı üretir: list[Chunk]."""

    @abstractmethod
    def split(self, text: str, metadata: dict | None = None) -> list[Chunk]:
        """
        Metni böler, tek format Chunk listesi döner.

        Args:
            text: Bölünecek metin.
            metadata: Chunk'lara kopyalanacak ek bilgi.

        Returns:
            content, chunk_index, token_count, char_count, metadata alanlı Chunk listesi.
        """
        ...

    def _chunks_from_pieces(
        self,
        pieces: list[str],
        metadata: dict | None,
        *,
        token_count_fn: Callable[[str], int] = lambda t: 0,
    ) -> list[Chunk]:
        """Parça listesinden Chunk listesi üretir (ortak yardımcı)."""
        meta = dict(metadata or {})
        result = []
        for i, piece in enumerate(pieces):
            s = piece.strip()
            if not s:
                continue
            result.append(
                Chunk(
                    content=s,
                    chunk_index=len(result),
                    token_count=token_count_fn(piece),
                    char_count=len(piece),
                    metadata=meta,
                )
            )
        return result
