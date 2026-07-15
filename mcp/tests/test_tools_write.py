"""MCP write-tool behavior, annotations, and error surfacing (spec section 07).

Drives the tools through the real mounted transport (:mod:`mcp_harness`): the
bearer boundary resolves identity, the tool makes one internal call, and the
backend HTTP boundary is mocked. Asserts each tool maps to the right internal
call with the resolved ``X-User-ID`` (never a tool argument), optimistic
concurrency propagates as ``If-Match``, and backend problem+json failures surface
as model-recoverable tool errors.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError
from starlette.requests import Request

from mcp_harness import AgentHarness, json_error
from wren_mcp.auth import AGENT_STATE_KEY
from wren_mcp.tokens import VerifiedAgentToken
from wren_mcp.tools_write import require_agent

_ROADMAP_ID = "grokking-dsa-7f3k"

WRITE_TOOL_NAMES = {
    "create_roadmap_draft",
    "patch_roadmap_draft",
    "replace_roadmap_draft",
    "validate_roadmap_draft",
    "publish_roadmap",
    "fork_roadmap",
    "edit_roadmap_metadata",
}

# readOnly / idempotent / destructive per spec section 07's write-tool table.
EXPECTED_ANNOTATIONS = {
    "create_roadmap_draft": {"readOnlyHint": False, "destructiveHint": False},
    "patch_roadmap_draft": {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
    },
    "replace_roadmap_draft": {"readOnlyHint": False, "destructiveHint": True},
    "validate_roadmap_draft": {"readOnlyHint": True, "idempotentHint": True},
    "publish_roadmap": {"readOnlyHint": False, "destructiveHint": True},
    "fork_roadmap": {"readOnlyHint": False, "destructiveHint": False},
    "edit_roadmap_metadata": {
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
    },
}


def _roadmap(**overrides: object) -> dict[str, object]:
    body: dict[str, object] = {
        "id": _ROADMAP_ID,
        "owner": "user-ada",
        "title": "Grokking DSA",
        "description": None,
        "subject_tags": [],
        "status": "draft",
        "revision": 1,
    }
    body.update(overrides)
    return body


# ---------- registration + annotations ----------


def test_exactly_the_seven_write_tools_are_registered() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json={}))
    with harness.open() as client:
        names = {tool["name"] for tool in harness.list_tools(client)}
    assert names == WRITE_TOOL_NAMES


def test_no_visibility_archive_or_delete_tool_is_exposed() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json={}))
    with harness.open() as client:
        names = {tool["name"] for tool in harness.list_tools(client)}
    forbidden = {n for n in names if any(k in n for k in ("visib", "archive", "delete"))}
    assert forbidden == set()


def test_annotations_match_the_write_tool_table() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json={}))
    with harness.open() as client:
        by_name = {tool["name"]: tool for tool in harness.list_tools(client)}
    for name, expected in EXPECTED_ANNOTATIONS.items():
        annotations = by_name[name]["annotations"]
        for hint, value in expected.items():
            assert annotations[hint] == value, f"{name}.{hint}"


def test_no_tool_exposes_a_user_id_argument() -> None:
    # Identity is resolved from the validated bearer, never a tool argument, so a
    # tool can never be steered to another user's roadmap.
    harness = AgentHarness(lambda _r: httpx.Response(200, json={}))
    with harness.open() as client:
        tools = harness.list_tools(client)
    for tool in tools:
        properties = set(tool["inputSchema"].get("properties", {}))
        assert not properties & {"user_id", "owner", "user"}, tool["name"]


# ---------- create ----------


def test_create_maps_to_post_roadmaps_with_resolved_identity() -> None:
    harness = AgentHarness(
        lambda _r: httpx.Response(201, json=_roadmap(remap={"sub_x": "sub-x-9a"}))
    )
    with harness.open() as client:
        result = harness.call_tool(
            client, "create_roadmap_draft", {"roadmap": {"title": "Grokking DSA"}}
        )

    assert result["isError"] is False
    assert result["structuredContent"] == {
        "roadmap_id": _ROADMAP_ID,
        "revision": 1,
        "status": "draft",
        "remap": {"sub_x": "sub-x-9a"},
    }
    request = harness.captured[0]
    assert request.method == "POST"
    assert request.url.path == "/roadmaps"
    assert request.headers["X-User-ID"] == "user-ada"


# ---------- patch ----------


def test_patch_sends_revision_as_if_match_and_returns_the_remap() -> None:
    changed = {"kind": "subsection", "id": "sub_hashing", "change": "added"}
    backend = lambda _r: httpx.Response(  # noqa: E731
        200,
        json={
            "roadmap_id": _ROADMAP_ID,
            "revision": 18,
            "changed_nodes": [changed],
            "remap": {"sub_hashing": "sub-hashing-2b"},
        },
    )
    harness = AgentHarness(backend)
    operations = [
        {"op": "add_subsection", "section_id": "sec_found", "subsection": {"title": "Hashing"}}
    ]
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "patch_roadmap_draft",
            {"roadmap_id": _ROADMAP_ID, "revision": 17, "operations": operations},
        )

    assert result["structuredContent"]["revision"] == 18
    assert result["structuredContent"]["remap"] == {"sub_hashing": "sub-hashing-2b"}
    assert result["structuredContent"]["changed_nodes"] == [changed]
    request = harness.captured[0]
    assert request.method == "PATCH"
    assert request.headers["If-Match"] == "17"
    assert request.headers["X-User-ID"] == "user-ada"


def test_patch_stale_revision_surfaces_a_reread_error() -> None:
    backend = lambda _r: json_error(  # noqa: E731
        409, "STALE_REVISION", "The roadmap changed since revision 17; re-read and retry."
    )
    harness = AgentHarness(backend)
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "patch_roadmap_draft",
            {
                "roadmap_id": _ROADMAP_ID,
                "revision": 17,
                "operations": [{"op": "remove_item", "item_id": "item_x"}],
            },
        )
    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert "STALE_REVISION" in text
    assert "re-read" in text


def test_patch_on_published_roadmap_is_rejected_as_immutable() -> None:
    backend = lambda _r: json_error(  # noqa: E731
        409, "IMMUTABLE", "Published roadmaps are immutable; fork to change structure."
    )
    harness = AgentHarness(backend)
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "patch_roadmap_draft",
            {
                "roadmap_id": _ROADMAP_ID,
                "revision": 3,
                "operations": [{"op": "remove_item", "item_id": "item_x"}],
            },
        )
    assert result["isError"] is True
    assert "IMMUTABLE" in result["content"][0]["text"]


def test_patch_dag_cycle_violation_names_the_offending_nodes() -> None:
    violation = {"rule": "V2_CYCLE", "ids": ["sub_a", "sub_b"], "message": "prerequisite cycle"}
    backend = lambda _r: json_error(  # noqa: E731
        422, "VALIDATION", "1 structural violation.", violations=[violation]
    )
    harness = AgentHarness(backend)
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "patch_roadmap_draft",
            {
                "roadmap_id": _ROADMAP_ID,
                "revision": 4,
                "operations": [{"op": "add_edge", "from_id": "sub_a", "to_id": "sub_b"}],
            },
        )
    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert "V2_CYCLE" in text
    assert "sub_a" in text and "sub_b" in text


# ---------- replace (read-then-import) ----------


def test_replace_reads_current_revision_then_imports_under_if_match() -> None:
    def backend(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=_roadmap(revision=5))
        return httpx.Response(200, json=_roadmap(revision=6, remap={"sub_y": "sub-y-3c"}))

    harness = AgentHarness(backend)
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "replace_roadmap_draft",
            {"roadmap_id": _ROADMAP_ID, "full_document": {"title": "Grokking DSA v2"}},
        )

    assert result["structuredContent"]["remap"] == {"sub_y": "sub-y-3c"}
    get_request, put_request = harness.captured[0], harness.captured[1]
    assert get_request.method == "GET"
    assert get_request.url.path == f"/roadmaps/{_ROADMAP_ID}"
    assert put_request.method == "PUT"
    assert put_request.headers["If-Match"] == "5"
    assert put_request.headers["X-User-ID"] == "user-ada"


def test_replace_on_published_roadmap_is_rejected_as_immutable() -> None:
    def backend(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json=_roadmap(status="published", revision=9))
        return json_error(409, "IMMUTABLE", "Published roadmaps are immutable; fork to change.")

    harness = AgentHarness(backend)
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "replace_roadmap_draft",
            {"roadmap_id": _ROADMAP_ID, "full_document": {"title": "x"}},
        )
    assert result["isError"] is True
    assert "IMMUTABLE" in result["content"][0]["text"]


# ---------- validate ----------


def test_validate_reports_violations_without_mutating() -> None:
    violation = {"rule": "V1_EMPTY", "ids": ["sec_intro"], "message": "section has no subsections"}
    harness = AgentHarness(lambda _r: httpx.Response(200, json={"violations": [violation]}))
    with harness.open() as client:
        result = harness.call_tool(client, "validate_roadmap_draft", {"roadmap_id": _ROADMAP_ID})

    assert result["isError"] is False
    assert result["structuredContent"]["publishable"] is False
    assert result["structuredContent"]["violations"] == [violation]
    assert harness.captured[0].url.path == f"/roadmaps/{_ROADMAP_ID}:validate"


def test_validate_of_a_clean_draft_is_publishable() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json={"violations": []}))
    with harness.open() as client:
        result = harness.call_tool(client, "validate_roadmap_draft", {"roadmap_id": _ROADMAP_ID})
    assert result["structuredContent"] == {"publishable": True, "violations": []}


# ---------- publish ----------


def test_publish_transitions_to_published() -> None:
    harness = AgentHarness(
        lambda _r: httpx.Response(200, json=_roadmap(status="published", revision=2))
    )
    with harness.open() as client:
        result = harness.call_tool(client, "publish_roadmap", {"roadmap_id": _ROADMAP_ID})
    assert result["structuredContent"] == {
        "roadmap_id": _ROADMAP_ID,
        "revision": 2,
        "status": "published",
    }
    assert harness.captured[0].url.path == f"/roadmaps/{_ROADMAP_ID}:publish"


def test_publish_hard_block_surfaces_the_violation_list() -> None:
    violation = {"rule": "V4_ORDER", "ids": ["sub_b"], "message": "prerequisite after dependent"}
    backend = lambda _r: json_error(  # noqa: E731
        422, "VALIDATION", "publish blocked", violations=[violation]
    )
    harness = AgentHarness(backend)
    with harness.open() as client:
        result = harness.call_tool(client, "publish_roadmap", {"roadmap_id": _ROADMAP_ID})
    assert result["isError"] is True
    assert "V4_ORDER" in result["content"][0]["text"]


# ---------- fork ----------


def test_fork_creates_a_new_draft_and_echoes_the_source() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(201, json=_roadmap(id="grokking-dsa-fork-1a")))
    with harness.open() as client:
        result = harness.call_tool(client, "fork_roadmap", {"source_roadmap_id": _ROADMAP_ID})
    assert result["structuredContent"] == {
        "roadmap_id": "grokking-dsa-fork-1a",
        "revision": 1,
        "status": "draft",
        "source_roadmap_id": _ROADMAP_ID,
    }
    assert harness.captured[0].url.path == f"/roadmaps/{_ROADMAP_ID}:fork"


def test_fork_of_an_unreadable_source_surfaces_not_found() -> None:
    harness = AgentHarness(lambda _r: json_error(404, "NOT_FOUND", "No such roadmap."))
    with harness.open() as client:
        result = harness.call_tool(client, "fork_roadmap", {"source_roadmap_id": "missing-0000"})
    assert result["isError"] is True
    assert "NOT_FOUND" in result["content"][0]["text"]


# ---------- edit_metadata ----------


def test_edit_metadata_sends_only_provided_fields_and_needs_no_if_match() -> None:
    harness = AgentHarness(
        lambda _r: httpx.Response(
            200, json=_roadmap(status="published", title="Grokking DSA", subject_tags=["cs"])
        )
    )
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "edit_roadmap_metadata",
            {"roadmap_id": _ROADMAP_ID, "subject_tags": ["cs"]},
        )
    assert result["isError"] is False
    assert result["structuredContent"]["subject_tags"] == ["cs"]
    request = harness.captured[0]
    assert request.method == "PATCH"
    assert request.url.path == f"/roadmaps/{_ROADMAP_ID}/metadata"
    assert "If-Match" not in request.headers
    import json

    assert json.loads(request.content) == {"subject_tags": ["cs"]}


# ---------- identity guard ----------


def _ctx_with(request: Request | None) -> SimpleNamespace:
    return SimpleNamespace(request_context=SimpleNamespace(request=request))


def _request_with_agent(principal: object) -> Request:
    request = Request({"type": "http", "headers": [], "method": "POST", "path": "/mcp"})
    setattr(request.state, AGENT_STATE_KEY, principal)
    return request


def test_require_agent_returns_the_resolved_user_id() -> None:
    principal = VerifiedAgentToken(user_id="user-ada", client_id="agent", scope="roadmaps:write")
    assert require_agent(_ctx_with(_request_with_agent(principal))) == "user-ada"


def test_require_agent_fails_closed_when_identity_is_absent() -> None:
    bare = Request({"type": "http", "headers": [], "method": "POST", "path": "/mcp"})
    with pytest.raises(ToolError):
        require_agent(_ctx_with(bare))


def test_require_agent_fails_closed_without_a_request() -> None:
    with pytest.raises(ToolError):
        require_agent(_ctx_with(None))
