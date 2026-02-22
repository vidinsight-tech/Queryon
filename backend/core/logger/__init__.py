"""
Project logger: rotating file (JSON) + console, easy to configure.

Usage:
    from backend.core.logger import get_logger, configure, LoggerConfig

    # Configure once at startup (optional; from_env() if not called)
    configure(LoggerConfig(level="DEBUG", log_dir="/var/log/myapp", log_file_basename="myapp"))

    # Or from env: LOG_LEVEL, LOG_DIR, LOG_FILE_BASENAME, LOG_MAX_BYTES, LOG_BACKUP_COUNT, etc.
    configure()  # uses LoggerConfig.from_env()

    logger = get_logger(__name__)
    logger.info("Started")

    # Build handlers on demand for custom loggers
    from backend.core.logger import build_rotating_file_handler, build_console_handler
    custom = logging.getLogger("custom")
    custom.addHandler(build_rotating_file_handler("/tmp/logs", basename="custom"))
    custom.addHandler(build_console_handler())
"""
from backend.core.logger.config import LoggerConfig
from backend.core.logger.formatters import JsonFormatter, PlainConsoleFormatter
from backend.core.logger.setup import (
    build_console_handler,
    build_rotating_file_handler,
    configure,
    get_logger,
)

__all__ = [
    "LoggerConfig",
    "JsonFormatter",
    "PlainConsoleFormatter",
    "configure",
    "get_logger",
    "build_rotating_file_handler",
    "build_console_handler",
]
