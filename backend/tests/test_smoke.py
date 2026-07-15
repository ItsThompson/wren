"""Smoke test.

Boots both real apps in one process and asserts /healthz and /metrics respond.
Booting both together also proves the per-app metric registries do not collide.
Readiness is now dependency-gated, so this asserts the Postgres check
is wired into both apps; its up/down state is covered by the DB readiness tests.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wren.api.main import app as external_app
from wren.api_internal.main import app as internal_app


@pytest.mark.parametrize(
    ("label", "app"),
    [("external", external_app), ("internal", internal_app)],
)
def test_both_apps_serve_health_and_metrics(label: str, app: FastAPI) -> None:
    client = TestClient(app)

    assert client.get("/healthz").status_code == 200

    readyz = client.get("/readyz")
    # Readiness reflects live Postgres connectivity; assert the DB check is wired
    # into both real apps rather than a specific up/down outcome (no DB here).
    assert readyz.status_code in (200, 503)
    assert "postgres" in readyz.json()["checks"]

    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    assert "http_requests_total" in metrics.text
    assert "http_request_duration_seconds" in metrics.text
