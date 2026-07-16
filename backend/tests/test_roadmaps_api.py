"""Contract tests for the /roadmaps surface on an external-shaped app.

Asserts the RFC 9457 problem+json shapes, that create returns 201 with a minted
roadmap_id + slug IDs, that owner-scoped reads return 200 to the owner and 404 to
a non-owner (no existence leak), that require_user gates the surface (401
anonymous, spoofed X-User-ID stripped), and that malformed input is a 422 in the
one error contract. The service is backed by the in-memory repository; no
database is required.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI
from fastapi.testclient import TestClient

from accounts_fakes import InMemoryAccountRepository, build_test_codec, build_test_hasher
from roadmaps_fakes import (
    InMemoryRoadmapRepository,
    constant_follower_counter,
    sequence_token_factory,
)
from wren.accounts.api import create_accounts_router
from wren.accounts.config import CookieConfig
from wren.accounts.service import AccountService
from wren.accounts.session import create_session_verifier
from wren.core.app_factory import create_app
from wren.core.errors import build_exception_handlers
from wren.core.identity import USER_ID_HEADER, StripInboundIdentityMiddleware
from wren.core.settings import AppSettings
from wren.roadmaps.api import create_roadmaps_router
from wren.roadmaps.read_service import RoadmapReadService
from wren.roadmaps.service import RoadmapService

MakeSettings = Callable[..., AppSettings]

_PASSWORD = "Str0ngPass"

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

# A draft that satisfies the minimal structural contract (adds the suggested_path
# the minimal validator requires once there is a subsection to sequence).
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

# A full-document import (PUT body): one subsection keeps its proposed_id, the
# other omits it and is re-minted from its title (sub_graphs).
_REPLACE_ROADMAP = {
    "title": "Grokking DSA v2",
    "suggested_path": ["sub_arrays", "sub_graphs"],
    "sections": [
        {
            "proposed_id": "sec_core",
            "title": "Core",
            "subsections": [
                {
                    "proposed_id": "sub_arrays",
                    "title": "Arrays",
                    "resources": [{"title": "Guide", "url": "https://x.test", "type": "article"}],
                    "checklist_items": [{"text": "Read it"}],
                },
                {
                    "title": "Graphs",
                    "prereq_ids": ["sub_arrays"],
                    "resources": [{"title": "G", "url": "https://x.test", "type": "article"}],
                    "checklist_items": [{"text": "Do it"}],
                },
            ],
        }
    ],
}


def _build_client(
    make_settings: MakeSettings, *, tokens: list[str] | None = None, followers: int = 0
) -> tuple[TestClient, InMemoryRoadmapRepository]:
    """An external-shaped app with the /auth + /roadmaps routers over in-memory
    repositories and the real session verifier (so login sets a resolvable
    cookie). ``followers`` drives the injected follower counter for the delete
    guard (0 lets a delete through; a positive value forces the 409)."""
    account_repo = InMemoryAccountRepository()
    codec = build_test_codec()
    hasher = build_test_hasher()
    roadmap_repo = InMemoryRoadmapRepository()

    def account_provider() -> AccountService:
        return AccountService(account_repo, hasher, codec)

    def roadmap_provider() -> RoadmapService:
        return RoadmapService(
            roadmap_repo,
            follower_counter=constant_follower_counter(followers),
            token_factory=sequence_token_factory(tokens or ["7f3k", "9x2b", "abcd", "efgh"]),
        )

    def read_provider() -> RoadmapReadService:
        return RoadmapReadService(roadmap_repo)

    accounts_router = create_accounts_router(
        account_provider, cookie_config=CookieConfig(secure=False, domain=None)
    )
    roadmaps_router = create_roadmaps_router(roadmap_provider, read_provider)

    app: FastAPI = create_app(
        make_settings(),
        routers=[accounts_router, roadmaps_router],
        exception_handlers=build_exception_handlers(),
    )
    app.state.session_verifier = create_session_verifier(codec, account_repo.is_session_revoked)
    app.add_middleware(StripInboundIdentityMiddleware)
    return TestClient(app), roadmap_repo


def _login(client: TestClient, username: str = "ada", email: str = "ada@example.com") -> None:
    response = client.post(
        "/auth/register",
        json={"username": username, "email": email, "password": _PASSWORD},
    )
    assert response.status_code == 201, response.text


# --- create -----------------------------------------------------------------


def test_create_returns_201_with_a_minted_roadmap_id(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    response = client.post("/roadmaps", json=_MINIMAL_ROADMAP)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] == "grokking-dsa-7f3k"
    assert body["status"] == "draft"
    assert body["revision"] == 1
    assert body["visibility"] == "private"


def test_create_mints_prefixed_slug_ids_for_every_node(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    body = client.post("/roadmaps", json=_MINIMAL_ROADMAP).json()
    section = body["sections"]["sec_foundations"]
    subsection = section["subsections"]["sub_arrays"]
    assert section["subsection_order"] == ["sub_arrays"]
    assert subsection["resource_order"][0].startswith("res_")
    assert subsection["item_order"][0].startswith("chk_")
    # remap is present (empty here: nothing was de-duped).
    assert body["remap"] == {}


def test_create_requires_authentication(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.post("/roadmaps", json=_MINIMAL_ROADMAP)
    assert response.status_code == 401
    assert response.json()["code"] == "UNAUTHORIZED"


def test_create_malformed_body_is_a_422_problem_json(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    _login(client)
    # Missing the required "title".
    response = client.post("/roadmaps", json={"sections": []})
    assert response.status_code == 422
    body = response.json()
    assert response.headers["content-type"] == "application/problem+json"
    assert body["code"] == "VALIDATION"
    assert any("title" in field for field in body["fields"])


# --- get: owner-scoped, no existence leak -----------------------------------


def test_get_returns_the_full_roadmap_to_its_owner(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    created_id = client.post("/roadmaps", json=_MINIMAL_ROADMAP).json()["id"]

    response = client.get(f"/roadmaps/{created_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created_id
    assert "sec_foundations" in body["sections"]


def test_get_is_404_to_a_non_owner_without_leaking_existence(
    make_settings: MakeSettings,
) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client, username="owner", email="owner@example.com")
    created_id = client.post("/roadmaps", json=_MINIMAL_ROADMAP).json()["id"]

    # Switch to a different user session.
    client.cookies.clear()
    _login(client, username="intruder", email="intruder@example.com")
    response = client.get(f"/roadmaps/{created_id}")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_get_requires_authentication(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.get("/roadmaps/anything-0000")
    assert response.status_code == 401


def test_get_ignores_a_spoofed_x_user_id_header(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client, username="owner", email="owner@example.com")
    created_id = client.post("/roadmaps", json=_MINIMAL_ROADMAP).json()["id"]

    # A second user cannot reach the draft even by spoofing the owner's id: the
    # header is stripped and identity comes from the cookie.
    client.cookies.clear()
    _login(client, username="intruder", email="intruder@example.com")
    response = client.get(f"/roadmaps/{created_id}", headers={USER_ID_HEADER: "owner"})
    assert response.status_code == 404


# --- validate ---------------------------------------------------------------


def test_validate_returns_200_and_an_empty_list_for_a_publishable_draft(
    make_settings: MakeSettings,
) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    created_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP).json()["id"]

    response = client.post(f"/roadmaps/{created_id}:validate")
    assert response.status_code == 200, response.text
    assert response.json() == {"violations": []}


def test_validate_returns_200_with_violations_for_an_incomplete_draft(
    make_settings: MakeSettings,
) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    created_id = client.post("/roadmaps", json=_MINIMAL_ROADMAP).json()["id"]

    response = client.post(f"/roadmaps/{created_id}:validate")
    assert response.status_code == 200, response.text
    violations = response.json()["violations"]
    assert [v["rule"] for v in violations] == ["V3_PATH_COVERAGE"]
    assert violations[0]["ids"] == ["sub_arrays"]
    # Validate never mutates: the roadmap stays a draft.
    assert client.get(f"/roadmaps/{created_id}").json()["status"] == "draft"


def test_validate_is_404_to_a_non_owner(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client, username="owner", email="owner@example.com")
    created_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP).json()["id"]

    client.cookies.clear()
    _login(client, username="intruder", email="intruder@example.com")
    response = client.post(f"/roadmaps/{created_id}:validate")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_validate_requires_authentication(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.post("/roadmaps/anything-0000:validate")
    assert response.status_code == 401


# --- publish ----------------------------------------------------------------


def test_publish_transitions_a_valid_draft_to_published(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    created_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP).json()["id"]

    response = client.post(f"/roadmaps/{created_id}:publish")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "published"
    # Persisted transition, visible on a fresh read.
    assert client.get(f"/roadmaps/{created_id}").json()["status"] == "published"


def test_publish_hard_blocks_with_a_422_problem_json(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    created_id = client.post("/roadmaps", json=_MINIMAL_ROADMAP).json()["id"]

    response = client.post(f"/roadmaps/{created_id}:publish")
    assert response.status_code == 422, response.text
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "VALIDATION"
    assert [v["rule"] for v in body["violations"]] == ["V3_PATH_COVERAGE"]
    # Hard-block: the roadmap stays a draft.
    assert client.get(f"/roadmaps/{created_id}").json()["status"] == "draft"


def test_publish_is_one_way_republishing_is_a_409(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    created_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP).json()["id"]
    assert client.post(f"/roadmaps/{created_id}:publish").status_code == 200

    republish = client.post(f"/roadmaps/{created_id}:publish")
    assert republish.status_code == 409
    assert republish.json()["code"] == "CONFLICT"


def test_publish_is_404_to_a_non_owner(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client, username="owner", email="owner@example.com")
    created_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP).json()["id"]

    client.cookies.clear()
    _login(client, username="intruder", email="intruder@example.com")
    response = client.post(f"/roadmaps/{created_id}:publish")
    assert response.status_code == 404


# --- patch (If-Match optimistic concurrency) --------------------------------


def _create_publishable(client: TestClient) -> str:
    return client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP).json()["id"]


def test_patch_applies_ops_and_returns_the_bumped_revision(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    created_id = _create_publishable(client)

    response = client.patch(
        f"/roadmaps/{created_id}",
        headers={"If-Match": "1"},
        json={"operations": [{"op": "set_tags", "subsection_id": "sub_arrays", "tags": ["core"]}]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["roadmap_id"] == created_id
    assert body["revision"] == 2
    assert body["changed_nodes"] == [
        {"kind": "subsection", "id": "sub_arrays", "change": "updated"}
    ]
    # Persisted: a fresh read reflects the edit and the bumped revision.
    fetched = client.get(f"/roadmaps/{created_id}").json()
    assert fetched["revision"] == 2
    assert fetched["sections"]["sec_foundations"]["subsections"]["sub_arrays"]["tags"] == ["core"]


def test_patch_with_a_stale_if_match_is_a_409(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    created_id = _create_publishable(client)

    response = client.patch(
        f"/roadmaps/{created_id}",
        headers={"If-Match": "99"},
        json={"operations": [{"op": "set_tags", "subsection_id": "sub_arrays", "tags": ["x"]}]},
    )
    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "STALE_REVISION"
    assert "re-read" in body["detail"].lower()


def test_patch_with_an_invalid_op_is_a_422_naming_valid_ids(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    created_id = _create_publishable(client)

    response = client.patch(
        f"/roadmaps/{created_id}",
        headers={"If-Match": "1"},
        json={"operations": [{"op": "set_tags", "subsection_id": "sub_ghost", "tags": ["x"]}]},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION"
    field, message = next(iter(body["fields"].items()))
    assert field == "operations[0].subsection_id"
    assert "sub_arrays" in message


def test_patch_cycle_creating_edge_is_a_422_explaining_the_cycle(
    make_settings: MakeSettings,
) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    created_id = _create_publishable(client)

    response = client.patch(
        f"/roadmaps/{created_id}",
        headers={"If-Match": "1"},
        json={"operations": [{"op": "add_edge", "from_id": "sub_arrays", "to_id": "sub_arrays"}]},
    )
    assert response.status_code == 422
    body = response.json()
    assert "cycle" in next(iter(body["fields"].values()))


def test_patch_missing_if_match_header_is_a_422(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    created_id = _create_publishable(client)

    response = client.patch(
        f"/roadmaps/{created_id}",
        json={"operations": [{"op": "set_tags", "subsection_id": "sub_arrays", "tags": ["x"]}]},
    )
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


def test_patch_requires_authentication(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.patch(
        "/roadmaps/anything-0000",
        headers={"If-Match": "1"},
        json={"operations": [{"op": "set_tags", "subsection_id": "sub_x", "tags": []}]},
    )
    assert response.status_code == 401


def test_patch_is_404_to_a_non_owner(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client, username="owner", email="owner@example.com")
    created_id = _create_publishable(client)

    client.cookies.clear()
    _login(client, username="intruder", email="intruder@example.com")
    response = client.patch(
        f"/roadmaps/{created_id}",
        headers={"If-Match": "1"},
        json={"operations": [{"op": "set_tags", "subsection_id": "sub_arrays", "tags": ["x"]}]},
    )
    assert response.status_code == 404


# --- replace (full-document import escape hatch) -----------------------------


def test_replace_imports_the_full_document_and_bumps_the_revision(
    make_settings: MakeSettings,
) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    created_id = _create_publishable(client)

    response = client.put(
        f"/roadmaps/{created_id}", headers={"If-Match": "1"}, json=_REPLACE_ROADMAP
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # The roadmap ID (route param) is unchanged; the whole document is rebuilt.
    assert body["id"] == created_id
    assert body["title"] == "Grokking DSA v2"
    assert body["revision"] == 2
    assert body["remap"] == {}
    core = body["sections"]["sec_core"]
    # proposed_ids preserved; the node without one is re-minted from its title.
    assert core["subsection_order"] == ["sub_arrays", "sub_graphs"]
    assert core["subsections"]["sub_graphs"]["prereq_ids"] == ["sub_arrays"]
    # Persisted: a fresh read reflects the imported content and the bumped revision.
    fetched = client.get(f"/roadmaps/{created_id}").json()
    assert fetched["revision"] == 2
    assert "sub_graphs" in fetched["sections"]["sec_core"]["subsections"]


def test_replace_with_a_stale_if_match_is_a_409(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    created_id = _create_publishable(client)

    response = client.put(
        f"/roadmaps/{created_id}", headers={"If-Match": "99"}, json=_REPLACE_ROADMAP
    )
    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "STALE_REVISION"
    assert "re-read" in body["detail"].lower()


def test_replace_missing_if_match_header_is_a_422(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    created_id = _create_publishable(client)

    response = client.put(f"/roadmaps/{created_id}", json=_REPLACE_ROADMAP)
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


def test_replace_requires_authentication(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.put(
        "/roadmaps/anything-0000", headers={"If-Match": "1"}, json=_REPLACE_ROADMAP
    )
    assert response.status_code == 401


def test_replace_is_404_to_a_non_owner(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client, username="owner", email="owner@example.com")
    created_id = _create_publishable(client)

    client.cookies.clear()
    _login(client, username="intruder", email="intruder@example.com")
    response = client.put(
        f"/roadmaps/{created_id}", headers={"If-Match": "1"}, json=_REPLACE_ROADMAP
    )
    assert response.status_code == 404


# --- immutability boundary (structural writes reject published) -------------
#
# Every content-mutating write (patch, replace) rejects a published roadmap with a
# 409 IMMUTABLE pointing to fork-to-change. The sanctioned
# presentation-only path (edit_metadata) is NOT routed through the
# content-write guard, which is what keeps it allowed post-publish.


def _publish(client: TestClient) -> str:
    created_id = _create_publishable(client)
    assert client.post(f"/roadmaps/{created_id}:publish").status_code == 200
    return created_id


def test_patch_against_a_published_roadmap_is_a_409_immutable(
    make_settings: MakeSettings,
) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    published_id = _publish(client)

    response = client.patch(
        f"/roadmaps/{published_id}",
        headers={"If-Match": "1"},
        json={"operations": [{"op": "set_tags", "subsection_id": "sub_arrays", "tags": ["x"]}]},
    )
    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "IMMUTABLE"
    assert "fork" in body["detail"].lower()


def test_replace_against_a_published_roadmap_is_a_409_immutable(
    make_settings: MakeSettings,
) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    published_id = _publish(client)

    response = client.put(
        f"/roadmaps/{published_id}", headers={"If-Match": "1"}, json=_REPLACE_ROADMAP
    )
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "IMMUTABLE"
    assert "fork" in body["detail"].lower()


# --- fork --------------------------------------------------------------


def _make_public(repo: InMemoryRoadmapRepository, roadmap_id: str) -> None:
    """Force a stored roadmap to published + public directly, so a non-owner
    readability path can be exercised over HTTP."""
    record = repo._by_id[roadmap_id]
    record.status = "published"
    record.visibility = "public"
    record.document = {**record.document, "status": "published", "visibility": "public"}


def test_fork_returns_201_with_a_fresh_draft(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k", "9x2b"])
    _login(client)
    source_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP).json()["id"]

    response = client.post(f"/roadmaps/{source_id}:fork")
    assert response.status_code == 201, response.text
    body = response.json()
    # A brand-new roadmap ID, a fresh private draft owned by the forking user.
    assert body["id"] == "grokking-dsa-9x2b"
    assert body["id"] != source_id
    assert body["status"] == "draft"
    assert body["visibility"] == "private"
    assert body["revision"] == 1
    # Content copied verbatim (same child IDs, uniqueness is within-roadmap).
    assert "sub_arrays" in body["sections"]["sec_foundations"]["subsections"]
    assert body["suggested_path"] == ["sub_arrays"]
    # The source is untouched and still owned by its creator.
    assert client.get(f"/roadmaps/{source_id}").json()["id"] == source_id


def test_fork_of_a_public_roadmap_by_a_non_owner_succeeds(make_settings: MakeSettings) -> None:
    client, repo = _build_client(make_settings, tokens=["7f3k", "9x2b"])
    _login(client, username="author", email="author@example.com")
    source_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP).json()["id"]
    _make_public(repo, source_id)

    # A different user forks the public roadmap and owns the fresh draft.
    client.cookies.clear()
    _login(client, username="forker", email="forker@example.com")
    response = client.post(f"/roadmaps/{source_id}:fork")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "draft"
    assert body["visibility"] == "private"
    # The forker can now read their own fork.
    assert client.get(f"/roadmaps/{body['id']}").status_code == 200


def test_fork_of_a_private_roadmap_i_do_not_own_is_404(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k", "9x2b"])
    _login(client, username="owner", email="owner@example.com")
    source_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP).json()["id"]

    client.cookies.clear()
    _login(client, username="intruder", email="intruder@example.com")
    response = client.post(f"/roadmaps/{source_id}:fork")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_fork_requires_authentication(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.post("/roadmaps/anything-0000:fork")
    assert response.status_code == 401


# --- edit_metadata (presentation-only, published-mutable) -------------------


def test_edit_metadata_updates_presentation_fields_without_bumping_revision(
    make_settings: MakeSettings,
) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    source_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP).json()["id"]

    response = client.patch(
        f"/roadmaps/{source_id}/metadata",
        json={"title": "Renamed", "description": "New blurb", "subject_tags": ["cs"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Renamed"
    assert body["description"] == "New blurb"
    assert body["subject_tags"] == ["cs"]
    # Presentation edit is last-write-wins: no If-Match, revision unchanged.
    assert body["revision"] == 1
    assert client.get(f"/roadmaps/{source_id}").json()["revision"] == 1


def test_edit_metadata_is_allowed_on_a_published_roadmap(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    published_id = _publish(client)

    response = client.patch(f"/roadmaps/{published_id}/metadata", json={"title": "Renamed live"})
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Renamed live"
    # A presentation edit is not a lifecycle change: still published.
    assert client.get(f"/roadmaps/{published_id}").json()["status"] == "published"


def test_edit_metadata_smuggled_structural_field_is_a_409_immutable(
    make_settings: MakeSettings,
) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    source_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP).json()["id"]

    # A caller cannot smuggle a visibility/structural change through the metadata
    # endpoint: it is rejected as immutable rather than silently applied/ignored.
    response = client.patch(
        f"/roadmaps/{source_id}/metadata",
        json={"title": "Renamed", "visibility": "public", "sections": []},
    )
    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "IMMUTABLE"
    assert "visibility" in body["detail"] and "sections" in body["detail"]
    # Nothing was applied: the title is unchanged.
    assert client.get(f"/roadmaps/{source_id}").json()["title"] == "Grokking DSA"


def test_edit_metadata_is_404_to_a_non_owner(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client, username="owner", email="owner@example.com")
    source_id = client.post("/roadmaps", json=_PUBLISHABLE_ROADMAP).json()["id"]

    client.cookies.clear()
    _login(client, username="intruder", email="intruder@example.com")
    response = client.patch(f"/roadmaps/{source_id}/metadata", json={"title": "Hijack"})
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_edit_metadata_requires_authentication(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.patch("/roadmaps/anything-0000/metadata", json={"title": "x"})
    assert response.status_code == 401


def test_published_rejects_structural_write_but_allows_metadata_edit(
    make_settings: MakeSettings,
) -> None:
    # On a published roadmap a structural write (PATCH) is a 409 IMMUTABLE while
    # the presentation-only metadata edit succeeds.
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    published_id = _publish(client)

    structural = client.patch(
        f"/roadmaps/{published_id}",
        headers={"If-Match": "1"},
        json={"operations": [{"op": "set_tags", "subsection_id": "sub_arrays", "tags": ["x"]}]},
    )
    assert structural.status_code == 409
    assert structural.json()["code"] == "IMMUTABLE"

    metadata = client.patch(f"/roadmaps/{published_id}/metadata", json={"title": "Renamed live"})
    assert metadata.status_code == 200, metadata.text
    assert metadata.json()["title"] == "Renamed live"


# --- web-only lifecycle: visibility toggle ----------------------------------


def test_set_visibility_toggles_public_and_private(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    created_id = client.post("/roadmaps", json=_MINIMAL_ROADMAP).json()["id"]

    made_public = client.put(f"/roadmaps/{created_id}/visibility", json={"visibility": "public"})
    assert made_public.status_code == 200, made_public.text
    assert made_public.json()["visibility"] == "public"
    assert client.get(f"/roadmaps/{created_id}").json()["visibility"] == "public"

    made_private = client.put(f"/roadmaps/{created_id}/visibility", json={"visibility": "private"})
    assert made_private.status_code == 200
    assert made_private.json()["visibility"] == "private"


def test_set_visibility_does_not_bump_the_revision(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    created_id = client.post("/roadmaps", json=_MINIMAL_ROADMAP).json()["id"]
    body = client.put(f"/roadmaps/{created_id}/visibility", json={"visibility": "public"}).json()
    assert body["revision"] == 1


def test_set_visibility_rejects_a_bad_value_as_422(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    created_id = client.post("/roadmaps", json=_MINIMAL_ROADMAP).json()["id"]
    response = client.put(f"/roadmaps/{created_id}/visibility", json={"visibility": "secret"})
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


def test_set_visibility_is_404_to_a_non_owner(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client, username="owner", email="owner@example.com")
    created_id = client.post("/roadmaps", json=_MINIMAL_ROADMAP).json()["id"]

    client.cookies.clear()
    _login(client, username="intruder", email="intruder@example.com")
    response = client.put(f"/roadmaps/{created_id}/visibility", json={"visibility": "public"})
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_set_visibility_requires_authentication(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.put("/roadmaps/anything-0000/visibility", json={"visibility": "public"})
    assert response.status_code == 401


# --- web-only lifecycle: archive --------------------------------------------


def test_archive_hides_a_published_roadmap(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    published_id = _publish(client)

    response = client.post(f"/roadmaps/{published_id}:archive")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "archived"
    assert client.get(f"/roadmaps/{published_id}").json()["status"] == "archived"


def test_archive_a_draft_is_a_409(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client)
    created_id = _create_publishable(client)
    response = client.post(f"/roadmaps/{created_id}:archive")
    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"


def test_archive_is_404_to_a_non_owner(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"])
    _login(client, username="owner", email="owner@example.com")
    published_id = _publish(client)

    client.cookies.clear()
    _login(client, username="intruder", email="intruder@example.com")
    response = client.post(f"/roadmaps/{published_id}:archive")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_archive_requires_authentication(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.post("/roadmaps/anything-0000:archive")
    assert response.status_code == 401


# --- web-only lifecycle: delete (zero-followers guard) ----------------------


def test_delete_returns_204_with_zero_followers(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"], followers=0)
    _login(client)
    created_id = client.post("/roadmaps", json=_MINIMAL_ROADMAP).json()["id"]

    response = client.delete(f"/roadmaps/{created_id}")
    assert response.status_code == 204, response.text
    assert response.content == b""
    # Gone: a subsequent read is a 404.
    assert client.get(f"/roadmaps/{created_id}").status_code == 404


def test_delete_with_followers_is_a_409_steering_to_archive(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"], followers=2)
    _login(client)
    published_id = _publish(client)

    response = client.delete(f"/roadmaps/{published_id}")
    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["code"] == "DELETE_HAS_FOLLOWERS"
    assert "archive" in body["detail"].lower()
    # Not deleted: still readable.
    assert client.get(f"/roadmaps/{published_id}").status_code == 200


def test_delete_is_404_to_a_non_owner(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings, tokens=["7f3k"], followers=0)
    _login(client, username="owner", email="owner@example.com")
    created_id = client.post("/roadmaps", json=_MINIMAL_ROADMAP).json()["id"]

    client.cookies.clear()
    _login(client, username="intruder", email="intruder@example.com")
    response = client.delete(f"/roadmaps/{created_id}")
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
    # The intruder cannot even see it (owner-scoped, no existence leak).
    assert client.get(f"/roadmaps/{created_id}").status_code == 404


def test_delete_requires_authentication(make_settings: MakeSettings) -> None:
    client, _ = _build_client(make_settings)
    response = client.delete("/roadmaps/anything-0000")
    assert response.status_code == 401
