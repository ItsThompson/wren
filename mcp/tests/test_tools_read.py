"""MCP read-tool behavior, annotations, scope gate, and token guidance.

Drives the study-time tools through the real mounted transport (:mod:`mcp_harness`):
the bearer boundary resolves identity, the shared scope gate authorizes, the tool
makes one internal GET (or the progress POST), and the backend HTTP boundary is
mocked. Asserts each tool maps to the right internal read route with the resolved
``X-User-ID`` (never a tool argument), the ``concise|detailed`` / cursor / include /
tags switches propagate, ``progress_update`` is an explicit-set batch, and a token
missing the required scope surfaces a model-recoverable ``insufficient_scope``.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from mcp_harness import AgentHarness, json_error

_RID = "grokking-dsa-7f3k"

READ_TOOL_NAMES = {
    "roadmap_get_overview",
    "roadmap_get_next",
    "roadmap_get_node",
    "roadmap_get_section",
    "roadmap_search",
    "progress_get",
    "progress_update",
}

# readOnly for the six reads; progress_update is an explicit-set write, so it is
# idempotent (a retry is a no-op) and non-destructive, not readOnly.
EXPECTED_READ_ANNOTATIONS = {
    "roadmap_get_overview": {"readOnlyHint": True},
    "roadmap_get_next": {"readOnlyHint": True},
    "roadmap_get_node": {"readOnlyHint": True},
    "roadmap_get_section": {"readOnlyHint": True},
    "roadmap_search": {"readOnlyHint": True},
    "progress_get": {"readOnlyHint": True},
    "progress_update": {
        "readOnlyHint": False,
        "idempotentHint": True,
        "destructiveHint": False,
    },
}


def _node_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "subsection_id": "sub_hashing",
        "title": "Hashing",
        "description": "Hash tables, collisions, and load factors.",
        "tags": ["core"],
        "effort_estimate": "2h",
        "resources": [
            {"id": "res_1", "title": "Hashing 101", "url": "https://x/h", "type": "article"}
        ],
        "prereqs": [{"id": "sub_arrays", "title": "Arrays", "done": True}],
        "items": [{"id": "item_1", "text": "Read the article", "done": False}],
    }
    body.update(overrides)
    return body


def _overview_body(sections: int = 1) -> dict[str, Any]:
    section_list = [
        {
            "section_id": f"sec_{i:02d}",
            "title": f"Section {i}",
            "total_items": 4,
            "checked_items": 2,
            "percent": 50,
        }
        for i in range(sections)
    ]
    total = 4 * max(sections, 1)
    return {
        "roadmap_id": _RID,
        "title": "Grokking DSA",
        "status": "published",
        "revision": 3,
        "sections": section_list,
        "overall": {"total_items": total, "checked_items": total // 2, "percent": 50},
    }


def _next_body() -> dict[str, Any]:
    return {
        "items": [
            {
                "subsection_id": "sub_hashing",
                "item_id": "item_1",
                "text": "Read the article",
                "why_now": (
                    "Next unchecked subsection in the suggested path; "
                    "prerequisites sub_arrays are complete."
                ),
                "resources": [{"title": "Hashing 101", "url": "https://x/h", "type": "article"}],
                "path_position": 2,
            }
        ],
        "remaining_in_path": 3,
        "complete": False,
    }


def _progress_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "roadmap_id": _RID,
        "total_items": 4,
        "checked_items": 2,
        "percent": 50,
        "deadline": "2026-08-01",
        "sections": [{"section_id": "sec_00", "total_items": 4, "checked_items": 2, "percent": 50}],
        "checked_ids": None,
    }
    body.update(overrides)
    return body


# ---------- registration + annotations ----------


def test_all_seven_read_tools_are_registered() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json={}))
    with harness.open() as client:
        names = {tool["name"] for tool in harness.list_tools(client)}
    assert names >= READ_TOOL_NAMES


def test_read_annotations_match_the_read_tool_table() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json={}))
    with harness.open() as client:
        by_name = {tool["name"]: tool for tool in harness.list_tools(client)}
    for name, expected in EXPECTED_READ_ANNOTATIONS.items():
        annotations = by_name[name]["annotations"]
        for hint, value in expected.items():
            assert annotations[hint] == value, f"{name}.{hint}"


def test_no_read_tool_exposes_a_user_id_argument() -> None:
    # Identity is resolved from the validated bearer, never a tool argument, so a
    # read can never be steered to another user's roadmap or progress.
    harness = AgentHarness(lambda _r: httpx.Response(200, json={}))
    with harness.open() as client:
        tools = {tool["name"]: tool for tool in harness.list_tools(client)}
    for name in READ_TOOL_NAMES:
        properties = set(tools[name]["inputSchema"].get("properties", {}))
        assert not properties & {"user_id", "owner", "user"}, name


# ---------- overview ----------


def test_overview_maps_to_the_internal_overview_route_concise_by_default() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=_overview_body()))
    with harness.open() as client:
        result = harness.call_tool(client, "roadmap_get_overview", {"roadmap_id": _RID})

    assert result["isError"] is False
    assert result["structuredContent"]["roadmap_id"] == _RID
    assert result["structuredContent"]["overall"]["percent"] == 50
    request = harness.captured[0]
    assert request.method == "GET"
    assert request.url.path == f"/roadmaps/{_RID}/overview"
    assert request.url.params.get("format") == "concise"
    assert request.headers["X-User-ID"] == "user-ada"


def test_overview_forwards_the_detailed_format_switch() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=_overview_body()))
    with harness.open() as client:
        harness.call_tool(
            client, "roadmap_get_overview", {"roadmap_id": _RID, "format": "detailed"}
        )
    assert harness.captured[0].url.params.get("format") == "detailed"


# ---------- next ----------


def test_next_maps_to_the_internal_next_route_with_structural_why_now() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=_next_body()))
    with harness.open() as client:
        result = harness.call_tool(
            client, "roadmap_get_next", {"roadmap_id": _RID, "format": "detailed"}
        )

    content = result["structuredContent"]
    assert content["remaining_in_path"] == 3
    assert content["complete"] is False
    item = content["items"][0]
    assert item["subsection_id"] == "sub_hashing"
    assert item["path_position"] == 2
    assert "suggested path" in item["why_now"]
    assert item["resources"][0]["url"] == "https://x/h"
    request = harness.captured[0]
    assert request.url.path == f"/roadmaps/{_RID}/next"
    assert request.url.params.get("format") == "detailed"


# ---------- node ----------


def test_node_maps_to_the_internal_node_route_with_links_and_resolved_prereqs() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=_node_body()))
    with harness.open() as client:
        result = harness.call_tool(
            client, "roadmap_get_node", {"roadmap_id": _RID, "subsection_id": "sub_hashing"}
        )

    content = result["structuredContent"]
    assert content["subsection_id"] == "sub_hashing"
    assert content["resources"][0] == {
        "id": "res_1",
        "title": "Hashing 101",
        "url": "https://x/h",
        "type": "article",
    }
    assert content["prereqs"][0] == {"id": "sub_arrays", "title": "Arrays", "done": True}
    assert content["items"][0]["done"] is False
    request = harness.captured[0]
    assert request.url.path == f"/roadmaps/{_RID}/nodes/sub_hashing"
    assert request.url.params.get("format") == "concise"


def test_node_unknown_id_surfaces_the_backend_error_naming_siblings() -> None:
    harness = AgentHarness(
        lambda _r: json_error(
            404, "NOT_FOUND", "No such subsection. Valid ids: sub_arrays, sub_hashing."
        )
    )
    with harness.open() as client:
        result = harness.call_tool(
            client, "roadmap_get_node", {"roadmap_id": _RID, "subsection_id": "sub_bogus"}
        )
    assert result["isError"] is True
    assert "sub_arrays" in result["content"][0]["text"]


# ---------- section (pagination) ----------


def test_section_forwards_cursor_and_include_and_returns_steering() -> None:
    page = {
        "section_id": "sec_found",
        "title": "Foundations",
        "include": "items",
        "subsections": [_node_body()],
        "next_cursor": "b3BhcXVl",
        "steering": "showing 1 of 3; pass cursor=b3BhcXVl",
    }
    harness = AgentHarness(lambda _r: httpx.Response(200, json=page))
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "roadmap_get_section",
            {
                "roadmap_id": _RID,
                "section_id": "sec_found",
                "cursor": "b3BhcXVl",
                "include": "items",
            },
        )

    content = result["structuredContent"]
    assert content["next_cursor"] == "b3BhcXVl"
    assert content["steering"].startswith("showing 1 of 3")
    assert content["include"] == "items"
    request = harness.captured[0]
    assert request.url.path == f"/roadmaps/{_RID}/sections/sec_found"
    assert request.url.params.get("cursor") == "b3BhcXVl"
    assert request.url.params.get("include") == "items"


def test_section_omits_the_cursor_on_the_first_page() -> None:
    page = {
        "section_id": "sec_found",
        "title": "Foundations",
        "include": "both",
        "subsections": [],
        "next_cursor": None,
        "steering": None,
    }
    harness = AgentHarness(lambda _r: httpx.Response(200, json=page))
    with harness.open() as client:
        harness.call_tool(
            client, "roadmap_get_section", {"roadmap_id": _RID, "section_id": "sec_found"}
        )
    request = harness.captured[0]
    assert "cursor" not in request.url.params
    assert request.url.params.get("include") == "both"


# ---------- search ----------


def test_search_forwards_query_and_tags_and_wraps_the_hits() -> None:
    hits = [
        {
            "kind": "subsection",
            "subsection_id": "sub_hashing",
            "item_id": None,
            "title_or_text": "Hashing",
            "matched_tags": ["core"],
        },
        {
            "kind": "item",
            "subsection_id": "sub_hashing",
            "item_id": "item_1",
            "title_or_text": "Read the article",
            "matched_tags": None,
        },
    ]
    harness = AgentHarness(lambda _r: httpx.Response(200, json=hits))
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "roadmap_search",
            {"roadmap_id": _RID, "query": "hash", "tags": ["core", "graphs"]},
        )

    content = result["structuredContent"]
    assert [hit["kind"] for hit in content["hits"]] == ["subsection", "item"]
    assert content["hits"][1]["item_id"] == "item_1"
    request = harness.captured[0]
    assert request.url.path == f"/roadmaps/{_RID}/search"
    assert request.url.params.get("q") == "hash"
    query = str(request.url)
    assert "tags=core" in query and "tags=graphs" in query


def test_search_omits_tags_when_none_given() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=[]))
    with harness.open() as client:
        result = harness.call_tool(
            client, "roadmap_search", {"roadmap_id": _RID, "query": "graphs"}
        )
    assert result["structuredContent"] == {"hits": []}
    assert "tags" not in harness.captured[0].url.params


# ---------- progress_get ----------


def test_progress_get_maps_to_the_internal_progress_route() -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json=_progress_body()))
    with harness.open() as client:
        result = harness.call_tool(client, "progress_get", {"roadmap_id": _RID})

    content = result["structuredContent"]
    assert content["percent"] == 50
    assert content["deadline"] == "2026-08-01"
    request = harness.captured[0]
    assert request.method == "GET"
    assert request.url.path == f"/roadmaps/{_RID}/progress"
    assert request.url.params.get("detailed") == "false"


def test_progress_get_forwards_the_detailed_flag() -> None:
    harness = AgentHarness(
        lambda _r: httpx.Response(200, json=_progress_body(checked_ids=["item_1", "item_2"]))
    )
    with harness.open() as client:
        result = harness.call_tool(client, "progress_get", {"roadmap_id": _RID, "detailed": True})
    assert result["structuredContent"]["checked_ids"] == ["item_1", "item_2"]
    assert harness.captured[0].url.params.get("detailed") == "true"


# ---------- progress_update (explicit-set write) ----------


def test_progress_update_posts_an_explicit_set_and_returns_progress_plus_next() -> None:
    update_result = {"progress": _progress_body(checked_ids=["item_1"]), "next": _next_body()}
    harness = AgentHarness(
        lambda _r: httpx.Response(200, json=update_result), scope="progress:write"
    )
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "progress_update",
            {"roadmap_id": _RID, "item_ids": ["item_1"], "state": "complete"},
        )

    assert result["isError"] is False
    content = result["structuredContent"]
    assert content["progress"]["checked_ids"] == ["item_1"]
    assert content["next"]["remaining_in_path"] == 3
    request = harness.captured[0]
    assert request.method == "POST"
    assert request.url.path == f"/roadmaps/{_RID}/progress"
    assert json.loads(request.content) == {"item_ids": ["item_1"], "state": "complete"}
    assert request.headers["X-User-ID"] == "user-ada"


def test_progress_update_foreign_item_id_surfaces_an_error_and_applies_nothing() -> None:
    harness = AgentHarness(
        lambda _r: json_error(
            422, "UNKNOWN_ITEM", "item_zzz is not part of this roadmap; nothing was applied."
        ),
        scope="progress:write",
    )
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "progress_update",
            {"roadmap_id": _RID, "item_ids": ["item_zzz"], "state": "complete"},
        )
    assert result["isError"] is True
    assert "UNKNOWN_ITEM" in result["content"][0]["text"]


# ---------- scope gate (read surface + progress:write) ----------


def test_read_tool_without_roadmaps_read_scope_is_insufficient_scope() -> None:
    # A write-only token cannot drive a read tool; the gate rejects it as a
    # model-recoverable error and no internal call is made.
    harness = AgentHarness(
        lambda _r: httpx.Response(200, json=_overview_body()), scope="roadmaps:write"
    )
    with harness.open() as client:
        result = harness.call_tool(client, "roadmap_get_overview", {"roadmap_id": _RID})
    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert "insufficient_scope" in text
    assert "roadmaps:read" in text
    assert harness.captured == []


def test_progress_update_without_progress_write_scope_is_insufficient_scope() -> None:
    # roadmaps:read + roadmaps:write is NOT enough for the progress write: it needs
    # the dedicated progress:write scope.
    harness = AgentHarness(
        lambda _r: httpx.Response(200, json={}), scope="roadmaps:read roadmaps:write"
    )
    with harness.open() as client:
        result = harness.call_tool(
            client,
            "progress_update",
            {"roadmap_id": _RID, "item_ids": ["item_1"], "state": "complete"},
        )
    assert result["isError"] is True
    text = result["content"][0]["text"]
    assert "insufficient_scope" in text
    assert "progress:write" in text
    assert harness.captured == []


# ---------- token guidance ----------


def test_read_responses_stay_within_the_mcp_token_guidance() -> None:
    # Summary-first + pagination keep responses lean: even a large single page is
    # well within MCP's ~25k-token guidance. Estimate tokens at
    # ~4 chars/token over the serialized structured content.
    harness = AgentHarness(lambda _r: httpx.Response(200, json=_overview_body(sections=100)))
    with harness.open() as client:
        result = harness.call_tool(client, "roadmap_get_overview", {"roadmap_id": _RID})
    serialized = json.dumps(result["structuredContent"])
    assert len(serialized) // 4 < 25_000
