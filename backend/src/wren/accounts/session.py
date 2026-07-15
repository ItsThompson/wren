"""The real session verifier wired behind the identity seam.

``core.identity.require_user`` resolves the external app's ``user_id`` through an
injectable async :data:`SessionVerifier` (``deny_all_sessions`` until now). This
supplies the real one: verify the access-token cookie (HS256) and, because the
seam is async, do the per-request ``sid`` blacklist lookup so a revoked session
stops resolving immediately.

The two concerns are split so the composition is testable without a database:
:func:`create_session_verifier` takes an injected revocation lookup, and
:func:`build_revocation_lookup` is the thin DB glue that opens its own
short-lived session (it runs outside a request-scoped ``get_session``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from wren.accounts.repository import SqlAlchemyAccountRepository
from wren.accounts.tokens import SessionTokenCodec
from wren.core.db import Database
from wren.core.identity import SessionVerifier

# Resolves whether a session id has been revoked (blacklisted).
RevocationLookup = Callable[[str], Awaitable[bool]]


def create_session_verifier(
    codec: SessionTokenCodec, is_revoked: RevocationLookup
) -> SessionVerifier:
    """Build the async cookie -> ``user_id`` verifier for ``app.state``."""

    async def verify(cookie: str) -> str | None:
        claims = codec.verify_access(cookie)
        if claims is None:
            return None
        if await is_revoked(claims.sid):
            return None
        return claims.user_id

    return verify


def build_revocation_lookup(database: Database) -> RevocationLookup:
    """The DB-backed ``sid`` blacklist lookup, one short-lived session per call."""

    async def is_revoked(sid: str) -> bool:
        async with database.sessionmaker() as session:
            return await SqlAlchemyAccountRepository(session).is_session_revoked(sid)

    return is_revoked
