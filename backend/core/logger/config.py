"""
Logger configuration. Easy to configure via code or env.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class LoggerConfig:
    """
    Configuration for the project logger.

    Use LoggerConfig.from_env() for env-based config, or build explicitly.
    """

    # Level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    level: str = "INFO"
    # Log directory for rotating file (if None, file handler is skipped)
    log_dir: Optional[str] = None
    # Basename for log file (e.g. "app" -> app.log)
    log_file_basename: str = "app"
    # Max bytes per file before rotation
    max_bytes: int = 5 * 1024 * 1024  # 5 MB
    # Number of backup files to keep
    backup_count: int = 5
    # Root logger name (handlers attached here; children inherit)
    root_name: str = ""
    # Enable console handler
    console: bool = True
    # Enable rotating file handler (only if log_dir is set)
    file_rotating: bool = True
    # Console format style: "plain" (default) or "color" (if supported)
    console_style: str = "plain"

    @classmethod
    def from_env(
        cls,
        *,
        level_var: str = "LOG_LEVEL",
        log_dir_var: str = "LOG_DIR",
        log_file_var: str = "LOG_FILE_BASENAME",
        max_bytes_var: str = "LOG_MAX_BYTES",
        backup_count_var: str = "LOG_BACKUP_COUNT",
        root_name_var: str = "LOG_ROOT_NAME",
        console_var: str = "LOG_CONSOLE",
        file_rotating_var: str = "LOG_FILE_ROTATING",
    ) -> "LoggerConfig":
        """Build config from environment variables."""
        level = os.environ.get(level_var, "INFO").upper()
        log_dir = os.environ.get(log_dir_var) or None
        log_file_basename = os.environ.get(log_file_var, "app")
        max_bytes = int(os.environ.get(max_bytes_var, "5242880"))  # 5MB
        backup_count = int(os.environ.get(backup_count_var, "5"))
        root_name = os.environ.get(root_name_var, "")
        console = os.environ.get(console_var, "true").lower() in ("1", "true", "yes")
        file_rotating = os.environ.get(file_rotating_var, "true").lower() in (
            "1",
            "true",
            "yes",
        )
        return cls(
            level=level,
            log_dir=log_dir,
            log_file_basename=log_file_basename,
            max_bytes=max_bytes,
            backup_count=backup_count,
            root_name=root_name,
            console=console,
            file_rotating=file_rotating,
        )

    def with_overrides(
        self,
        *,
        level: Optional[str] = None,
        log_dir: Optional[str] = None,
        log_file_basename: Optional[str] = None,
        max_bytes: Optional[int] = None,
        backup_count: Optional[int] = None,
        root_name: Optional[str] = None,
        console: Optional[bool] = None,
        file_rotating: Optional[bool] = None,
        console_style: Optional[str] = None,
    ) -> "LoggerConfig":
        """Return a new config with the given overrides (for immutability)."""
        return LoggerConfig(
            level=level if level is not None else self.level,
            log_dir=log_dir if log_dir is not None else self.log_dir,
            log_file_basename=log_file_basename or self.log_file_basename,
            max_bytes=max_bytes if max_bytes is not None else self.max_bytes,
            backup_count=backup_count if backup_count is not None else self.backup_count,
            root_name=root_name if root_name is not None else self.root_name,
            console=console if console is not None else self.console,
            file_rotating=file_rotating if file_rotating is not None else self.file_rotating,
            console_style=console_style or self.console_style,
        )
