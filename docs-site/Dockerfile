# syntax=docker/dockerfile:1

# =============================================================================
# Wren docs-site image (spec section 04): build the VitePress static site, then
# serve the static bundle from nginx with a history-API fallback. Two stages so
# node and the build toolchain never ship in the runtime image. Mirrors
# frontend/Dockerfile.
# =============================================================================

FROM node:22-alpine AS builder
WORKDIR /app

# Install deps first (cached across source-only changes). npm ci requires the
# committed package-lock.json.
COPY package.json package-lock.json ./
RUN npm ci

# Build. VitePress emits static output to .vitepress/dist.
COPY . .
RUN npm run build

# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# Replace the stock server block with the docs config (static + history fallback).
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/.vitepress/dist /usr/share/nginx/html

EXPOSE 80
# nginx:alpine's default CMD runs nginx in the foreground.
