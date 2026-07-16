"""Session JWTs: a short-lived access token + a rotating refresh token.

Both tokens are HS256-signed with the dedicated ``SESSION_JWT_SECRET``. An
access/refresh pair shares one opaque session id (``sid``); the
``sid`` is what the blacklist revokes, so revoking a session invalidates the
still-unexpired access token immediately (not just future refreshes). This is
why the identity seam's :data:`SessionVerifier` is async: verifying an access
token includes a ``sid`` blacklist lookup.

The codec is pure crypto over the config: no I/O, no DB. The service layer owns
the blacklist and the rotation policy; this module only mints and verifies.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import jwt

from wren.accounts.injection import Clock, OpaqueIdFactory, new_hex_id, utcnow

if TYPE_CHECKING:
    from wren.accounts.config import SessionConfig

_ALGORITHM = "HS256"
_ACCESS_TYPE = "access"
_REFRESH_TYPE = "refresh"


@dataclass(frozen=True)
class AccessClaims:
    """Verified access-token claims: the user and the session it belongs to."""

    user_id: str
    sid: str


@dataclass(frozen=True)
class RefreshClaims:
    """Verified refresh-token claims, plus the expiry the blacklist stores."""

    user_id: str
    sid: str
    expires_at: datetime


@dataclass(frozen=True)
class TokenPair:
    """A freshly minted access + refresh pair for one session (``sid``)."""

    access_token: str
    refresh_token: str
    sid: str
    access_max_age: int
    refresh_max_age: int
    refresh_expires_at: datetime


class SessionTokenCodec:
    """Mints and verifies session JWTs for one signing config."""

    def __init__(
        self,
        config: SessionConfig,
        *,
        clock: Clock = utcnow,
        new_id: OpaqueIdFactory = new_hex_id,
    ) -> None:
        self._config = config
        # Injected so mint and verify share one clock (tests advance it to assert
        # expiry) and the sid is deterministic; defaults reproduce the ambient calls.
        self._clock = clock
        self._new_id = new_id

    def mint_pair(self, user_id: str) -> TokenPair:
        """Mint an access + refresh pair sharing a fresh session id."""
        sid = self._new_id()
        now = self._clock()
        access_expires = now + self._config.access_ttl
        refresh_expires = now + self._config.refresh_ttl
        access_token = self._encode(user_id, sid, _ACCESS_TYPE, now, access_expires)
        refresh_token = self._encode(user_id, sid, _REFRESH_TYPE, now, refresh_expires)
        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            sid=sid,
            access_max_age=int(self._config.access_ttl.total_seconds()),
            refresh_max_age=int(self._config.refresh_ttl.total_seconds()),
            refresh_expires_at=refresh_expires,
        )

    def verify_access(self, token: str) -> AccessClaims | None:
        """Verify an access token; ``None`` on any signature/expiry/type failure."""
        payload = self._decode(token, _ACCESS_TYPE)
        if payload is None:
            return None
        return AccessClaims(user_id=payload["sub"], sid=payload["sid"])

    def verify_refresh(self, token: str) -> RefreshClaims | None:
        """Verify a refresh token; ``None`` on any signature/expiry/type failure."""
        payload = self._decode(token, _REFRESH_TYPE)
        if payload is None:
            return None
        return RefreshClaims(
            user_id=payload["sub"],
            sid=payload["sid"],
            expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
        )

    def _encode(
        self, user_id: str, sid: str, token_type: str, issued: datetime, expires: datetime
    ) -> str:
        payload = {
            "sub": user_id,
            "sid": sid,
            "type": token_type,
            "iat": issued,
            "exp": expires,
        }
        return jwt.encode(payload, self._config.secret.get_secret_value(), algorithm=_ALGORITHM)

    def _decode(self, token: str, expected_type: str) -> dict[str, Any] | None:
        try:
            payload = jwt.decode(
                token,
                self._config.secret.get_secret_value(),
                algorithms=[_ALGORITHM],
                # exp presence is still required; expiry itself is checked against
                # the injected clock below so a pinned clock governs the assertion.
                options={"require": ["exp", "sub"], "verify_exp": False},
            )
        except jwt.InvalidTokenError:
            return None
        if payload.get("type") != expected_type or "sid" not in payload:
            return None
        if datetime.fromtimestamp(payload["exp"], tz=UTC) <= self._clock():
            return None
        return payload
