"""Integration tests: the OAuth migration and repository against real Postgres.

Applies Alembic to head on a containerized ``postgres:17-alpine`` and drives the
AS services through the SQLAlchemy repository so the parking store, one-time
codes, and refresh-token rotation/replay run against the real driver (not just
the in-memory fake). Skipped automatically when Docker is unavailable.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from tests.oauth_fakes import build_test_codec, build_test_config, build_test_keyset, make_pkce_pair
from wren.core.db import create_database
from wren.core.errors import NotFound
from wren.oauth.authorization import AuthorizationService
from wren.oauth.errors import OAuthError
from wren.oauth.repository import SqlAlchemyOAuthRepository
from wren.oauth.schemas import AuthorizeParams, ClientRegistrationRequest, TokenRequest
from wren.oauth.token_exchange import TokenService

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[1]
_USER = "user-ada"
_REDIRECT = "http://127.0.0.1:8765/callback"


@pytest.fixture(scope="session")
def migrated_postgres_url(postgres_url: str) -> Iterator[str]:
    """Apply Alembic to head against the container (sync: env.py drives asyncio)."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", postgres_url)
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


async def test_migration_creates_the_oauth_tables(migrated_postgres_url: str) -> None:
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
    assert {
        "oauth_clients",
        "oauth_auth_requests",
        "oauth_authorization_codes",
        "oauth_refresh_tokens",
        "oauth_grants",
        "oauth_audit_log",
    } <= tables


def _query(url: str) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


async def test_oauth_flow_persists_and_rotation_replay_is_rejected(
    migrated_postgres_url: str,
) -> None:
    database = create_database(migrated_postgres_url)
    config = build_test_config()
    codec = build_test_codec(config, build_test_keyset(config))

    @asynccontextmanager
    async def auth() -> AsyncIterator[AuthorizationService]:
        async with database.sessionmaker() as session:
            yield AuthorizationService(SqlAlchemyOAuthRepository(session), config)

    @asynccontextmanager
    async def tokens() -> AsyncIterator[TokenService]:
        async with database.sessionmaker() as session:
            yield TokenService(SqlAlchemyOAuthRepository(session), config, codec)

    try:
        async with auth() as auth_service:
            registration = await auth_service.register_client(
                ClientRegistrationRequest(redirect_uris=[_REDIRECT], client_name="Persist Agent")
            )
        client_id = registration.client_id

        verifier, challenge = make_pkce_pair()
        async with auth() as auth_service:
            consent_url = await auth_service.start_authorization(
                AuthorizeParams(
                    client_id=client_id,
                    redirect_uri=_REDIRECT,
                    response_type="code",
                    code_challenge=challenge,
                    code_challenge_method="S256",
                    state="xyz",
                )
            )
        request_id = _query(consent_url)["auth_request_id"]

        async with auth() as auth_service:
            redirect = await auth_service.decide(
                auth_request_id=request_id, user_id=_USER, approve=True
            )
        code = _query(redirect)["code"]

        async with tokens() as token_service:
            issued = await token_service.exchange(
                TokenRequest(
                    grant_type="authorization_code",
                    client_id=client_id,
                    code=code,
                    code_verifier=verifier,
                    redirect_uri=_REDIRECT,
                )
            )
        # The access token is audience-bound to the MCP resource and verifies.
        verified = codec.verify(issued.access_token)
        assert verified is not None and verified.audience == config.resource

        # Rotate the refresh token; the old one is now persisted as revoked.
        async with tokens() as token_service:
            rotated = await token_service.exchange(
                TokenRequest(
                    grant_type="refresh_token",
                    client_id=client_id,
                    refresh_token=issued.refresh_token,
                )
            )
        assert rotated.refresh_token != issued.refresh_token

        # Replaying the rotated-out refresh token is rejected by the real DB state.
        async with tokens() as token_service:
            with pytest.raises(OAuthError):
                await token_service.exchange(
                    TokenRequest(
                        grant_type="refresh_token",
                        client_id=client_id,
                        refresh_token=issued.refresh_token,
                    )
                )

        # The connected-client list reflects the persisted grant.
        async with tokens() as token_service:
            connected = await token_service.list_connected_clients(_USER)
        assert [c.client_id for c in connected] == [client_id]

        # Revoking the connected client persists the grant + refresh-token
        # revocation, so the list empties and the rotated refresh dies.
        async with tokens() as token_service:
            await token_service.revoke_connected_client(_USER, client_id)
        async with tokens() as token_service:
            assert await token_service.list_connected_clients(_USER) == []
        # Revoking an already-revoked grant against the real DB is a 404 (the
        # repository's guard returns None).
        async with tokens() as token_service:
            with pytest.raises(NotFound):
                await token_service.revoke_connected_client(_USER, client_id)
        async with tokens() as token_service:
            with pytest.raises(OAuthError):
                await token_service.exchange(
                    TokenRequest(
                        grant_type="refresh_token",
                        client_id=client_id,
                        refresh_token=rotated.refresh_token,
                    )
                )

        # The stale-client cleanup hook deletes the registration row.
        async with tokens() as token_service:
            deleted = await token_service.cleanup_stale_clients(older_than=timedelta(seconds=-1))
        assert deleted >= 1
    finally:
        await database.engine.dispose()


async def test_cleanup_cascade_revokes_orphaned_grants(migrated_postgres_url: str) -> None:
    # Against the real DB: sweeping a client with a still-active grant cascade-
    # revokes the grant + its refresh chain in the same transaction, so no grant
    # survives that is hidden from /me/clients yet whose refresh token still
    # rotates (the orphaned-grant defect).
    database = create_database(migrated_postgres_url)
    config = build_test_config()
    codec = build_test_codec(config, build_test_keyset(config))

    @asynccontextmanager
    async def auth() -> AsyncIterator[AuthorizationService]:
        async with database.sessionmaker() as session:
            yield AuthorizationService(SqlAlchemyOAuthRepository(session), config)

    @asynccontextmanager
    async def tokens() -> AsyncIterator[TokenService]:
        async with database.sessionmaker() as session:
            yield TokenService(SqlAlchemyOAuthRepository(session), config, codec)

    try:
        async with auth() as auth_service:
            registration = await auth_service.register_client(
                ClientRegistrationRequest(redirect_uris=[_REDIRECT], client_name="Stale Agent")
            )
        client_id = registration.client_id

        verifier, challenge = make_pkce_pair()
        async with auth() as auth_service:
            consent_url = await auth_service.start_authorization(
                AuthorizeParams(
                    client_id=client_id,
                    redirect_uri=_REDIRECT,
                    response_type="code",
                    code_challenge=challenge,
                    code_challenge_method="S256",
                    state="xyz",
                )
            )
        request_id = _query(consent_url)["auth_request_id"]
        async with auth() as auth_service:
            redirect = await auth_service.decide(
                auth_request_id=request_id, user_id=_USER, approve=True
            )
        code = _query(redirect)["code"]
        async with tokens() as token_service:
            issued = await token_service.exchange(
                TokenRequest(
                    grant_type="authorization_code",
                    client_id=client_id,
                    code=code,
                    code_verifier=verifier,
                    redirect_uri=_REDIRECT,
                )
            )

        # Sweep everything: the cascade revokes the still-active grant + refresh.
        async with tokens() as token_service:
            deleted = await token_service.cleanup_stale_clients(older_than=timedelta(seconds=-1))
        assert deleted >= 1

        # The refresh no longer rotates against real DB state.
        async with tokens() as token_service:
            with pytest.raises(OAuthError):
                await token_service.exchange(
                    TokenRequest(
                        grant_type="refresh_token",
                        client_id=client_id,
                        refresh_token=issued.refresh_token,
                    )
                )
        # The grant is persisted as revoked (not merely hidden) and omitted.
        async with database.sessionmaker() as session:
            grant = await SqlAlchemyOAuthRepository(session).get_grant(_USER, client_id)
        assert grant is not None and grant.revoked_at is not None
        async with tokens() as token_service:
            assert await token_service.list_connected_clients(_USER) == []

        # A follow-up sweep finds nothing: the delete + grant batch-read short
        # circuit on the empty id list.
        async with tokens() as token_service:
            assert await token_service.cleanup_stale_clients(older_than=timedelta(seconds=-1)) == 0
    finally:
        await database.engine.dispose()
