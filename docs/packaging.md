# Packaging

This guide describes how the Python packages are organized into a uv workspace,
how they build into images, and where the backend/MCP boundary sits. It documents
the current implemented state.

## uv workspace

The repository is a single uv workspace. One root `pyproject.toml` declares the
members and one root `uv.lock` resolves them together, so every shared library
(for example `pydantic`) has exactly one version across all members.

Members:

- `backend/` (`wren`): the modular-monolith backend (external `:8000` + internal `:8001`).
- `mcp/` (`wren-mcp`): the OAuth 2.1 Resource Server (`:9000`).
- `contract/` (`wren-contract-tests`): the dev/test-only cross-package harness.
- `shared/wren-common/` (`wren-common`): shared infrastructure both deployables consume.

The root is a virtual workspace: it defines the workspace but builds no artifact.
Each consumer references its workspace dependencies through `[tool.uv.sources]`
with `{ workspace = true }`, never a published version.

### Sync model

- **Local dev and CI** use one shared root `.venv`:

  ```sh
  uv sync --all-packages    # every member + dev tools in one venv
  ```

  With the shared venv, `cd backend && uv run pytest` (and the same for `mcp`,
  `contract`, `shared/wren-common`) resolves against it. CI syncs once with
  `uv sync --all-packages --frozen`, then runs each member's tools with
  `uv run --no-sync`.

- **Images** install one member's locked dependency set (see below).

There are no per-package lockfiles; the single root `uv.lock` is the source of
truth for every `uv` step.

## shared/wren-common

`wren-common` is the single definition of the infrastructure both deployables
share: structured logging (`wren_common.logging`), Prometheus HTTP metrics
(`wren_common.metrics`), and the liveness/readiness router (`wren_common.health`).

It carries no backend or MCP dependency. The per-app parts are injected, not
imported:

- `metrics.instrument(app, custom_registry)` concatenates the caller's registry
  onto `/metrics` (the backend passes `WREN_REGISTRY`; the MCP passes
  `TOOL_METRICS_REGISTRY`).
- `health.create_health_router(readiness_checks)` aggregates the caller's checks
  (the backend passes its Postgres check; the MCP passes its JWKS check).

This keeps the shared package free of either deployable while still single-sourcing
the infra, so there is no hand-sync drift to guard.

## Per-member images

The backend and MCP images build from the **repo-root** build context (the
pattern `frontend` and `docs-site` already use to reach `shared/`), selected in
`docker-compose.yml` with `context: .` and a member `dockerfile:`. The single
repo-root `.dockerignore` keeps every context lean and keeps secrets (`.env*`) and
rebuilt artifacts out.

uv installs every workspace member into one shared environment, so there is no
`uv sync` that installs a single member in isolation. To keep each image lean and
preserve the backend/MCP firewall, each Dockerfile:

1. Copies the workspace metadata (root + every member's `pyproject.toml` + the
   lockfile) so uv can resolve the workspace graph.
2. Exports the member's locked third-party set with
   `uv export --frozen --no-emit-workspace --package <member>` and installs it.
3. Editable-installs only that member plus `wren-common`.

The runtime stage copies only the venv, the member, and `shared/`. The backend
image therefore carries no MCP code (no `mcp` SDK, no `wren_mcp`) and the MCP
image carries no backend code (no `asyncpg`, no `alembic`, no `wren`).

## The backend/MCP boundary

The backend and MCP share no **domain** code, and neither imports the other:

- **Shared infrastructure** lives in `wren-common` and is single-sourced.
- **Shared wire truths** stay mirrored, not shared: the internal-boundary header
  constants, the OAuth scope constants, and the Pydantic schema types in
  `wren_mcp`. The Group-A schema types (enums, authoring inputs, patch ops, read
  projections) are GENERATED from the internal app's OpenAPI document by `just
  codegen-mcp` into `mcp/src/wren_mcp/_schemas_generated.py`, so they cannot drift;
  the header/scope constants and the lean write results stay hand-mirrored. The
  `contract/` project asserts the generated module is exactly Group A and that the
  hand-authored parts stay equal (see `docs/ci-cd.md` and `docs/testing.md`).

The OpenAPI-to-Pydantic generator (`datamodel-code-generator`) is an MCP **dev**
dependency, resolved through the root lockfile. `just codegen-mcp` exports the
internal app's OpenAPI to the committed `mcp/internal-openapi.json`, restricts a
copy to the Group-A component set, and runs the generator; CI regenerates and
`git diff --exit-code`s the committed artifacts, mirroring the frontend
`codegen-drift` job. The MCP image build (`uv sync ... --package wren-mcp`) exports
with `--no-dev`, so the generator never ships in the runtime image, which only
copies the committed generated file and never runs codegen or imports `wren`.

Collapsing the wire mirror into `wren-common` would drag the whole domain schema
into the MCP image and re-couple the frozen agent contract to backend refactors,
so the mirror is deliberate and contract-tested rather than shared.
