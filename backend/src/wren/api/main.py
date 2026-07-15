"""External app entrypoint (:8000).

Internet-reachable via the Cloudflare tunnel. Authenticates humans by session
cookie and hosts the public REST surface + OAuth AS (later tickets). Built from
the shared factory with the external service identity injected.
"""

from __future__ import annotations

from fastapi import FastAPI

from wren.accounts.api import create_accounts_router
from wren.accounts.config import (
    build_cookie_config,
    build_session_config,
    validate_session_secret,
)
from wren.accounts.passwords import BcryptPasswordHasher
from wren.accounts.session import build_revocation_lookup, create_session_verifier
from wren.accounts.tokens import SessionTokenCodec
from wren.accounts.wiring import build_account_service_provider
from wren.core.app_factory import create_app
from wren.core.db import create_database, create_db_lifespan, db_readiness_check
from wren.core.errors import build_exception_handlers
from wren.core.identity import StripInboundIdentityMiddleware, deny_all_sessions
from wren.core.settings import EXTERNAL_PORT, EXTERNAL_SERVICE, build_app_settings
from wren.roadmaps.api import create_roadmaps_router
from wren.roadmaps.wiring import build_roadmap_service_provider

settings = build_app_settings(service=EXTERNAL_SERVICE, port=EXTERNAL_PORT)
db = create_database(settings.database_url)

# Human session cookies (spec section 08): HS256 codec + bcrypt hasher wired into
# the /auth router and the real cookie verifier behind require_user.
session_config = build_session_config(settings)
# Fail fast on a missing/weak secret outside development (dev stays lenient and
# fail-safe denies), so a prod misconfig cannot silently mint unusable tokens.
validate_session_secret(session_config, is_dev=settings.is_dev)
cookie_config = build_cookie_config(settings)
codec = SessionTokenCodec(session_config)
service_provider = build_account_service_provider(BcryptPasswordHasher(), codec)
accounts_router = create_accounts_router(service_provider, cookie_config=cookie_config)

# Roadmap authoring (#7): create-draft + owner-scoped read over the same service
# layer, resolving identity via the human session cookie (require_user).
roadmaps_router = create_roadmaps_router(build_roadmap_service_provider())

app: FastAPI = create_app(
    settings,
    routers=[accounts_router, roadmaps_router],
    readiness_checks=[db_readiness_check(db.engine)],
    exception_handlers=build_exception_handlers(),
    lifespan=create_db_lifespan(db.engine),
)
app.state.db = db
# Replace the Ticket 3 deny-all default with the real signed-JWT + jti-blacklist
# verifier. With no configured SESSION_JWT_SECRET the app fail-safe denies every
# session rather than sign with an empty key.
app.state.session_verifier = (
    create_session_verifier(codec, build_revocation_lookup(db))
    if session_config.secret
    else deny_all_sessions
)
# Strip any client-supplied X-User-ID app-wide: the external app never trusts it.
app.add_middleware(StripInboundIdentityMiddleware)


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn

    uvicorn.run("wren.api.main:app", host=settings.host, port=settings.port)
