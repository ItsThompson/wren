"""Contract tests for the internal /roadmaps surface (:8001).

The internal app is the surface the MCP server calls: it resolves identity from
the trusted ``X-User-ID`` header behind the shared ``INTERNAL_API_TOKEN`` (spec
section 08), not a session cookie. These assert the trust boundary
(``require_internal_user``): a missing/invalid token or a missing trusted header
is a 401, a valid pair resolves the user, and every query stays per-user scoped
so a tool cannot reach another user's roadmap even though the identity is
injected. The service is backed by the in-memory repository; no database is
required.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient

from roadmaps_fakes import InMemoryRoadmapRepository, sequence_token_factory
from wren.core.app_factory import create_app
from wren.core.errors import build_exception_handlers
from wren.core.identity import INTERNAL_TOKEN_HEADER, USER_ID_HEADER
from wren.core.settings import AppSettings
from wren.roadmaps.api_internal import create_internal_roadmaps_router
from wren.roadmaps.service import RoadmapService

MakeSettings = Callable[..., AppSettings]

_INTERNAL_TOKEN = "test-internal-token"
_USER = "user-ada"
_OTHER_USER = "user-grace"

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

_PUBLISHABLE_ROADMAP = {
    "title": "Grokking DSA",
    "suggested_path": ["sub_arrays"],
    "sections": [
        {
            "title": "Foundations",
            "subsections": [
                {
                    "proposed_id": "sub_arrays",
                    "title": "Arrays",
                    "resources": [{"title": "Guide", "url": "https://x.test", "type": "article"}],
                    "checklist_items": [{"text": "Read it"}],
                }
            ],
        }
    ],
}


def _build_client(
    make_settings: MakeSettings, *, tokens: list[str] | None = None
) -> tuple[TestClient, InMemoryRoadmapRepository]:
    """An internal-shaped app: the internal /roadmaps router over an in-memory
    repository, with the shared internal token on app.state and no cookie
    verifier or identity-strip middleware (the internal app trusts X-User-ID)."""
    roadmap_repo = InMemoryRoadmapRepository()

    def roadmap_provider() -> RoadmapService:
        return RoadmapService(
            roadmap_repo,
            token_factory=sequence_token_factory(tokens or ["7f3k", "9x2b", "abcd", "efgh"]),
        )

    app: FastAPI = create_app(
        make_settings(),
        routers=[create_internal_roadmaps_router(roadmap_provider)],
        exception_handlers=build_exception_handlers(),
    )
    app.state.internal_api_token = _INTERNAL_TOKEN
    return TestClient(app), roadmap_repo


def _trusted(user_id: str = _USER) -> dict[str, str]:
    """The header pair a compute-net caller (the MCP server) sends."""
    return {INTERNAL_TOKEN_HEADER: _INTERNAL_TOKEN, USER_ID_HEADER: user_id}


# --- trust boundary (require_internal_user) ---------------------------------


def test_create_without_the_internal_token_is_401(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.post("/roadmaps", json=_MINIMAL_ROADMAP, headers={USER_ID_HEADER: _USER})
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_create_with_a_wrong_internal_token_is_401(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.post(
        "/roadmaps",
        json=_MINIMAL_ROADMAP,
        headers={INTERNAL_TOKEN_HEADER: "not-the-token", USER_ID_HEADER: _USER},
    )
    assert response.status_code == 401


def test_create_without_a_trusted_user_header_is_401(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.post(
        "/roadmaps", json=_MINIMAL_ROADMAP, headers={INTERNAL_TOKEN_HEADER: _INTERNAL_TOKEN}
    )
    assert response.status_code == 401


# --- create + read over the trusted identity --------------------------------


def test_create_returns_201_with_a_minted_roadmap_id(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    response = client.post("/roadmaps", json=_MINIMAL_ROADMAP, headers=_trusted())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] == "grokking-dsa-7f3k"
    assert body["owner"] == _USER
    assert body["status"] == "draft"


def test_get_returns_the_owned_roadmap_to_the_trusted_user(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    created_id = client.post("/roadmaps", json=_MINIMAL_ROADMAP, headers=_trusted()).json()["id"]

    response = client.get(f"/roadmaps/{created_id}", headers=_trusted())
    assert response.status_code == 200
    assert response.json()["id"] == created_id


def test_get_is_404_for_a_different_trusted_user_no_existence_leak(
    make_settings: MakeSettings,
) -> None:
    # Per-user scoping holds even though the internal app trusts X-User-ID: the
    # service scopes every query to the resolved user, so a token minted for one
    # user can never reach another user's roadmap.
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    created_id = client.post("/roadmaps", json=_MINIMAL_ROADMAP, headers=_trusted()).json()["id"]

    response = client.get(f"/roadmaps/{created_id}", headers=_trusted(_OTHER_USER))
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


# --- write lifecycle (patch / validate / publish) ---------------------------


def test_patch_applies_ops_under_if_match(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    created_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP, headers=_trusted()).json()[
        "id"
    ]

    response = client.patch(
        f"/roadmaps/{created_id}",
        headers={**_trusted(), "If-Match": "1"},
        json={"operations": [{"op": "set_tags", "subsection_id": "sub_arrays", "tags": ["core"]}]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 2


def test_patch_with_a_stale_if_match_is_a_409(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    created_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP, headers=_trusted()).json()[
        "id"
    ]

    response = client.patch(
        f"/roadmaps/{created_id}",
        headers={**_trusted(), "If-Match": "99"},
        json={"operations": [{"op": "set_tags", "subsection_id": "sub_arrays", "tags": ["x"]}]},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "STALE_REVISION"


def test_validate_returns_200_with_violations(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    created_id = client.post("/roadmaps", json=_MINIMAL_ROADMAP, headers=_trusted()).json()["id"]

    response = client.post(f"/roadmaps/{created_id}:validate", headers=_trusted())
    assert response.status_code == 200, response.text
    assert [v["rule"] for v in response.json()["violations"]] == ["V3_PATH_COVERAGE"]


def test_publish_transitions_a_valid_draft(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    created_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP, headers=_trusted()).json()[
        "id"
    ]

    response = client.post(f"/roadmaps/{created_id}:publish", headers=_trusted())
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "published"


def test_publish_is_404_for_a_different_trusted_user(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    created_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP, headers=_trusted()).json()[
        "id"
    ]

    response = client.post(f"/roadmaps/{created_id}:publish", headers=_trusted(_OTHER_USER))
    assert response.status_code == 404
