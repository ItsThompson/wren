# Backend

## Commands

All recipes run from the repo root and change into `backend/`.

| Command | Purpose |
|---------|---------|
| `just setup` | Install dependencies from `uv.lock` |
| `just dev-api` | Run the external app (`:8000`) with autoreload |
| `just dev-api-internal` | Run the internal app (`:8001`) with autoreload |
| `just test-backend` | Run the test suite with coverage |
| `just lint-backend` | Ruff check, format check, and mypy |
| `just fmt-backend` | Format and autofix |
| `just migrate` | Apply migrations up to head |
| `just migrate-new "msg"` | Autogenerate a migration from model changes |
| `just codegen` | Regenerate the frontend client after any external REST change (CI drift-gates it) |

## Boundaries and identity

- Two apps, one factory. When you add a route, decide which app or apps mount it and add a matching `route_registry.py` entry per app, or the coverage test fails deny.
- Never trust `X-User-ID` on the external app. It is stripped app-wide. Resolve human identity only through `require_user`. The internal app trusts `X-User-ID` only behind a valid `INTERNAL_API_TOKEN`. Never add the strip middleware there and never host-publish or tunnel-route `:8001`.
- Read `app.state` seams through `core/state.py`, never by raw `getattr`. The external app sets `session_verifier`; the internal app sets `internal_api_token`. Do not assume both seams exist on both apps.
- Keep `app_factory.py` wiring-only. Do not import a domain package into it.
- 404 over 403 everywhere. Do not convert a private-resource 404 into a 403.

## Error contract and logging

- Raise `WrenError` subclasses from the service layer. Never build problem+json by hand. One exception handler owns the wire shape. See `docs/api.md`.
- Two error contracts on the OAuth router. Agent protocol endpoints raise `OAuthError` (RFC 6749 JSON). SPA-facing endpoints raise `WrenError` (problem+json). Do not mix them.

## Cross-package duplication

- The backend and MCP packages share no code. `logging.py`, `metrics.py`, and `health.py` are hand-duplicated. The internal-boundary header constants (`USER_ID_HEADER`, `INTERNAL_TOKEN_HEADER`) are re-declared in `mcp/config.py` and guarded by `contract/tests/test_header_constants.py`. Change both copies together. See `docs/infra-duplication.md`.

## Rules

- JSON casing matches the shared schema. The frontend client is generated from the external OpenAPI document. Run `just codegen` after a contract change.
- Follow the layering convention: config, models, schemas, repository, service, router, wiring.
- Keep dependency direction one-way. A domain receives narrow injected callables, never a foreign repository.
