"""Accounts ORM models: the ``users`` table and the refresh-``jti`` blacklist.

``username`` is the public handle; ``email`` is stored normalized (lowercased by
the service) and both are uniquely constrained. The password is stored only as a
bcrypt hash. ``revoked_sessions`` is the ``jti`` blacklist (spec section 08):
each row revokes one session id (shared by an access/refresh pair); ``expires_at``
lets a later cleanup job drop rows once the refresh token would have expired
anyway.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from wren.core.orm import Base


class User(Base):
    """A human account. ``id`` is a server-minted uuid hex; never client-set."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RevokedSession(Base):
    """One revoked session id (the refresh ``jti``); presence == revoked."""

    __tablename__ = "revoked_sessions"

    jti: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(32), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
