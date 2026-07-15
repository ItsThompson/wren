"""Integration tests: the accounts migration and repository against real Postgres.

Applies Alembic to head on a containerized ``postgres:17-alpine`` and exercises
the SQLAlchemy repository + service end to end, so the unique-constraint ->
``Conflict`` path and the ``sid`` blacklist run against the real driver. Skipped
automatically when Docker is unavailable (spec section 13).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from accounts_fakes import build_test_codec, build_test_hasher
from wren.accounts.repository import SqlAlchemyAccountRepository
from wren.accounts.service import AccountService
from wren.accounts.session import build_revocation_lookup
from wren.core.db import create_database
from wren.core.errors import Conflict

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]
_PASSWORD = "Str0ngPass"


@pytest.fixture(scope="session")
def migrated_postgres_url(postgres_url: str) -> Iterator[str]:
    """Apply Alembic to head against the container (sync: env.py drives asyncio)."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", postgres_url)
    # env.py reads DATABASE_URL from settings; point it at the container.
    import os

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = postgres_url
    try:
        command.upgrade(config, "head")
        yield postgres_url
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


async def test_migration_creates_the_accounts_tables(migrated_postgres_url: str) -> None:
    database = create_database(migrated_postgres_url)
    try:
        async with database.engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                )
            )
            tables = {row[0] for row in rows}
    finally:
        await database.engine.dispose()
    assert {"users", "revoked_sessions"} <= tables


async def test_register_persists_and_duplicate_email_conflicts(migrated_postgres_url: str) -> None:
    database = create_database(migrated_postgres_url)
    codec = build_test_codec()
    hasher = build_test_hasher()
    email = "persist@example.com"
    try:
        async with database.sessionmaker() as session:
            service = AccountService(SqlAlchemyAccountRepository(session), hasher, codec)
            created = await service.register("persistuser", email, _PASSWORD)
            assert created.user.email == email

        # A second registration on the same email hits the real unique constraint,
        # which the service surfaces as a field-level Conflict (is_unique_violation).
        async with database.sessionmaker() as session:
            service = AccountService(SqlAlchemyAccountRepository(session), hasher, codec)
            with pytest.raises(Conflict) as excinfo:
                await service.register("otheruser", email, _PASSWORD)
            assert excinfo.value.fields is not None
            assert "email" in excinfo.value.fields

        # The persisted password is a bcrypt hash, never the plaintext.
        async with database.sessionmaker() as session:
            repo = SqlAlchemyAccountRepository(session)
            stored = await repo.get_by_email(email)
            assert stored is not None
            assert stored.password_hash.startswith("$2b$")
            assert _PASSWORD not in stored.password_hash
            # The by-username and by-id lookups resolve the same persisted row.
            assert (await repo.get_by_username("persistuser")) is not None
            by_id = await repo.get_by_id(stored.id)
            assert by_id is not None and by_id.email == email
    finally:
        await database.engine.dispose()


async def test_logout_revocation_is_visible_to_the_revocation_lookup(
    migrated_postgres_url: str,
) -> None:
    database = create_database(migrated_postgres_url)
    codec = build_test_codec()
    hasher = build_test_hasher()
    try:
        async with database.sessionmaker() as session:
            service = AccountService(SqlAlchemyAccountRepository(session), hasher, codec)
            registered = await service.register("revokeuser", "revoke@example.com", _PASSWORD)
            sid = registered.tokens.sid

        is_revoked = build_revocation_lookup(database)
        assert await is_revoked(sid) is False

        async with database.sessionmaker() as session:
            service = AccountService(SqlAlchemyAccountRepository(session), hasher, codec)
            await service.logout(registered.tokens.refresh_token)

        # The blacklist lookup the session verifier uses now sees the revocation.
        assert await is_revoked(sid) is True
    finally:
        await database.engine.dispose()
