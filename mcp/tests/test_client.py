"""Internal-client tests: the RS -> backend internal hop (spec section 08).

The security-critical invariant: every call carries the resolved ``X-User-ID`` and
the shared ``INTERNAL_API_TOKEN``, the agent's bearer token is never forwarded,
and a caller cannot override the trusted headers. Uses httpx's ``MockTransport``
to capture the outgoing request without a live backend.
"""

from __future__ import annotations

import json

import httpx

from wren_mcp.client import InternalApiClient
from wren_mcp.config import INTERNAL_TOKEN_HEADER, USER_ID_HEADER

_API_TOKEN = "shared-internal-token"


def _client_with_capture() -> tuple[InternalApiClient, list[httpx.Request]]:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"ok": True})

    http = httpx.AsyncClient(base_url="http://backend:8001", transport=httpx.MockTransport(handler))
    return InternalApiClient(http, api_token=_API_TOKEN), captured


async def test_create_draft_sends_trusted_identity_headers() -> None:
    client, captured = _client_with_capture()
    document = {"title": "Grokking DSA"}

    await client.create_draft("user-ada", document)

    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == "/roadmaps"
    assert request.headers[USER_ID_HEADER] == "user-ada"
    assert request.headers[INTERNAL_TOKEN_HEADER] == _API_TOKEN
    assert json.loads(request.content) == document


async def test_no_bearer_token_is_forwarded_downstream() -> None:
    # The client API takes a resolved user_id, never a token: the agent bearer is
    # exchanged for X-User-ID and cannot leak to the internal app.
    client, captured = _client_with_capture()

    await client.get_roadmap("user-ada", "grokking-dsa-7f3k")

    request = captured[0]
    assert request.method == "GET"
    assert request.url.path == "/roadmaps/grokking-dsa-7f3k"
    assert "authorization" not in {name.lower() for name in request.headers}


async def test_patch_draft_carries_the_revision_in_if_match() -> None:
    client, captured = _client_with_capture()
    operations = [{"op": "set_tags", "subsection_id": "sub_arrays", "tags": ["core"]}]

    await client.patch_draft("user-ada", "grokking-dsa-7f3k", 3, operations)

    request = captured[0]
    assert request.method == "PATCH"
    assert request.url.path == "/roadmaps/grokking-dsa-7f3k"
    assert request.headers["If-Match"] == "3"
    assert json.loads(request.content) == {"operations": operations}


async def test_validate_and_publish_hit_the_action_sub_resources() -> None:
    client, captured = _client_with_capture()

    await client.validate_draft("user-ada", "grokking-dsa-7f3k")
    await client.publish("user-ada", "grokking-dsa-7f3k")

    assert captured[0].url.path == "/roadmaps/grokking-dsa-7f3k:validate"
    assert captured[1].url.path == "/roadmaps/grokking-dsa-7f3k:publish"
    for request in captured:
        assert request.headers[USER_ID_HEADER] == "user-ada"
        assert request.headers[INTERNAL_TOKEN_HEADER] == _API_TOKEN


async def test_replace_draft_carries_the_revision_in_if_match() -> None:
    client, captured = _client_with_capture()
    document = {"title": "Grokking DSA v2"}

    await client.replace_draft("user-ada", "grokking-dsa-7f3k", 5, document)

    request = captured[0]
    assert request.method == "PUT"
    assert request.url.path == "/roadmaps/grokking-dsa-7f3k"
    assert request.headers["If-Match"] == "5"
    assert request.headers[USER_ID_HEADER] == "user-ada"
    assert json.loads(request.content) == document


async def test_fork_hits_the_fork_action_with_trusted_identity() -> None:
    client, captured = _client_with_capture()

    await client.fork("user-ada", "grokking-dsa-7f3k")

    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == "/roadmaps/grokking-dsa-7f3k:fork"
    assert request.headers[USER_ID_HEADER] == "user-ada"
    assert request.headers[INTERNAL_TOKEN_HEADER] == _API_TOKEN


async def test_edit_metadata_sends_only_provided_fields_and_no_if_match() -> None:
    client, captured = _client_with_capture()

    await client.edit_metadata(
        "user-ada",
        "grokking-dsa-7f3k",
        title="New Title",
        description="A new blurb",
        subject_tags=["cs"],
    )

    request = captured[0]
    assert request.method == "PATCH"
    assert request.url.path == "/roadmaps/grokking-dsa-7f3k/metadata"
    assert "If-Match" not in request.headers
    # Only provided fields are sent; an omitted field is left unchanged server-side.
    assert json.loads(request.content) == {
        "title": "New Title",
        "description": "A new blurb",
        "subject_tags": ["cs"],
    }


async def test_extra_headers_cannot_override_the_trusted_identity() -> None:
    # A caller-supplied header must never be able to spoof the resolved user or
    # the shared secret: the trusted pair is applied last.
    client, captured = _client_with_capture()

    await client.request(
        "GET",
        "/roadmaps/x-0000",
        user_id="user-ada",
        extra_headers={USER_ID_HEADER: "user-evil", INTERNAL_TOKEN_HEADER: "forged"},
    )

    request = captured[0]
    assert request.headers[USER_ID_HEADER] == "user-ada"
    assert request.headers[INTERNAL_TOKEN_HEADER] == _API_TOKEN
