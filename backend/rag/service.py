"""
RAG doküman servisi: parse + split tek giriş noktası.

Verilen dosya/bytes → tek formatta ParsedContent; istenen splitter ile Chunk listesi.
"""
from __future__ import annotations

from pathlib import Path

from backend.rag.parsers import get_parser, list_supported_extensions
from backend.rag.parsers.base import PathOrBytes
from backend.rag.splitters import CharacterSplitter, TokenSplitter
from backend.rag.types import Chunk, ParsedContent


class RAGDocService:
    """Parse (PDF, DOCX, DOC, TXT) ve split (token / character) tek servis."""

    def __init__(
        self,
        token_chunk_size: int = 512,
        token_overlap: int = 64,
        char_chunk_size: int = 500,
        char_overlap: int = 50,
    ) -> None:
        self._token_splitter = TokenSplitter(chunk_size=token_chunk_size, overlap=token_overlap)
        self._char_splitter = CharacterSplitter(chunk_size=char_chunk_size, overlap=char_overlap)

    def parse(self, source: PathOrBytes, filename_hint: str | None = None) -> ParsedContent:
        """Dosya veya bytes → tek format ParsedContent. bytes ise filename_hint gerekli."""
        ext = self._extension(source, filename_hint)
        if not ext and isinstance(source, bytes):
            from backend.core.exceptions import UnsupportedFileTypeError
            raise UnsupportedFileTypeError("bytes kaynağı için filename_hint (uzantılı dosya adı) gerekli.")
        parser = get_parser(ext)
        return parser.extract(source, filename_hint=filename_hint)

    def chunk(
        self,
        parsed: ParsedContent,
        method: str = "token",
        **kwargs: object,
    ) -> list[Chunk]:
        """ParsedContent → Chunk listesi. method: 'token' | 'character'."""
        meta = dict(parsed.metadata)
        meta["source_type"] = parsed.source_type
        if method == "character":
            size = kwargs.get("chunk_size", self._char_splitter.chunk_size)
            overlap = kwargs.get("overlap", self._char_splitter.overlap)
            splitter = CharacterSplitter(chunk_size=size, overlap=overlap)
        else:
            size = kwargs.get("chunk_size", self._token_splitter.chunk_size)
            overlap = kwargs.get("overlap", self._token_splitter.overlap)
            splitter = TokenSplitter(chunk_size=size, overlap=overlap)
        return splitter.split(parsed.text, metadata=meta)

    def parse_and_chunk(
        self,
        source: PathOrBytes,
        method: str = "token",
        filename_hint: str | None = None,
        **kwargs: object,
    ) -> list[Chunk]:
        """Dosya/bytes → parse → chunk. Tek çağrıda hazır chunk listesi."""
        parsed = self.parse(source, filename_hint=filename_hint)
        return self.chunk(parsed, method=method, **kwargs)

    @staticmethod
    def _extension(source: PathOrBytes, filename_hint: str | None) -> str:
        if filename_hint:
            return Path(filename_hint).suffix.lstrip(".")
        if isinstance(source, (str, Path)):
            return Path(source).suffix.lstrip(".")
        return ""

    @staticmethod
    def supported_extensions() -> tuple[str, ...]:
        """Desteklenen dosya uzantılarını döner."""
        return list_supported_extensions()
