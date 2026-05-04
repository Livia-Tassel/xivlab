"""Alembic environment configuration for xivLab.

Async-first; uses the project's Settings to read DATABASE_URL.
Attaches the sqlite-vec extension loader to the alembic engine so that
migrations creating virtual `vec0` tables succeed.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.models  # noqa: F401  -- ensure all models import so Base.metadata is populated
from alembic import context
from app.config import get_settings
from app.db import Base, attach_sqlite_extensions

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    # Wire sqlite-vec extension into the migration engine before any connect.
    attach_sqlite_extensions(connectable.sync_engine)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


asyncio.run(run_migrations_online())
