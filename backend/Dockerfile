# syntax=docker/dockerfile:1

# =============================================================================
# Wren backend image.
#
# One image serves both ASGI apps: the external app (:8000, internet-facing via
# the tunnel) and the internal app (:8001, app-net, token-gated). Built from the
# REPO-ROOT context (docker-compose backend.build.context: .) so the build can
# reach the shared/wren-common workspace member, mirroring the frontend/docs
# pattern. The on-disk layout mirrors the repo (/app/backend, /app/shared) and
# the runtime WORKDIR is /app/backend so alembic.ini, docker/serve.sh, and
# `docker compose run --rm backend alembic upgrade head` resolve as before.
#
# uv installs every workspace member into one shared environment, so a plain
# `uv sync --package wren` would drag the MCP SDK and wren_mcp source into this
# image and break the backend<->MCP firewall. Instead the builder exports the
# lean, locked third-party set for wren alone (uv export --package wren) and
# editable-installs only wren + wren-common. The image carries no mcp or
# contract code.
# =============================================================================

FROM python:3.12-slim-bookworm AS builder

# uv: fast, lockfile-driven installs. Pinned; review with the base image.
COPY --from=ghcr.io/astral-sh/uv:0.11.20 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Resolve layer: the workspace scaffolding (root + every member's pyproject +
# the lockfile) is all uv needs to export the locked graph and, below, to
# resolve the `wren-common = { workspace = true }` source. Every member's
# pyproject must be present for uv to load the workspace graph, but only their
# metadata (not their source) lands here, so this layer stays cached across
# source-only changes.
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/pyproject.toml
COPY mcp/pyproject.toml mcp/pyproject.toml
COPY contract/pyproject.toml contract/pyproject.toml
COPY shared/wren-common/pyproject.toml shared/wren-common/pyproject.toml

# Export the lean, locked third-party set for wren only (no workspace members)
# and install it into the venv. Deps-only cached layer.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv export --frozen --no-dev --no-emit-workspace --package wren --output-file /tmp/requirements.txt \
    && uv venv "$VIRTUAL_ENV" \
    && uv pip install --requirement /tmp/requirements.txt

# Build layer: copy only wren and the shared package, then editable-install both
# (dependencies already resolved above, so --no-deps). Editable so the dev
# overlay's src bind-mount + --reload picks up edits.
COPY backend/ backend/
COPY shared/wren-common/ shared/wren-common/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-deps --editable ./shared/wren-common --editable ./backend

# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# Non-root runtime user: the app never needs root (defense-in-depth).
RUN groupadd --system wren && useradd --system --gid wren --home-dir /app wren

WORKDIR /app/backend
# Only the venv and the two installed members ship; the workspace scaffolding
# and sibling members stay out of the runtime image.
COPY --from=builder --chown=wren:wren /app/.venv /app/.venv
COPY --from=builder --chown=wren:wren /app/backend /app/backend
COPY --from=builder --chown=wren:wren /app/shared /app/shared

# venv console scripts + interpreter on PATH (uvicorn, alembic, python). The
# interpreter backs the compose healthcheck (`python -c ... urlopen /readyz`).
ENV PATH="/app/.venv/bin:$PATH"

RUN chmod +x /app/backend/docker/serve.sh

USER wren
EXPOSE 8000 8001
CMD ["/app/backend/docker/serve.sh"]
