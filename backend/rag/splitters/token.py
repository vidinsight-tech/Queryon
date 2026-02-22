"""Token bazlı bölücü: tahmini token sayısı + overlap."""
from __future__ import annotations

from backend.rag.types import Chunk

from .base import BaseSplitter


def _count_tokens(text: str) -> int:
    """tiktoken varsa kullanır, yoksa boşlukla split."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        return len(text.split())


class TokenSplitter(BaseSplitter):
    """Metni token tahminine göre böler. Çıktı tek format: Chunk."""

    def __init__(
        self,
        chunk_size: int = 512,
        overlap: int = 64,
        separators: list[str] | None = None,
    ) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.separators = separators or ["\n\n", "\n", ". ", " ", ""]

    def split(self, text: str, metadata: dict | None = None) -> list[Chunk]:
        if not text or not text.strip():
            return []
        meta = metadata or {}
        pieces = self._split_recursive(text, self.separators)
        merged = self._merge_with_overlap(pieces)
        return self._chunks_from_pieces(
            [p for p in merged if p.strip()],
            meta,
            token_count_fn=_count_tokens,
        )

    def _split_recursive(self, text: str, separators: list[str]) -> list[str]:
        if _count_tokens(text) <= self.chunk_size:
            return [text]
        if not separators:
            return self._split_by_tokens(text)
        sep = separators[0]
        rest = separators[1:]
        if sep == "":
            return self._split_by_tokens(text)
        parts = text.split(sep)
        result = []
        current = ""
        for part in parts:
            candidate = current + (sep if current else "") + part
            if _count_tokens(candidate) <= self.chunk_size:
                current = candidate
            else:
                if current:
                    result.append(current)
                if _count_tokens(part) <= self.chunk_size:
                    current = part
                else:
                    result.extend(self._split_recursive(part, rest))
                    current = ""
        if current:
            result.append(current)
        return result

    def _split_by_tokens(self, text: str) -> list[str]:
        words = text.split()
        out = []
        current = []
        n = 0
        for w in words:
            current.append(w)
            n += 1
            if n >= self.chunk_size:
                out.append(" ".join(current))
                overlap_start = max(0, len(current) - self.overlap)
                current = current[overlap_start:]
                n = len(current)
        if current:
            out.append(" ".join(current))
        return out

    def _merge_with_overlap(self, pieces: list[str]) -> list[str]:
        if not pieces:
            return []
        out = [pieces[0]]
        for p in pieces[1:]:
            if _count_tokens(out[-1]) + _count_tokens(p) <= self.chunk_size:
                out[-1] = out[-1] + " " + p
            else:
                tail = out[-1].split()
                keep = tail[-self.overlap:] if len(tail) >= self.overlap else tail
                out[-1] = " ".join(tail[: len(tail) - len(keep)])
                out.append(" ".join(keep) + " " + p)
        return [x for x in out if x.strip()]
