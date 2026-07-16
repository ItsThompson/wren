"""Prometheus HTTP metrics.

Metric names and labels follow a stable convention so alert
rules and dashboards can be dropped in later:

- ``http_requests_total{method,path,status}`` (counter)
- ``http_request_duration_seconds{method,path}`` (histogram)

``path`` is the matched route template (e.g. ``/roadmaps/{id}``) to bound label
cardinality; untemplated paths group to ``none``. ``/metrics`` is excluded from
its own counters to avoid self-referential scrape noise.

Each app owns a private ``CollectorRegistry`` for its HTTP families so the
external and internal apps can run in one process (the smoke test does) without
duplicate-timeseries errors. ``/metrics`` serves that private registry
concatenated with the shared :data:`~wren.core.observability.WREN_REGISTRY`
(domain, service, and DB-pool families), so one scrape sees the whole picture.

Kept in sync with :mod:`wren_mcp.metrics` by hand: the two differ only by which
shared registry is concatenated onto ``/metrics`` (``WREN_REGISTRY`` here vs the
MCP's ``TOOL_METRICS_REGISTRY``). Any change to the HTTP-metric families or
instrumentator wiring here MUST be mirrored there. See
``docs/infra-duplication.md`` for the `wren-common` deferral and drift checklist.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_fastapi_instrumentator.metrics import Info
from starlette.responses import Response

from wren.core.observability import WREN_REGISTRY

if TYPE_CHECKING:
    from fastapi import FastAPI

# An instrumentation function receives one request's Info and records to a metric.
Instrumentation = Callable[[Info], None]

METRICS_ENDPOINT = "/metrics"


def _requests_total(registry: CollectorRegistry) -> Instrumentation:
    metric = Counter(
        "http_requests_total",
        "Total number of HTTP requests by method, matched route template, and status.",
        labelnames=("method", "path", "status"),
        registry=registry,
    )

    def instrumentation(info: Info) -> None:
        metric.labels(
            method=info.method,
            path=info.modified_handler,
            status=info.modified_status,
        ).inc()

    return instrumentation


def _request_duration(registry: CollectorRegistry) -> Instrumentation:
    metric = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency in seconds by method and matched route template.",
        labelnames=("method", "path"),
        registry=registry,
    )

    def instrumentation(info: Info) -> None:
        metric.labels(
            method=info.method,
            path=info.modified_handler,
        ).observe(info.modified_duration)

    return instrumentation


def _expose_combined(app: FastAPI, http_registry: CollectorRegistry) -> None:
    """Serve ``/metrics`` as the app's private HTTP registry followed by the shared
    custom-metrics registry. Both are text exposition with disjoint metric names,
    so concatenation is a valid single scrape response."""

    @app.get(METRICS_ENDPOINT, include_in_schema=False)
    async def metrics() -> Response:
        payload = generate_latest(http_registry) + generate_latest(WREN_REGISTRY)
        return Response(content=payload, media_type=CONTENT_TYPE_LATEST)


def instrument(app: FastAPI) -> CollectorRegistry:
    """Wire request metrics and expose ``/metrics`` on ``app``.

    Returns the app's private HTTP registry (useful for tests).
    """
    registry = CollectorRegistry()
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_group_untemplated=True,
        excluded_handlers=[METRICS_ENDPOINT],
        registry=registry,
    )
    instrumentator.add(_requests_total(registry))
    instrumentator.add(_request_duration(registry))
    instrumentator.instrument(app)
    _expose_combined(app, registry)
    return registry
