"""OAuth 2.1 AS persistence models.

Six tables back the AS:

- ``oauth_clients``: Dynamic Client Registration records (RFC 7591); open
  registration at P0, public clients (PKCE, no secret).
- ``oauth_auth_requests``: authorize requests **parked** server-side under an
  opaque ``auth_request_id`` so the SPA only round-trips the id, not the OAuth
  params. Short-lived.
- ``oauth_authorization_codes``: one-time codes minted at consent, PKCE-bound.
- ``oauth_refresh_tokens``: rotating refresh tokens, stored only as a SHA-256
  hash; ``revoked`` supports rotation and replay rejection.
- ``oauth_grants``: the connected-client relationship (one per user+client) that
  ``/me/clients`` lists and revokes.
- ``oauth_audit_log``: append-only record of agent grants (client, user, event,
  date), the authorization audit log the security contract requires.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from wren.core.orm import Base

# Opaque server-minted identifiers/secrets are url-safe tokens (~43 chars) or uuid
# hex (32); 64 leaves headroom. Token hashes are SHA-256 hex (64 chars exactly).
_ID_LEN = 64
_HASH_LEN = 64


class OAuthClient(Base):
    """A dynamically registered client. ``client_id`` is server-minted, opaque."""

    __tablename__ = "oauth_clients"

    client_id: Mapped[str] = mapped_column(String(_ID_LEN), primary_key=True)
    client_name: Mapped[str] = mapped_column(String(200))
    redirect_uris: Mapped[list[str]] = mapped_column(JSONB)
    grant_types: Mapped[list[str]] = mapped_column(JSONB)
    response_types: Mapped[list[str]] = mapped_column(JSONB)
    scope: Mapped[str] = mapped_column(String(500))
    token_endpoint_auth_method: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OAuthAuthRequest(Base):
    """A parked authorize request, addressed by an opaque ``auth_request_id``."""

    __tablename__ = "oauth_auth_requests"

    id: Mapped[str] = mapped_column(String(_ID_LEN), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(_ID_LEN))
    redirect_uri: Mapped[str] = mapped_column(String(2000))
    scope: Mapped[str] = mapped_column(String(500))
    state: Mapped[str | None] = mapped_column(String(500), nullable=True)
    code_challenge: Mapped[str] = mapped_column(String(128))
    code_challenge_method: Mapped[str] = mapped_column(String(8))
    resource: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OAuthAuthorizationCode(Base):
    """A one-time authorization code bound to a user, client, and PKCE challenge."""

    __tablename__ = "oauth_authorization_codes"

    code: Mapped[str] = mapped_column(String(_ID_LEN), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(_ID_LEN))
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    redirect_uri: Mapped[str] = mapped_column(String(2000))
    scope: Mapped[str] = mapped_column(String(500))
    code_challenge: Mapped[str] = mapped_column(String(128))
    code_challenge_method: Mapped[str] = mapped_column(String(8))
    resource: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OAuthRefreshToken(Base):
    """A rotating refresh token, stored only as a hash; ``revoked`` gates reuse."""

    __tablename__ = "oauth_refresh_tokens"

    token_hash: Mapped[str] = mapped_column(String(_HASH_LEN), primary_key=True)
    grant_id: Mapped[str] = mapped_column(String(_ID_LEN), index=True)
    client_id: Mapped[str] = mapped_column(String(_ID_LEN))
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    scope: Mapped[str] = mapped_column(String(500))
    resource: Mapped[str] = mapped_column(String(500))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OAuthGrant(Base):
    """The connected-client relationship: one active authorization per user+client."""

    __tablename__ = "oauth_grants"
    __table_args__ = (UniqueConstraint("user_id", "client_id"),)

    id: Mapped[str] = mapped_column(String(_ID_LEN), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    client_id: Mapped[str] = mapped_column(String(_ID_LEN))
    scope: Mapped[str] = mapped_column(String(500))
    authorized_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OAuthAuditLog(Base):
    """Append-only authorization audit: which client acted for which user, when."""

    __tablename__ = "oauth_audit_log"

    id: Mapped[str] = mapped_column(String(_ID_LEN), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    client_id: Mapped[str] = mapped_column(String(_ID_LEN))
    event: Mapped[str] = mapped_column(String(32))
    scope: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
