# Wren monorepo dev + ops recipes.
#
# Backend and infra recipes live here. Frontend and full-stack recipes are added
# by the slices that own them; keep recipes grouped and this file appendable.

# List available recipes
default:
    @just --list

# --- Backend ----------------------------------------------------------------

# Install backend dependencies (creates backend/.venv from uv.lock)
setup:
    cd backend && uv sync

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

# --- Infra & migrations -----------------------------------------------------

# Bring up local dev infrastructure (Postgres; observability added later)
dev-infra:
    docker compose -f docker-compose.dev.yml up -d postgres

# Tear down local dev infrastructure (keeps the pgdata volume)
dev-infra-down:
    docker compose -f docker-compose.dev.yml down

# Apply all migrations up to head (run pre-traffic; never at app startup)
migrate:
    cd backend && uv run alembic upgrade head

# Autogenerate a new migration from model changes: just migrate-new "add roadmaps"
migrate-new msg:
    cd backend && uv run alembic revision --autogenerate -m "{{msg}}"
