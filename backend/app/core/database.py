"""
app/core/database.py
────────────────────
Async SQLAlchemy 2.x engine + session factory for PostgreSQL (asyncpg).

Connection pool is kept tiny (size=2, overflow=5) to stay within
Raspberry Pi Zero 2 W's 512 MB RAM budget.

Usage inside endpoints / services:
    async for db in get_db():
        result = await db.execute(...)
"""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

log = structlog.get_logger(__name__)


# ── Shared declarative base ───────────────────────────────────────────────────
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


# ── Private singletons ────────────────────────────────────────────────────────
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def _get_engine() -> AsyncEngine:
    """Lazy-create and return the async engine singleton."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            pool_size=2,            # tiny pool – Pi Zero 2 W has 512 MB RAM
            max_overflow=5,
            pool_pre_ping=True,     # detect and recover stale connections
            pool_recycle=3600,      # recycle hourly to avoid idle-disconnect
        )
    return _engine


def _get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Lazy-create and return the session factory singleton."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,  # safe for async; prevents lazy-load errors
            autoflush=False,
        )
    return _session_factory


# ── Lifecycle helpers (called by lifespan) ────────────────────────────────────

async def init_db() -> None:
    """
    Verify DB connectivity at startup.
    Table creation is handled by Alembic — not done here.
    """
    engine = _get_engine()
    try:
        async with engine.begin() as conn:
            await conn.run_sync(lambda _: None)  # no-op connectivity check
        log.info("database.init_db.ok", url=settings.DATABASE_URL.split("@")[-1])
    except Exception as exc:
        log.error("database.init_db.failed", error=str(exc))
        raise


async def close_db() -> None:
    """Dispose all pool connections on shutdown."""
    global _engine
    if _engine:
        await _engine.dispose()
        log.info("database.close_db.ok")
        _engine = None


# ── FastAPI dependency ────────────────────────────────────────────────────────

async def get_db() -> AsyncSession:  # type: ignore[return]  # generator
    """
    FastAPI dependency: yield an async DB session, commit on success,
    rollback on any exception, and always close.

    Usage:
        @router.get("/")
        async def route(db: AsyncSession = Depends(get_db)):
            ...
    """
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
