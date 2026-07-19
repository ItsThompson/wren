"""Wire schemas and domain objects for the accounts domain.

Request bodies are validated at the boundary (FastAPI/Pydantic); the response
models deliberately never carry the password hash. :class:`Session` is a domain
object the service returns: it bundles the authenticated user with the freshly
minted token pair so the transport adapter can both set cookies and return the
user body, without the service knowing about HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel, EmailStr

if TYPE_CHECKING:
    from wren.accounts.tokens import TokenPair


class RegisterRequest(BaseModel):
    """Registration input. Structural typing only; domain rules (password
    strength, handle charset) are enforced in the service for specific messages."""

    username: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    """Login input. ``email`` is a plain string (not ``EmailStr``) so a malformed
    address takes the same generic 401 path as a wrong password, never leaking
    whether the address is even well-formed vs. registered."""

    email: str
    password: str


class AuthenticatedUser(BaseModel):
    """The authenticated user's own view, returned by register/login/refresh.

    Carries the private ``email`` (the caller is the account owner) but never the
    password hash. The public, cross-user projection lives in ``PublicProfile``.
    """

    id: str
    username: str
    email: str
    created_at: datetime
    has_completed_onboarding: bool


class PublicProfile(BaseModel):
    """Public, cross-user profile projection keyed by the handle.

    Stubbed here (handle + display name).
    """

    handle: str
    display_name: str


@dataclass(frozen=True)
class Session:
    """A resolved session: the authenticated user plus its minted token pair."""

    user: AuthenticatedUser
    tokens: TokenPair
