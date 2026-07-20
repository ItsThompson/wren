# Development

This guide covers local setup, the per-area development loops, code generation,
and the environment-variable groups. It documents the current implemented state.
Commands run through `just`; run `just --list` for the full recipe set.

## Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| uv | Python package and venv manager (backend, MCP) | https://docs.astral.sh/uv/ |
| just | Command runner for all recipes | https://github.com/casey/just |
| Node.js | Frontend toolchain (version 22) | https://nodejs.org/ |
| Docker | Postgres, the full stack, and E2E | https://docs.docker.com/get-docker/ |

## Environment setup

Copy the annotated example file to a working `.env`:

```sh
cp .env.example .env
```

`.env.example` is the canonical, sectioned list of every variable, grouped by
consumer. Read it for the meaning and default of each key. This guide names the
groups; it does not restate each variable.

The host inner-loop recipes read `.env` from the repo root. `wren.core.settings`
anchors the file to the repo root, so `just dev-api` loads it regardless of the
recipe working directory.

## Development workflows

### Backend host inner loop

```sh
just setup             # install backend dependencies (uv sync)
just dev-infra         # start local Postgres in Docker
just dev-api           # external app on http://127.0.0.1:8000, autoreload
just dev-api-internal  # internal app on http://127.0.0.1:8001, autoreload
just migrate           # apply migrations up to head
```

Run the two apps in separate terminals. The external app serves the SPA and the
OAuth AS; the internal app serves the routes the MCP server calls.

### Frontend

```sh
just setup-frontend    # install frontend dependencies (npm install)
just dev-web           # SPA against the real backend
just dev-mock          # SPA against the zero-backend MSW mock harness
```

Use `just dev-mock` to develop the SPA with no backend running. It starts the
MSW mock worker (`VITE_MOCK_API=true`).

### MCP server

```sh
just setup-mcp         # install MCP dependencies (uv sync)
just dev-mcp           # MCP Resource Server on :9000, autoreload
```

The MCP Inspector attaches to `:9000`. The RS validates agent tokens against the
external app's JWKS, so run the external app (or the full stack) alongside it.

### Full stack

```sh
just up-dev            # full stack in Docker: bind mounts, reload, relaxed cookies
just down-dev          # stop the dev stack (keeps named volumes)
just reset             # stop the dev stack and drop its volumes
```

`just up-dev` builds and runs every service locally as a self-contained stack.

### End-to-end

```sh
just setup-e2e         # install the Playwright runner and the chromium browser (once)
just e2e-up            # build and boot the e2e stack, run pre-traffic migrations
just test-e2e          # run the Playwright spine and smoke
just e2e-down          # tear down the e2e stack and drop its volumes
```

See `docs/testing.md` for the test layers and `docs/ci-cd.md` for how CI runs
E2E.

## Code generation

The frontend REST client is generated, never hand-written.

```sh
just codegen           # export the external OpenAPI document, then run openapi-typescript
```

`just codegen` writes `frontend/openapi.json` from the live external app, then
regenerates `frontend/src/api/schema.d.ts`. Run it after any change to the
external REST surface. CI drift-gates it: the `codegen-drift` job fails on a stale
committed client.

## Skill sync

The agent authoring guidance lives at `skill/SKILL.md`. The backend serves a
bundled copy of it.

```sh
just sync-skill        # re-sync the backend-bundled copy with the root copy
```

Run `just sync-skill` after editing `skill/SKILL.md`. A drift test
(`backend/tests/test_skill_content.py`) fails if the two copies diverge.

## Workspace layout

The monorepo holds:

- A Python **backend** package: a shared core kit plus the external and internal
  apps over one service layer.
- A Python **MCP server** package: the agent front door, which shares no code
  with the backend.
- A React **frontend** SPA.
- A `contract/` project: the dev/test-only cross-package tests, the only place
  both Python packages import together.
- `shared/theme/`: the design tokens the SPA and the docs site share.
- Ops assets: Docker Compose files, `scripts/`, and `deployments/`.

See `docs/architecture.md` for the conceptual model.

## Environment variables

`.env.example` is the canonical annotated list. The variables group by consumer:

| Group | Purpose |
|-------|---------|
| Shared (both apps) | Environment, log level, host bind, trusted proxies, pinned public URLs |
| Backend container entrypoint | Ports and reload flag read by `backend/docker/serve.sh` |
| Database | The async SQLAlchemy connection URL |
| Internal trust boundary | `INTERNAL_API_TOKEN` and the backend internal URL the MCP server calls |
| MCP Resource Server | The RS port and its trusted proxies |
| Human sessions | The HS256 session secret and the cookie domain |
| OAuth 2.1 AS | The signing key path and id, token TTLs, and the stale-client reaper knobs |
| CORS | The single browser origin allowed to send credentialed XHRs |
| Infrastructure / Compose | GHCR owner, image tag, app-net subnet, Postgres bootstrap credentials |
| Discord | The webhook shared by Alertmanager and the signup notifier |
| Cloudflare tunnel | The tunnel id and the four public hostnames (deploy-time) |

### OAuth stale-client reaper knobs

The external app runs a background reaper that reaps stale
open-registration OAuth clients. Two variables tune it:

| Variable | Default | Meaning |
|----------|---------|---------|
| `OAUTH_CLIENT_CLEANUP_INTERVAL_SECONDS` | `21600` (6 hours) | How often the sweep runs. A non-positive value disables the task. |
| `OAUTH_STALE_CLIENT_MAX_AGE_SECONDS` | `2592000` (30 days) | The registration-age threshold for a reap. Independent of the refresh-token TTL. |

The reaper is an in-process asyncio task, started and stopped by the external app
lifespan. See `docs/architecture.md` for its place in the system and
`backend/src/wren/oauth/cleanup.py` for the implementation.

## Cross-references

- Testing layers and commands: `docs/testing.md`.
- CI jobs and the deploy pipeline: `docs/ci-cd.md`.
- System topology and trust zones: `docs/architecture.md`.
- Per-package guides: `backend/README.md`, `mcp/README.md`, `frontend/README.md`.
