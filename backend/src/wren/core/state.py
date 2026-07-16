"""Typed accessors for the auth-boundary ``app.state`` seams.

Starlette's ``app.state`` is dynamically typed: attribute access launders to
``Any``, which silently bypasses ``mypy --strict`` at the identity boundary (a
renamed or missing seam is not caught statically). This module is the one typed
place that reads those seams. Each accessor performs the ``getattr`` plus a
runtime type check and returns the fail-safe default on a missing OR wrong-type
attribute, so the boundary stays fail-closed exactly as before.

The session-seam contract (:data:`SessionVerifier`) and its deny-all default live
here (the lowest layer) so :mod:`wren.core.identity` can route through the
accessors without a circular import.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from starlette.applications import Starlette

# The app.state attributes the two identity boundaries resolve from.
SESSION_VERIFIER_ATTR = "session_verifier"
INTERNAL_API_TOKEN_ATTR = "internal_api_token"

# A SessionVerifier turns a raw session-cookie value into a resolved user_id, or
# None if the cookie is missing/invalid/expired. It is async so a per-request
# jti-blacklist lookup (an I/O call) can run behind this same contract without
# reworking require_user.
SessionVerifier = Callable[[str], Awaitable[str | None]]


async def deny_all_sessions(_cookie: str) -> str | None:
    """Default deny-all verifier: every cookie fails to resolve, so
    :func:`wren.core.identity.require_user` fail-safe denies. Replaced by injecting
    a real ``SessionVerifier`` on ``app.state.session_verifier``."""
    return None


def get_session_verifier(app: Starlette) -> SessionVerifier:
    """The injected session verifier, or the deny-all default.

    Returns :func:`deny_all_sessions` when the seam is unset OR not callable, so a
    missing or wrong-type wiring fail-safe denies rather than raising at the auth
    boundary."""
    verifier = getattr(app.state, SESSION_VERIFIER_ATTR, deny_all_sessions)
    if callable(verifier):
        return cast("SessionVerifier", verifier)
    return deny_all_sessions


def get_internal_token(app: Starlette) -> str:
    """The configured internal API token, or ``""``.

    Returns the empty string when the seam is unset OR not a ``str``; an empty
    expected token fail-safe denies every internal call (see
    :func:`wren.core.identity.require_internal_user`)."""
    token = getattr(app.state, INTERNAL_API_TOKEN_ATTR, "")
    return token if isinstance(token, str) else ""
