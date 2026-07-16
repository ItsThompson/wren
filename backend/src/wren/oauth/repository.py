"""OAuth AS persistence: the repository interface and its SQLAlchemy binding.

The service depends on this interface and receives resolved identities, never
building queries itself. Tests substitute an in-memory
repository; production binds :class:`SqlAlchemyOAuthRepository` over a
request-scoped ``AsyncSession``. As with accounts, ``get_session`` is yield-only,
so the transaction boundary lives here: the service calls :meth:`commit` after a
successful write and :meth:`rollback` on failure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from wren.core.db import fetch_optional
from wren.oauth.models import (
    OAuthAuditLog,
    OAuthAuthorizationCode,
    OAuthAuthRequest,
    OAuthClient,
    OAuthGrant,
    OAuthRefreshToken,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession


class OAuthRepository(Protocol):
    """Data access for the OAuth AS, scoped to the operations the service needs."""

    async def add_client(self, client: OAuthClient) -> None: ...
    async def get_client(self, client_id: str) -> OAuthClient | None: ...
    async def get_clients(self, client_ids: Sequence[str]) -> dict[str, str]: ...
    async def delete_clients_created_before(self, cutoff: datetime) -> list[str]: ...

    async def add_auth_request(self, request: OAuthAuthRequest) -> None: ...
    async def get_auth_request(self, request_id: str) -> OAuthAuthRequest | None: ...
    async def delete_auth_request(self, request_id: str) -> None: ...

    async def add_code(self, code: OAuthAuthorizationCode) -> None: ...
    async def get_code(self, code: str) -> OAuthAuthorizationCode | None: ...
    async def delete_code(self, code: str) -> None: ...

    async def add_refresh_token(self, token: OAuthRefreshToken, *, now: datetime) -> None: ...
    async def get_refresh_token(self, token_hash: str) -> OAuthRefreshToken | None: ...
    async def revoke_refresh_token(self, token_hash: str) -> None: ...
    async def revoke_grant_refresh_tokens(self, grant_id: str) -> None: ...

    async def upsert_grant(
        self, *, user_id: str, client_id: str, scope: str, now: datetime, grant_id: str
    ) -> str: ...
    async def get_grant(self, user_id: str, client_id: str) -> OAuthGrant | None: ...
    async def list_active_grants(self, user_id: str) -> list[OAuthGrant]: ...
    async def list_grants_for_clients(self, client_ids: Sequence[str]) -> list[OAuthGrant]: ...
    async def revoke_grant(
        self, user_id: str, client_id: str, *, now: datetime
    ) -> OAuthGrant | None: ...

    async def record_event(
        self,
        *,
        user_id: str,
        client_id: str,
        event: str,
        scope: str | None = None,
        now: datetime,
        event_id: str,
    ) -> None: ...

    async def commit(self) -> None: ...


class SqlAlchemyOAuthRepository:
    """The production repository over a request-scoped :class:`AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- clients ------------------------------------------------------------

    async def add_client(self, client: OAuthClient) -> None:
        self._session.add(client)
        await self._session.flush()

    async def get_client(self, client_id: str) -> OAuthClient | None:
        return await fetch_optional(
            self._session, select(OAuthClient).where(OAuthClient.client_id == client_id)
        )

    async def get_clients(self, client_ids: Sequence[str]) -> dict[str, str]:
        """Batch-load ``client_id -> client_name`` for the connected-client list.

        One query instead of N serial :meth:`get_client` awaits over the shared
        session. A key missing from the returned map means the client was deleted
        (the caller skips its orphaned grant); an empty input returns ``{}``
        without a query.
        """
        if not client_ids:
            return {}
        result = await self._session.scalars(
            select(OAuthClient).where(OAuthClient.client_id.in_(client_ids))
        )
        return {client.client_id: client.client_name for client in result}

    async def delete_clients_created_before(self, cutoff: datetime) -> list[str]:
        """Delete stale open-registration clients (periodic cleanup hook, P0).

        Returns the deleted ``client_id``s so the caller can cascade-revoke their
        grants + refresh chains in the same transaction, leaving no grant that is
        invisible to ``/me/clients`` yet whose refresh token still rotates.
        """
        result = await self._session.execute(
            delete(OAuthClient)
            .where(OAuthClient.created_at < cutoff)
            .returning(OAuthClient.client_id)
        )
        return list(result.scalars().all())

    # --- parked authorize requests ------------------------------------------

    async def add_auth_request(self, request: OAuthAuthRequest) -> None:
        self._session.add(request)
        await self._session.flush()

    async def get_auth_request(self, request_id: str) -> OAuthAuthRequest | None:
        return await fetch_optional(
            self._session, select(OAuthAuthRequest).where(OAuthAuthRequest.id == request_id)
        )

    async def delete_auth_request(self, request_id: str) -> None:
        await self._session.execute(
            delete(OAuthAuthRequest).where(OAuthAuthRequest.id == request_id)
        )

    # --- authorization codes ------------------------------------------------

    async def add_code(self, code: OAuthAuthorizationCode) -> None:
        self._session.add(code)
        await self._session.flush()

    async def get_code(self, code: str) -> OAuthAuthorizationCode | None:
        return await fetch_optional(
            self._session, select(OAuthAuthorizationCode).where(OAuthAuthorizationCode.code == code)
        )

    async def delete_code(self, code: str) -> None:
        await self._session.execute(
            delete(OAuthAuthorizationCode).where(OAuthAuthorizationCode.code == code)
        )

    # --- refresh tokens -----------------------------------------------------

    async def add_refresh_token(self, token: OAuthRefreshToken, *, now: datetime) -> None:
        # Stamp created_at from the resolved clock so a pinned clock governs the
        # whole flow (the model's server_default would otherwise use DB time).
        token.created_at = now
        self._session.add(token)
        await self._session.flush()

    async def get_refresh_token(self, token_hash: str) -> OAuthRefreshToken | None:
        return await fetch_optional(
            self._session,
            select(OAuthRefreshToken).where(OAuthRefreshToken.token_hash == token_hash),
        )

    async def revoke_refresh_token(self, token_hash: str) -> None:
        await self._session.execute(
            update(OAuthRefreshToken)
            .where(OAuthRefreshToken.token_hash == token_hash)
            .values(revoked=True)
        )

    async def revoke_grant_refresh_tokens(self, grant_id: str) -> None:
        await self._session.execute(
            update(OAuthRefreshToken)
            .where(OAuthRefreshToken.grant_id == grant_id)
            .values(revoked=True)
        )

    # --- grants (connected clients) -----------------------------------------

    async def upsert_grant(
        self, *, user_id: str, client_id: str, scope: str, now: datetime, grant_id: str
    ) -> str:
        """Insert or refresh the (user, client) grant; returns its ``grant_id``.

        Re-consent refreshes ``authorized_at`` and clears any prior revocation, so
        one active grant per (user, client) is the connected-client record. The
        resolved ``now``/``grant_id`` are supplied by the service so one pinned
        clock and id factory govern the flow (on conflict the existing id is
        kept).
        """
        statement = (
            pg_insert(OAuthGrant)
            .values(
                id=grant_id, user_id=user_id, client_id=client_id, scope=scope, authorized_at=now
            )
            .on_conflict_do_update(
                index_elements=[OAuthGrant.user_id, OAuthGrant.client_id],
                set_={
                    "scope": scope,
                    "authorized_at": now,
                    "revoked_at": None,
                },
            )
            .returning(OAuthGrant.id)
        )
        result = await self._session.execute(statement)
        return result.scalar_one()

    async def get_grant(self, user_id: str, client_id: str) -> OAuthGrant | None:
        return await fetch_optional(
            self._session,
            select(OAuthGrant).where(
                OAuthGrant.user_id == user_id, OAuthGrant.client_id == client_id
            ),
        )

    async def list_active_grants(self, user_id: str) -> list[OAuthGrant]:
        result = await self._session.execute(
            select(OAuthGrant)
            .where(OAuthGrant.user_id == user_id, OAuthGrant.revoked_at.is_(None))
            .order_by(OAuthGrant.authorized_at.desc())
        )
        return list(result.scalars().all())

    async def list_grants_for_clients(self, client_ids: Sequence[str]) -> list[OAuthGrant]:
        """Batch-load the grants belonging to the given clients (cascade-revoke on
        client cleanup).

        Mirrors :meth:`get_clients` / roadmaps ``list_by_ids``: an empty input
        returns ``[]`` without a query; otherwise one ``.in_()`` read replaces N
        serial lookups.
        """
        if not client_ids:
            return []
        result = await self._session.scalars(
            select(OAuthGrant).where(OAuthGrant.client_id.in_(client_ids))
        )
        return list(result)

    async def revoke_grant(
        self, user_id: str, client_id: str, *, now: datetime
    ) -> OAuthGrant | None:
        grant = await self.get_grant(user_id, client_id)
        if grant is None or grant.revoked_at is not None:
            return None
        grant.revoked_at = now
        await self.revoke_grant_refresh_tokens(grant.id)
        return grant

    # --- audit --------------------------------------------------------------

    async def record_event(
        self,
        *,
        user_id: str,
        client_id: str,
        event: str,
        scope: str | None = None,
        now: datetime,
        event_id: str,
    ) -> None:
        """Append one authorization audit entry (client, user, event, date)."""
        self._session.add(
            OAuthAuditLog(
                id=event_id,
                user_id=user_id,
                client_id=client_id,
                event=event,
                scope=scope,
                created_at=now,
            )
        )

    async def commit(self) -> None:
        await self._session.commit()
