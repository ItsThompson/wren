# Wren

A multi-user learning-roadmap platform. Humans use it through a web app; AI
agents use it through an MCP server. Both go through the same backend, so the
rules for creating, publishing, and tracking roadmaps are defined in exactly one
place.

## Architecture

Wren is a monorepo with a Python modular-monolith backend, a separate MCP server,
a React frontend, and the deployment assets. The backend is one codebase that
serves two apps over a shared service layer:

- **External app (`:8000`)** is internet-facing: it authenticates humans by
  session cookie and hosts the public REST API and OAuth authorization server.
- **Internal app (`:8001`)** trusts an injected identity header and is reachable
  only from inside the compute network (the MCP server calls it). It is never
  exposed to the internet.

Both apps are assembled from one factory (`wren.core.app_factory.create_app`) and
differ only by injected settings.

## Layout

- `backend/`: Python backend (uv-managed); `src/wren/core` shared kit,
  `src/wren/api` external app, `src/wren/api_internal` internal app.
- `frontend/`: React SPA.
- `deployments/`, `scripts/`: operational assets.

## Backend development

Requires [uv](https://docs.astral.sh/uv/) and [just](https://github.com/casey/just).

```sh
just setup             # install backend dependencies
just dev-api           # boot the external app on http://127.0.0.1:8000
just dev-api-internal  # boot the internal app on http://127.0.0.1:8001
just test-backend      # run tests with coverage
just lint-backend      # ruff + mypy
```

Health and metrics are available on both apps: `GET /healthz` (liveness),
`GET /readyz` (readiness), and `GET /metrics` (Prometheus).

Configuration comes from environment variables; see `.env.example` for the
canonical list.
