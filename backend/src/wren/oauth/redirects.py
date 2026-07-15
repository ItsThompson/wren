"""Redirect-URI policy for public clients (RFC 8252).

Public (agent) clients use a loopback redirect, ``http://127.0.0.1:PORT/callback``
(or ``[::1]`` / ``localhost``), where the port is an ephemeral listener the agent
opens per run. The AS therefore permits loopback redirect URIs on **any port**
as long as scheme, host, and path match a registered loopback URI; non-loopback
(HTTPS) redirects require an exact match.
"""

from __future__ import annotations

from urllib.parse import urlsplit

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})


def is_loopback(uri: str) -> bool:
    """True for an ``http`` loopback redirect (127.0.0.1 / [::1] / localhost)."""
    parts = urlsplit(uri)
    return parts.scheme == "http" and (parts.hostname or "") in _LOOPBACK_HOSTS


def _loopback_identity(uri: str) -> tuple[str, str, str]:
    """The (scheme, host, path) of a loopback URI, ignoring the ephemeral port."""
    parts = urlsplit(uri)
    return parts.scheme, (parts.hostname or ""), parts.path


def is_allowed_redirect(requested: str, registered: list[str]) -> bool:
    """Whether ``requested`` is permitted given the client's ``registered`` URIs.

    Exact match is always allowed. A loopback ``requested`` additionally matches
    any registered loopback URI with the same scheme/host/path on a different
    port (RFC 8252), so an agent can bind a fresh ephemeral port each run.
    """
    if requested in registered:
        return True
    if not is_loopback(requested):
        return False
    target = _loopback_identity(requested)
    return any(is_loopback(uri) and _loopback_identity(uri) == target for uri in registered)
