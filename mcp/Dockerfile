# syntax=docker/dockerfile:1

# =============================================================================
# Wren MCP server image.
#
# OAuth 2.1 Resource Server (PRM + bearer validation) and thin client of the
# backend internal API (:8001). Single ASGI app on :9000. Built from the
# REPO-ROOT context (docker-compose mcp.build.context: .) so the build can reach
# the shared/wren-common workspace member, mirroring the frontend/docs pattern.
# The on-disk layout mirrors the repo (/app/mcp, /app/shared) with the runtime
# WORKDIR at /app/mcp.
#
# uv installs every workspace member into one shared environment, so a plain
# `uv sync --package wren-mcp` would drag the backend (asyncpg, alembic, the
# wren domain source) into this image and break the MCP<->backend firewall.
# Instead the builder exports the lean, locked third-party set for wren-mcp
# alone (uv export --package wren-mcp) and editable-installs only wren-mcp +
# wren-common. The image carries no backend or contract code.
#
# Note: /metrics, /healthz and /readyz are NOT tunnel-exposed. Only PRM + the
# /mcp transport are public (mcp.usewren.com); /metrics is scraped in-network
# (app-net) and health is probed in-container. The tunnel ingress rules
# (deployments/cloudflare/config.yml) enforce this.
# =============================================================================

FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.20 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Resolve layer: the workspace scaffolding (root + every member's pyproject +
# the lockfile). Every member's pyproject must be present for uv to load the
# workspace graph and resolve the `wren-common = { workspace = true }` source,
# but only their metadata (not their source) lands here, so this layer stays
# cached across source-only changes.
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/pyproject.toml
COPY mcp/pyproject.toml mcp/pyproject.toml
COPY contract/pyproject.toml contract/pyproject.toml
COPY shared/wren-common/pyproject.toml shared/wren-common/pyproject.toml

# Export the lean, locked third-party set for wren-mcp only (no workspace
# members) and install it into the venv. Deps-only cached layer.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-dev --no-emit-workspace --package wren-mcp --output-file /tmp/requirements.txt \
    && uv venv "$VIRTUAL_ENV" \
    && uv pip install --requirement /tmp/requirements.txt

# Build layer: copy only wren-mcp and the shared package, then editable-install
# both (dependencies already resolved above, so --no-deps). Editable so the dev
# overlay's src bind-mount + --reload picks up edits.
COPY mcp/ mcp/
COPY shared/wren-common/ shared/wren-common/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-deps --editable ./shared/wren-common --editable ./mcp

# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

RUN groupadd --system wren && useradd --system --gid wren --home-dir /app wren

WORKDIR /app/mcp
# Only the venv and the two installed members ship; the workspace scaffolding
# and sibling members stay out of the runtime image.
COPY --from=builder --chown=wren:wren /app/.venv /app/.venv
COPY --from=builder --chown=wren:wren /app/mcp /app/mcp
COPY --from=builder --chown=wren:wren /app/shared /app/shared

# venv console scripts + interpreter on PATH (uvicorn, python). The interpreter
# backs the compose healthcheck (`python -c ... urlopen /readyz`).
ENV PATH="/app/.venv/bin:$PATH"

USER wren
EXPOSE 9000
# `wren-mcp` console script boots uvicorn on the settings host/port (0.0.0.0:9000).
CMD ["wren-mcp"]
