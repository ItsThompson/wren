"""Injection seams for the OAuth AS: the clock and opaque-id factories.

Mirrors the roadmaps exemplar (``roadmaps/service.py``'s ``Clock``/``TokenFactory``),
but hoisted to one module because the OAuth service, codec, and token-exchange
layers all inject the same two seams and the SqlAlchemy repository is fed the
*resolved* values (never minting its own). A pinned clock and deterministic id
factory then govern the whole mint -> park -> expire -> rotate -> revoke flow, so
tests assert expiry without ``sleep`` or negative ``timedelta``.

The defaults reproduce the pre-injection ambient calls exactly:

- :func:`new_urlsafe_id` -> ``secrets.token_urlsafe(32)``: the high-entropy opaque
  protocol identifiers (``client_id``, ``auth_request_id``, authorization ``code``).
- :func:`new_hex_id` -> ``uuid.uuid4().hex``: the internal surrogate record keys
  (``oauth_grants.id``, ``oauth_audit_log.id``, the access-token ``jti``).
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]
OpaqueIdFactory = Callable[[], str]

# Opaque protocol identifiers are high-entropy url-safe tokens (~43 chars from 32
# bytes); unguessability is defense-in-depth (authorization is by row scoping).
_URLSAFE_ID_BYTES = 32


def utcnow() -> datetime:
    """Behavior-preserving default clock: the current UTC wall-clock time."""
    return datetime.now(UTC)


def new_urlsafe_id() -> str:
    """A high-entropy url-safe opaque identifier (client_id, request_id, code)."""
    return secrets.token_urlsafe(_URLSAFE_ID_BYTES)


def new_hex_id() -> str:
    """A uuid4 hex surrogate key (grant id, audit-event id, access-token jti)."""
    return uuid.uuid4().hex
