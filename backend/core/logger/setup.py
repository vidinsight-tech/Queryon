"""
Logger setup: attach rotating file (JSON) and console handlers from config.
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

from backend.core.logger.config import LoggerConfig
from backend.core.logger.formatters import JsonFormatter, PlainConsoleFormatter


# Module-level default config; can be replaced before first get_logger call
_default_config: Optional[LoggerConfig] = None


def configure(config: Optional[LoggerConfig] = None) -> None:
    """
    Configure the root logger (or named root) with the given config.
    If config is None, uses LoggerConfig.from_env().
    Call once at application startup.
    """
    global _default_config
    if config is None:
        config = LoggerConfig.from_env()
    _default_config = config

    root_name = config.root_name or "backend"
    root = logging.getLogger(root_name)
    root.setLevel(getattr(logging, config.level.upper(), logging.INFO))

    # Avoid duplicate handlers when reconfigured (e.g. in tests)
    root.handlers.clear()

    if config.console:
        console = logging.StreamHandler()
        console.setLevel(getattr(logging, config.level.upper(), logging.INFO))
        console.setFormatter(PlainConsoleFormatter())
        root.addHandler(console)

    if config.file_rotating and (config.log_dir and config.log_dir.strip()):
        try:
            os.makedirs(config.log_dir, exist_ok=True)
        except OSError:
            root.warning("Could not create log dir %s, skipping file handler", config.log_dir)
        else:
            path = os.path.join(config.log_dir, f"{config.log_file_basename}.log")
            file_handler = RotatingFileHandler(
                path,
                maxBytes=config.max_bytes,
                backupCount=config.backup_count,
                encoding="utf-8",
            )
            file_handler.setLevel(getattr(logging, config.level.upper(), logging.INFO))
            file_handler.setFormatter(JsonFormatter())
            root.addHandler(file_handler)

    root.propagate = False


def get_logger(name: str, config: Optional[LoggerConfig] = None) -> logging.Logger:
    """
    Return a logger for the given name. If configure() was never called,
    calls configure(config or from_env()) so that the root has handlers.
    Use get_logger(__name__) from backend packages so names stay under the configured root.
    """
    global _default_config
    if _default_config is None:
        configure(config)
    return logging.getLogger(name)


def build_rotating_file_handler(
    log_dir: str,
    basename: str = "app",
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 5,
    level: str = "INFO",
) -> RotatingFileHandler:
    """Build a standalone rotating file handler with JSON formatter (for custom use)."""
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, f"{basename}.log")
    handler = RotatingFileHandler(
        path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler.setFormatter(JsonFormatter())
    return handler


def build_console_handler(
    level: str = "INFO",
    fmt: Optional[str] = None,
) -> logging.StreamHandler:
    """Build a standalone console handler with plain formatter (for custom use)."""
    handler = logging.StreamHandler()
    handler.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler.setFormatter(PlainConsoleFormatter(fmt=fmt))
    return handler
