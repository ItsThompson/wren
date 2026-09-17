# syntax=docker/dockerfile:1

# =============================================================================
# Wren frontend image: build the Vite SPA, then serve the
# static bundle from nginx with a history-API fallback. Two stages so node and
# the build toolchain never ship in the runtime image.
#
# Built from the REPO-ROOT context (docker-compose frontend.build.context: .)
# so the SPA can import the shared shared/theme/*.css. Paths are prefixed with
# frontend/ and the on-disk layout mirrors the repo (/app/frontend, /app/shared)
# so the SPA's relative ../../shared import resolves.
# =============================================================================

FROM node:22-alpine AS builder
WORKDIR /app

# Install deps first (cached across source-only changes). --legacy-peer-deps
# mirrors the local install: openapi-typescript's peer pins typescript ^5.x while
# the toolchain runs typescript 6, a benign conflict the lockfile already
# resolves. (Dependency alignment is the frontend package's call, not this image's.)
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci --legacy-peer-deps

# Build. VITE_API_BASE_URL is baked into the bundle at build time (the SPA reads
# import.meta.env.VITE_API_BASE_URL); prod passes the API origin (api.usewren.com),
# empty means same-origin. VITE_MCP_BASE_URL is likewise baked from MCP_PUBLIC_URL
# (mcp.usewren.com); the onboarding wizard displays the MCP endpoint derived from
# it. Both supplied by compose build.args. shared/ carries the shared design
# tokens + fonts the SPA imports.
COPY frontend/ ./frontend/
COPY shared/ ./shared/
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ARG VITE_MCP_BASE_URL=""
ENV VITE_MCP_BASE_URL=$VITE_MCP_BASE_URL
ARG VITE_SENTRY_DSN=""
ARG VITE_SENTRY_RELEASE=""
ARG SENTRY_ORG=""
ARG SENTRY_PROJECT_FRONTEND=""
ARG SENTRY_UPLOAD_RUN_ID=""
ENV VITE_SENTRY_DSN=$VITE_SENTRY_DSN \
    VITE_SENTRY_RELEASE=$VITE_SENTRY_RELEASE
RUN --mount=type=secret,id=sentry_auth_token,required=false \
    set -eu; \
    cd frontend; \
    npm run build; \
    printf 'Sentry source-map upload run: %s\\n' "${SENTRY_UPLOAD_RUN_ID}"; \
    if [ -s /run/secrets/sentry_auth_token ] && [ -n "${SENTRY_ORG}" ] && \
       [ -n "${SENTRY_PROJECT_FRONTEND}" ] && [ -n "${VITE_SENTRY_RELEASE}" ]; then \
      export SENTRY_AUTH_TOKEN="$(cat /run/secrets/sentry_auth_token)"; \
      ./node_modules/.bin/sentry-cli sourcemaps inject dist; \
      ./node_modules/.bin/sentry-cli sourcemaps upload dist \
        --org "${SENTRY_ORG}" \
        --project "${SENTRY_PROJECT_FRONTEND}" \
        --release "${VITE_SENTRY_RELEASE}"; \
    else \
      echo 'Sentry source-map upload disabled: credentials or release arguments absent'; \
    fi; \
    find dist -type f -name '*.map' -delete

# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# Replace the stock server block with the SPA config (static + history fallback).
# Paths are repo-root-relative now that the build context is the repo root.
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/frontend/dist /usr/share/nginx/html

EXPOSE 80
# nginx:alpine's default CMD runs nginx in the foreground.
