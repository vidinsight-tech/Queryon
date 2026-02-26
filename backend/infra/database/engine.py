"""
backend.infra.database.engine – Async SQLAlchemy 2.0 engine, session factory, get_db.

Pool tuned for load. Accepts PostgresConfig; if not provided, loads from env via load_postgres_config().

On first run, ensure_database_exists() can create the target database if it does not exist
(connects to "postgres", then CREATE DATABASE).
"""
from __future__ import annotations

import logging
import re
from collections.abc import AsyncGenerator
from urllib.parse import urlparse, urlunparse
from typing import TYPE_CHECKING, Optional

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from backend.infra.database.models.base import Base

# Ensure all ORM models are registered with Base.metadata before create_all()
import backend.infra.database.models  # noqa: F401
import backend.orchestrator.rules.models  # noqa: F401 — so init_db() creates orchestrator_rules too

if TYPE_CHECKING:
    from backend.config import PostgresConfig

logger = logging.getLogger(__name__)

# Veritabanı adı için izin verilen karakterler (SQL injection önlemi)
_DBNAME_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def _make_async_url(url: str) -> str:
    """Convert postgresql:// or postgres:// to postgresql+asyncpg://."""
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix) and "+asyncpg" not in url:
            return url.replace(prefix, "postgresql+asyncpg://", 1)
    return url


def _parse_db_name_and_postgres_url(url: str) -> tuple[str, str]:
    """URL'den hedef veritabanı adını ve 'postgres' bağlantı URL'ini çıkarır."""
    parsed = urlparse(url)
    path = (parsed.path or "/postgres").strip("/")
    dbname = (path.split("?")[0] or "postgres").strip()
    postgres_url = urlunparse((parsed.scheme, parsed.netloc, "/postgres", parsed.params, parsed.query, parsed.fragment))
    return dbname, postgres_url


async def ensure_database_exists(config: Optional["PostgresConfig"] = None) -> None:
    """
    Hedef veritabanı yoksa oluşturur (postgres'e bağlanıp CREATE DATABASE).
    İlk bağlantıda çağrılabilir; dbname sadece [a-zA-Z0-9_] ile güvenli kabul edilir.
    """
    if config is None:
        from backend.config import load_postgres_config
        config = load_postgres_config()
    dbname, postgres_url = _parse_db_name_and_postgres_url(config.url)
    if dbname == "postgres":
        return
    if not _DBNAME_PATTERN.match(dbname):
        logger.warning("ensure_database_exists: dbname %r güvenlik nedeniyle atlanıyor (sadece alfanumerik/alt çizgi)", dbname)
        return
    try:
        conn = await asyncpg.connect(postgres_url)
    except Exception as e:
        logger.debug("ensure_database_exists: postgres'e bağlanılamadı (%s), veritabanı oluşturma atlanıyor", e)
        return
    try:
        row = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", dbname)
        if row is None:
            await conn.execute(f'CREATE DATABASE "{dbname}"')
            logger.info("Veritabanı oluşturuldu: %s", dbname)
    finally:
        await conn.close()


def build_engine(
    config: Optional["PostgresConfig"] = None,
    *,
    echo: Optional[bool] = None,
    use_null_pool: bool = False,
) -> AsyncEngine:
    """
    Create and cache the async SQLAlchemy engine.

    Args:
        config: PostgresConfig (url, pool_size, etc.). If None, loaded from env.
        echo: Override SQL echo (default: use config.echo).
        use_null_pool: Use NullPool (e.g. for tests).
    """
    global _engine
    if _engine is not None:
        return _engine

    if config is None:
        from backend.config import load_postgres_config
        config = load_postgres_config()

    url = _make_async_url(config.url)
    connect_args: dict = {
        "server_settings": {
            "application_name": config.application_name,
            "jit": "off",
        }
    }
    do_echo = echo if echo is not None else config.echo

    if use_null_pool:
        _engine = create_async_engine(
            url,
            echo=do_echo,
            poolclass=NullPool,
            connect_args=connect_args,
        )
        logger.info("AsyncEngine created with NullPool (test mode)")
    else:
        _engine = create_async_engine(
            url,
            echo=do_echo,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
            pool_timeout=config.pool_timeout,
            pool_recycle=config.pool_recycle,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
        logger.info(
            "AsyncEngine created: pool_size=%d max_overflow=%d",
            config.pool_size, config.max_overflow,
        )
    return _engine


def build_session_factory(
    engine: Optional[AsyncEngine] = None,
) -> async_sessionmaker[AsyncSession]:
    """Create async session factory bound to engine."""
    global _session_factory
    if _session_factory is not None:
        return _session_factory
    if engine is None:
        engine = build_engine()
    _session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    logger.debug("AsyncSessionFactory created")
    return _session_factory


async def get_db(
    config: Optional["PostgresConfig"] = None,
) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yield a transactional AsyncSession (commit on success, rollback on error)."""
    engine = build_engine(config)
    session_factory = build_session_factory(engine)
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def _migrate_db(conn: AsyncConnection) -> None:
    """Add columns that were introduced after initial table creation.

    Uses ADD COLUMN IF NOT EXISTS so repeated runs are safe.
    This is intentionally simple DDL for dev/staging; use Alembic in production.
    """
    migrations = [
        # orchestrator_rules: flow / conditions columns added after initial release
        "ALTER TABLE orchestrator_rules ADD COLUMN IF NOT EXISTS flow_id VARCHAR(64)",
        "ALTER TABLE orchestrator_rules ADD COLUMN IF NOT EXISTS step_key VARCHAR(64)",
        "ALTER TABLE orchestrator_rules ADD COLUMN IF NOT EXISTS required_step VARCHAR(64)",
        "ALTER TABLE orchestrator_rules ADD COLUMN IF NOT EXISTS next_steps JSONB",
        "ALTER TABLE orchestrator_rules ADD COLUMN IF NOT EXISTS conditions JSONB",
        # appointments: event_time added for slot-based booking
        "ALTER TABLE appointments ADD COLUMN IF NOT EXISTS event_time TEXT",
        # appointments: human-readable reference number
        "ALTER TABLE appointments ADD COLUMN IF NOT EXISTS appt_number VARCHAR(20)",
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_appointments_appt_number ON appointments(appt_number)",
        # conversations: platform-specific contact identity
        "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS contact_username VARCHAR(255)",
        "CREATE INDEX IF NOT EXISTS ix_conversations_contact_username ON conversations(contact_username)",
    ]
    for stmt in migrations:
        try:
            await conn.execute(text(stmt))
        except Exception as exc:
            logger.warning("Migration statement skipped (%s): %s", exc.__class__.__name__, stmt)
    logger.info("Database migration complete")


async def init_db(
    config: Optional["PostgresConfig"] = None,
    *,
    drop_all: bool = False,
) -> None:
    """Create all ORM tables and run schema migrations.

    For dev/test only; use Alembic in production.
    """
    if config is None:
        from backend.config import load_postgres_config
        config = load_postgres_config()
    engine = build_engine(config)
    async with engine.begin() as conn:
        if drop_all:
            logger.warning("Dropping all ORM tables (drop_all=True)")
            await conn.run_sync(Base.metadata.drop_all)
        logger.info("Creating ORM tables")
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_db(conn)
    logger.info("Database initialised successfully")


async def get_raw_connection(
    config: Optional["PostgresConfig"] = None,
) -> AsyncGenerator[AsyncConnection, None]:
    """Yield a raw AsyncConnection from the pool (for DDL/bulk)."""
    engine = build_engine(config)
    async with engine.connect() as conn:
        yield conn


async def close_engine() -> None:
    """Dispose the connection pool. Call on app shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        logger.info("AsyncEngine disposed")
        _engine = None
        _session_factory = None
