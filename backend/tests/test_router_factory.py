"""Router-factory tests for the collapsed roadmaps + progress adapters.

One factory per domain replaces the external/internal forked routers
(byte-identical handler bodies differing only by identity), taking an ``App``
selector and reading both which routes mount and the identity each resolves from
the route registry. These tests guard the seams that collapse introduced,
complementing the per-app contract suites (``test_roadmaps_api*`` /
``test_progress_api*``) which still exercise each mode's full behavior:

- the one factory serves BOTH apps (a parameterized suite): the registry-resolved
  identity denies an anonymous caller and resolves an authenticated one;
- the web-only routes (visibility/archive/delete and follow/deadline) are declared
  for the external app only, so ``App.INTERNAL`` never mounts them while
  ``App.EXTERNAL`` does;
- the mounted ``/roadmaps`` surface is EXACTLY each app's registry declaration, so
  mounting is registry-driven (load-bearing), and it equals the HEAD surface.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.support.fakes.accounts_fakes import (
    InMemoryAccountRepository,
    build_test_codec,
    build_test_hasher,
)
from tests.support.fakes.progress_fakes import InMemoryProgressRepository
from tests.support.fakes.roadmaps_fakes import (
    InMemoryRoadmapRepository,
    constant_follower_counter,
    sequence_token_factory,
)
from wren.accounts.api import create_accounts_router
from wren.accounts.config import CookieConfig
from wren.accounts.service import AccountService
from wren.accounts.session import create_session_verifier
from wren.api.main import app as external_app
from wren.api_internal.main import app as internal_app
from wren.core.app_factory import create_app
from wren.core.errors import build_exception_handlers
from wren.core.identity import (
    INTERNAL_TOKEN_HEADER,
    USER_ID_HEADER,
    StripInboundIdentityMiddleware,
)
from wren.core.route_registry import (
    EXTERNAL_ROUTE_ACCESS,
    INTERNAL_ROUTE_ACCESS,
    App,
    RouteKey,
    mounted_product_routes,
)
from wren.core.settings import AppSettings
from wren.progress.router import create_progress_router
from wren.progress.service import ProgressService
from wren.roadmaps.read_service import RoadmapReadService
from wren.roadmaps.router import create_roadmaps_router
from wren.roadmaps.service import RoadmapService

if TYPE_CHECKING:
    from fastapi import FastAPI
    from httpx import Response

MakeSettings = Callable[..., AppSettings]

_PASSWORD = "Str0ngPass"
_INTERNAL_TOKEN = "test-internal-token"
_USER = "user-ada"

_MINIMAL_ROADMAP = {
    "title": "Grokking DSA",
    "sections": [
        {
            "title": "Foundations",
            "subsections": [
                {
                    "title": "Arrays",
                    "resources": [{"title": "Guide", "url": "https://x.test", "type": "article"}],
                    "checklist_items": [{"text": "Read it"}],
                }
            ],
        }
    ],
}

# The three web-only lifecycle routes: visibility toggle, archive, delete. They
# mount on the external app only (no internal-app route, no MCP tool).
_WEB_LIFECYCLE_ROUTES = frozenset(
    {
        RouteKey(method="PUT", path="/roadmaps/{roadmap_id}/visibility"),
        RouteKey(method="POST", path="/roadmaps/{roadmap_id}:archive"),
        RouteKey(method="DELETE", path="/roadmaps/{roadmap_id}"),
    }
)

# The full external ``/roadmaps`` surface at HEAD: 15 roadmap routes + 5 progress
# routes. Frozen here so the router collapse is proven byte-for-byte
# route-preserving (paths + methods) independently of the access registry.
_EXTERNAL_ROADMAP_SURFACE = frozenset(
    {
        RouteKey(method="POST", path="/roadmaps"),
        RouteKey(method="GET", path="/roadmaps/{roadmap_id}"),
        RouteKey(method="PATCH", path="/roadmaps/{roadmap_id}"),
        RouteKey(method="PUT", path="/roadmaps/{roadmap_id}"),
        RouteKey(method="DELETE", path="/roadmaps/{roadmap_id}"),
        RouteKey(method="GET", path="/roadmaps/{roadmap_id}/overview"),
        RouteKey(method="GET", path="/roadmaps/{roadmap_id}/nodes/{subsection_id}"),
        RouteKey(method="GET", path="/roadmaps/{roadmap_id}/sections/{section_id}"),
        RouteKey(method="GET", path="/roadmaps/{roadmap_id}/search"),
        RouteKey(method="POST", path="/roadmaps/{roadmap_id}:validate"),
        RouteKey(method="POST", path="/roadmaps/{roadmap_id}:publish"),
        RouteKey(method="POST", path="/roadmaps/{roadmap_id}:fork"),
        RouteKey(method="PATCH", path="/roadmaps/{roadmap_id}/metadata"),
        RouteKey(method="PUT", path="/roadmaps/{roadmap_id}/visibility"),
        RouteKey(method="POST", path="/roadmaps/{roadmap_id}:archive"),
        RouteKey(method="POST", path="/roadmaps/{roadmap_id}/follow"),
        RouteKey(method="GET", path="/roadmaps/{roadmap_id}/progress"),
        RouteKey(method="POST", path="/roadmaps/{roadmap_id}/progress"),
        RouteKey(method="GET", path="/roadmaps/{roadmap_id}/next"),
        RouteKey(method="PUT", path="/roadmaps/{roadmap_id}/deadline"),
    }
)

# The two web-only progress routes: follow + deadline. They mount on the external
# app only (no internal-app route, no MCP tool).
_WEB_ONLY_PROGRESS_ROUTES = frozenset(
    {
        RouteKey(method="POST", path="/roadmaps/{roadmap_id}/follow"),
        RouteKey(method="PUT", path="/roadmaps/{roadmap_id}/deadline"),
    }
)

# The internal app is the external surface minus the web-only routes: the web
# lifecycle (visibility/archive/delete) and the web-only progress routes
# (follow/deadline). It mounts only what an MCP tool consumes.
_INTERNAL_ROADMAP_SURFACE = (
    _EXTERNAL_ROADMAP_SURFACE - _WEB_LIFECYCLE_ROUTES - _WEB_ONLY_PROGRESS_ROUTES
)


def _roadmap_surface(app: FastAPI) -> set[RouteKey]:
    """The mounted product routes under the ``/roadmaps`` prefix (roadmaps +
    progress), which is exactly the surface this ticket's factories mount."""
    return {key for key in mounted_product_routes(app) if key.path.startswith("/roadmaps")}


# --- registry-driven composition: web-only routes are external-app only ------


def _dummy_provider() -> object:  # pragma: no cover - never invoked (build-time only)
    """A stand-in provider; the factory stores it as a dependency but never calls
    it when we only inspect the built router's route table."""
    raise AssertionError("provider should not be invoked in a structural test")


_NON_PRODUCT_METHODS = frozenset({"HEAD", "OPTIONS"})


def _roadmap_route_keys(router_routes: object) -> set[RouteKey]:
    keys: set[RouteKey] = set()
    for route in router_routes:  # type: ignore[attr-defined]
        for method in route.methods:
            if method in _NON_PRODUCT_METHODS:
                continue
            keys.add(RouteKey(method=method, path=route.path))
    return keys


def test_external_app_builds_the_web_only_routes() -> None:
    roadmaps = create_roadmaps_router(_dummy_provider, _dummy_provider, app=App.EXTERNAL)
    progress = create_progress_router(_dummy_provider, app=App.EXTERNAL)
    keys = _roadmap_route_keys(roadmaps.routes) | _roadmap_route_keys(progress.routes)
    assert keys >= _WEB_LIFECYCLE_ROUTES
    assert keys >= _WEB_ONLY_PROGRESS_ROUTES


def test_internal_app_omits_the_web_only_routes() -> None:
    roadmaps = create_roadmaps_router(_dummy_provider, _dummy_provider, app=App.INTERNAL)
    progress = create_progress_router(_dummy_provider, app=App.INTERNAL)
    keys = _roadmap_route_keys(roadmaps.routes) | _roadmap_route_keys(progress.routes)
    assert keys.isdisjoint(_WEB_LIFECYCLE_ROUTES)
    assert keys.isdisjoint(_WEB_ONLY_PROGRESS_ROUTES)


def test_mounted_surface_is_exactly_the_registry_declaration() -> None:
    # Mounting is registry-driven (load-bearing): the roadmaps + progress routes
    # the factories mount on each app are EXACTLY the /roadmaps-prefixed routes that
    # app's registry declares. Change a route's registry membership and what mounts
    # follows; the coverage test guards the same table in both directions.
    for app, registry in (
        (App.EXTERNAL, EXTERNAL_ROUTE_ACCESS),
        (App.INTERNAL, INTERNAL_ROUTE_ACCESS),
    ):
        roadmaps = create_roadmaps_router(_dummy_provider, _dummy_provider, app=app)
        progress = create_progress_router(_dummy_provider, app=app)
        mounted = _roadmap_route_keys(roadmaps.routes) | _roadmap_route_keys(progress.routes)
        declared = {key for key in registry if key.path.startswith("/roadmaps")}
        assert mounted == declared


# --- per-app mount: web-lifecycle is external-only, surface unchanged --------


def test_web_lifecycle_routes_are_external_only_on_the_real_apps() -> None:
    external = _roadmap_surface(external_app)
    internal = _roadmap_surface(internal_app)
    # Present on :8000, absent on :8001 (the internal app the MCP server calls).
    assert external >= _WEB_LIFECYCLE_ROUTES
    assert _WEB_LIFECYCLE_ROUTES.isdisjoint(internal)


def test_external_app_roadmap_surface_matches_head() -> None:
    assert _roadmap_surface(external_app) == set(_EXTERNAL_ROADMAP_SURFACE)


def test_internal_app_roadmap_surface_matches_head() -> None:
    assert _roadmap_surface(internal_app) == set(_INTERNAL_ROADMAP_SURFACE)


# --- one factory, both identity modes (parameterized) -----------------------


class _Harness:
    """Drives an app built from the identity-injected factory in one mode.

    ``anon_headers`` are the headers an *un*authenticated caller sends (none for
    the external cookie app; the internal app just omits the trusted token);
    ``auth_headers`` are what an authenticated caller sends. ``login`` establishes
    the session for the cookie app and is a no-op for the trusted-header app."""

    def __init__(
        self,
        client: TestClient,
        *,
        auth_headers: dict[str, str],
        login: Callable[[], None],
    ) -> None:
        self.client = client
        self._auth = auth_headers
        self._login = login

    def anon_create(self) -> Response:
        response: Response = self.client.post("/roadmaps", json=_MINIMAL_ROADMAP)
        return response

    def anon_progress(self) -> Response:
        response: Response = self.client.get("/roadmaps/any-roadmap-0000/progress")
        return response

    def login(self) -> None:
        self._login()

    def create(self) -> Response:
        response: Response = self.client.post(
            "/roadmaps", json=_MINIMAL_ROADMAP, headers=self._auth
        )
        return response

    def get(self, roadmap_id: str) -> Response:
        response: Response = self.client.get(f"/roadmaps/{roadmap_id}", headers=self._auth)
        return response


def _external_harness(make_settings: MakeSettings) -> _Harness:
    account_repo = InMemoryAccountRepository()
    codec = build_test_codec()
    hasher = build_test_hasher()
    roadmap_repo = InMemoryRoadmapRepository()

    def account_provider() -> AccountService:
        return AccountService(account_repo, hasher, codec)

    def roadmap_provider() -> RoadmapService:
        return RoadmapService(
            roadmap_repo,
            follower_counter=constant_follower_counter(),
            token_factory=sequence_token_factory(["7f3k", "9x2b"]),
        )

    def read_provider() -> RoadmapReadService:
        return RoadmapReadService(roadmap_repo)

    progress_repo = InMemoryProgressRepository()

    def progress_provider() -> ProgressService:
        return ProgressService(roadmap_repo, progress_repo)

    app: FastAPI = create_app(
        make_settings(),
        routers=[
            create_accounts_router(
                account_provider, cookie_config=CookieConfig(secure=False, domain=None)
            ),
            create_roadmaps_router(roadmap_provider, read_provider, app=App.EXTERNAL),
            create_progress_router(progress_provider, app=App.EXTERNAL),
        ],
        exception_handlers=build_exception_handlers(),
    )
    app.state.session_verifier = create_session_verifier(codec, account_repo.is_session_revoked)
    app.add_middleware(StripInboundIdentityMiddleware)
    client = TestClient(app)

    def login() -> None:
        response = client.post(
            "/auth/register",
            json={"username": "ada", "email": "ada@example.com", "password": _PASSWORD},
        )
        assert response.status_code == 201, response.text

    return _Harness(client, auth_headers={}, login=login)


def _internal_harness(make_settings: MakeSettings) -> _Harness:
    roadmap_repo = InMemoryRoadmapRepository()

    def roadmap_provider() -> RoadmapService:
        return RoadmapService(
            roadmap_repo,
            follower_counter=constant_follower_counter(),
            token_factory=sequence_token_factory(["7f3k", "9x2b"]),
        )

    def read_provider() -> RoadmapReadService:
        return RoadmapReadService(roadmap_repo)

    progress_repo = InMemoryProgressRepository()

    def progress_provider() -> ProgressService:
        return ProgressService(roadmap_repo, progress_repo)

    app: FastAPI = create_app(
        make_settings(),
        routers=[
            create_roadmaps_router(roadmap_provider, read_provider, app=App.INTERNAL),
            create_progress_router(progress_provider, app=App.INTERNAL),
        ],
        exception_handlers=build_exception_handlers(),
    )
    app.state.internal_api_token = SecretStr(_INTERNAL_TOKEN)
    client = TestClient(app)
    trusted = {INTERNAL_TOKEN_HEADER: _INTERNAL_TOKEN, USER_ID_HEADER: _USER}
    return _Harness(client, auth_headers=trusted, login=lambda: None)


_HARNESS_BUILDERS: dict[str, Callable[[MakeSettings], _Harness]] = {
    "external-cookie": _external_harness,
    "internal-trusted": _internal_harness,
}


@pytest.mark.parametrize("mode", list(_HARNESS_BUILDERS))
def test_identity_injected_factory_denies_anonymous_then_serves_authenticated(
    mode: str, make_settings: MakeSettings
) -> None:
    # The one factory, given each identity strategy, gates its routes on that
    # dependency: an anonymous caller is 401, and an authenticated caller resolves
    # through the same code and can create + read a roadmap.
    harness = _HARNESS_BUILDERS[mode](make_settings)

    assert harness.anon_create().status_code == 401
    # Progress got the same one-factory treatment: its routes are identity-gated too.
    assert harness.anon_progress().status_code == 401

    harness.login()
    created = harness.create()
    assert created.status_code == 201, created.text
    roadmap_id = created.json()["id"]
    assert harness.get(roadmap_id).status_code == 200
