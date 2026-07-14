"""Alembic environment: async, driven by wren settings.

The migration engine reuses ``wren.core.db.create_db_engine`` and reads the URL
from ``EnvSettings`` (``DATABASE_URL``), so migrations, the app, and tests share
one source of truth for the connection string (spec section 11: no hardcoded URL).

``target_metadata`` is an empty ``MetaData()`` for now: Ticket 2 is DB plumbing
only, with no domain tables yet (so ``--autogenerate`` emits empty migrations).
Ticket 6 sets it to the shared declarative ``Base.metadata`` so ``--autogenerate``
can diff the real schema.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import MetaData
from sqlalchemy.engine import Connection

from wren.core.db import create_db_engine
from wren.core.settings import EnvSettings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Empty for now: Ticket 2 is DB plumbing only, with no domain tables. Ticket 6
# replaces this with the shared declarative ``Base.metadata`` so ``--autogenerate``
# diffs the real schema. Until then autogenerate produces empty migrations
# (``alembic_version`` is managed by Alembic and never diffed).
target_metadata = MetaData()


def _database_url() -> str:
    return EnvSettings().database_url


def run_migrations_offline() -> None:
    """Emit SQL without a live connection (``alembic upgrade --sql``)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against a live async connection."""
    engine = create_db_engine(_database_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
