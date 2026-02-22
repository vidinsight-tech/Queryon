"""Uzantı → parser. Kayıtlı parser'lar tek format (ParsedContent) döner."""
from __future__ import annotations

from typing import Dict, TYPE_CHECKING

from backend.core.exceptions import UnsupportedFileTypeError

if TYPE_CHECKING:
    from backend.rag.parsers.base import BaseParser

_registry: Dict[str, "BaseParser"] = {}


def register_parser(parser: "BaseParser") -> None:
    """Parser'ı desteklediği tüm uzantılar için kaydeder."""
    for ext in parser.supported_extensions:
        _registry[ext.lower().lstrip(".")] = parser


def get_parser(extension: str) -> "BaseParser":
    """Uzantıya göre parser döner. .pdf, pdf kabul edilir."""
    key = extension.lower().strip().lstrip(".")
    if not key:
        raise UnsupportedFileTypeError("Dosya uzantısı belirtilmedi.")
    parser = _registry.get(key)
    if parser is None:
        raise UnsupportedFileTypeError(
            f"Desteklenmeyen dosya tipi: .{key}. Kayıtlı: {sorted(_registry.keys())}."
        )
    return parser


def list_supported_extensions() -> tuple[str, ...]:
    """Desteklenen tüm uzantıları döner."""
    return tuple(sorted(_registry.keys()))
