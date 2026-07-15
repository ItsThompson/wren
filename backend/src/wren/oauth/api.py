"""External REST adapter for the OAuth 2.1 AS (spec sections 06/08).

Thin handlers: each maps one request to one service call. The AS-metadata and
JWKS endpoints are static (built from pinned config + the signing key set at
router-creation time, never the request host). Protocol endpoints (`/register`,
`/authorize`, `/token`, `/revoke`) surface ``OAuthError`` as RFC 6749 JSON; the
SPA-facing endpoints (`/authorize/context`, `/authorize/decision`, `/me/clients`)
resolve the human session and render ``WrenError`` as problem+json.

Mounted on the external app only. Every route is declared in the external route
registry (``core.route_registry``) so the coverage test can enforce access levels.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Body, Depends, Form, Query, Request, Response
from starlette.responses import JSONResponse, RedirectResponse

from wren.core.errors import Unauthorized
from wren.core.identity import require_user
from wren.oauth.authorization import AuthorizationService
from wren.oauth.config import (
    AUTHORIZE_CONTEXT_PATH,
    AUTHORIZE_DECISION_PATH,
    AUTHORIZE_PATH,
    CLIENTS_PATH,
    JWKS_PATH,
    REGISTER_PATH,
    REVOKE_PATH,
    TOKEN_PATH,
    WELL_KNOWN_AS_METADATA_PATH,
    OAuthConfig,
)
from wren.oauth.keys import SigningKeySet
from wren.oauth.metadata import build_as_metadata
from wren.oauth.schemas import (
    AuthorizationContext,
    AuthorizeParams,
    ClientRegistrationRequest,
    ClientRegistrationResponse,
    ConnectedClient,
    DecisionRequest,
    DecisionResult,
    TokenRequest,
)
from wren.oauth.token_exchange import TokenService

# FastAPI dependencies that yield the request-scoped services.
ServiceProvider = Callable[..., Any]
# Response headers for token/metadata responses that must not be cached.
_NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


async def _optional_user(request: Request) -> str | None:
    """Resolve the human session if present, else ``None`` (consent context)."""
    try:
        return await require_user(request)
    except Unauthorized:
        return None


def create_oauth_router(
    *,
    config: OAuthConfig,
    keyset: SigningKeySet,
    authorization_provider: ServiceProvider,
    token_provider: ServiceProvider,
) -> APIRouter:
    """Build the OAuth AS router from pinned config, the key set, and providers."""
    router = APIRouter(tags=["oauth"])
    _mount_discovery(router, config=config, keyset=keyset)
    _mount_registration(router, authorization_provider)
    _mount_authorize(router, authorization_provider)
    _mount_token(router, token_provider)
    _mount_clients(router, token_provider)
    return router


def _mount_discovery(router: APIRouter, *, config: OAuthConfig, keyset: SigningKeySet) -> None:
    metadata = build_as_metadata(config)
    jwks = keyset.jwks()

    @router.get(WELL_KNOWN_AS_METADATA_PATH)
    async def as_metadata() -> JSONResponse:
        return JSONResponse(metadata, headers=_NO_STORE)

    @router.get(JWKS_PATH)
    async def jwks_document() -> JSONResponse:
        return JSONResponse(jwks, headers=_NO_STORE)


def _mount_registration(router: APIRouter, authorization_provider: ServiceProvider) -> None:
    @router.post(REGISTER_PATH, status_code=201)
    async def register_client(
        body: ClientRegistrationRequest,
        service: AuthorizationService = Depends(authorization_provider),
    ) -> ClientRegistrationResponse:
        return await service.register_client(body)


def _mount_authorize(router: APIRouter, authorization_provider: ServiceProvider) -> None:
    @router.get(AUTHORIZE_PATH)
    async def authorize(
        client_id: str = Query(default=""),
        redirect_uri: str = Query(default=""),
        response_type: str = Query(default=""),
        code_challenge: str = Query(default=""),
        code_challenge_method: str = Query(default=""),
        scope: str | None = Query(default=None),
        state: str | None = Query(default=None),
        resource: str | None = Query(default=None),
        service: AuthorizationService = Depends(authorization_provider),
    ) -> RedirectResponse:
        params = AuthorizeParams(
            client_id=client_id,
            redirect_uri=redirect_uri,
            response_type=response_type,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            scope=scope,
            state=state,
            resource=resource,
        )
        consent_url = await service.start_authorization(params)
        return RedirectResponse(consent_url, status_code=302)

    @router.get(AUTHORIZE_CONTEXT_PATH)
    async def authorize_context(
        request: Request,
        auth_request_id: str = Query(),
        service: AuthorizationService = Depends(authorization_provider),
    ) -> AuthorizationContext:
        user_id = await _optional_user(request)
        return await service.get_context(auth_request_id, authenticated=user_id is not None)

    @router.post(AUTHORIZE_DECISION_PATH)
    async def authorize_decision(
        body: DecisionRequest = Body(),
        user_id: str = Depends(require_user),
        service: AuthorizationService = Depends(authorization_provider),
    ) -> DecisionResult:
        redirect_uri = await service.decide(
            auth_request_id=body.auth_request_id, user_id=user_id, approve=body.approve
        )
        return DecisionResult(redirect_uri=redirect_uri)


def _mount_token(router: APIRouter, token_provider: ServiceProvider) -> None:
    @router.post(TOKEN_PATH)
    async def token(
        grant_type: str = Form(default=""),
        client_id: str | None = Form(default=None),
        code: str | None = Form(default=None),
        code_verifier: str | None = Form(default=None),
        redirect_uri: str | None = Form(default=None),
        refresh_token: str | None = Form(default=None),
        resource: str | None = Form(default=None),
        service: TokenService = Depends(token_provider),
    ) -> JSONResponse:
        result = await service.exchange(
            TokenRequest(
                grant_type=grant_type,
                client_id=client_id,
                code=code,
                code_verifier=code_verifier,
                redirect_uri=redirect_uri,
                refresh_token=refresh_token,
                resource=resource,
            )
        )
        return JSONResponse(result.model_dump(), headers=_NO_STORE)

    @router.post(REVOKE_PATH)
    async def revoke(
        token: str = Form(),
        token_type_hint: str | None = Form(default=None),
        client_id: str | None = Form(default=None),
        service: TokenService = Depends(token_provider),
    ) -> Response:
        await service.revoke(token, client_id=client_id)
        return Response(status_code=200, headers=_NO_STORE)


def _mount_clients(router: APIRouter, token_provider: ServiceProvider) -> None:
    @router.get(CLIENTS_PATH)
    async def list_clients(
        user_id: str = Depends(require_user),
        service: TokenService = Depends(token_provider),
    ) -> list[ConnectedClient]:
        return await service.list_connected_clients(user_id)

    @router.delete(CLIENTS_PATH + "/{client_id}", status_code=204)
    async def revoke_client(
        client_id: str,
        user_id: str = Depends(require_user),
        service: TokenService = Depends(token_provider),
    ) -> None:
        await service.revoke_connected_client(user_id, client_id)
