"""Wire schemas and domain objects for the OAuth AS.

DCR (`/register`) uses RFC 7591 JSON shapes; the SPA-facing endpoints
(`/authorize/context`, `/authorize/decision`, `/me/clients`) use typed models the
frontend codegen consumes. The form-encoded `/token` and `/revoke` inputs are
parsed by the router into the small dataclasses here so the service methods take
typed values, never raw request objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class OAuthEvent(StrEnum):
    """Authorization audit-log event kinds (client, user, event, date)."""

    GRANTED = "granted"
    TOKEN_ISSUED = "token_issued"
    REFRESHED = "refreshed"
    REVOKED = "revoked"


# --- Dynamic Client Registration (RFC 7591) ---------------------------------


class ClientRegistrationRequest(BaseModel):
    """RFC 7591 registration input. Only ``redirect_uris`` is required at P0."""

    redirect_uris: list[str] = Field(min_length=1)
    client_name: str | None = None
    grant_types: list[str] | None = None
    response_types: list[str] | None = None
    scope: str | None = None
    token_endpoint_auth_method: str | None = None


class ClientRegistrationResponse(BaseModel):
    """RFC 7591 registration response echoing the stored client metadata."""

    client_id: str
    client_name: str
    redirect_uris: list[str]
    grant_types: list[str]
    response_types: list[str]
    scope: str
    token_endpoint_auth_method: str
    client_id_issued_at: int


# --- SPA consent flow (Ticket 19 backend seam) ------------------------------


class AuthorizationContext(BaseModel):
    """What the SPA consent screen renders for a parked ``auth_request_id``."""

    client_name: str
    scopes: list[str]
    authenticated: bool


class DecisionRequest(BaseModel):
    """The human's consent decision for a parked request."""

    auth_request_id: str
    approve: bool


class DecisionResult(BaseModel):
    """The loopback URL the SPA redirects the browser to (approve or deny).

    Returned as JSON (not a 302) because the SPA calls the decision endpoint via a
    credentialed XHR; the SPA performs the browser navigation to the loopback
    listener itself.
    """

    redirect_uri: str


# --- Token endpoint ---------------------------------------------------------


@dataclass(frozen=True)
class AuthorizeParams:
    """Parsed ``GET /authorize`` query params, validated + parked by the service."""

    client_id: str
    redirect_uri: str
    response_type: str
    code_challenge: str
    code_challenge_method: str
    scope: str | None = None
    state: str | None = None
    resource: str | None = None


class TokenResponse(BaseModel):
    """RFC 6749 token response: access token + rotating refresh."""

    access_token: str
    token_type: str
    expires_in: int
    refresh_token: str
    scope: str


@dataclass(frozen=True)
class TokenRequest:
    """Parsed form-encoded ``/token`` input (both grant types)."""

    grant_type: str
    client_id: str | None = None
    code: str | None = None
    code_verifier: str | None = None
    redirect_uri: str | None = None
    refresh_token: str | None = None
    resource: str | None = None


# --- Connected clients (Ticket 19 backend seam) -----------------------------


class ConnectedClient(BaseModel):
    """One authorized agent in the user's connected-clients list."""

    client_id: str
    client_name: str
    scopes: list[str]
    last_authorized: datetime
