"""In-memory test doubles for the accounts domain.

The service layer is tested sociably: real password hasher (at a cheap cost),
real token codec, and this in-memory repository substituted at the repository
interface (the only true external boundary, Postgres). The fake enforces the
same unique constraints as the real ``users`` table so the duplicate-conflict
path is exercised without a database.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import SecretStr
from sqlalchemy.exc import IntegrityError

from wren.accounts.config import SessionConfig
from wren.accounts.injection import Clock, utcnow
from wren.accounts.passwords import BcryptPasswordHasher
from wren.accounts.tokens import RefreshClaims, SessionTokenCodec

if TYPE_CHECKING:
    from wren.accounts.models import User
    from wren.accounts.notifications import UserRegistered

# Cheap bcrypt cost for tests: real hashing + verification path, fast. Cost 12 is
# asserted directly in test_accounts_passwords.
TEST_BCRYPT_COST = 4
TEST_SESSION_SECRET = "unit-test-session-secret"


class _UniqueViolation(Exception):
    """Mimics an asyncpg unique-violation carried on IntegrityError.orig."""

    sqlstate = "23505"


class InMemoryAccountRepository:
    """A dict-backed :class:`AccountRepository` with real uniqueness semantics."""

    def __init__(self) -> None:
        self._by_id: dict[str, User] = {}
        self._revoked: set[str] = set()
        self.commits = 0
        self.rollbacks = 0

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self._by_id.values() if u.email == email), None)

    async def get_by_username(self, username: str) -> User | None:
        return next((u for u in self._by_id.values() if u.username == username), None)

    async def get_by_id(self, user_id: str) -> User | None:
        return self._by_id.get(user_id)

    async def add_user(self, user: User) -> None:
        for existing in self._by_id.values():
            if existing.email == user.email or existing.username == user.username:
                raise IntegrityError("INSERT INTO users", {}, _UniqueViolation())
        self._by_id[user.id] = user

    async def set_onboarding_complete(self, user_id: str) -> User | None:
        user = self._by_id.get(user_id)
        if user is None:
            return None
        user.has_completed_onboarding = True
        return user

    async def is_session_revoked(self, jti: str) -> bool:
        return jti in self._revoked

    async def revoke_session(self, claims: RefreshClaims) -> None:
        self._revoked.add(claims.sid)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


def build_test_codec(
    *,
    access_ttl: timedelta = timedelta(minutes=15),
    refresh_ttl: timedelta = timedelta(days=14),
    clock: Clock = utcnow,
) -> SessionTokenCodec:
    """A codec with the test secret and overridable TTLs/clock (for expiry tests)."""
    return SessionTokenCodec(
        SessionConfig(
            secret=SecretStr(TEST_SESSION_SECRET), access_ttl=access_ttl, refresh_ttl=refresh_ttl
        ),
        clock=clock,
    )


class MutableClock:
    """A pinned, advanceable clock for expiry tests (no ``sleep``/negative TTL)."""

    def __init__(self, now: datetime) -> None:
        self._now = now

    def __call__(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


def build_test_hasher() -> BcryptPasswordHasher:
    """The real bcrypt hasher at a cheap cost for fast tests."""
    return BcryptPasswordHasher(cost=TEST_BCRYPT_COST)


class SpyEventPublisher:
    """Records published user-registration events so tests can assert them."""

    def __init__(self) -> None:
        self.events: list[UserRegistered] = []

    def publish(self, event: UserRegistered) -> None:
        self.events.append(event)

    async def aclose(self) -> None:
        return
