"""Config Alembic async — l'URL de la base vient des Settings (DATABASE_URL)."""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from investia.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def do_run_migrations(sync_connection) -> None:
    context.configure(connection=sync_connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_settings().database_url.get_secret_value()
    connectable = async_engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


asyncio.run(run_migrations_online())
