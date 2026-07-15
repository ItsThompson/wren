"""Session and cookie configuration for the accounts domain (spec section 08).

Human sessions are HS256-signed JWTs with a dedicated ``SESSION_JWT_SECRET``,
kept separate from the agent OAuth keypair so the two actors have separate blast
radii. The cookie carries a short-lived access token plus a rotating refresh
token; TTLs and cookie attributes live here so the token codec, the cookie
writer, and tests all read one source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from wren.core.settings import AppSettings

# The access cookie is the session cookie the shared identity seam reads
# (``wren_session``); the refresh cookie is scoped to the /auth path so it is
# only sent to the endpoints that rotate or revoke it.
REFRESH_COOKIE_NAME = "wren_refresh"
AUTH_PATH = "/auth"

# Short access token, long rotating refresh (spec section 08). Defaults live in
# the domain that owns them; overridable for tests.
DEFAULT_ACCESS_TTL = timedelta(minutes=15)
DEFAULT_REFRESH_TTL = timedelta(days=14)


@dataclass(frozen=True)
class SessionConfig:
    """Inputs the token codec needs to sign and verify session JWTs."""

    secret: str
    access_ttl: timedelta = DEFAULT_ACCESS_TTL
    refresh_ttl: timedelta = DEFAULT_REFRESH_TTL


SameSite = Literal["lax", "strict", "none"]


@dataclass(frozen=True)
class CookieConfig:
    """How session cookies are written (attributes come from deployment config).

    ``Secure`` is on outside development (Cloudflare terminates TLS); ``domain``
    is ``.usewren.com`` in prod so ``usewren.com`` and ``api.usewren.com`` share
    the cookie, and empty in dev so the browser scopes it to ``localhost``.
    """

    secure: bool
    domain: str | None
    samesite: SameSite = "lax"


def build_session_config(settings: AppSettings) -> SessionConfig:
    """Compose the token-signing config from deployment settings."""
    return SessionConfig(secret=settings.session_jwt_secret)


def build_cookie_config(settings: AppSettings) -> CookieConfig:
    """Compose cookie attributes from deployment settings.

    Dev keeps ``Secure`` off (plain-HTTP localhost) and omits ``Domain`` (so the
    cookie is host-only); prod turns ``Secure`` on and pins ``Domain`` to the
    configured apex so the SPA and API subdomains share the session.
    """
    return CookieConfig(
        secure=not settings.is_dev,
        domain=settings.cookie_domain or None,
    )
