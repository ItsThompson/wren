"""Prometheus HTTP metrics.

Metric names and labels mirror gofin (spec section 11) so its alert rules and
dashboards drop in later:

- ``http_requests_total{method,path,status}`` (counter)
- ``http_request_duration_seconds{method,path}`` (histogram)

``path`` is the matched route template (e.g. ``/roadmaps/{id}``) to bound label
cardinality; untemplated paths group to ``none``. ``/metrics`` is excluded from
its own counters to avoid self-referential scrape noise.

Each app owns a private ``CollectorRegistry`` so the external and internal apps
can run in one process (the smoke test does) without duplicate-timeseries errors.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from prometheus_client import CollectorRegistry, Counter, Histogram
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_fastapi_instrumentator.metrics import Info

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


def instrument(app: FastAPI) -> CollectorRegistry:
    """Wire request metrics and expose ``/metrics`` on ``app``.

    Returns the app's private registry (useful for tests).
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
    instrumentator.instrument(app).expose(app, endpoint=METRICS_ENDPOINT, include_in_schema=False)
    return registry
