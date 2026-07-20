"""Prometheus HTTP metrics shared by every Wren service.

Metric names and labels follow a stable convention so alert
rules and dashboards can be dropped in later:

- ``http_requests_total{method,path,status}`` (counter)
- ``http_request_duration_seconds{method,path}`` (histogram)

``path`` is the matched route template (e.g. ``/roadmaps/{id}``) to bound label
cardinality; untemplated paths group to ``none``. ``/metrics`` is excluded from
its own counters to avoid self-referential scrape noise.

Each app owns a private ``CollectorRegistry`` for its HTTP families so several
apps can run in one process (the smoke test does) without duplicate-timeseries
errors. :func:`instrument` serves that private registry concatenated with a
custom registry the caller injects (for example the backend's domain/service
families or the MCP's tool-invocation counter), so one scrape sees both the HTTP
edge and the domain families. The registry is injected rather than imported, so
this module carries no dependency on any specific app.
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


def _expose_combined(
    app: FastAPI, http_registry: CollectorRegistry, custom_registry: CollectorRegistry
) -> None:
    """Serve ``/metrics`` as the app's private HTTP registry followed by the
    injected custom-metrics registry. Both are text exposition with disjoint
    metric names, so concatenation is a valid single scrape response."""

    @app.get(METRICS_ENDPOINT, include_in_schema=False)
    async def metrics() -> Response:
        payload = generate_latest(http_registry) + generate_latest(custom_registry)
        return Response(content=payload, media_type=CONTENT_TYPE_LATEST)


def instrument(app: FastAPI, custom_registry: CollectorRegistry) -> CollectorRegistry:
    """Wire request metrics and expose ``/metrics`` on ``app``.

    ``/metrics`` serves the app's private HTTP registry concatenated with
    ``custom_registry`` (the caller's domain/service families). The registry is
    a parameter rather than a module import, so this module stays free of any
    consumer dependency. Returns the app's private HTTP registry (useful for
    tests).
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
    _expose_combined(app, registry, custom_registry)
    return registry
