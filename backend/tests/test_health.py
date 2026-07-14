"""Health router: liveness always ok; readiness aggregates injected checks."""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import FastAPI
from fastapi.testclient import TestClient

from wren.core.health import CheckResult, ReadinessCheck, create_health_router


def _client(checks: Sequence[ReadinessCheck] = ()) -> TestClient:
    app = FastAPI()
    app.include_router(create_health_router(checks))
    return TestClient(app)


def test_healthz_is_always_ok() -> None:
    response = _client().get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_ready_with_no_checks() -> None:
    response = _client().get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {}}


def test_readyz_ready_when_all_checks_pass() -> None:
    async def db_ok() -> CheckResult:
        return CheckResult(name="db", ok=True)

    response = _client([db_ok]).get("/readyz")
    assert response.status_code == 200
    assert response.json()["checks"]["db"] == {"ok": True, "detail": None}


def test_readyz_503_when_any_check_fails() -> None:
    async def cache_ok() -> CheckResult:
        return CheckResult(name="cache", ok=True)

    async def db_down() -> CheckResult:
        return CheckResult(name="db", ok=False, detail="unreachable")

    response = _client([cache_ok, db_down]).get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["db"] == {"ok": False, "detail": "unreachable"}
    assert body["checks"]["cache"]["ok"] is True


def test_readyz_503_when_a_check_raises() -> None:
    # Seam hardening (Ticket 2): a check that raises must degrade to 503, not 500,
    # so one misbehaving probe cannot crash readiness for the others.
    async def cache_ok() -> CheckResult:
        return CheckResult(name="cache", ok=True)

    async def db_boom() -> CheckResult:
        raise RuntimeError("pool exhausted")

    response = _client([cache_ok, db_boom]).get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["cache"]["ok"] is True
    # The raising check is reported as failed under a positional name.
    assert body["checks"]["check_1"]["ok"] is False
    assert "pool exhausted" in body["checks"]["check_1"]["detail"]
