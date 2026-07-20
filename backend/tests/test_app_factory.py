"""App factory wiring: health, metrics, injected routers/checks/handlers, state."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from wren.core.app_factory import create_app
from wren.core.settings import AppSettings
from wren_common.health import CheckResult

MakeSettings = Callable[..., AppSettings]


def test_mounts_health_and_metrics_by_default(make_settings: MakeSettings) -> None:
    client = TestClient(create_app(make_settings()))
    assert client.get("/healthz").status_code == 200
    assert client.get("/metrics").status_code == 200


def test_mounts_injected_routers(make_settings: MakeSettings) -> None:
    router = APIRouter()

    @router.get("/ping")
    async def ping() -> dict[str, bool]:
        return {"pong": True}

    client = TestClient(create_app(make_settings(), routers=[router]))
    assert client.get("/ping").json() == {"pong": True}


def test_wires_injected_readiness_checks(make_settings: MakeSettings) -> None:
    async def db_down() -> CheckResult:
        return CheckResult(name="db", ok=False, detail="down")

    client = TestClient(create_app(make_settings(), readiness_checks=[db_down]))
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"]["db"]["ok"] is False


def test_registers_injected_exception_handlers(make_settings: MakeSettings) -> None:
    class Boom(Exception):
        pass

    async def handle_boom(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse({"handled": True}, status_code=418)

    router = APIRouter()

    @router.get("/boom")
    async def boom() -> None:
        raise Boom

    client = TestClient(
        create_app(
            make_settings(),
            routers=[router],
            exception_handlers={Boom: handle_boom},
        ),
        raise_server_exceptions=False,
    )
    response = client.get("/boom")
    assert response.status_code == 418
    assert response.json() == {"handled": True}


def test_stores_settings_and_logger_on_app_state(make_settings: MakeSettings) -> None:
    settings = make_settings()
    app = create_app(settings)
    assert app.state.settings is settings
    assert app.state.log is not None
