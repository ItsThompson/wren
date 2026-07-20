# wren backend

The wren backend is a Python modular monolith. It serves two ASGI apps over one shared service layer, so the rules for creating, publishing, and tracking roadmaps live in one place.

## Purpose

- The external app (`:8000`) is internet-facing through the Cloudflare tunnel. It authenticates humans by a session cookie and hosts the public REST API and the OAuth 2.1 authorization server.
- The internal app (`:8001`) is app-net only. It trusts an injected `X-User-ID` header behind a shared `INTERNAL_API_TOKEN`. The MCP server is its only intended caller.

Both apps come from one factory (`wren.core.app_factory.create_app`) and differ only by injected settings and by which routers and identity dependency they mount.

## Architecture

- `wren.core` is the shared infrastructure kit: the app factory, settings, the two identity boundaries, persistence, logging, metrics, the error contract, correlation, health, and the route-access registry. It holds no domain logic. Two entrypoints assemble the apps: `wren.api.main` (external) and `wren.api_internal.main` (internal).
- The domain packages (`roadmaps`, `progress`, `accounts`, `oauth`, `skill`) each own one area of business rules.
- Each domain follows one layering convention: config, models, schemas, repository, service, router, and wiring. The service layer owns the transaction boundary and every business rule; routers are thin adapters.
- Dependency direction stays one-way. A domain receives narrow injected callables rather than importing another domain's repository.

See `../docs/architecture.md` for the system shape and trust zones.

## Setup and run

All recipes run from the repo root and change into `backend/`.

| Command | Purpose |
|---------|---------|
| `just setup` | Install dependencies into `backend/.venv` from `uv.lock` |
| `just dev-api` | Run the external app (`:8000`) with autoreload |
| `just dev-api-internal` | Run the internal app (`:8001`) with autoreload |
| `just dev-infra` | Start local Postgres for the host inner loop |
| `just migrate` | Apply all migrations up to head |
| `just migrate-new "msg"` | Autogenerate a migration from model changes |
| `just test-backend` | Run the test suite with coverage |
| `just lint-backend` | Ruff check, format check, and mypy |
| `just fmt-backend` | Format and autofix |

