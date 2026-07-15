"""AccountService: registration, login/logout, session refresh, and profile.

The single source of truth for account business rules (spec section 05). It
receives a repository and collaborators, resolves identity from credentials or
tokens (never from caller-supplied ids), raises ``WrenError`` subclasses for the
adapter to render, and owns the transaction boundary (commit on success,
rollback on failure) because ``get_session`` is yield-only.

Session model (spec section 08): an access/refresh pair shares one session id
(``sid``). Logout and refresh-rotation revoke the old ``sid`` via the blacklist,
so a revoked refresh cannot mint a new access token and a revoked session's
still-unexpired access token stops resolving.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError

from wren.accounts.models import User
from wren.accounts.passwords import PasswordHasher, validate_password_strength
from wren.accounts.repository import AccountRepository
from wren.accounts.schemas import AuthenticatedUser, PublicProfile, Session
from wren.accounts.tokens import SessionTokenCodec
from wren.core.db import is_unique_violation
from wren.core.errors import Conflict, NotFound, Unauthorized, Validation
from wren.core.logging import get_logger
from wren.core.observability import track_failures

# A public handle: 3..32 chars, lowercase letters/digits/underscore/hyphen. Kept
# conservative because it appears in public profile URLs (Ticket 25).
_HANDLE_PATTERN = re.compile(r"^[a-z0-9_-]{3,32}$")
_HANDLE_REQUIREMENT = (
    "Username must be 3-32 characters using lowercase letters, digits, '_' or '-'."
)
# One message for both credential failures so login never reveals whether an
# email is registered (spec section 08 / US-ACCT-02).
_INVALID_CREDENTIALS = "Invalid email or password."

_log = get_logger("wren-accounts")


@track_failures("accounts")
class AccountService:
    """Business rules for human accounts and sessions."""

    def __init__(
        self,
        repo: AccountRepository,
        hasher: PasswordHasher,
        codec: SessionTokenCodec,
    ) -> None:
        self._repo = repo
        self._hasher = hasher
        self._codec = codec

    async def register(self, username: str, email: str, password: str) -> Session:
        """Create a user and start a session, or raise a field-level error.

        Duplicate detection is delegated to the ``users`` unique constraints (the
        authoritative, race-free source): on the resulting integrity error the
        transaction is rolled back and the colliding field is resolved for a
        field-level 409. No plaintext password is ever logged or returned.
        """
        handle = username.strip()
        normalized_email = _normalize_email(email)
        self._reject_invalid_handle(handle)
        self._reject_weak_password(password)

        now = datetime.now(UTC)
        user = User(
            id=uuid.uuid4().hex,
            username=handle,
            email=normalized_email,
            password_hash=self._hasher.hash(password),
            created_at=now,
            updated_at=now,
        )
        try:
            await self._repo.add_user(user)
            await self._repo.commit()
        except IntegrityError as exc:
            await self._repo.rollback()
            if not is_unique_violation(exc):
                raise
            raise await self._duplicate_conflict(normalized_email) from exc

        _log.info("user_registered", user_id=user.id)
        return self._start_session(user)

    async def login(self, email: str, password: str) -> Session:
        """Authenticate by email + password; generic 401 on any mismatch."""
        user = await self._repo.get_by_email(_normalize_email(email))
        if user is None or not self._hasher.verify(password, user.password_hash):
            raise Unauthorized(_INVALID_CREDENTIALS)
        _log.info("user_logged_in", user_id=user.id)
        return self._start_session(user)

    async def refresh(self, refresh_token: str) -> Session:
        """Rotate a valid refresh token into a fresh session; revoke the old id."""
        claims = self._codec.verify_refresh(refresh_token)
        if claims is None or await self._repo.is_session_revoked(claims.sid):
            raise Unauthorized("Session expired or revoked; log in again.")
        user = await self._repo.get_by_id(claims.user_id)
        if user is None:
            raise Unauthorized("Session expired or revoked; log in again.")
        await self._repo.revoke_session(claims)
        await self._repo.commit()
        _log.info("session_refreshed", user_id=user.id)
        return self._start_session(user)

    async def logout(self, refresh_token: str | None) -> None:
        """Revoke the current session's refresh id so it cannot be reused.

        Best-effort: a missing or already-invalid refresh token has nothing to
        revoke, so logout still succeeds (the adapter clears the cookies).
        """
        if refresh_token is None:
            return
        claims = self._codec.verify_refresh(refresh_token)
        if claims is None:
            return
        await self._repo.revoke_session(claims)
        await self._repo.commit()
        _log.info("user_logged_out", user_id=claims.user_id)

    async def profile(self, handle: str) -> PublicProfile:
        """Public profile by handle (stubbed; Ticket 25 adds public roadmaps)."""
        user = await self._repo.get_by_username(handle)
        if user is None:
            raise NotFound(f"No profile for handle '{handle}'.")
        return PublicProfile(handle=user.username, display_name=user.username)

    def _start_session(self, user: User) -> Session:
        return Session(user=_to_authenticated(user), tokens=self._codec.mint_pair(user.id))

    def _reject_invalid_handle(self, handle: str) -> None:
        if not _HANDLE_PATTERN.match(handle):
            raise Validation(_HANDLE_REQUIREMENT, fields={"username": _HANDLE_REQUIREMENT})

    def _reject_weak_password(self, password: str) -> None:
        message = validate_password_strength(password)
        if message is not None:
            raise Validation(message, fields={"password": message})

    async def _duplicate_conflict(self, email: str) -> Conflict:
        """Resolve which unique field collided so the 409 names the right field."""
        if await self._repo.get_by_email(email) is not None:
            return Conflict(
                "An account with this email already exists.",
                fields={"email": "This email is already registered."},
            )
        return Conflict(
            "This username is already taken.",
            fields={"username": "This username is already taken."},
        )


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _to_authenticated(user: User) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=user.id,
        username=user.username,
        email=user.email,
        created_at=user.created_at,
    )
