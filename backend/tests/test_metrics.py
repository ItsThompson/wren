"""HTTP metrics: conventional names/labels, self-exclusion, registry isolation."""

from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from wren.core.app_factory import create_app
from wren.core.settings import AppSettings

MakeSettings = Callable[..., AppSettings]


def test_exposes_metric_names_with_route_template_and_status(
    make_settings: MakeSettings,
) -> None:
    client = TestClient(create_app(make_settings()))
    client.get("/healthz")  # generate one sample

    body = client.get("/metrics").text
    assert 'http_requests_total{method="GET",path="/healthz",status="200"}' in body
    assert "http_request_duration_seconds_bucket{" in body
    assert 'path="/healthz"' in body


def test_metrics_endpoint_excluded_from_its_own_counters(
    make_settings: MakeSettings,
) -> None:
    client = TestClient(create_app(make_settings()))
    client.get("/healthz")  # recorded traffic
    client.get("/metrics")  # excluded from counters

    body = client.get("/metrics").text
    request_lines = [line for line in body.splitlines() if line.startswith("http_requests_total")]
    assert request_lines  # there is traffic recorded
    assert all('path="/metrics"' not in line for line in request_lines)


def test_untemplated_paths_group_to_none(make_settings: MakeSettings) -> None:
    client = TestClient(create_app(make_settings()))
    client.get("/does-not-exist")

    body = client.get("/metrics").text
    assert 'path="none"' in body
    assert 'path="/does-not-exist"' not in body


def test_each_app_owns_an_isolated_registry(make_settings: MakeSettings) -> None:
    # Two apps built in one process must not raise a duplicate-timeseries error.
    app_a = create_app(make_settings(service="wren-a"))
    app_b = create_app(make_settings(service="wren-b"))

    assert TestClient(app_a).get("/metrics").status_code == 200
    assert TestClient(app_b).get("/metrics").status_code == 200
