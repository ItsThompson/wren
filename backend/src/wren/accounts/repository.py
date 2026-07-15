"""Account persistence: the repository interface and its SQLAlchemy binding.

The service depends on the :class:`AccountRepository` interface and receives a
resolved identity, never building queries itself (spec section 05). Tests
substitute an in-memory repository at this interface; production binds
:class:`SqlAlchemyAccountRepository` over a request-scoped ``AsyncSession``.

Transaction ownership: ``core.db.get_session`` is yield-only (it does not commit),
so the transaction boundary lives here. The service calls :meth:`commit` after a
successful write and :meth:`rollback` on failure; this keeps the "one row or
None" reads and the commit policy in one place.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from wren.accounts.models import RevokedSession, User
from wren.accounts.tokens import RefreshClaims
from wren.core.db import fetch_optional


class AccountRepository(Protocol):
    """Data access for accounts, scoped to the operations the service needs."""

    async def get_by_email(self, email: str) -> User | None: ...

    async def get_by_username(self, username: str) -> User | None: ...

    async def get_by_id(self, user_id: str) -> User | None: ...

    async def add_user(self, user: User) -> None: ...

    async def is_session_revoked(self, jti: str) -> bool: ...

    async def revoke_session(self, claims: RefreshClaims) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class SqlAlchemyAccountRepository:
    """The production repository over a request-scoped :class:`AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        return await fetch_optional(self._session, select(User).where(User.email == email))

    async def get_by_username(self, username: str) -> User | None:
        return await fetch_optional(self._session, select(User).where(User.username == username))

    async def get_by_id(self, user_id: str) -> User | None:
        return await fetch_optional(self._session, select(User).where(User.id == user_id))

    async def add_user(self, user: User) -> None:
        self._session.add(user)
        # Flush so a unique-constraint breach surfaces as an IntegrityError now,
        # inside the service's try/except, rather than at commit time.
        await self._session.flush()

    async def is_session_revoked(self, jti: str) -> bool:
        found = await fetch_optional(
            self._session, select(RevokedSession.jti).where(RevokedSession.jti == jti)
        )
        return found is not None

    async def revoke_session(self, claims: RefreshClaims) -> None:
        # Insert-or-ignore: revoking an already-revoked session is idempotent
        # (logout twice, or a rotated session id re-submitted).
        statement = (
            pg_insert(RevokedSession)
            .values(jti=claims.sid, user_id=claims.user_id, expires_at=claims.expires_at)
            .on_conflict_do_nothing(index_elements=[RevokedSession.jti])
        )
        await self._session.execute(statement)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
