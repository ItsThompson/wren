"""MCP server entrypoint (:9000).

Internet-reachable via the Cloudflare tunnel (``mcp.usewren.com``). Serves the
PRM, validates agent bearer tokens as an OAuth Resource Server, and forwards tool
calls (Tickets 21/22) to the backend internal app. Built from :func:`build_app`.
"""

from __future__ import annotations

from fastapi import FastAPI

from wren_mcp.app import build_app
from wren_mcp.settings import build_rs_settings

settings = build_rs_settings()
app: FastAPI = build_app(settings)


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn

    uvicorn.run("wren_mcp.main:app", host=settings.host, port=settings.port)
