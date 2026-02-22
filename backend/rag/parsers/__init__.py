"""Parsers: PDF, DOCX, DOC, TXT → ParsedContent."""
from backend.rag.parsers.base import BaseParser, PathOrBytes
from backend.rag.parsers.docx import DocxParser
from backend.rag.parsers.doc import DocParser
from backend.rag.parsers.pdf import PdfParser
from backend.rag.parsers.registry import get_parser, list_supported_extensions, register_parser
from backend.rag.parsers.txt import TxtParser

# Varsayılan parser'ları kaydet
register_parser(TxtParser())
register_parser(PdfParser())
register_parser(DocxParser())
register_parser(DocParser())

__all__ = [
    "BaseParser",
    "PathOrBytes",
    "TxtParser",
    "PdfParser",
    "DocxParser",
    "DocParser",
    "register_parser",
    "get_parser",
    "list_supported_extensions",
]
