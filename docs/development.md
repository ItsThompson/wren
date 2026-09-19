# Development

This guide separates the fast development inner loop from production-mode system E2E. Commands run through `just`; run `just --list` for the full recipe set.

## Prerequisites

| Tool | Purpose | Install |
|---|---|---|
| uv | Python package and virtual-environment manager | https://docs.astral.sh/uv/ |
| just | Repository command runner | https://github.com/casey/just |
| Node.js 22 | Frontend and E2E toolchain | https://nodejs.org/ |
| Docker | Postgres, development stack, and E2E topology | https://docs.docker.com/get-docker/ |
| mkcert | Isolated local E2E CA and certificate | https://github.com/FiloSottile/mkcert |

## Development inner loop

The inner loop favors fast reloads and direct local ports. It uses the existing development cookie and transport posture. It is not the production-parity E2E environment.

```sh
cp .env.example .env
just setup
just dev-infra
just dev-api           # external app on http://127.0.0.1:8000
just dev-api-internal  # internal app on http://127.0.0.1:8001
just migrate
just setup-frontend
just dev-web
```

Run the two backend apps in separate terminals. Use `just dev-mock` for frontend iteration without a backend. Use `just dev-mcp` for the MCP Resource Server on local port `9000`.

For the full development stack, run `just up-dev`, `just down-dev`, or `just reset`. This stack uses bind mounts, reload, and development cookie behavior. It is separate from E2E.

## Production-mode E2E

E2E verifies public HTTPS contracts through exactly these hosts:

- `https://app.wren.test` for the SPA, browser consent, and recorder routes.
- `https://api.wren.test` for REST and OAuth authorization-server routes.
- `https://mcp.wren.test` for protected-resource metadata and `/mcp` transport.

The topology contains ingress, frontend, one backend container with external and internal listeners, MCP, disposable Postgres, and recorder. Only ingress publishes host port `443`. The backend listeners are not separate containers. E2E runs with `ENVIRONMENT=production`, Secure `.wren.test` cookies, trusted forwarded HTTPS headers, and internal HTTP only after ingress or MCP routing has selected the service.

The E2E environment never uses the production database, production keys, production hostnames, production Sentry service, or Cloudflare tunnel. It uses synthetic test-only secrets, a disposable database, an isolated mkcert `CAROOT`, and generated OAuth RSA signing material. Generated files live under ignored E2E paths and are removed by teardown or trust reset.

### Setup and command sequence

```sh
just setup-e2e          # Install npm and Chromium dependencies, hosts, CA, and OAuth key
just test-e2e-unit      # Run E2E Vitest unit and harness tests without Compose
just e2e-up             # Run migrations, start the focused stack, and wait for HTTPS readiness
just test-e2e           # Run typecheck, lint, Vitest, and Playwright
just e2e-logs           # Show six-service logs
just e2e-down           # Stop the stack and remove disposable volumes and generated OAuth material
just reset-e2e-trust    # Remove only Wren-managed hosts and isolated certificate material
```

`just setup-e2e` supports macOS contributor workstations and Ubuntu CI hosts. It maps `app.wren.test`, `api.wren.test`, and `mcp.wren.test` to local ingress, issues a certificate for all three names, installs or verifies OS trust, validates Node trust through `NODE_EXTRA_CA_CERTS`, and creates the generated OAuth signing key. It is safe to run again. Host reset preserves unrelated entries and certificate authorities.

`just e2e-up` starts Postgres, runs the migration before application traffic, builds only the focused topology, and waits for app root, API authorization-server metadata, MCP PRM and JWKS health, and recorder readiness. It fails closed on any check. Use `just test-e2e-system` for only the Playwright run against an already-ready stack. Use `just e2e-capture-artifacts` before teardown to create the safe failure bundle.

Always clean up with `just e2e-down`. Run `just reset-e2e-trust` when the E2E hosts or CA are no longer needed. Teardown is safe after interruption and removes containers, networks, Postgres and recorder volumes, control tokens, and generated OAuth signing material.

## Code generation

The frontend REST client is generated, never hand-written.

```sh
just codegen           # export the external OpenAPI document, then run openapi-typescript
```

`just codegen` writes `frontend/openapi.json` from the live external app, then regenerates `frontend/src/api/schema.d.ts`. Run it after any change to the external REST surface. CI drift-gates it: the `codegen-drift` job fails on a stale committed client.

The MCP Group-A schemas are generated the same way, from the internal app.

```sh
just codegen-mcp       # export the internal OpenAPI, restrict to Group A, run datamodel-codegen
```

`just codegen-mcp` writes `mcp/internal-openapi.json` from the live internal app, restricts a copy to the Group-A component set (dropping the authoring input's `published_visibility` and renaming `RoadmapInput` to `RoadmapDraftInput`), then regenerates `mcp/src/wren_mcp/_schemas_generated.py`. The generator is a dev-only dependency; run it after any change to a Group-A schema on the internal surface. CI drift-gates it: the `mcp-codegen-drift` job fails on a stale committed artifact or module.

## Skill sync

The agent authoring guidance lives at `skill/SKILL.md`. The backend serves a bundled copy of it.

```sh
just sync-skill        # re-sync the backend-bundled copy with the root copy
```

Run `just sync-skill` after editing `skill/SKILL.md`. A drift test (`backend/tests/`) fails if the two copies diverge.

## Workspace layout

The monorepo holds:

- A Python **backend** package: a shared core kit plus the external and internal apps over one service layer.
- A Python **MCP server** package: the agent front door, which shares no domain code with the backend (shared infra comes from `wren-common`).
- A React **frontend** SPA.
- A `contract/` project: the dev/test-only cross-package tests, the only place both Python packages import together.
- `shared/wren-common/`: the shared backend/MCP infrastructure (logging, metrics, health).
- `shared/theme/`: the design tokens the SPA and the docs site share.
- Ops assets: Docker Compose files, `scripts/`, and `deployments/`.

The four Python packages form a uv workspace with a single root `uv.lock`. See `docs/packaging.md` for the workspace and image-build model, and `docs/architecture.md` for the conceptual model.

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

The external app runs a background reaper that reaps stale open-registration OAuth clients. Two variables tune it:

| Variable | Default | Meaning |
|----------|---------|---------|
| `OAUTH_CLIENT_CLEANUP_INTERVAL_SECONDS` | `21600` (6 hours) | How often the sweep runs. A non-positive value disables the task. |
| `OAUTH_STALE_CLIENT_MAX_AGE_SECONDS` | `2592000` (30 days) | The registration-age threshold for a reap. Independent of the refresh-token TTL. |

The reaper is an in-process asyncio task, started and stopped by the external app lifespan. See `docs/architecture.md` for its place in the system and `backend/src/wren/oauth/` for the implementation.

## Cross-references

- Testing layers and commands: `docs/testing.md`.
- CI jobs and the deploy pipeline: `docs/ci-cd.md`.
- System topology and trust zones: `docs/architecture.md`.
- Per-package guides: `backend/README.md`, `mcp/README.md`, `frontend/README.md`.
