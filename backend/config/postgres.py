"""
backend.config.postgres – PostgreSQL connection config (dataclass + validators).

Env vars: DATABASE_URL, DB_POOL_SIZE, DB_MAX_OVERFLOW, DB_POOL_TIMEOUT, DB_POOL_RECYCLE, DB_ECHO.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _validate_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ValueError("DATABASE_URL is required and must be non-empty")
    if not (
        url.startswith("postgresql://")
        or url.startswith("postgres://")
        or ("+asyncpg" in url and "postgresql" in url)
    ):
        raise ValueError(
            "DATABASE_URL must start with postgresql:// or postgres:// "
            "(or postgresql+asyncpg://)"
        )
    return url


def _validate_positive_int(value: int, name: str, min_val: int = 1) -> int:
    if not isinstance(value, int) or value < min_val:
        raise ValueError(f"{name} must be an integer >= {min_val}, got {value!r}")
    return value


def _validate_nonnegative_int(value: int, name: str) -> int:
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer, got {value!r}")
    return value


@dataclass(frozen=True)
class PostgresConfig:
    """
    PostgreSQL connection and pool configuration.

    All fields are validated on construction. Use load_postgres_config()
    to build from environment variables.
    """

    url: str
    """DSN (postgresql:// or postgres://). Converted to postgresql+asyncpg in engine."""

    pool_size: int = 10
    """Number of connections to keep in the pool."""

    max_overflow: int = 20
    """Extra connections allowed above pool_size."""

    pool_timeout: int = 30
    """Seconds to wait for a connection from the pool."""

    pool_recycle: int = 1800
    """Seconds after which a connection is recycled (e.g. 30 min)."""

    echo: bool = False
    """Log SQL statements (debug)."""

    application_name: str = "queryon-backend"
    """server_settings.application_name."""

    def __post_init__(self) -> None:
        _validate_url(self.url)
        _validate_positive_int(self.pool_size, "pool_size")
        _validate_nonnegative_int(self.max_overflow, "max_overflow")
        _validate_positive_int(self.pool_timeout, "pool_timeout")
        _validate_positive_int(self.pool_recycle, "pool_recycle")
        if not isinstance(self.echo, bool):
            raise ValueError("echo must be a boolean")
        if not isinstance(self.application_name, str) or not self.application_name.strip():
            raise ValueError("application_name must be a non-empty string")

    @classmethod
    def from_env(cls, **overrides: object) -> PostgresConfig:
        """
        Build config from environment variables.

        Env:
            DATABASE_URL          – default postgresql://localhost/queryon
            DB_POOL_SIZE          – default 10
            DB_MAX_OVERFLOW       – default 20
            DB_POOL_TIMEOUT       – default 30
            DB_POOL_RECYCLE       – default 1800
            DB_ECHO               – "1" / "true" / "yes" → True
            DB_APPLICATION_NAME   – default queryon-backend

        Overrides (keyword args) take precedence over env.
        """
        raw_url = overrides.get("url")
        if raw_url is None:
            raw_url = os.environ.get("DATABASE_URL", "postgresql://localhost/queryon")
        url = _validate_url(str(raw_url).strip())

        _env_int = {
            "pool_size": "DB_POOL_SIZE",
            "max_overflow": "DB_MAX_OVERFLOW",
            "pool_timeout": "DB_POOL_TIMEOUT",
            "pool_recycle": "DB_POOL_RECYCLE",
        }

        def _int(attr: str, default: int) -> int:
            v = overrides.get(attr)
            if v is not None:
                return int(v)
            return int(os.environ.get(_env_int[attr], default))

        def _bool(attr: str, default: bool) -> bool:
            v = overrides.get(attr)
            if v is not None:
                return bool(v) if not isinstance(v, str) else str(v).lower() in ("1", "true", "yes")
            raw = os.environ.get("DB_ECHO", "").strip().lower()
            return raw in ("1", "true", "yes") if raw else default

        app_name = overrides.get("application_name") or os.environ.get("DB_APPLICATION_NAME", "queryon-backend")
        return cls(
            url=url,
            pool_size=_int("pool_size", 10),
            max_overflow=_int("max_overflow", 20),
            pool_timeout=_int("pool_timeout", 30),
            pool_recycle=_int("pool_recycle", 1800),
            echo=_bool("echo", False),
            application_name=str(app_name),
        )


def load_postgres_config(**overrides: object) -> PostgresConfig:
    """
    Load and validate PostgreSQL config from environment (with optional overrides).

    Returns:
        Validated PostgresConfig. Raises ValueError on invalid env/values.
    """
    return PostgresConfig.from_env(**overrides)
