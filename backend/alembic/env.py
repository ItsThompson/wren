"""Alembic environment: async, driven by wren settings.

The migration engine reuses ``wren.core.db.create_db_engine`` and reads the URL
from ``EnvSettings`` (``DATABASE_URL``), so migrations, the app, and tests share
one source of truth for the connection string (no hardcoded URL).

``target_metadata`` is the shared declarative ``Base.metadata``. Each domain's
model module is imported below so its tables attach to that metadata and
``--autogenerate`` can diff the real schema.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

# Import every domain's models for their side effect of registering tables on
# Base.metadata. Add new domain model modules here as slices land.
import wren.accounts.models  # noqa: F401  (registers the accounts tables)
import wren.oauth.models  # noqa: F401  (registers the OAuth AS tables)
import wren.progress.models  # noqa: F401  (registers the progress table)
import wren.roadmaps.models  # noqa: F401  (registers the roadmaps table)
from wren.core.db import create_db_engine
from wren.core.orm import Base
from wren.core.settings import EnvSettings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The shared schema Alembic diffs. All ORM models subclass wren.core.orm.Base,
# so their tables live on this one metadata once their modules are imported.
target_metadata = Base.metadata


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
