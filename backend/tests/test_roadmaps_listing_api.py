"""Contract tests for the dashboard + profile surface.

Asserts ``GET /me/dashboard`` and ``GET /users/{handle}`` over real HTTP on an
external-shaped app (accounts + listing + progress routers over shared in-memory
repos). Covers US-ACCT-03: the private dashboard is auth-gated and caller-scoped
(authored any status + followed), the public profile needs no session and exposes
only published-public roadmaps (no draft/private/archived or social-graph leak),
and an unknown handle is a 404. Roadmaps are seeded owned by the registered
user's real id; follows go through the real progress endpoint so the followed
list is exercised end to end (as the production wiring binds it).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from accounts_fakes import InMemoryAccountRepository, build_test_codec, build_test_hasher
from progress_fakes import InMemoryProgressRepository
from roadmaps_fakes import InMemoryRoadmapRepository
from wren.accounts.api import create_accounts_router
from wren.accounts.config import CookieConfig
from wren.accounts.service import AccountService
from wren.accounts.session import create_session_verifier
from wren.core.app_factory import create_app
from wren.core.errors import build_exception_handlers
from wren.core.identity import StripInboundIdentityMiddleware
from wren.core.settings import AppSettings
from wren.progress.api import create_progress_router
from wren.progress.service import ProgressService
from wren.roadmaps.listing import ListingService, ProfileOwner
from wren.roadmaps.listing_api import create_listing_router
from wren.roadmaps.models import RoadmapRecord
from wren.roadmaps.schemas import Roadmap, RoadmapStatus, Visibility

MakeSettings = Callable[..., AppSettings]

_PASSWORD = "Str0ngPass"
_NOW = datetime(2026, 7, 15, tzinfo=UTC)


class _Harness:
    """The assembled app plus the shared repos, so a test can seed roadmaps owned
    by a registered user's real id and drive follows through the API."""

    def __init__(self, client: TestClient, roadmaps: InMemoryRoadmapRepository) -> None:
        self.client = client
        self.roadmaps = roadmaps

    def register(self, username: str, email: str) -> str:
        response = self.client.post(
            "/auth/register",
            json={"username": username, "email": email, "password": _PASSWORD},
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def logout(self) -> None:
        self.client.post("/auth/logout")

    def login(self, email: str) -> None:
        response = self.client.post("/auth/login", json={"email": email, "password": _PASSWORD})
        assert response.status_code == 200, response.text

    def seed(
        self,
        roadmap_id: str,
        owner: str,
        *,
        status: RoadmapStatus,
        visibility: Visibility,
        title: str = "A Roadmap",
        subject_tags: list[str] | None = None,
    ) -> None:
        roadmap = Roadmap(
            id=roadmap_id,
            owner=owner,
            title=title,
            subject_tags=subject_tags or [],
            visibility=visibility,
            status=status,
            revision=1,
            created_at=_NOW,
            updated_at=_NOW,
        )
        self.roadmaps._by_id[roadmap_id] = RoadmapRecord(
            id=roadmap.id,
            owner=roadmap.owner,
            title=roadmap.title,
            status=roadmap.status.value,
            visibility=roadmap.visibility.value,
            revision=roadmap.revision,
            document=roadmap.model_dump(mode="json"),
            created_at=roadmap.created_at,
            updated_at=roadmap.updated_at,
        )

    def follow(self, roadmap_id: str) -> None:
        response = self.client.post(f"/roadmaps/{roadmap_id}/follow")
        assert response.status_code == 201, response.text


def _build_harness(make_settings: MakeSettings) -> _Harness:
    account_repo = InMemoryAccountRepository()
    codec = build_test_codec()
    hasher = build_test_hasher()
    roadmap_repo = InMemoryRoadmapRepository()
    progress_repo = InMemoryProgressRepository()

    def account_provider() -> AccountService:
        return AccountService(account_repo, hasher, codec)

    def progress_provider() -> ProgressService:
        return ProgressService(roadmap_repo, progress_repo)

    async def handle_resolver(handle: str) -> ProfileOwner | None:
        user = await account_repo.get_by_username(handle)
        if user is None:
            return None
        return ProfileOwner(user_id=user.id, handle=user.username, display_name=user.username)

    def listing_provider() -> ListingService:
        return ListingService(
            roadmap_repo,
            handle_resolver=handle_resolver,
            followed_reader=progress_repo.list_followed_roadmap_ids,
        )

    accounts_router = create_accounts_router(
        account_provider, cookie_config=CookieConfig(secure=False, domain=None)
    )
    app: FastAPI = create_app(
        make_settings(),
        routers=[
            accounts_router,
            create_listing_router(listing_provider),
            create_progress_router(progress_provider),
        ],
        exception_handlers=build_exception_handlers(),
    )
    app.state.session_verifier = create_session_verifier(codec, account_repo.is_session_revoked)
    app.add_middleware(StripInboundIdentityMiddleware)
    return _Harness(TestClient(app), roadmap_repo)


# --- dashboard --------------------------------------------------------------


def test_dashboard_requires_authentication(make_settings: MakeSettings) -> None:
    harness = _build_harness(make_settings)
    assert harness.client.get("/me/dashboard").status_code == 401


def test_dashboard_lists_authored_all_statuses_and_followed(make_settings: MakeSettings) -> None:
    harness = _build_harness(make_settings)
    ada = harness.register("ada", "ada@example.com")
    bob = harness.register("bob", "bob@example.com")
    # ada owns a draft, a public+published, an archived, and a private+published.
    harness.seed("r-ada-draft", ada, status=RoadmapStatus.DRAFT, visibility=Visibility.PRIVATE)
    harness.seed("r-ada-pub", ada, status=RoadmapStatus.PUBLISHED, visibility=Visibility.PUBLIC)
    harness.seed("r-ada-arch", ada, status=RoadmapStatus.ARCHIVED, visibility=Visibility.PUBLIC)
    harness.seed("r-ada-priv", ada, status=RoadmapStatus.PUBLISHED, visibility=Visibility.PRIVATE)
    harness.seed("r-bob-pub", bob, status=RoadmapStatus.PUBLISHED, visibility=Visibility.PUBLIC)

    # ada logs in (bob's registration left his session active) and follows bob's
    # roadmap, so the dashboard resolves to ada.
    harness.login("ada@example.com")
    harness.follow("r-bob-pub")

    body = harness.client.get("/me/dashboard").json()
    assert {card["id"] for card in body["authored"]} == {
        "r-ada-draft",
        "r-ada-pub",
        "r-ada-arch",
        "r-ada-priv",
    }
    assert [card["id"] for card in body["followed"]] == ["r-bob-pub"]


def test_dashboard_is_scoped_to_the_caller(make_settings: MakeSettings) -> None:
    harness = _build_harness(make_settings)
    ada = harness.register("ada", "ada@example.com")
    harness.seed("r-ada", ada, status=RoadmapStatus.PUBLISHED, visibility=Visibility.PUBLIC)
    harness.logout()

    # bob registers (session now bob) and reads his own empty dashboard: ada's
    # roadmap is never visible to him.
    harness.register("bob", "bob@example.com")
    body = harness.client.get("/me/dashboard").json()
    assert body["authored"] == []
    assert body["followed"] == []


def test_dashboard_card_carries_status_and_visibility(make_settings: MakeSettings) -> None:
    harness = _build_harness(make_settings)
    ada = harness.register("ada", "ada@example.com")
    harness.seed(
        "r-ada",
        ada,
        status=RoadmapStatus.PUBLISHED,
        visibility=Visibility.PUBLIC,
        title="Grokking DSA",
        subject_tags=["cs"],
    )
    card = harness.client.get("/me/dashboard").json()["authored"][0]
    assert card == {
        "id": "r-ada",
        "title": "Grokking DSA",
        "status": "published",
        "visibility": "public",
        "subject_tags": ["cs"],
    }


# --- profile ----------------------------------------------------------------


def test_profile_returns_published_public_only(make_settings: MakeSettings) -> None:
    harness = _build_harness(make_settings)
    ada = harness.register("ada", "ada@example.com")
    harness.seed("r-draft", ada, status=RoadmapStatus.DRAFT, visibility=Visibility.PUBLIC)
    harness.seed("r-private", ada, status=RoadmapStatus.PUBLISHED, visibility=Visibility.PRIVATE)
    harness.seed("r-archived", ada, status=RoadmapStatus.ARCHIVED, visibility=Visibility.PUBLIC)
    harness.seed("r-public", ada, status=RoadmapStatus.PUBLISHED, visibility=Visibility.PUBLIC)
    harness.logout()

    body = harness.client.get("/users/ada").json()
    assert body["handle"] == "ada"
    assert body["display_name"] == "ada"
    assert [card["id"] for card in body["roadmaps"]] == ["r-public"]


def test_profile_is_public_and_needs_no_session(make_settings: MakeSettings) -> None:
    harness = _build_harness(make_settings)
    ada = harness.register("ada", "ada@example.com")
    harness.seed("r-public", ada, status=RoadmapStatus.PUBLISHED, visibility=Visibility.PUBLIC)
    harness.logout()  # no session cookie remains

    response = harness.client.get("/users/ada")
    assert response.status_code == 200
    assert [card["id"] for card in response.json()["roadmaps"]] == ["r-public"]


def test_profile_is_viewer_agnostic_for_another_user(make_settings: MakeSettings) -> None:
    harness = _build_harness(make_settings)
    ada = harness.register("ada", "ada@example.com")
    harness.seed("r-ada-draft", ada, status=RoadmapStatus.DRAFT, visibility=Visibility.PRIVATE)
    harness.seed("r-ada-pub", ada, status=RoadmapStatus.PUBLISHED, visibility=Visibility.PUBLIC)
    harness.logout()
    # bob signs in and views ada's profile: still only her published-public one.
    harness.register("bob", "bob@example.com")
    body = harness.client.get("/users/ada").json()
    assert [card["id"] for card in body["roadmaps"]] == ["r-ada-pub"]


def test_profile_unknown_handle_is_404(make_settings: MakeSettings) -> None:
    harness = _build_harness(make_settings)
    response = harness.client.get("/users/nobody")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
