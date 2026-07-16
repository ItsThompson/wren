"""Domain, service, and DB-pool metric families.

Complements the HTTP request metrics in :mod:`wren.core.metrics`. Where those
count traffic at the edge, these count the things the three P0 alerts and future
dashboards need below the edge: unexpected service-method failures, OAuth token
issuance, and database-pool health. Every family is a process-global singleton
registered on the dedicated :data:`WREN_REGISTRY`, which
:func:`wren.core.metrics.instrument` exposes on ``/metrics`` alongside each app's
private HTTP registry.

Metric names and labels follow a stable convention so alert
rules and dashboards can be dropped in later:

- ``service_method_failures_total{service,method}`` (counter): one increment when
  a public service method exits with an *unexpected* error. A model-recoverable
  4xx (any ``ExpectedError`` with ``status < 500``: a ``WrenError`` 404/409/422 or
  an OAuth ``invalid_grant``) is a domain outcome, not an operational failure, so
  it is deliberately excluded; an ``ExpectedError`` with ``status >= 500`` (e.g. an
  OAuth ``server_error``) and any non-``ExpectedError`` exception are counted. This
  counter tracks the faults that surface as 5xx and correlates with the
  ``HighErrorRate`` alert.
- ``oauth_tokens_issued_total{grant_type}`` (counter): access/refresh token
  issuance, split by grant (``authorization_code`` = first issuance,
  ``refresh_token`` = rotation).
- ``db_query_duration_seconds{query_name}`` (histogram) and
  ``active_connections`` (gauge): pool observability wired via SQLAlchemy engine
  events in :mod:`wren.core.db`, which owns the engine.

This module is a leaf: it must not import :mod:`wren.core.errors` at module scope
(``errors`` -> ``app_factory`` -> ``metrics`` -> here would cycle). The one place
that needs ``WrenError`` imports it lazily on the failure path.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

# The custom-metrics registry. Kept separate from each app's private HTTP
# registry so both the external and internal apps can be built in one process
# (the smoke test does) without duplicate-timeseries errors, while these
# process-global families are defined exactly once at import.
WREN_REGISTRY = CollectorRegistry()

SERVICE_METHOD_FAILURES = Counter(
    "service_method_failures_total",
    "Public service-layer methods that exited with an unexpected (5xx / non-ExpectedError) error.",
    labelnames=("service", "method"),
    registry=WREN_REGISTRY,
)

OAUTH_TOKENS_ISSUED = Counter(
    "oauth_tokens_issued_total",
    "OAuth access/refresh token pairs issued, by grant type.",
    labelnames=("grant_type",),
    registry=WREN_REGISTRY,
)

DB_QUERY_DURATION = Histogram(
    "db_query_duration_seconds",
    "Database statement execution latency in seconds by query name.",
    labelnames=("query_name",),
    registry=WREN_REGISTRY,
)

ACTIVE_CONNECTIONS = Gauge(
    "active_connections",
    "Connections currently checked out of the SQLAlchemy pool.",
    registry=WREN_REGISTRY,
)

_ServiceT = TypeVar("_ServiceT")


def track_failures(service: str) -> Callable[[type[_ServiceT]], type[_ServiceT]]:
    """Class decorator: count each public async method's *unexpected* failures.

    Wraps every public coroutine method (``async def`` not prefixed with ``_``)
    so that an exception increments ``service_method_failures_total{service,
    method}`` and is then re-raised. Private helpers are left alone, so a public
    method that delegates to private helpers is counted exactly once (no
    double-count); the service layer has no public-to-public calls, so no wrapped
    method is reached through another wrapped method.
    """

    def decorate(cls: type[_ServiceT]) -> type[_ServiceT]:
        for name, attr in list(vars(cls).items()):
            if name.startswith("_") or not inspect.iscoroutinefunction(attr):
                continue
            setattr(cls, name, _wrap_method(service, name, attr))
        return cls

    return decorate


def _wrap_method(
    service: str, method: str, fn: Callable[..., Awaitable[Any]]
) -> Callable[..., Awaitable[Any]]:
    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except Exception as exc:
            if _is_unexpected(exc):
                SERVICE_METHOD_FAILURES.labels(service=service, method=method).inc()
            raise

    return wrapper


def _is_unexpected(exc: BaseException) -> bool:
    """True for a fault that should surface as 5xx (an operational failure).

    An :class:`~wren.core.errors.ExpectedError` (a ``WrenError`` or an
    ``OAuthError``) with an HTTP ``status`` below 500 is a model-recoverable 4xx
    outcome and is NOT counted; one with ``status`` >= 500 (e.g. an OAuth
    ``server_error``) IS counted; any other exception IS counted. Classification is
    by status, not by type: ``status`` is read via ``getattr`` because ``WrenError``
    declares it at class level while ``OAuthError`` sets it per-instance.

    ``ExpectedError`` is imported lazily here (only on the failure path) so this
    leaf module stays free of the ``errors`` -> ``app_factory`` -> ``metrics``
    import chain at module load.
    """
    from wren.core.errors import ExpectedError

    if isinstance(exc, ExpectedError):
        return getattr(exc, "status", 500) >= 500
    return True
