"""MCP correlation hop + tool-layer logging + auth-rejection logging.

Sociable tests driven through the real mounted transport (:mod:`mcp_harness`):
the bearer boundary mints a per-action ``request_id``, the tool layer logs
``tool_invoked``/``tool_failed`` around the counted call, and the internal client
forwards the id to the backend. Logs are asserted with structlog's ``capture_logs``
running the real ``merge_contextvars`` processor (never a mock).

The module loggers freeze their processor list at import (``get_logger`` binds
eagerly), so each test resets the module ``_log`` to a fresh ``structlog.get_logger()``
inside the capture block, mirroring the backend correlation tests.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from log_capture import capture_correlated_logs
from mcp_harness import AgentHarness, json_error
from wren_mcp.client import REQUEST_ID_HEADER

if TYPE_CHECKING:
    from collections.abc import MutableMapping

    import pytest

_ROADMAP_ID = "grokking-dsa-7f3k"
_MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}

# The backend's inbound X-Request-ID honoring guard
# (backend/src/wren/core/correlation.py ``_REQUEST_ID_RE``): an id matching this
# in full is honored rather than re-minted, keeping the hop continuous.
_BACKEND_HONORS_RE = re.compile(r"[A-Za-z0-9._-]{1,128}")


def _events(logs: list[MutableMapping[str, Any]], event: str) -> list[MutableMapping[str, Any]]:
    return [entry for entry in logs if entry.get("event") == event]


def _one(logs: list[MutableMapping[str, Any]], event: str) -> MutableMapping[str, Any]:
    matches = _events(logs, event)
    assert len(matches) == 1, f"expected exactly one {event!r}, got {len(matches)}"
    return matches[0]


# ---------- request-id propagation across the MCP -> backend hop ----------


def test_client_request_id_is_the_correlated_id_and_backend_honorable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = AgentHarness(lambda _r: json_error(404, "NOT_FOUND", "no such roadmap"))
    with capture_correlated_logs() as mcp_logs:
        monkeypatch.setattr("wren_mcp.tool_metrics._log", structlog.get_logger())
        with harness.open() as client:
            harness.call_tool(client, "roadmap_get_overview", {"roadmap_id": _ROADMAP_ID})

    # The id minted at the bearer boundary is what the tool layer logs and what
    # the client sets on the backend hop: one id for the whole agent action.
    mcp_request_id = _one(mcp_logs, "tool_invoked")["request_id"]
    assert mcp_request_id
    sent = harness.captured[0].headers[REQUEST_ID_HEADER]
    assert sent == mcp_request_id

    # The minted id satisfies the backend's X-Request-ID wire constraint, so the
    # backend CorrelationMiddleware honors it instead of re-minting and one id
    # spans the hop.
    assert _BACKEND_HONORS_RE.fullmatch(sent)


# ---------- tool-layer logging ----------


def test_tool_invoked_and_tool_failed_carry_tool_and_correlation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = AgentHarness(lambda _r: json_error(409, "STALE_REVISION", "re-read and retry"))
    with capture_correlated_logs() as logs:
        monkeypatch.setattr("wren_mcp.tool_metrics._log", structlog.get_logger())
        with harness.open() as client:
            result = harness.call_tool(client, "roadmap_get_overview", {"roadmap_id": _ROADMAP_ID})

    assert result["isError"] is True

    invoked = _one(logs, "tool_invoked")
    assert invoked["log_level"] == "info"
    assert invoked["tool"] == "roadmap_get_overview"
    # Both correlation keys ride the entry line: request_id and user_id are bound
    # at the bearer boundary, before the counted call runs.
    assert invoked["request_id"]
    assert invoked["user_id"] == "user-ada"

    failed = _one(logs, "tool_failed")
    assert failed["log_level"] == "warning"
    assert failed["tool"] == "roadmap_get_overview"
    assert failed["request_id"] == invoked["request_id"]
    assert failed["user_id"] == "user-ada"
    # The backend HTTP status + problem code surface on the failure line.
    assert failed["status"] == 409
    assert failed["code"] == "STALE_REVISION"
    assert failed["error_type"] == "BackendToolError"


def test_tool_success_logs_tool_invoked_without_a_tool_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ok = {
        "id": _ROADMAP_ID,
        "revision": 1,
        "status": "draft",
        "remap": {},
    }
    harness = AgentHarness(lambda _r: httpx.Response(201, json=ok))
    with capture_correlated_logs() as logs:
        monkeypatch.setattr("wren_mcp.tool_metrics._log", structlog.get_logger())
        with harness.open() as client:
            result = harness.call_tool(
                client, "create_roadmap_draft", {"roadmap": {"title": "Grokking DSA"}}
            )

    assert result["isError"] is False
    invoked = _one(logs, "tool_invoked")
    assert invoked["tool"] == "create_roadmap_draft"
    assert invoked["request_id"]
    assert _events(logs, "tool_failed") == []


def test_no_raw_bearer_token_is_logged_on_a_tool_call(monkeypatch: pytest.MonkeyPatch) -> None:
    harness = AgentHarness(lambda _r: json_error(409, "STALE_REVISION", "re-read and retry"))
    raw_token = harness._auth["Authorization"].removeprefix("Bearer ")
    with capture_correlated_logs() as logs:
        monkeypatch.setattr("wren_mcp.tool_metrics._log", structlog.get_logger())
        with harness.open() as client:
            harness.call_tool(client, "roadmap_get_overview", {"roadmap_id": _ROADMAP_ID})

    assert raw_token
    assert raw_token not in repr(logs)


# ---------- MCP auth-rejection logging ----------


def test_missing_bearer_logs_agent_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    harness = AgentHarness(lambda _r: httpx.Response(200, json={}))
    with capture_correlated_logs() as logs:
        monkeypatch.setattr("wren_mcp.auth._log", structlog.get_logger())
        with harness.open() as client:
            response = client.post(
                "/mcp/",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                headers=_MCP_HEADERS,
            )

    assert response.status_code == 401
    rejection = _one(logs, "agent_token_rejected")
    assert rejection["log_level"] == "warning"
    assert rejection["reason"] == "missing_bearer"


def test_invalid_bearer_logs_agent_token_rejected_without_leaking_the_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "super-secret-but-invalid-token"
    harness = AgentHarness(lambda _r: httpx.Response(200, json={}))
    with capture_correlated_logs() as logs:
        monkeypatch.setattr("wren_mcp.auth._log", structlog.get_logger())
        with harness.open() as client:
            response = client.post(
                "/mcp/",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                headers={**_MCP_HEADERS, "Authorization": f"Bearer {secret}"},
            )

    assert response.status_code == 401
    rejection = _one(logs, "agent_token_rejected")
    assert rejection["log_level"] == "warning"
    assert rejection["reason"] == "invalid_token"
    # The raw (rejected) token never reaches a log field.
    assert secret not in repr(logs)
