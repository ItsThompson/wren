"""Internal-client tests: the RS -> backend internal hop.

The security-critical invariant: every call carries the resolved ``X-User-ID`` and
the shared ``INTERNAL_API_TOKEN``, the agent's bearer token is never forwarded,
and a caller cannot override the trusted headers. Uses httpx's ``MockTransport``
to capture the outgoing request without a live backend.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest
import structlog
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import SecretStr

from wren_mcp.client import REQUEST_ID_HEADER, InternalApiClient
from wren_mcp.config import INTERNAL_TOKEN_HEADER, USER_ID_HEADER

if TYPE_CHECKING:
    from collections.abc import Callable

_API_TOKEN = "shared-internal-token"


def _client_with_capture() -> tuple[InternalApiClient, list[httpx.Request]]:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"ok": True})

    http = httpx.AsyncClient(base_url="http://backend:8001", transport=httpx.MockTransport(handler))
    return InternalApiClient(http, api_token=SecretStr(_API_TOKEN)), captured


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

    await client._request(
        "GET",
        "/roadmaps/x-0000",
        user_id="user-ada",
        extra_headers={USER_ID_HEADER: "user-evil", INTERNAL_TOKEN_HEADER: "forged"},
    )

    request = captured[0]
    assert request.headers[USER_ID_HEADER] == "user-ada"
    assert request.headers[INTERNAL_TOKEN_HEADER] == _API_TOKEN


# ---------- read projections ----------


async def test_read_projection_calls_hit_their_routes_with_the_switches() -> None:
    # Each read tool is one internal GET; the concise|detailed switch travels as
    # ?format=, and every call still carries the trusted identity headers.
    client, captured = _client_with_capture()

    await client.get_overview("user-ada", "r-1", "concise")
    await client.get_next("user-ada", "r-1", "detailed")
    await client.get_node("user-ada", "r-1", "sub_hashing", "detailed")
    await client.get_progress("user-ada", "r-1", True)

    overview, nxt, node, progress = captured
    assert overview.url.path == "/roadmaps/r-1/overview"
    assert overview.url.params.get("format") == "concise"
    assert nxt.url.path == "/roadmaps/r-1/next"
    assert nxt.url.params.get("format") == "detailed"
    assert node.url.path == "/roadmaps/r-1/nodes/sub_hashing"
    assert progress.url.path == "/roadmaps/r-1/progress"
    assert progress.url.params.get("detailed") == "true"
    for request in captured:
        assert request.method == "GET"
        assert request.headers[USER_ID_HEADER] == "user-ada"
        assert request.headers[INTERNAL_TOKEN_HEADER] == _API_TOKEN


async def test_get_section_omits_the_cursor_on_the_first_page() -> None:
    client, captured = _client_with_capture()

    await client.get_section("user-ada", "r-1", "sec_1", None, "both")
    await client.get_section("user-ada", "r-1", "sec_1", "b3BhcXVl", "items")

    first, second = captured
    assert "cursor" not in first.url.params
    assert first.url.params.get("include") == "both"
    assert second.url.params.get("cursor") == "b3BhcXVl"
    assert second.url.params.get("include") == "items"


async def test_search_sends_query_and_repeated_tag_params() -> None:
    client, captured = _client_with_capture()

    await client.search("user-ada", "r-1", "hash", ["core", "graphs"])
    await client.search("user-ada", "r-1", "graphs", None)

    with_tags, without_tags = captured
    assert with_tags.url.params.get("q") == "hash"
    assert "tags=core" in str(with_tags.url) and "tags=graphs" in str(with_tags.url)
    assert without_tags.url.params.get("q") == "graphs"
    assert "tags" not in without_tags.url.params


async def test_update_progress_posts_the_explicit_set_batch() -> None:
    client, captured = _client_with_capture()

    await client.update_progress("user-ada", "r-1", ["item_1", "item_2"], "complete")

    request = captured[0]
    assert request.method == "POST"
    assert request.url.path == "/roadmaps/r-1/progress"
    assert json.loads(request.content) == {
        "item_ids": ["item_1", "item_2"],
        "state": "complete",
    }
    assert request.headers[USER_ID_HEADER] == "user-ada"


# ---------- request-id propagation (F4) ----------


async def test_request_forwards_the_bound_request_id() -> None:
    # The correlation id bound for the agent action (by the bearer boundary)
    # rides to the backend as X-Request-ID so the hop is traceable end to end.
    client, captured = _client_with_capture()

    structlog.contextvars.bind_contextvars(request_id="corr-abc-123")
    try:
        await client.get_roadmap("user-ada", "r-1")
    finally:
        structlog.contextvars.clear_contextvars()

    assert captured[0].headers[REQUEST_ID_HEADER] == "corr-abc-123"


async def test_request_omits_x_request_id_when_none_is_bound() -> None:
    # Off the transport there is no bound request_id, so the header is simply
    # absent rather than sent empty.
    client, captured = _client_with_capture()

    await client.get_roadmap("user-ada", "r-1")

    assert REQUEST_ID_HEADER not in captured[0].headers


# ---------- transport-failure translation (F15) ----------


def _client_with_transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> InternalApiClient:
    http = httpx.AsyncClient(base_url="http://backend:8001", transport=httpx.MockTransport(handler))
    return InternalApiClient(http, api_token=SecretStr(_API_TOKEN))


async def test_connect_error_is_translated_to_a_structured_tool_error() -> None:
    # The backend being unreachable must reach the agent as a model-recoverable
    # ToolError, not the opaque (often empty) transport exception FastMCP would
    # otherwise stringify.
    def unreachable(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = _client_with_transport(unreachable)
    with pytest.raises(ToolError) as excinfo:
        await client.get_roadmap("user-ada", "r-1")
    assert "backend_unavailable" in str(excinfo.value)


async def test_timeout_is_translated_to_a_structured_tool_error() -> None:
    def times_out(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = _client_with_transport(times_out)
    with pytest.raises(ToolError) as excinfo:
        await client.create_draft("user-ada", {"title": "Grokking DSA"})
    assert "backend_unavailable" in str(excinfo.value)


async def test_error_status_response_passes_through_untranslated() -> None:
    # A backend that ANSWERS with a >=400 status is not a transport failure: the
    # response passes through unchanged for raise_for_problem to map, so the
    # transport except must not swallow it.
    def five_hundred(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"code": "INTERNAL"})

    client = _client_with_transport(five_hundred)
    response = await client.get_roadmap("user-ada", "r-1")
    assert response.status_code == 500
