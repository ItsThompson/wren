"""TokenService: token exchange, rotating refresh, revocation, and grants.

The token endpoint: an ``authorization_code`` exchange verifies
the PKCE ``code_verifier`` against the code's stored S256 challenge and mints a
short-lived RS256 access token (``aud`` = the MCP resource) plus a rotating
refresh token; a ``refresh_token`` exchange rotates: it revokes the presented
refresh and issues a fresh pair, and a **replay** of an already-rotated refresh
revokes the whole grant chain. ``/revoke`` (RFC 7009) invalidates a refresh
token. ``/me/clients`` list/revoke are the connected-client seam.

Access tokens are stateless JWTs and cannot be individually revoked, so agent
tokens are short-lived and revocation takes effect within the access-token TTL.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from wren.core.errors import NotFound
from wren.core.observability import OAUTH_TOKENS_ISSUED, track_failures
from wren.oauth.config import (
    GRANT_TYPE_AUTHORIZATION_CODE,
    GRANT_TYPE_REFRESH_TOKEN,
    OAuthConfig,
)
from wren.oauth.errors import OAuthError
from wren.oauth.injection import Clock, OpaqueIdFactory, new_hex_id, utcnow
from wren.oauth.models import OAuthRefreshToken
from wren.oauth.pkce import is_valid_s256
from wren.oauth.schemas import ConnectedClient, OAuthEvent, TokenRequest, TokenResponse
from wren.oauth.tokens import AccessTokenCodec, hash_token, mint_refresh_token
from wren_common.logging import get_logger

if TYPE_CHECKING:
    from datetime import datetime, timedelta

    from wren.oauth.repository import OAuthRepository

_log = get_logger("wren-oauth")
_BEARER = "Bearer"

# grant_type -> increment. Injected so no business method names the global
# metric; the default keeps the metric name/labels stable.
IssuedCounter = Callable[[str], None]


def _default_issued_counter(grant_type: str) -> None:
    """Default issuance counter: bump the process-global ``OAUTH_TOKENS_ISSUED``."""
    OAUTH_TOKENS_ISSUED.labels(grant_type=grant_type).inc()


@track_failures("oauth")
class TokenService:
    """Token issuance, refresh rotation, revocation, and connected-client grants."""

    def __init__(
        self,
        repo: OAuthRepository,
        config: OAuthConfig,
        codec: AccessTokenCodec,
        *,
        clock: Clock = utcnow,
        new_id: OpaqueIdFactory = mint_refresh_token,
        new_record_id: OpaqueIdFactory = new_hex_id,
        issued_counter: IssuedCounter = _default_issued_counter,
    ) -> None:
        self._repo = repo
        self._config = config
        self._codec = codec
        # Injected so tests pin expiry and force deterministic ids/counting without
        # patching globals; the defaults reproduce the prior ambient behavior.
        self._clock = clock
        # Raw refresh-token secret (url-safe); grant/audit surrogate keys (hex).
        self._new_id = new_id
        self._new_record_id = new_record_id
        # Counts issuance post-commit; default binds OAUTH_TOKENS_ISSUED.
        self._issued_counter = issued_counter

    async def exchange(self, request: TokenRequest) -> TokenResponse:
        """Dispatch the token endpoint on ``grant_type`` (RFC 6749)."""
        if request.grant_type == GRANT_TYPE_AUTHORIZATION_CODE:
            return await self._exchange_code(request)
        if request.grant_type == GRANT_TYPE_REFRESH_TOKEN:
            return await self._refresh(request)
        raise OAuthError.unsupported_grant_type(f"Unsupported grant_type: {request.grant_type}")

    async def _exchange_code(self, request: TokenRequest) -> TokenResponse:
        if not request.code or not request.code_verifier or not request.client_id:
            raise OAuthError.invalid_request("code, code_verifier, and client_id are required.")
        code = await self._repo.get_code(request.code)
        if code is None or self._is_expired(code.expires_at):
            raise OAuthError.invalid_grant("Authorization code is invalid or expired.")
        if code.client_id != request.client_id:
            raise OAuthError.invalid_grant("Authorization code was issued to another client.")
        if request.redirect_uri is not None and request.redirect_uri != code.redirect_uri:
            raise OAuthError.invalid_grant("redirect_uri does not match the authorization request.")
        if not is_valid_s256(request.code_verifier, code.code_challenge):
            raise OAuthError.invalid_grant("PKCE verification failed.")
        if self._config.canonical_resource(request.resource) != code.resource:
            raise OAuthError.invalid_target("resource does not match the authorization request.")

        # One-time use: consume the code before minting so it cannot be replayed.
        await self._repo.delete_code(code.code)
        grant = await self._repo.get_grant(code.user_id, code.client_id)
        if grant is None:  # pragma: no cover - decision always upserts the grant
            raise OAuthError.invalid_grant("No active grant for this authorization.")
        if grant.revoked_at is not None:
            # The user revoked the client after this code was minted (within the
            # code TTL): honor the revocation rather than re-establish access.
            raise OAuthError.invalid_grant("The authorization grant has been revoked.")
        tokens = await self._issue_pair(
            grant_id=grant.id,
            user_id=code.user_id,
            client_id=code.client_id,
            scope=code.scope,
            resource=code.resource,
            event=OAuthEvent.TOKEN_ISSUED,
        )
        await self._repo.commit()
        self._issued_counter(GRANT_TYPE_AUTHORIZATION_CODE)
        _log.info("oauth_token_issued", client_id=code.client_id, user_id=code.user_id)
        return tokens

    async def _refresh(self, request: TokenRequest) -> TokenResponse:
        if not request.refresh_token or not request.client_id:
            raise OAuthError.invalid_request("refresh_token and client_id are required.")
        existing = await self._repo.get_refresh_token(hash_token(request.refresh_token))
        if existing is None:
            raise OAuthError.invalid_grant("Refresh token is invalid.")
        if existing.revoked:
            # A rotated/revoked refresh being reused: treat as a compromised chain
            # and revoke every refresh token for the grant (replay defense).
            await self._repo.revoke_grant_refresh_tokens(existing.grant_id)
            await self._repo.commit()
            raise OAuthError.invalid_grant("Refresh token has already been used.")
        if self._is_expired(existing.expires_at):
            raise OAuthError.invalid_grant("Refresh token is expired.")
        if existing.client_id != request.client_id:
            raise OAuthError.invalid_grant("Refresh token was issued to another client.")
        if await self._repo.get_client(existing.client_id) is None:
            # Defense in depth: a deleted client's refresh fails closed even if its
            # grant were somehow left un-revoked (cleanup cascade-revokes it first).
            raise OAuthError.invalid_grant("Refresh token's client no longer exists.")

        # Rotate: revoke the presented refresh, then issue a fresh pair.
        await self._repo.revoke_refresh_token(existing.token_hash)
        tokens = await self._issue_pair(
            grant_id=existing.grant_id,
            user_id=existing.user_id,
            client_id=existing.client_id,
            scope=existing.scope,
            resource=existing.resource,
            event=OAuthEvent.REFRESHED,
        )
        await self._repo.commit()
        self._issued_counter(GRANT_TYPE_REFRESH_TOKEN)
        _log.info("oauth_token_refreshed", client_id=existing.client_id, user_id=existing.user_id)
        return tokens

    async def revoke(self, token: str, *, client_id: str | None = None) -> None:
        """RFC 7009: revoke a refresh token. Always succeeds (no token-scanning leak).

        Access tokens are stateless and cannot be revoked here; the request still
        succeeds. When the token is a known refresh token owned by the given
        client, it (and thus the current chain) is marked revoked.
        """
        existing = await self._repo.get_refresh_token(hash_token(token))
        if existing is None:
            return
        if client_id is not None and existing.client_id != client_id:
            return
        await self._repo.revoke_refresh_token(existing.token_hash)
        await self._repo.record_event(
            user_id=existing.user_id,
            client_id=existing.client_id,
            event=OAuthEvent.REVOKED.value,
            scope=existing.scope,
            now=self._clock(),
            event_id=self._new_record_id(),
        )
        await self._repo.commit()
        _log.info("oauth_token_revoked", client_id=existing.client_id, user_id=existing.user_id)

    async def list_connected_clients(self, user_id: str) -> list[ConnectedClient]:
        """The user's authorized agents (``GET /me/clients``).

        One batch ``get_clients`` read over the shared session instead of N serial
        ``get_client`` awaits; a grant whose client was deleted (a map miss) is
        skipped.
        """
        grants = await self._repo.list_active_grants(user_id)
        names = await self._repo.get_clients([grant.client_id for grant in grants])
        connected: list[ConnectedClient] = []
        for grant in grants:
            client_name = names.get(grant.client_id)
            if client_name is None:
                continue
            connected.append(
                ConnectedClient(
                    client_id=grant.client_id,
                    client_name=client_name,
                    scopes=grant.scope.split(),
                    last_authorized=grant.authorized_at,
                )
            )
        return connected

    async def revoke_connected_client(self, user_id: str, client_id: str) -> None:
        """Revoke a user's grant + its refresh tokens (``DELETE``)."""
        grant = await self._repo.revoke_grant(user_id, client_id, now=self._clock())
        if grant is None:
            raise NotFound("No connected client to revoke.")
        await self._repo.record_event(
            user_id=user_id,
            client_id=client_id,
            event=OAuthEvent.REVOKED.value,
            scope=grant.scope,
            now=self._clock(),
            event_id=self._new_record_id(),
        )
        await self._repo.commit()
        _log.info("oauth_client_revoked", client_id=client_id, user_id=user_id)

    async def cleanup_stale_clients(self, older_than: timedelta) -> int:
        """Periodic P0 hook: drop open-registration clients older than ``older_than``.

        Cascade-revokes each doomed client's grant + refresh chain in the same
        transaction, so cleanup can never leave a grant that is hidden from
        ``/me/clients`` (which skips clientless grants) yet whose refresh token
        still rotates.
        """
        cutoff = self._clock() - older_than
        now = self._clock()
        deleted_client_ids = await self._repo.delete_clients_created_before(cutoff)
        for grant in await self._repo.list_grants_for_clients(deleted_client_ids):
            await self._repo.revoke_grant(grant.user_id, grant.client_id, now=now)
        await self._repo.commit()
        return len(deleted_client_ids)

    async def _issue_pair(
        self,
        *,
        grant_id: str,
        user_id: str,
        client_id: str,
        scope: str,
        resource: str,
        event: OAuthEvent,
    ) -> TokenResponse:
        access = self._codec.mint(
            subject=user_id, client_id=client_id, scope=scope, audience=resource
        )
        now = self._clock()
        refresh_raw = self._new_id()
        await self._repo.add_refresh_token(
            OAuthRefreshToken(
                token_hash=hash_token(refresh_raw),
                grant_id=grant_id,
                client_id=client_id,
                user_id=user_id,
                scope=scope,
                resource=resource,
                expires_at=now + self._config.refresh_ttl,
            ),
            now=now,
        )
        await self._repo.record_event(
            user_id=user_id,
            client_id=client_id,
            event=event.value,
            scope=scope,
            now=now,
            event_id=self._new_record_id(),
        )
        return TokenResponse(
            access_token=access.token,
            token_type=_BEARER,
            expires_in=access.expires_in,
            refresh_token=refresh_raw,
            scope=scope,
        )

    def _is_expired(self, expires_at: datetime) -> bool:
        return expires_at <= self._clock()
