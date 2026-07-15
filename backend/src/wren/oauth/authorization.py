"""AuthorizationService: DCR, the authorize/park flow, and the consent decision.

The authorization-grant lifecycle up to code minting (spec section 08): a client
registers (RFC 7591), an ``/authorize`` request is validated and **parked**
server-side under an opaque ``auth_request_id`` (so the SPA only round-trips the
id), the SPA reads the consent context, and the human's decision either mints a
one-time PKCE-bound code or returns ``access_denied``. Token exchange lives in
:mod:`wren.oauth.token_exchange`.

Protocol errors on the agent-facing ``/register`` and ``/authorize`` paths are
``OAuthError`` (RFC 6749 JSON); the SPA-facing context/decision paths raise
``WrenError`` (problem+json), since our own frontend consumes them.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from urllib.parse import urlencode, urlsplit

from wren.core.errors import NotFound
from wren.core.logging import get_logger
from wren.oauth.config import (
    CODE_CHALLENGE_METHOD_S256,
    GRANT_TYPE_AUTHORIZATION_CODE,
    GRANT_TYPE_REFRESH_TOKEN,
    RESPONSE_TYPE_CODE,
    SUPPORTED_SCOPES,
    TOKEN_ENDPOINT_AUTH_NONE,
    OAuthConfig,
)
from wren.oauth.errors import OAuthError
from wren.oauth.models import OAuthAuthorizationCode, OAuthAuthRequest, OAuthClient
from wren.oauth.redirects import is_allowed_redirect, is_loopback
from wren.oauth.repository import OAuthRepository
from wren.oauth.schemas import (
    AuthorizationContext,
    AuthorizeParams,
    ClientRegistrationRequest,
    ClientRegistrationResponse,
    OAuthEvent,
)

_log = get_logger("wren-oauth")

# Opaque identifiers (client_id, auth_request_id, code) are high-entropy url-safe
# tokens; unguessability is defense-in-depth (authorization is by row scoping).
_TOKEN_BYTES = 32
_DEFAULT_SCOPE = " ".join(SUPPORTED_SCOPES)
_DEFAULT_GRANT_TYPES = [GRANT_TYPE_AUTHORIZATION_CODE, GRANT_TYPE_REFRESH_TOKEN]
_DEFAULT_RESPONSE_TYPES = [RESPONSE_TYPE_CODE]


def _new_opaque_id() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def _append_query(uri: str, params: dict[str, str]) -> str:
    separator = "&" if urlsplit(uri).query else "?"
    return f"{uri}{separator}{urlencode(params)}"


def _is_expired(expires_at: datetime) -> bool:
    return expires_at <= datetime.now(UTC)


class AuthorizationService:
    """Client registration, request parking, consent context, and decision."""

    def __init__(self, repo: OAuthRepository, config: OAuthConfig) -> None:
        self._repo = repo
        self._config = config

    async def register_client(
        self, request: ClientRegistrationRequest
    ) -> ClientRegistrationResponse:
        """Open Dynamic Client Registration (RFC 7591): mint a public ``client_id``."""
        self._reject_invalid_redirect_uris(request.redirect_uris)
        scope = self._resolve_registration_scope(request.scope)
        now = datetime.now(UTC)
        client = OAuthClient(
            client_id=_new_opaque_id(),
            client_name=request.client_name or "Unnamed agent",
            redirect_uris=request.redirect_uris,
            grant_types=request.grant_types or _DEFAULT_GRANT_TYPES,
            response_types=request.response_types or _DEFAULT_RESPONSE_TYPES,
            scope=scope,
            token_endpoint_auth_method=TOKEN_ENDPOINT_AUTH_NONE,
            created_at=now,
        )
        await self._repo.add_client(client)
        await self._repo.commit()
        _log.info("oauth_client_registered", client_id=client.client_id)
        return ClientRegistrationResponse(
            client_id=client.client_id,
            client_name=client.client_name,
            redirect_uris=client.redirect_uris,
            grant_types=client.grant_types,
            response_types=client.response_types,
            scope=client.scope,
            token_endpoint_auth_method=client.token_endpoint_auth_method,
            client_id_issued_at=int(now.timestamp()),
        )

    async def start_authorization(self, params: AuthorizeParams) -> str:
        """Validate + park an ``/authorize`` request; return the SPA consent URL."""
        client = await self._repo.get_client(params.client_id)
        if client is None:
            raise OAuthError.invalid_client("Unknown client_id.")
        if not is_allowed_redirect(params.redirect_uri, client.redirect_uris):
            raise OAuthError.invalid_request("redirect_uri is not registered for this client.")
        if params.response_type != RESPONSE_TYPE_CODE:
            raise OAuthError.invalid_request("Only response_type=code is supported.")
        if params.code_challenge_method != CODE_CHALLENGE_METHOD_S256 or not params.code_challenge:
            raise OAuthError.invalid_request("PKCE with code_challenge_method=S256 is required.")
        scope = self._resolve_requested_scope(params.scope, client.scope)
        resource = self._config.canonical_resource(params.resource)
        if resource is None:
            raise OAuthError.invalid_target("resource does not match the MCP resource.")

        request_id = _new_opaque_id()
        await self._repo.add_auth_request(
            OAuthAuthRequest(
                id=request_id,
                client_id=client.client_id,
                redirect_uri=params.redirect_uri,
                scope=scope,
                state=params.state,
                code_challenge=params.code_challenge,
                code_challenge_method=params.code_challenge_method,
                resource=resource,
                expires_at=datetime.now(UTC) + self._config.auth_request_ttl,
            )
        )
        await self._repo.commit()
        _log.info("oauth_authorization_parked", client_id=client.client_id)
        return _append_query(self._config.consent_url, {"auth_request_id": request_id})

    async def get_context(
        self, auth_request_id: str, *, authenticated: bool
    ) -> AuthorizationContext:
        """Consent-screen context for a parked request (Ticket 19 SPA seam)."""
        request = await self._load_live_request(auth_request_id)
        client = await self._repo.get_client(request.client_id)
        client_name = client.client_name if client is not None else request.client_id
        return AuthorizationContext(
            client_name=client_name,
            scopes=request.scope.split(),
            authenticated=authenticated,
        )

    async def decide(self, *, auth_request_id: str, user_id: str, approve: bool) -> str:
        """Resolve consent: mint a code (approve) or return ``access_denied`` (deny).

        The parked request is one-time: it is consumed on any decision so a replay
        cannot re-approve. Approve records the connected-client grant and an audit
        entry; the returned loopback URL is what the SPA navigates the browser to.
        """
        request = await self._load_live_request(auth_request_id)
        await self._repo.delete_auth_request(auth_request_id)

        if not approve:
            await self._repo.commit()
            _log.info("oauth_authorization_denied", client_id=request.client_id, user_id=user_id)
            denied = self._state_only(request.state, "access_denied")
            return _append_query(request.redirect_uri, denied)

        await self._repo.upsert_grant(
            user_id=user_id, client_id=request.client_id, scope=request.scope
        )
        code = _new_opaque_id()
        await self._repo.add_code(
            OAuthAuthorizationCode(
                code=code,
                client_id=request.client_id,
                user_id=user_id,
                redirect_uri=request.redirect_uri,
                scope=request.scope,
                code_challenge=request.code_challenge,
                code_challenge_method=request.code_challenge_method,
                resource=request.resource,
                expires_at=datetime.now(UTC) + self._config.code_ttl,
            )
        )
        await self._repo.record_event(
            user_id=user_id,
            client_id=request.client_id,
            event=OAuthEvent.GRANTED.value,
            scope=request.scope,
        )
        await self._repo.commit()
        _log.info("oauth_authorization_granted", client_id=request.client_id, user_id=user_id)
        params = {"code": code}
        if request.state is not None:
            params["state"] = request.state
        return _append_query(request.redirect_uri, params)

    async def _load_live_request(self, auth_request_id: str) -> OAuthAuthRequest:
        request = await self._repo.get_auth_request(auth_request_id)
        if request is None or _is_expired(request.expires_at):
            raise NotFound("This authorization request expired or does not exist.")
        return request

    @staticmethod
    def _state_only(state: str | None, error: str) -> dict[str, str]:
        params = {"error": error}
        if state is not None:
            params["state"] = state
        return params

    def _reject_invalid_redirect_uris(self, uris: list[str]) -> None:
        for uri in uris:
            parts = urlsplit(uri)
            if not parts.scheme:
                raise OAuthError.invalid_client_metadata(f"redirect_uri is not absolute: {uri}")
            # Cleartext http is only acceptable to a loopback listener (RFC 8252);
            # a non-loopback http redirect is interceptable and rejected.
            if parts.scheme == "http" and not is_loopback(uri):
                raise OAuthError.invalid_client_metadata(
                    f"non-loopback http redirect_uri is not allowed: {uri}"
                )

    def _resolve_registration_scope(self, requested: str | None) -> str:
        if requested is None:
            return _DEFAULT_SCOPE
        return self._require_supported_scopes(requested)

    def _resolve_requested_scope(self, requested: str | None, client_scope: str) -> str:
        if requested is None:
            return client_scope
        granted = set(client_scope.split())
        for scope in self._require_supported_scopes(requested).split():
            if scope not in granted:
                raise OAuthError.invalid_scope(f"scope '{scope}' was not granted to this client.")
        return requested

    @staticmethod
    def _require_supported_scopes(requested: str) -> str:
        for scope in requested.split():
            if scope not in SUPPORTED_SCOPES:
                raise OAuthError.invalid_scope(f"Unsupported scope: {scope}")
        return requested
