"""Thin client of the backend internal API (:8001).

Each MCP tool call becomes one HTTP call to the backend internal
app over ``compute-net``. This client owns the one security-critical invariant of
that hop: **every** request carries the resolved ``X-User-ID`` plus the shared
``INTERNAL_API_TOKEN``, and the agent's bearer token is **never** forwarded
(confused-deputy defense). The trusted headers are set last so a
caller cannot override them.

The named methods mirror the internal roadmap router op-for-op; the tool layer
maps their responses to tool outputs. The ``httpx.AsyncClient`` is injected (bound
to ``BACKEND_INTERNAL_URL``) so tests substitute a transport without a live
backend.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import structlog
from mcp.server.fastmcp.exceptions import ToolError

from wren_mcp.config import INTERNAL_TOKEN_HEADER, USER_ID_HEADER

if TYPE_CHECKING:
    from pydantic import SecretStr

    from wren_mcp.settings import RsSettings

# Bound so a hung internal call cannot pin an MCP worker indefinitely.
_DEFAULT_TIMEOUT_SECONDS = 10.0

# Forwarded so one agent action is traceable across the MCP -> backend hop: the
# backend CorrelationMiddleware honors this inbound id instead of minting a new
# one. Mirrors ``wren.core.correlation.REQUEST_ID_HEADER`` (a duplicated wire
# contract, since the RS and backend are separate images with no shared code).
REQUEST_ID_HEADER = "X-Request-ID"


class InternalApiClient:
    """Forwards user-scoped calls to the backend internal app."""

    def __init__(self, http_client: httpx.AsyncClient, *, api_token: SecretStr) -> None:
        self._http = http_client
        self._api_token = api_token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        user_id: str,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """One internal call scoped to ``user_id``.

        The trusted identity + shared-secret headers are applied last, so they
        can never be overridden by ``extra_headers`` and the agent token is never
        propagated (only ``user_id`` crosses this boundary). The correlation
        ``request_id`` bound for this agent action (:mod:`wren_mcp.correlation`)
        rides along as ``X-Request-ID`` so the backend logs share the same id.

        A transport failure (the backend unreachable or timed out) is translated
        into a model-recoverable :class:`ToolError` here, so every named method
        inherits a structured "retry shortly" error instead of an opaque,
        often-empty transport exception. A backend that answers with a >=400
        status still returns a ``Response``; that path is handled by
        :func:`wren_mcp.tool_errors.raise_for_problem`, not this ``except``.
        """
        headers = dict(extra_headers or {})
        headers[USER_ID_HEADER] = user_id
        # Unwrap the SecretStr only here, at the single wire-header use site; the
        # raw value is never logged.
        headers[INTERNAL_TOKEN_HEADER] = self._api_token.get_secret_value()
        request_id = structlog.contextvars.get_contextvars().get("request_id")
        if request_id is not None:
            headers[REQUEST_ID_HEADER] = str(request_id)
        try:
            return await self._http.request(method, path, json=json, params=params, headers=headers)
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise ToolError(
                "backend_unavailable: the roadmap service is unreachable or timed out; "
                "retry shortly."
            ) from exc

    async def create_draft(self, user_id: str, document: Any) -> httpx.Response:
        return await self._request("POST", "/roadmaps", user_id=user_id, json=document)

    async def get_roadmap(self, user_id: str, roadmap_id: str) -> httpx.Response:
        return await self._request("GET", f"/roadmaps/{roadmap_id}", user_id=user_id)

    # ---------- Read projections (study-time tools) ----------
    # Each backs one MCP read tool, one internal GET per tool. The
    # concise|detailed switch travels as ``?format=``; pagination as an opaque
    # ``?cursor=``; ``?include=`` selects the section-page shape.

    async def get_overview(self, user_id: str, roadmap_id: str, fmt: str) -> httpx.Response:
        return await self._request(
            "GET", f"/roadmaps/{roadmap_id}/overview", user_id=user_id, params={"format": fmt}
        )

    async def get_next(self, user_id: str, roadmap_id: str, fmt: str) -> httpx.Response:
        return await self._request(
            "GET", f"/roadmaps/{roadmap_id}/next", user_id=user_id, params={"format": fmt}
        )

    async def get_node(
        self, user_id: str, roadmap_id: str, subsection_id: str, fmt: str
    ) -> httpx.Response:
        return await self._request(
            "GET",
            f"/roadmaps/{roadmap_id}/nodes/{subsection_id}",
            user_id=user_id,
            params={"format": fmt},
        )

    async def get_section(
        self, user_id: str, roadmap_id: str, section_id: str, cursor: str | None, include: str
    ) -> httpx.Response:
        # The opaque cursor is omitted on the first page (a null cursor is not a
        # valid token); ``include`` always travels.
        params: dict[str, Any] = {"include": include}
        if cursor is not None:
            params["cursor"] = cursor
        return await self._request(
            "GET", f"/roadmaps/{roadmap_id}/sections/{section_id}", user_id=user_id, params=params
        )

    async def search(
        self, user_id: str, roadmap_id: str, q: str, tags: list[str] | None
    ) -> httpx.Response:
        # ``tags`` is a repeated query param (tags=a&tags=b), omitted when empty.
        params: dict[str, Any] = {"q": q}
        if tags:
            params["tags"] = tags
        return await self._request(
            "GET", f"/roadmaps/{roadmap_id}/search", user_id=user_id, params=params
        )

    async def get_progress(self, user_id: str, roadmap_id: str, detailed: bool) -> httpx.Response:
        return await self._request(
            "GET",
            f"/roadmaps/{roadmap_id}/progress",
            user_id=user_id,
            params={"detailed": detailed},
        )

    async def update_progress(
        self, user_id: str, roadmap_id: str, item_ids: list[str], state: str
    ) -> httpx.Response:
        # Explicit set (complete|incomplete), batch item_ids: the
        # server applies atomically and returns the fresh snapshot + next.
        return await self._request(
            "POST",
            f"/roadmaps/{roadmap_id}/progress",
            user_id=user_id,
            json={"item_ids": item_ids, "state": state},
        )

    async def patch_draft(
        self, user_id: str, roadmap_id: str, revision: int, operations: list[Any]
    ) -> httpx.Response:
        # The target revision travels in If-Match, matching the
        # internal router's PATCH contract.
        return await self._request(
            "PATCH",
            f"/roadmaps/{roadmap_id}",
            user_id=user_id,
            json={"operations": operations},
            extra_headers={"If-Match": str(revision)},
        )

    async def replace_draft(
        self, user_id: str, roadmap_id: str, revision: int, document: Any
    ) -> httpx.Response:
        # The full-document import escape hatch (PUT) shares the PATCH's If-Match
        # optimistic-concurrency guard; the roadmap ID is unchanged.
        return await self._request(
            "PUT",
            f"/roadmaps/{roadmap_id}",
            user_id=user_id,
            json=document,
            extra_headers={"If-Match": str(revision)},
        )

    async def validate_draft(self, user_id: str, roadmap_id: str) -> httpx.Response:
        return await self._request("POST", f"/roadmaps/{roadmap_id}:validate", user_id=user_id)

    async def publish(self, user_id: str, roadmap_id: str) -> httpx.Response:
        return await self._request("POST", f"/roadmaps/{roadmap_id}:publish", user_id=user_id)

    async def fork(self, user_id: str, roadmap_id: str) -> httpx.Response:
        # Forks any roadmap the user can read into a fresh draft.
        return await self._request("POST", f"/roadmaps/{roadmap_id}:fork", user_id=user_id)

    async def edit_metadata(
        self,
        user_id: str,
        roadmap_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        subject_tags: list[str] | None = None,
    ) -> httpx.Response:
        # Presentation-only edit, allowed post-publish and never If-Match-guarded.
        # Only provided fields are sent so an omitted field is left unchanged; a
        # structural field can never be smuggled through here.
        body: dict[str, Any] = {}
        if title is not None:
            body["title"] = title
        if description is not None:
            body["description"] = description
        if subject_tags is not None:
            body["subject_tags"] = subject_tags
        return await self._request(
            "PATCH", f"/roadmaps/{roadmap_id}/metadata", user_id=user_id, json=body
        )


def create_internal_http_client(settings: RsSettings) -> httpx.AsyncClient:
    """Build the ``httpx.AsyncClient`` bound to the backend internal base URL."""
    return httpx.AsyncClient(
        base_url=settings.backend_internal_url,
        timeout=_DEFAULT_TIMEOUT_SECONDS,
    )
