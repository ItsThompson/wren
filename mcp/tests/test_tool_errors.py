"""Problem+json -> ToolError mapping (spec sections 06/07).

The backend renders failures as RFC 9457 problem+json; these assert the mapping
that turns that body into one model-recoverable message (code + detail, plus
field and violation IDs) and that a success passes straight through.
"""

from __future__ import annotations

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from wren_mcp.tool_errors import raise_for_problem


def _problem(status: int, **body: object) -> httpx.Response:
    return httpx.Response(status, json=body, headers={"content-type": "application/problem+json"})


def test_success_response_passes_through() -> None:
    response = httpx.Response(200, json={"ok": True})
    assert raise_for_problem(response) is response


def test_stale_revision_message_carries_code_and_detail() -> None:
    response = _problem(409, code="STALE_REVISION", title="Conflict", detail="re-read revision 17")
    with pytest.raises(ToolError) as excinfo:
        raise_for_problem(response)
    message = str(excinfo.value)
    assert "STALE_REVISION" in message
    assert "re-read revision 17" in message


def test_field_errors_are_rendered() -> None:
    response = _problem(
        422, code="VALIDATION", detail="request invalid", fields={"body.title": "field required"}
    )
    with pytest.raises(ToolError) as excinfo:
        raise_for_problem(response)
    message = str(excinfo.value)
    assert "body.title" in message
    assert "field required" in message


def test_violations_name_the_rule_and_ids() -> None:
    response = _problem(
        422,
        code="VALIDATION",
        detail="publish blocked",
        violations=[
            {"rule": "V2_CYCLE", "ids": ["sub_a", "sub_b"], "message": "prerequisite cycle"},
        ],
    )
    with pytest.raises(ToolError) as excinfo:
        raise_for_problem(response)
    message = str(excinfo.value)
    assert "V2_CYCLE" in message
    assert "prerequisite cycle" in message
    assert "sub_a" in message and "sub_b" in message


def test_non_json_error_body_falls_back_to_status_and_text() -> None:
    response = httpx.Response(502, text="upstream boom")
    with pytest.raises(ToolError) as excinfo:
        raise_for_problem(response)
    message = str(excinfo.value)
    assert "502" in message
    assert "upstream boom" in message


def test_empty_error_body_still_produces_a_message() -> None:
    response = httpx.Response(500, text="")
    with pytest.raises(ToolError) as excinfo:
        raise_for_problem(response)
    assert "500" in str(excinfo.value)


def test_non_object_json_body_falls_back() -> None:
    # A JSON array is valid JSON but not a problem+json object: fall back cleanly.
    response = httpx.Response(400, json=["unexpected"])
    with pytest.raises(ToolError) as excinfo:
        raise_for_problem(response)
    assert "400" in str(excinfo.value)
