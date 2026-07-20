# syntax=docker/dockerfile:1

# =============================================================================
# Wren docs-site image: build the VitePress static site, then
# serve the static bundle from nginx with a history-API fallback. Two stages so
# node and the build toolchain never ship in the runtime image. Mirrors
# frontend/Dockerfile.
#
# Built from the REPO-ROOT context (docker-compose docs.build.context: .) so the
# custom VitePress theme can import the shared shared/theme/*.css. Paths are
# prefixed with docs-site/ and the on-disk layout mirrors the repo
# (/app/docs-site, /app/shared) so the theme's relative ../../../shared import
# resolves.
# =============================================================================

FROM node:22-alpine AS builder
WORKDIR /app

# Install deps first (cached across source-only changes). npm ci requires the
# committed package-lock.json.
COPY docs-site/package.json docs-site/package-lock.json ./docs-site/
RUN cd docs-site && npm ci

# Build. VitePress emits static output to .vitepress/dist. shared/ carries the
# shared design tokens + fonts the custom theme imports.
COPY docs-site/ ./docs-site/
COPY shared/ ./shared/
RUN cd docs-site && npm run build

# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# Replace the stock server block with the docs config (static + history fallback).
# Paths are repo-root-relative now that the build context is the repo root.
COPY docs-site/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/docs-site/.vitepress/dist /usr/share/nginx/html

EXPOSE 80
# nginx:alpine's default CMD runs nginx in the foreground.
