"""
Formatters: JSON for file, plain (or color) for console.
"""
from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from typing import Any, Optional


class JsonFormatter(logging.Formatter):
    """
    Format log records as one JSON object per line (JSON Lines).
    Production-friendly for aggregation and parsing.
    """

    def __init__(
        self,
        *,
        include_extra: bool = True,
        timestamp_key: str = "timestamp",
        level_key: str = "level",
        logger_key: str = "logger",
        message_key: str = "message",
    ) -> None:
        super().__init__()
        self.include_extra = include_extra
        self.timestamp_key = timestamp_key
        self.level_key = level_key
        self.logger_key = logger_key
        self.message_key = message_key

    def format(self, record: logging.LogRecord) -> str:
        log_dict: dict[str, Any] = {
            self.timestamp_key: _utc_iso(record.created),
            self.level_key: record.levelname,
            self.logger_key: record.name,
            self.message_key: record.getMessage(),
        }
        if record.exc_info:
            log_dict["exception"] = "".join(
                traceback.format_exception(*record.exc_info)
            ).strip()
        if record.pathname:
            log_dict["pathname"] = record.pathname
        if record.lineno:
            log_dict["lineno"] = record.lineno
        if self.include_extra and getattr(record, "extra", None):
            log_dict["extra"] = record.extra
        return json.dumps(log_dict, default=str, ensure_ascii=False)


def _utc_iso(created: float) -> str:
    return datetime.fromtimestamp(created, tz=timezone.utc).isoformat()


class PlainConsoleFormatter(logging.Formatter):
    """Human-readable format for console."""

    def __init__(
        self,
        fmt: Optional[str] = None,
        datefmt: Optional[str] = None,
    ) -> None:
        if fmt is None:
            fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        if datefmt is None:
            datefmt = "%Y-%m-%d %H:%M:%S"
        super().__init__(fmt=fmt, datefmt=datefmt)
