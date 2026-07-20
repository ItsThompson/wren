# Wren

- Learning-roadmap platform for humans (web SPA) and AI agents (MCP server) over
  one backend.

## Repository structure

- `backend/`: Python modular-monolith backend (uv). A shared `core` kit, the external app (`api`), and the internal app (`api_internal`) over one service layer.
- `mcp/`: Python MCP server (uv). An OAuth 2.1 Resource Server that calls the backend internal app and imports no backend code.
- `frontend/`: React SPA (npm) that talks to the external app over a typed REST client.
- `contract/`: the dev/test-only cross-package test project (the only interpreter where both Python packages import together).
- `shared/theme/`: the design tokens the SPA and the docs site share.
- `docs-site/`: the customer-facing VitePress site. It is not internal documentation.
- Ops assets: `docker-compose*.yml`, `scripts/`, `deployments/`, `justfile`.


## Docker / Deployment (Hetzner CX33: 4 vCPU, 8 GB RAM, 80 GB NVMe)

- The compose memory ceilings sum to under 4 GiB. 8 GB clears that with the OS, the Docker daemon, and burst headroom. A 4 GB box risks OOM under the always-on Postgres and Prometheus tenants.
- First-party images are amd64-only. An ARM box needs a multi-arch `cd.yml` change.
- Run `set -a` before `source .env.prod` when sourced vars feed subprocesses (`envsubst`, `docker compose`). See `docs/runbooks/bring-up.md` Phase E.
- The box holds no `.env`, no OAuth PEM, and no rendered config. All config and secrets are sourced CLI-side and transmitted over the Docker Context.
- Every service needs explicit `deploy.resources.limits` so the memory envelope holds and the monitoring alerts work.
- **Warning:** migrations run pre-traffic (deploy step 3 of 6), never at app startup. A migration failure aborts before any container serves traffic. Keep every normal migration additive (expand/contract) so image-only rollback stays safe.
- **Warning:** Alertmanager exits on config load if the webhook is unrendered. It is gated behind the `tunnels` profile. A blank webhook fails the deploy health gate. CI renders it with `envsubst`.
- Publish no host ports (expose-only). The tunnel is outbound-only. The only inbound port is SSH.
- Safe deploy pattern: preview with `just deploy-plan` (`DRY_RUN=1`), then deploy. The gate polls every service for about 60 seconds. Rollback is CI-owned and restores the previous images and config, never the database.

## Commands

Run `just --list` for the full set. Common recipes:

- `just up-dev` / `just up` / `just down`: run the full stack.
- `just codegen`: regenerate the frontend REST client after an external REST change.
- `just sync-skill`: re-sync the backend-bundled `SKILL.md`.
- `just deploy-plan <ip>` / `just deploy <ip>`: preview and run a deploy.

Per-package commands live in `backend/.pi/AGENTS.md`, `mcp/.pi/AGENTS.md`, and `frontend/.pi/AGENTS.md`.
