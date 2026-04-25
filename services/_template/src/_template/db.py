"""Async SQLAlchemy engine + session factory + declarative base.

Phase 0 ships the schema skeleton; Phase 1+ adds the migrations as Alembic
revisions under each service's `migrations/` dir.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base. Service-specific models inherit from here."""


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine(database_url: str) -> AsyncEngine:
    global _engine, _session_factory  # noqa: PLW0603
    if _engine is None:
        # asyncpg uses postgresql+asyncpg:// URLs.
        url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)
        _engine = create_async_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


@asynccontextmanager
async def get_session(database_url: str) -> AsyncIterator[AsyncSession]:
    if _session_factory is None:
        get_engine(database_url)
    assert _session_factory is not None
    async with _session_factory() as session:
        yield session
