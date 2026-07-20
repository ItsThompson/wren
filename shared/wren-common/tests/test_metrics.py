"""Metrics seam: instrument() concatenates exactly the injected custom registry.

The behavioral fork the move introduces: the custom-metrics registry is a
parameter, not a module import. These scenarios lock that seam: the private HTTP
registry is served alongside the caller's injected registry, and a registry that
was NOT injected never appears.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry, Counter

from wren_common.metrics import instrument


def _client_with(custom_registry: CollectorRegistry) -> TestClient:
    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    instrument(app, custom_registry)
    return TestClient(app)


def test_metrics_serves_http_families_and_the_injected_registry() -> None:
    custom = CollectorRegistry()
    Counter("domain_marker_total", "A domain family on the injected registry.", registry=custom)

    client = _client_with(custom)
    client.get("/ping")  # record one HTTP sample
    body = client.get("/metrics").text

    # The private HTTP families and the injected custom registry share one scrape.
    assert 'http_requests_total{method="GET",path="/ping",status="200"}' in body
    assert "http_request_duration_seconds_bucket{" in body
    assert "domain_marker_total" in body


def test_metrics_excludes_a_registry_that_was_not_injected() -> None:
    injected = CollectorRegistry()
    Counter("injected_total", "on the injected registry", registry=injected)
    foreign = CollectorRegistry()
    Counter("foreign_total", "on a registry never passed to instrument()", registry=foreign)

    body = _client_with(injected).get("/metrics").text

    assert "injected_total" in body
    assert "foreign_total" not in body


def test_instrument_returns_a_private_http_registry_distinct_from_the_custom_one() -> None:
    custom = CollectorRegistry()
    http_registry = instrument(FastAPI(), custom)

    assert isinstance(http_registry, CollectorRegistry)
    assert http_registry is not custom


def test_metrics_endpoint_is_excluded_from_its_own_counters() -> None:
    client = _client_with(CollectorRegistry())
    client.get("/ping")
    client.get("/metrics")

    body = client.get("/metrics").text
    request_lines = [line for line in body.splitlines() if line.startswith("http_requests_total")]
    assert request_lines
    assert all('path="/metrics"' not in line for line in request_lines)
