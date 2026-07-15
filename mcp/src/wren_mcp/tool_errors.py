"""Model-recoverable tool errors (spec sections 06/07).

The backend renders every failure as one RFC 9457 ``application/problem+json``
body (spec section 06): a machine ``code`` plus a human ``detail``, optionally a
field-level ``fields`` map and a structural ``violations`` list that names the
offending IDs (a stale-revision 409 says "re-read"; a DAG-cycle 422 names the
nodes). This module folds that body into a single :class:`ToolError` message so
the agent sees a structured, self-correctable error rather than a raw HTTP status
(spec section 07: "errors name valid IDs and explain violations so the agent can
self-correct without a human").

``ToolError`` is the FastMCP-preferred signal for an expected failure: FastMCP
returns its message to the client with ``isError=True``.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from mcp.server.fastmcp.exceptions import ToolError


def raise_for_problem(response: httpx.Response) -> httpx.Response:
    """Return the response on success; on a >=400 status raise a
    :class:`ToolError` carrying the backend's structured problem detail."""
    if response.status_code < 400:
        return response
    raise ToolError(_format_problem(response))


def _format_problem(response: httpx.Response) -> str:
    """Render a problem+json body (or a non-JSON fallback) into one recoverable
    message the model can act on."""
    problem = _parse_body(response)
    if problem is None:
        body = response.text or "no response body"
        return f"Backend error {response.status_code}: {body}".strip()

    code = problem.get("code") or f"HTTP_{response.status_code}"
    detail = problem.get("detail") or problem.get("title") or "request failed"
    parts = [f"{code}: {detail}"]

    fields = problem.get("fields")
    if isinstance(fields, dict) and fields:
        rendered = "; ".join(f"{name}: {message}" for name, message in fields.items())
        parts.append(f"invalid fields -> {rendered}")

    violations = problem.get("violations")
    if isinstance(violations, list) and violations:
        parts.append(f"violations -> {_format_violations(violations)}")

    return " | ".join(parts)


def _format_violations(violations: list[Any]) -> str:
    """One line per structural violation, naming the rule + offending IDs so the
    agent can locate and fix the exact nodes (e.g. a DAG cycle's members)."""
    rendered: list[str] = []
    for violation in violations:
        if not isinstance(violation, dict):
            continue
        rule = violation.get("rule", "violation")
        message = violation.get("message", "")
        ids = violation.get("ids") or []
        suffix = f" (ids: {', '.join(str(i) for i in ids)})" if ids else ""
        rendered.append(f"[{rule}] {message}{suffix}")
    return "; ".join(rendered)


def _parse_body(response: httpx.Response) -> dict[str, Any] | None:
    try:
        parsed = response.json()
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None
