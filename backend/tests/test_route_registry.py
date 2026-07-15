"""Route -> access-level coverage: every mounted product route must have a
declared level, and an undeclared route fails safe (deny). Mirrors gofin's
VerifyRegistration; also guards the two real apps against an unscoped endpoint."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, FastAPI

from wren.api.main import app as external_app
from wren.api_internal.main import app as internal_app
from wren.core.app_factory import create_app
from wren.core.route_registry import (
    EXTERNAL_ROUTE_ACCESS,
    INTERNAL_ROUTE_ACCESS,
    AccessLevel,
    RouteKey,
    RouteRegistry,
    mounted_product_routes,
    verify_route_coverage,
)
from wren.core.settings import AppSettings

MakeSettings = Callable[..., AppSettings]

_ROADMAP_ROUTE = RouteKey(method="GET", path="/roadmaps/{roadmap_id}")


def _app_with_roadmap_route() -> FastAPI:
    router = APIRouter()

    @router.get("/roadmaps/{roadmap_id}")
    async def get_roadmap(roadmap_id: str) -> dict[str, str]:
        return {"id": roadmap_id}

    app = FastAPI()
    app.include_router(router)
    return app


def test_undeclared_mounted_route_fails_coverage() -> None:
    report = verify_route_coverage(_app_with_roadmap_route(), {})
    assert not report.is_covered
    assert _ROADMAP_ROUTE in report.undeclared


def test_declared_route_passes_coverage() -> None:
    registry: RouteRegistry = {_ROADMAP_ROUTE: AccessLevel.EXTERNAL_COOKIE}
    report = verify_route_coverage(_app_with_roadmap_route(), registry)
    assert report.is_covered
    assert report.undeclared == []


def test_orphaned_declaration_is_reported() -> None:
    # A registry entry with no matching mounted route is a stale declaration.
    registry: RouteRegistry = {
        _ROADMAP_ROUTE: AccessLevel.EXTERNAL_COOKIE,
        RouteKey(method="DELETE", path="/roadmaps/{roadmap_id}"): AccessLevel.EXTERNAL_COOKIE,
    }
    report = verify_route_coverage(_app_with_roadmap_route(), registry)
    assert not report.is_covered
    assert RouteKey(method="DELETE", path="/roadmaps/{roadmap_id}") in report.orphaned


def test_enumerates_product_routes_from_the_api_surface() -> None:
    # Only the real HTTP method appears; auto-added HEAD/OPTIONS are not in the
    # OpenAPI surface, so they are not treated as access-controlled routes.
    routes = mounted_product_routes(_app_with_roadmap_route())
    assert routes == [_ROADMAP_ROUTE]


def test_non_method_path_item_keys_are_ignored() -> None:
    # An OpenAPI path item can carry non-method keys (e.g. "parameters"); those
    # are not routes and must not be treated as access-controlled.
    class _FakeApp:
        def openapi(self) -> dict[str, object]:
            return {"paths": {"/x": {"get": {}, "parameters": []}}}

    routes = mounted_product_routes(_FakeApp())  # type: ignore[arg-type]
    assert routes == [RouteKey(method="GET", path="/x")]


def test_infra_and_docs_routes_need_no_declaration(make_settings: MakeSettings) -> None:
    # A factory-built app mounts only health, metrics, and docs: no product routes.
    app = create_app(make_settings())
    assert mounted_product_routes(app) == []
    assert verify_route_coverage(app, {}).is_covered


def test_real_external_app_has_full_route_coverage() -> None:
    report = verify_route_coverage(external_app, EXTERNAL_ROUTE_ACCESS)
    assert report.is_covered, f"external app has undeclared routes: {report.undeclared}"


def test_real_internal_app_has_full_route_coverage() -> None:
    report = verify_route_coverage(internal_app, INTERNAL_ROUTE_ACCESS)
    assert report.is_covered, f"internal app has undeclared routes: {report.undeclared}"
