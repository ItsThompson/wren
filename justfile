# Wren monorepo dev + ops recipes.
#
# Backend and infra recipes live here. Frontend and full-stack recipes are added
# by the slices that own them; keep recipes grouped and this file appendable.

# The dev stack is always the base compose file plus the dev overlay; the
# overlay is never valid standalone (it only carries overrides).
dev_compose := "-f docker-compose.yml -f docker-compose.dev.yml"

# List available recipes
default:
    @just --list

# --- Backend ----------------------------------------------------------------

# Sync the Python workspace into the shared root venv (single root uv.lock)
setup:
    uv sync --all-packages

# Boot the external app (:8000) with autoreload
dev-api:
    cd backend && uv run uvicorn wren.api.main:app --host 127.0.0.1 --port 8000 --reload

# Boot the internal app (:8001) with autoreload
dev-api-internal:
    cd backend && uv run uvicorn wren.api_internal.main:app --host 127.0.0.1 --port 8001 --reload

# Run backend tests with coverage
test-backend:
    cd backend && uv run pytest

# Lint backend (ruff check + format check + mypy)
lint-backend:
    cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy

# Format backend
fmt-backend:
    cd backend && uv run ruff format . && uv run ruff check --fix .

# --- MCP server -------------------------------------------------------------

# Sync the Python workspace into the shared root venv (same as `just setup`)
setup-mcp:
    uv sync --all-packages

# Boot the MCP Resource Server (:9000) with autoreload. Also used by the MCP
# Inspector to attach during development.
dev-mcp:
    cd mcp && uv run uvicorn wren_mcp.main:app --host 127.0.0.1 --port 9000 --reload

# Run MCP server tests with coverage
test-mcp:
    cd mcp && uv run pytest

# Lint the MCP server (ruff check + format check + mypy)
lint-mcp:
    cd mcp && uv run ruff check . && uv run ruff format --check . && uv run mypy

# Format the MCP server
fmt-mcp:
    cd mcp && uv run ruff format . && uv run ruff check --fix .

# --- Authoring guidance (SKILL.md) ------------------------------------------

# Re-sync the backend-bundled SKILL.md with the canonical repo-root copy.
# The canonical, human-edited guidance lives at skill/SKILL.md; the backend
# serves a bundled copy (backend/src/wren/skill/SKILL.md), and a drift test
# (backend/tests/test_skill_content.py) fails if the two diverge. Run this after
# editing skill/SKILL.md.
sync-skill:
    cp skill/SKILL.md backend/src/wren/skill/SKILL.md

# --- Docker stack -----------------------------------------------------------

# Build the first-party images (backend, mcp, frontend, docs)
build:
    docker compose build

# Run the production-shaped stack locally (expose-only; tunnel added at deploy time).
# Prometheus reads its config via an environment-sourced Compose config, so
# populate the vars from the committed files (same mechanism as the deploy).
up:
    WREN_PROMETHEUS_CONFIG="$(cat deployments/prometheus/prometheus.yml)" \
      WREN_PROMETHEUS_ALERTS="$(cat deployments/prometheus/alerts.yml)" \
      docker compose up -d --build

# Stop the production-shaped stack (keeps named volumes)
down:
    docker compose down

# Run the full stack locally in dev mode (bind mounts, --reload, relaxed cookies)
up-dev:
    WREN_PROMETHEUS_CONFIG="$(cat deployments/prometheus/prometheus.yml)" \
      WREN_PROMETHEUS_ALERTS="$(cat deployments/prometheus/alerts.yml)" \
      docker compose {{dev_compose}} up -d --build

# Stop the dev stack (keeps named volumes)
down-dev:
    docker compose {{dev_compose}} down

# Tear down the dev stack AND drop its named volumes (fresh Postgres + TSDB)
reset:
    docker compose {{dev_compose}} down -v

# --- Infra & migrations -----------------------------------------------------

# Bring up local dev infrastructure (Postgres; observability added later)
dev-infra:
    docker compose {{dev_compose}} up -d postgres

# Tear down local dev infrastructure (keeps the pgdata volume)
dev-infra-down:
    docker compose {{dev_compose}} down

# Apply all migrations up to head (run pre-traffic; never at app startup)
migrate:
    cd backend && uv run alembic upgrade head

# Autogenerate a new migration from model changes: just migrate-new "add roadmaps"
migrate-new msg:
    cd backend && uv run alembic revision --autogenerate -m "{{msg}}"

# --- Frontend ---------------------------------------------------------------

# Install frontend dependencies
setup-frontend:
    cd frontend && npm install

# Boot the SPA dev server (talks to the real backend)
dev-web:
    cd frontend && npm run dev

# Boot the SPA against the zero-backend MSW mock harness
dev-mock:
    cd frontend && npm run dev:mock

# Run frontend tests with coverage
test-frontend:
    cd frontend && npm run test:coverage

# Lint + typecheck the frontend
lint-frontend:
    cd frontend && npx tsc -b && npm run lint

# Regenerate the OpenAPI -> TypeScript client from the live FastAPI schema.
# Exports the external app's OpenAPI document, then runs openapi-typescript.
# CI runs this and `git diff --exit-code` to fail on a stale committed client.
# Run after any change to the external REST surface.
codegen:
    cd backend && LOG_LEVEL=critical uv run python -c "import json; from wren.api.main import app; print(json.dumps(app.openapi(), indent=2))" > ../frontend/openapi.json
    cd frontend && npm run codegen

# --- Deploy / ops -----------------------------------------------------------

# Deploy the whole stack to a VPS over a Docker Context; DEPLOY_SHA optional
# (defaults to the checkout HEAD). Register the context and export the
# config/secret env first (see docs/runbooks/bring-up.md Phase E). Match
# DEPLOY_SHA to the CD-built image tags: DEPLOY_SHA=$(git rev-parse HEAD) just deploy 203.0.113.10
deploy ip user='deploy':
    ./scripts/deploy.sh {{ip}} {{user}}

# Print the deploy plan (every docker --context compose line + the single ssh
# line) without touching a server. The preflight runs, so the required
# config/secret env vars must be set (even dummy values) to reach the plan.
deploy-plan ip user='deploy':
    DRY_RUN=1 ./scripts/deploy.sh {{ip}} {{user}}

# Run the deploy-script test harness (pure helpers, dry-run plan, rollback).
test-deploy:
    bash scripts/tests/deploy_test.sh

# Preview the rendered Cloudflare tunnel ingress config from the local .env.
render-tunnel:
    set -a; . ./.env; set +a; \
    envsubst '$CF_TUNNEL_ID $CF_APP_HOSTNAME $CF_API_HOSTNAME $CF_MCP_HOSTNAME $CF_DOCS_HOSTNAME' \
      < deployments/cloudflare/config.yml

# Preview the rendered Alertmanager config from the local .env (substitutes only
# DISCORD_WEBHOOK_URL; the Go templating survives). Redirect to
# deployments/alertmanager/alertmanager.rendered.yml to exercise alerting locally.
render-alertmanager:
    set -a; . ./.env; set +a; \
    envsubst '$DISCORD_WEBHOOK_URL' \
      < deployments/alertmanager/alertmanager.yml

# --- E2E (Playwright, full stack) -------------------------------------------

# Every e2e compose invocation layers the e2e overlay (published frontend +
# backend ports, relaxed cookies) on the base stack. Test-only: a real deploy
# never uses this overlay (deploy.sh composes base + docker-compose.tunnel.yml).
e2e_compose := "-f docker-compose.yml -f e2e/docker-compose.e2e.yml"

# Install the Playwright runner + the chromium browser (run once).
setup-e2e:
    cd e2e && npm ci && npx playwright install --with-deps chromium

# Build + boot the e2e stack (published ports) and run pre-traffic migrations.
# Both `up` and the migration `run` materialize the environment-sourced
# Prometheus config, so export the vars for the whole recipe.
e2e-up:
    #!/usr/bin/env bash
    set -euo pipefail
    export WREN_PROMETHEUS_CONFIG="$(cat deployments/prometheus/prometheus.yml)"
    export WREN_PROMETHEUS_ALERTS="$(cat deployments/prometheus/alerts.yml)"
    docker compose {{e2e_compose}} up -d --build
    docker compose {{e2e_compose}} run --rm backend alembic upgrade head

# Run the Playwright spine + smoke against the running e2e stack.
test-e2e:
    cd e2e && npx playwright test

# Tear down the e2e stack and drop its named volumes.
e2e-down:
    docker compose {{e2e_compose}} down -v
