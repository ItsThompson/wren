"""OAuth protocol error responses (RFC 6749 §5.2 / RFC 7591 §3.2.2).

The OAuth handshake endpoints (`/token`, `/register`, `/revoke`, `/authorize`)
must return the OAuth-standard ``{"error", "error_description"}`` JSON that
clients and the MCP SDK parse, **not** the product's RFC 9457 problem+json. This
module owns that contract and its exception handler, wired only on the external
app alongside the shared ``WrenError`` handler. Product-shaped OAuth endpoints
consumed by our own SPA (`/authorize/context`, `/authorize/decision`,
`/me/clients`) keep raising ``WrenError`` and render as problem+json.
"""

from __future__ import annotations

from enum import StrEnum

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from wren.core.app_factory import ExceptionHandler, ExceptionKey
from wren.core.errors import ExpectedError


class OAuthErrorCode(StrEnum):
    """RFC 6749 / 8707 error codes returned by the protocol endpoints."""

    INVALID_REQUEST = "invalid_request"
    INVALID_CLIENT = "invalid_client"
    INVALID_GRANT = "invalid_grant"
    UNAUTHORIZED_CLIENT = "unauthorized_client"
    UNSUPPORTED_GRANT_TYPE = "unsupported_grant_type"
    INVALID_SCOPE = "invalid_scope"
    INVALID_TARGET = "invalid_target"  # RFC 8707: unknown/mismatched resource
    ACCESS_DENIED = "access_denied"
    INVALID_CLIENT_METADATA = "invalid_client_metadata"  # RFC 7591 DCR
    SERVER_ERROR = "server_error"


class OAuthError(ExpectedError):
    """An OAuth protocol error rendered as RFC 6749 ``error`` JSON.

    Subclasses :class:`wren.core.errors.ExpectedError` so the failure classifier
    treats a routine 4xx (``invalid_grant``, ``invalid_client``) as
    model-recoverable and leaves ``service_method_failures_total`` untouched, while
    a ``server_error`` (``status=500``) is still counted as an operational fault.
    ``status`` is set per-instance (default 400).
    """

    def __init__(self, error: OAuthErrorCode, description: str, *, status: int = 400) -> None:
        self.error = error
        self.description = description
        self.status = status
        super().__init__(f"{error}: {description}")

    @classmethod
    def invalid_request(cls, description: str) -> OAuthError:
        return cls(OAuthErrorCode.INVALID_REQUEST, description)

    @classmethod
    def invalid_client(cls, description: str) -> OAuthError:
        # RFC 6749 §5.2: invalid client authentication is 401.
        return cls(OAuthErrorCode.INVALID_CLIENT, description, status=401)

    @classmethod
    def invalid_grant(cls, description: str) -> OAuthError:
        return cls(OAuthErrorCode.INVALID_GRANT, description)

    @classmethod
    def unsupported_grant_type(cls, description: str) -> OAuthError:
        return cls(OAuthErrorCode.UNSUPPORTED_GRANT_TYPE, description)

    @classmethod
    def invalid_scope(cls, description: str) -> OAuthError:
        return cls(OAuthErrorCode.INVALID_SCOPE, description)

    @classmethod
    def invalid_target(cls, description: str) -> OAuthError:
        return cls(OAuthErrorCode.INVALID_TARGET, description)

    @classmethod
    def invalid_client_metadata(cls, description: str) -> OAuthError:
        return cls(OAuthErrorCode.INVALID_CLIENT_METADATA, description)


def _render(exc: OAuthError) -> Response:
    # Token/authorization responses must not be cached (RFC 6749 §5.1).
    return JSONResponse(
        status_code=exc.status,
        content={"error": exc.error.value, "error_description": exc.description},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )


async def handle_oauth_error(_request: Request, exc: Exception) -> Response:
    """Render an :class:`OAuthError` as RFC 6749 error JSON."""
    if not isinstance(exc, OAuthError):  # pragma: no cover - registered only for OAuthError
        raise exc
    return _render(exc)


def build_oauth_exception_handlers() -> dict[ExceptionKey, ExceptionHandler]:
    """The OAuth error handler the external app merges with the shared handlers."""
    return {OAuthError: handle_oauth_error}
