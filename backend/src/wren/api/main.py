"""External app entrypoint (:8000).

Internet-reachable via the Cloudflare tunnel. Authenticates humans by session
cookie and hosts the public REST surface + OAuth AS. Built from
the shared factory with the external service identity injected.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi.middleware.cors import CORSMiddleware

from wren.accounts.api import create_accounts_router
from wren.accounts.config import (
    build_cookie_config,
    build_session_config,
    validate_session_secret,
)
from wren.accounts.passwords import BcryptPasswordHasher
from wren.accounts.session import build_revocation_lookup, create_session_verifier
from wren.accounts.tokens import SessionTokenCodec
from wren.accounts.wiring import build_account_service_provider, build_event_publisher
from wren.core.app_factory import create_app
from wren.core.db import create_database, create_db_lifespan, db_readiness_check
from wren.core.errors import build_exception_handlers
from wren.core.identity import (
    StripInboundIdentityMiddleware,
    require_user,
)
from wren.core.settings import EXTERNAL_PORT, EXTERNAL_SERVICE, build_app_settings
from wren.core.state import deny_all_sessions
from wren.oauth.api import create_oauth_router
from wren.oauth.config import build_oauth_config
from wren.oauth.errors import build_oauth_exception_handlers
from wren.oauth.keys import load_signing_key_set
from wren.oauth.tokens import AccessTokenCodec
from wren.oauth.wiring import (
    build_authorization_service_provider,
    build_token_service_provider,
)
from wren.progress.router import create_progress_router
from wren.progress.wiring import build_progress_service_provider
from wren.roadmaps.listing_api import create_listing_router
from wren.roadmaps.router import create_roadmaps_router
from wren.roadmaps.wiring import (
    build_listing_service_provider,
    build_roadmap_read_service_provider,
    build_roadmap_service_provider,
)
from wren.skill.api import create_skill_router

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI

settings = build_app_settings(service=EXTERNAL_SERVICE, port=EXTERNAL_PORT)
db = create_database(settings.database_url)

# Human session cookies: HS256 codec + bcrypt hasher wired into
# the /auth router and the real cookie verifier behind require_user.
session_config = build_session_config(settings)
# Fail fast on a missing/weak secret outside development (dev stays lenient and
# fail-safe denies), so a prod misconfig cannot silently mint unusable tokens.
validate_session_secret(session_config, is_dev=settings.is_dev)
cookie_config = build_cookie_config(settings)
codec = SessionTokenCodec(session_config)
event_publisher = build_event_publisher(settings)
service_provider = build_account_service_provider(BcryptPasswordHasher(), codec, event_publisher)
accounts_router = create_accounts_router(service_provider, cookie_config=cookie_config)

# Roadmap authoring + reads over the same service layer, resolving identity via
# the human session cookie (require_user). The external app mounts the three
# web-only lifecycle routes (visibility / archive / delete) via
# include_web_lifecycle; the internal app never does.
roadmaps_router = create_roadmaps_router(
    build_roadmap_service_provider(),
    build_roadmap_read_service_provider(),
    identity=require_user,
    include_web_lifecycle=True,
)

# Dashboard + public profile: the private
# dashboard (authored + followed, require_user) and the public profile
# (published-public only, no session). The listing service composes the roadmaps,
# accounts, and progress repositories over one request-scoped session.
listing_router = create_listing_router(build_listing_service_provider())

# Follow + progress + server-computed next: the study-time surface over the
# progress service, resolving the human session via require_user and scoped to
# that user (another user's progress is never returned).
progress_router = create_progress_router(build_progress_service_provider(), identity=require_user)

# Shipped SKILL.md authoring guidance: the public,
# unauthenticated GET /skill an agent fetches (referenced from the MCP tool
# descriptions) to learn how to author a ZPD-ordered roadmap. Guidance, not user
# data, so no session is required or consulted.
skill_router = create_skill_router()

# Agent OAuth 2.1 Authorization Server. All issuer/metadata/
# endpoint URLs are built from pinned config (the Site-URL gotcha); the signing
# key is loaded from the mounted PEM (or an ephemeral dev keypair). Fails fast
# outside development when no key is configured, like the session secret.
oauth_config = build_oauth_config(settings)
oauth_keyset = load_signing_key_set(oauth_config, is_dev=settings.is_dev)
oauth_codec = AccessTokenCodec(oauth_keyset, oauth_config)
oauth_router = create_oauth_router(
    config=oauth_config,
    keyset=oauth_keyset,
    authorization_provider=build_authorization_service_provider(oauth_config),
    token_provider=build_token_service_provider(oauth_config, oauth_codec),
)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with create_db_lifespan(db.engine)(app):
        try:
            yield
        finally:
            await event_publisher.aclose()


app: FastAPI = create_app(
    settings,
    routers=[
        accounts_router,
        roadmaps_router,
        listing_router,
        progress_router,
        oauth_router,
        skill_router,
    ],
    readiness_checks=[db_readiness_check(db.engine)],
    exception_handlers={**build_exception_handlers(), **build_oauth_exception_handlers()},
    lifespan=_lifespan,
)
app.state.db = db
# Replace the deny-all default with the real signed-JWT + jti-blacklist
# verifier. With no configured SESSION_JWT_SECRET the app fail-safe denies every
# session rather than sign with an empty key.
app.state.session_verifier = (
    create_session_verifier(codec, build_revocation_lookup(db))
    if session_config.secret.get_secret_value()
    else deny_all_sessions
)
# Strip any client-supplied X-User-ID app-wide: the external app never trusts it.
app.add_middleware(StripInboundIdentityMiddleware)
# CORS for credentialed browser XHRs: the SPA origin for consent/login, plus the
# local MCP Inspector origin in development so its OAuth callback can exchange
# the authorization code. Added last so it is the outermost middleware and
# handles preflight before the identity strip.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn

    uvicorn.run("wren.api.main:app", host=settings.host, port=settings.port)
