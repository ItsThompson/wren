# syntax=docker/dockerfile:1

# =============================================================================
# Wren MCP server image (spec sections 07/08/11).
#
# OAuth 2.1 Resource Server (PRM + bearer validation) and thin client of the
# backend internal API (:8001). Single ASGI app on :9000. Multi-stage uv build,
# non-root runtime, mirroring the backend image.
#
# Note (tracked from Ticket 20 review): /metrics, /healthz and /readyz are NOT
# tunnel-exposed. Only PRM + the /mcp transport are public (mcp.usewren.com);
# /metrics is scraped in-network (app-net) and health is probed in-container.
# The tunnel ingress rules that enforce this land in Ticket 29.
# =============================================================================

FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

RUN groupadd --system wren && useradd --system --gid wren --home-dir /app wren

WORKDIR /app
COPY --from=builder --chown=wren:wren /app /app

# venv console scripts + interpreter on PATH (uvicorn, python). The interpreter
# backs the compose healthcheck (`python -c ... urlopen /readyz`).
ENV PATH="/app/.venv/bin:$PATH"

USER wren
EXPOSE 9000
# `wren-mcp` console script boots uvicorn on the settings host/port (0.0.0.0:9000).
CMD ["wren-mcp"]
