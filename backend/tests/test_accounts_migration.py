"""Integration tests: the accounts migration and repository against real Postgres.

Applies Alembic to head on a containerized ``postgres:17-alpine`` and exercises
the SQLAlchemy repository + service end to end, so the unique-constraint ->
``Conflict`` path and the ``sid`` blacklist run against the real driver. Skipped
automatically when Docker is unavailable.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from tests.support.fakes.accounts_fakes import build_test_codec, build_test_hasher
from wren.accounts.repository import SqlAlchemyAccountRepository
from wren.accounts.service import AccountService
from wren.accounts.session import build_revocation_lookup
from wren.core.db import create_database
from wren.core.errors import Conflict

if TYPE_CHECKING:
    from collections.abc import Iterator

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


async def test_freshly_registered_account_persists_as_not_onboarded(
    migrated_postgres_url: str,
) -> None:
    # AC4/US-BACK-02, end to end against Postgres: register writes the ORM default
    # (false), so a new account's persisted flag is false despite the DDL's
    # server_default being a backfill safety net rather than the new-user path.
    database = create_database(migrated_postgres_url)
    try:
        async with database.sessionmaker() as session:
            service = AccountService(
                SqlAlchemyAccountRepository(session), build_test_hasher(), build_test_codec()
            )
            created = await service.register("freshuser", "fresh@example.com", _PASSWORD)
            assert created.user.has_completed_onboarding is False

        async with database.sessionmaker() as session:
            stored = await SqlAlchemyAccountRepository(session).get_by_email("fresh@example.com")
            assert stored is not None and stored.has_completed_onboarding is False
    finally:
        await database.engine.dispose()


async def test_complete_onboarding_flips_the_persisted_flag(migrated_postgres_url: str) -> None:
    # Ticket 5, end to end against Postgres with a fresh request-scoped session per
    # step (as production does): the UPDATE ... RETURNING path flips the flag,
    # returns a fully-populated user view, commits, and bumps updated_at.
    database = create_database(migrated_postgres_url)
    try:
        async with database.sessionmaker() as session:
            service = AccountService(
                SqlAlchemyAccountRepository(session), build_test_hasher(), build_test_codec()
            )
            registered = await service.register("onboarduser", "onboard@example.com", _PASSWORD)
            assert registered.user.has_completed_onboarding is False

        # Baseline updated_at from a fresh session after the register commit.
        async with database.sessionmaker() as session:
            baseline = await SqlAlchemyAccountRepository(session).get_by_id(registered.user.id)
            assert baseline is not None
            registered_updated_at = baseline.updated_at

        async with database.sessionmaker() as session:
            service = AccountService(
                SqlAlchemyAccountRepository(session), build_test_hasher(), build_test_codec()
            )
            view = await service.complete_onboarding(registered.user.id)
            # RETURNING(User) yields a fully-populated row, not just the flag, even
            # though this session never loaded the user first.
            assert view.id == registered.user.id
            assert view.username == "onboarduser"
            assert view.email == "onboard@example.com"
            assert view.has_completed_onboarding is True

        async with database.sessionmaker() as session:
            stored = await SqlAlchemyAccountRepository(session).get_by_email("onboard@example.com")
            assert stored is not None
            assert stored.has_completed_onboarding is True
            # The completion UPDATE refreshed updated_at (SET ... updated_at = now()),
            # so it strictly advanced past the value written at registration.
            assert stored.updated_at > registered_updated_at
    finally:
        await database.engine.dispose()


async def test_complete_onboarding_is_idempotent_against_postgres(
    migrated_postgres_url: str,
) -> None:
    # Double-submit against the real UPDATE ... RETURNING, each in its own
    # request-scoped session: both calls return the row with the flag true, and it
    # ends true once (the second write is a no-op beyond the timestamp).
    database = create_database(migrated_postgres_url)
    try:
        async with database.sessionmaker() as session:
            service = AccountService(
                SqlAlchemyAccountRepository(session), build_test_hasher(), build_test_codec()
            )
            registered = await service.register("twiceuser", "twice@example.com", _PASSWORD)

        async with database.sessionmaker() as session:
            service = AccountService(
                SqlAlchemyAccountRepository(session), build_test_hasher(), build_test_codec()
            )
            first = await service.complete_onboarding(registered.user.id)
            assert first.has_completed_onboarding is True

        async with database.sessionmaker() as session:
            service = AccountService(
                SqlAlchemyAccountRepository(session), build_test_hasher(), build_test_codec()
            )
            second = await service.complete_onboarding(registered.user.id)
            assert second.has_completed_onboarding is True

        async with database.sessionmaker() as session:
            stored = await SqlAlchemyAccountRepository(session).get_by_email("twice@example.com")
            assert stored is not None and stored.has_completed_onboarding is True
    finally:
        await database.engine.dispose()


async def test_set_onboarding_complete_returns_none_for_a_missing_user(
    migrated_postgres_url: str,
) -> None:
    # No row matches the id, so the UPDATE ... RETURNING resolves to None (the
    # service maps this to Unauthorized).
    database = create_database(migrated_postgres_url)
    try:
        async with database.sessionmaker() as session:
            repo = SqlAlchemyAccountRepository(session)
            assert await repo.set_onboarding_complete("does-not-exist") is None
    finally:
        await database.engine.dispose()


async def _admin_execute(admin_url: str, statement: str) -> None:
    """Run one autocommit statement (CREATE/DROP DATABASE cannot run in a txn)."""
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            await conn.execute(text(statement))
    finally:
        await engine.dispose()


async def _seed_pre_onboarding_user(url: str, user_id: str) -> None:
    """Insert a user row in the pre-0006 schema (no onboarding column yet)."""
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO users (id, username, email, password_hash) "
                    "VALUES (:id, :username, :email, :password_hash)"
                ),
                {
                    "id": user_id,
                    "username": "legacy",
                    "email": "legacy@example.com",
                    "password_hash": "$2b$04$legacyhashplaceholder000000000000000000000",
                },
            )
    finally:
        await engine.dispose()


async def _read_onboarding_flag(url: str, user_id: str) -> bool | None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            result = await conn.scalar(
                text("SELECT has_completed_onboarding FROM users WHERE id = :id"),
                {"id": user_id},
            )
            return None if result is None else bool(result)
    finally:
        await engine.dispose()


def test_migration_backfills_existing_accounts_to_onboarded(postgres_url: str) -> None:
    """US-GUARD-04: accounts that existed before 0006 are backfilled to true.

    Runs on an isolated database in the same container so the staged upgrade
    (0005 -> seed a legacy row -> 0006) is independent of the shared session
    database other integration tests bring straight to head. ``command.upgrade``
    is synchronous (its env.py drives its own asyncio loop), so this is a sync
    test that wraps each direct DB step in ``asyncio.run``.
    """
    import os

    db_name = f"onboarding_backfill_{uuid.uuid4().hex[:12]}"
    asyncio.run(_admin_execute(postgres_url, f'CREATE DATABASE "{db_name}"'))
    target_url = make_url(postgres_url).set(database=db_name).render_as_string(hide_password=False)

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", target_url)
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = target_url
    try:
        # Bring the isolated DB to just before onboarding, then seed a legacy row.
        command.upgrade(config, "0005_progress")
        asyncio.run(_seed_pre_onboarding_user(target_url, "legacy-user-1"))
        # Applying 0006 adds the column (server_default false) and backfills to true.
        command.upgrade(config, "0006_onboarding")
        assert asyncio.run(_read_onboarding_flag(target_url, "legacy-user-1")) is True
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        asyncio.run(
            _admin_execute(postgres_url, f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        )
