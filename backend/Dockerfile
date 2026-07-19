# syntax=docker/dockerfile:1

# =============================================================================
# Wren backend image (spec sections 08/11).
#
# One image serves both ASGI apps: the external app (:8000, internet-facing via
# the tunnel) and the internal app (:8001, app-net, token-gated). Multi-stage uv
# build: a builder resolves the locked dependency graph into a venv; the runtime
# stage copies only that venv plus source and runs as a non-root user.
#
# The image also carries Alembic (alembic/ + alembic.ini) so the pre-traffic
# migration step runs as `docker compose run --rm backend alembic upgrade head`,
# which cleanly overrides the default two-app CMD (spec section 11).
# =============================================================================

FROM python:3.12-slim-bookworm AS builder

# uv: fast, lockfile-driven installs. Pinned; review with the base image.
COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Install the locked third-party graph first (without the project) so this layer
# stays cached across source-only changes.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

# Then the project itself (editable; the venv references /app/src).
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# Non-root runtime user: the app never needs root (defense-in-depth).
RUN groupadd --system wren && useradd --system --gid wren --home-dir /app wren

WORKDIR /app
COPY --from=builder --chown=wren:wren /app /app

# venv console scripts + interpreter on PATH (uvicorn, alembic, python). The
# interpreter backs the compose healthcheck (`python -c ... urlopen /readyz`).
ENV PATH="/app/.venv/bin:$PATH"

RUN chmod +x /app/docker/serve.sh

USER wren
EXPOSE 8000 8001
CMD ["/app/docker/serve.sh"]
