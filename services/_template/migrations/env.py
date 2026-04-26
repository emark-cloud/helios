"""Alembic env. Async engine, autogenerate enabled.

Each service that wants its own migrations sets `ALEMBIC_TARGET_METADATA`
to its own `Base.metadata` before invoking alembic.
"""

import asyncio
import os
from logging.config import fileConfig

from _template.db import Base as MetadataBase
from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = MetadataBase.metadata

# Allow override via env var for service-local migrations.
DATABASE_URL = os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
if DATABASE_URL and "postgresql+asyncpg" not in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    config_section = config.get_section(config.config_ini_section, {})
    config_section["sqlalchemy.url"] = DATABASE_URL or ""
    connectable = async_engine_from_config(
        config_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
