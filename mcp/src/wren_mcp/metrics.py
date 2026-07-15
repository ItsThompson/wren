"""Prometheus HTTP metrics for the MCP server.

Metric names and labels mirror the backend so the same
Prometheus rules and dashboards apply to both images:

- ``http_requests_total{method,path,status}`` (counter)
- ``http_request_duration_seconds{method,path}`` (histogram)

``path`` is the matched route template to bound label cardinality. ``/metrics``
is excluded from its own counters. A private ``CollectorRegistry`` keeps the RS
independent of any other app sharing a process (the tests do); ``/metrics`` serves
it concatenated with the shared
:data:`~wren_mcp.tool_metrics.TOOL_METRICS_REGISTRY` (MCP tool-invocation counter).
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
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

from wren_mcp.tool_metrics import TOOL_METRICS_REGISTRY

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
    """Serve ``/metrics`` as the private HTTP registry followed by the shared MCP
    domain registry. Disjoint metric names, so concatenation is a valid scrape."""

    @app.get(METRICS_ENDPOINT, include_in_schema=False)
    async def metrics() -> Response:
        payload = generate_latest(http_registry) + generate_latest(TOOL_METRICS_REGISTRY)
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
