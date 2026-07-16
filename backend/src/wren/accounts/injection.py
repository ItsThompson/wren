"""Injection seams for the accounts domain: the clock and opaque-id factory.

Mirrors the roadmaps exemplar (``roadmaps/service.py``'s ``Clock``/``TokenFactory``)
and the OAuth :mod:`wren.oauth.injection` seam, so ``AccountService`` and
``SessionTokenCodec`` decide "now" and "new id" through injected callables. A
pinned clock then makes session expiry and refresh rotation assertable without
``sleep`` or negative ``timedelta``.

The defaults reproduce the pre-injection ambient calls exactly: :func:`utcnow`
(``datetime.now(UTC)``) and :func:`new_hex_id` (``uuid.uuid4().hex``, used for the
user id and the session ``sid``).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]
OpaqueIdFactory = Callable[[], str]


def utcnow() -> datetime:
    """Behavior-preserving default clock: the current UTC wall-clock time."""
    return datetime.now(UTC)


def new_hex_id() -> str:
    """A uuid4 hex identifier (the user id and the session ``sid``)."""
    return uuid.uuid4().hex
