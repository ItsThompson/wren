"""In-memory test doubles and factories for the OAuth AS.

The service layer is tested sociably: real config, real signing keys (ephemeral),
real access-token codec, real PKCE, with this in-memory repository substituted at
the only true external boundary (Postgres). The fake mirrors the SQLAlchemy
semantics the services rely on (one active grant per user+client, refresh-token
revocation, one-time codes).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from authlib.oauth2.rfc7636 import create_s256_code_challenge

from wren.oauth.config import OAuthConfig
from wren.oauth.injection import Clock, utcnow
from wren.oauth.keys import SigningKeySet, load_signing_key_set
from wren.oauth.models import (
    OAuthAuthorizationCode,
    OAuthAuthRequest,
    OAuthClient,
    OAuthGrant,
    OAuthRefreshToken,
)
from wren.oauth.tokens import AccessTokenCodec

if TYPE_CHECKING:
    from collections.abc import Sequence

TEST_ISSUER = "https://api.usewren.com"
TEST_APP_URL = "https://usewren.com"
TEST_RESOURCE = "https://mcp.usewren.com"


def build_test_config(
    *,
    access_ttl: timedelta = timedelta(minutes=15),
    refresh_ttl: timedelta = timedelta(days=30),
    auth_request_ttl: timedelta = timedelta(minutes=10),
    code_ttl: timedelta = timedelta(minutes=1),
) -> OAuthConfig:
    """An OAuth config with pinned test URLs and overridable TTLs (expiry tests)."""
    return OAuthConfig(
        issuer=TEST_ISSUER,
        consent_base_url=TEST_APP_URL,
        resource=TEST_RESOURCE,
        key_path="",
        key_id="test-kid",
        access_ttl=access_ttl,
        refresh_ttl=refresh_ttl,
        auth_request_ttl=auth_request_ttl,
        code_ttl=code_ttl,
    )


def build_test_keyset(config: OAuthConfig) -> SigningKeySet:
    """An ephemeral in-memory signing key set (no PEM on disk)."""
    return load_signing_key_set(config, is_dev=True)


def build_test_codec(
    config: OAuthConfig, keyset: SigningKeySet, *, clock: Clock = utcnow
) -> AccessTokenCodec:
    return AccessTokenCodec(keyset, config, clock=clock)


class MutableClock:
    """A pinned, advanceable clock for expiry tests (no ``sleep``/negative TTL)."""

    def __init__(self, now: datetime) -> None:
        self._now = now

    def __call__(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


def make_pkce_pair() -> tuple[str, str]:
    """A (code_verifier, code_challenge) S256 pair for the token exchange."""
    verifier = uuid.uuid4().hex + uuid.uuid4().hex
    return verifier, create_s256_code_challenge(verifier)


class InMemoryOAuthRepository:
    """A dict-backed :class:`OAuthRepository` with the semantics the services need."""

    def __init__(self) -> None:
        self._clients: dict[str, OAuthClient] = {}
        self._requests: dict[str, OAuthAuthRequest] = {}
        self._codes: dict[str, OAuthAuthorizationCode] = {}
        self._refresh: dict[str, OAuthRefreshToken] = {}
        self._grants: dict[tuple[str, str], OAuthGrant] = {}
        self.audit: list[OAuthAuditEntry] = []
        self.commits = 0

    # --- clients ------------------------------------------------------------

    async def add_client(self, client: OAuthClient) -> None:
        self._clients[client.client_id] = client

    async def get_client(self, client_id: str) -> OAuthClient | None:
        return self._clients.get(client_id)

    async def get_clients(self, client_ids: Sequence[str]) -> dict[str, str]:
        return {cid: self._clients[cid].client_name for cid in client_ids if cid in self._clients}

    async def delete_client(self, client_id: str) -> None:
        """Test-support: drop a client row, orphaning any grant that referenced it."""
        self._clients.pop(client_id, None)

    async def delete_clients_created_before(self, cutoff: datetime) -> list[str]:
        stale = [cid for cid, c in self._clients.items() if c.created_at < cutoff]
        for cid in stale:
            del self._clients[cid]
        return stale

    # --- parked authorize requests ------------------------------------------

    async def add_auth_request(self, request: OAuthAuthRequest) -> None:
        self._requests[request.id] = request

    async def get_auth_request(self, request_id: str) -> OAuthAuthRequest | None:
        return self._requests.get(request_id)

    async def delete_auth_request(self, request_id: str) -> None:
        self._requests.pop(request_id, None)

    # --- authorization codes ------------------------------------------------

    async def add_code(self, code: OAuthAuthorizationCode) -> None:
        self._codes[code.code] = code

    async def get_code(self, code: str) -> OAuthAuthorizationCode | None:
        return self._codes.get(code)

    async def delete_code(self, code: str) -> None:
        self._codes.pop(code, None)

    # --- refresh tokens -----------------------------------------------------

    async def add_refresh_token(self, token: OAuthRefreshToken, *, now: datetime) -> None:
        token.created_at = now
        if token.revoked is None:
            token.revoked = False
        self._refresh[token.token_hash] = token

    async def get_refresh_token(self, token_hash: str) -> OAuthRefreshToken | None:
        return self._refresh.get(token_hash)

    async def revoke_refresh_token(self, token_hash: str) -> None:
        token = self._refresh.get(token_hash)
        if token is not None:
            token.revoked = True

    async def revoke_grant_refresh_tokens(self, grant_id: str) -> None:
        for token in self._refresh.values():
            if token.grant_id == grant_id:
                token.revoked = True

    # --- grants -------------------------------------------------------------

    async def upsert_grant(
        self, *, user_id: str, client_id: str, scope: str, now: datetime, grant_id: str
    ) -> str:
        key = (user_id, client_id)
        existing = self._grants.get(key)
        if existing is not None:
            existing.scope = scope
            existing.authorized_at = now
            existing.revoked_at = None
            return existing.id
        grant = OAuthGrant(
            id=grant_id,
            user_id=user_id,
            client_id=client_id,
            scope=scope,
            authorized_at=now,
        )
        self._grants[key] = grant
        return grant.id

    async def get_grant(self, user_id: str, client_id: str) -> OAuthGrant | None:
        return self._grants.get((user_id, client_id))

    async def list_active_grants(self, user_id: str) -> list[OAuthGrant]:
        active = [
            g for (uid, _), g in self._grants.items() if uid == user_id and g.revoked_at is None
        ]
        return sorted(active, key=lambda g: g.authorized_at, reverse=True)

    async def list_grants_for_clients(self, client_ids: Sequence[str]) -> list[OAuthGrant]:
        ids = set(client_ids)
        return [g for (_, cid), g in self._grants.items() if cid in ids]

    async def revoke_grant(
        self, user_id: str, client_id: str, *, now: datetime
    ) -> OAuthGrant | None:
        grant = self._grants.get((user_id, client_id))
        if grant is None or grant.revoked_at is not None:
            return None
        grant.revoked_at = now
        await self.revoke_grant_refresh_tokens(grant.id)
        return grant

    # --- audit --------------------------------------------------------------

    async def record_event(
        self,
        *,
        user_id: str,
        client_id: str,
        event: str,
        scope: str | None = None,
        now: datetime,
        event_id: str,
    ) -> None:
        self.audit.append(
            OAuthAuditEntry(
                event_id=event_id,
                user_id=user_id,
                client_id=client_id,
                event=event,
                scope=scope,
                created_at=now,
            )
        )

    async def commit(self) -> None:
        self.commits += 1


class OAuthAuditEntry:
    """A recorded audit event, so tests can assert (client, user, event)."""

    def __init__(
        self,
        *,
        event_id: str,
        user_id: str,
        client_id: str,
        event: str,
        scope: str | None,
        created_at: datetime,
    ) -> None:
        self.event_id = event_id
        self.user_id = user_id
        self.client_id = client_id
        self.event = event
        self.scope = scope
        self.created_at = created_at
