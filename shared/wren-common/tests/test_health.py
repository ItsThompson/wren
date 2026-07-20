"""Health seam: liveness is unconditional; readiness aggregates injected checks.

The behavioral fork the move preserves: readiness checks are injected as a
``Sequence[ReadinessCheck]`` and the aggregator is defensive. A check that
returns ``ok=False`` and a check that *raises* both degrade readiness to 503
(never 500), so one misbehaving probe cannot crash the endpoint for the others.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.testclient import TestClient

from wren_common.health import CheckResult, ReadinessCheck, create_health_router

if TYPE_CHECKING:
    from collections.abc import Sequence


def _client(checks: Sequence[ReadinessCheck] = ()) -> TestClient:
    app = FastAPI()
    app.include_router(create_health_router(checks))
    return TestClient(app)


def test_healthz_is_always_ok() -> None:
    response = _client().get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_is_ready_with_no_checks() -> None:
    response = _client().get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {}}


def test_readyz_is_ready_when_all_injected_checks_pass() -> None:
    async def dep_ok() -> CheckResult:
        return CheckResult(name="dep", ok=True)

    response = _client([dep_ok]).get("/readyz")
    assert response.status_code == 200
    assert response.json()["checks"]["dep"] == {"ok": True, "detail": None}


def test_readyz_is_503_when_any_injected_check_fails() -> None:
    async def cache_ok() -> CheckResult:
        return CheckResult(name="cache", ok=True)

    async def dep_down() -> CheckResult:
        return CheckResult(name="dep", ok=False, detail="unreachable")

    response = _client([cache_ok, dep_down]).get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["dep"] == {"ok": False, "detail": "unreachable"}
    assert body["checks"]["cache"]["ok"] is True


def test_readyz_degrades_to_503_when_a_check_raises() -> None:
    # A raising check must degrade to 503, not 500, so one misbehaving probe
    # cannot crash readiness for the others.
    async def cache_ok() -> CheckResult:
        return CheckResult(name="cache", ok=True)

    async def dep_boom() -> CheckResult:
        raise RuntimeError("pool exhausted")

    response = _client([cache_ok, dep_boom]).get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["cache"]["ok"] is True
    # The raising check is reported as failed under a positional name.
    assert body["checks"]["check_1"]["ok"] is False
    assert "pool exhausted" in body["checks"]["check_1"]["detail"]
