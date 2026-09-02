# Runbook: deploy

Docker Context deploy of the whole stack to the single VPS. The Compose CLI runs in CI (or an operator checkout); the engine runs on the VPS, reached over a Docker Context (`ssh://deploy@<ip>`). All config and secret content is sourced CLI-side and transmitted to the daemon, so the box holds no `.env`, OAuth key, or rendered config. Driven by `scripts/deploy.sh`; run automatically by CD on merge to `main`, or manually.

## How deployment works

Deployment is a two-phase, two-machine process:

- **Build (CI runner):** CD (`cd.yml`) discovers first-party services from `docker-compose.yml`, builds each image with Buildx, and pushes two tags to GHCR: `:latest` (what the next deploy pulls) and `:sha-<SHA>` (immutable, for rollback).
- **Deploy (CI runner -> VPS):** CD registers a Docker Context (`ssh://deploy@<ip>`) so Compose CLI commands run on the runner but target the engine on the VPS. It sources all config and secrets CLI-side (committed `.env.prod` + rendered config files + GitHub secrets) and hands off to `scripts/deploy.sh`, which drives the full lifecycle over the context: pull, migrate, start, health-gate, sync ops scripts, record SHA.
- **The box is stateless:** no repo checkout, no `.env`, no secret files. Only Docker containers, named volumes (`pgdata`, `promdata`), `/opt/wren/.deployed-sha` (rollback key), and `/opt/wren/scripts/` (ops scripts) persist on the VPS.

## What a deploy does

CD registers the context, exports the config/secret env (committed `.env.prod` + files rendered in the runner + GitHub secrets), and runs `scripts/deploy.sh <server-ip>`, which:

1. **Preflight:** assert every required config/secret env var is set (fail fast).
2. **Pull:** `docker --context wren compose ... pull`.
3. **Migrations (pre-traffic):** start postgres, wait healthy, then `... run --rm backend alembic upgrade head`. Aborts the deploy on failure. See `migration.md`.
4. **Start:** `docker --context wren compose --profile tunnels up -d`.
5. **Health gate:** poll `docker --context wren compose ps` health across all services (~60s).
6. **Sync ops scripts:** `tar` `scripts/ops/` over SSH to `/opt/wren/scripts/` on the box (clean-replace: wipe + extract). The box holds no repo checkout, so host-side ops scripts (`list-users.sh`, `delete-user.sh`, etc.) are otherwise absent; this keeps them version-matched to the running deploy. Only runs after the gate passes.
7. **Record on success:** the ONE remaining `ssh` line writes the deployed SHA to `/opt/wren/.deployed-sha` (the rollback key). On a failed gate the script exits non-zero and CD owns the rollback (below); the script never re-deploys itself.

Host bootstrap (Docker install, `daemon.json`, prune cron, the deploy user and docker group, the Docker Context) is a one-time bring-up concern (`bring-up.md`), not part of a deploy. Not zero-downtime: there is a brief per-deploy gap while containers recreate, accepted at this scale (~5 users).

## Triggering a deploy

- **Automatic:** CD (`cd.yml`) builds/pushes `:latest` + `:sha-<sha>` images, then registers the context, exports the config/secret env, and runs `./scripts/deploy.sh <ip>` with `DEPLOY_SHA` set. A concurrency lock at the CD layer prevents a manual dispatch and a push-deploy racing onto the box.
- **Manual:** register the context and export the config/secret env first (see `bring-up.md` Phase E), then `DEPLOY_SHA=$(git rev-parse HEAD) just deploy <server-ip>`. Set `DEPLOY_SHA` to the SHA whose images CD pushed.
- **Preview only:** `just deploy-plan <server-ip>` (or `DRY_RUN=1 ./scripts/deploy.sh <ip>`) prints the compose/ssh plan without touching a server. The preflight still runs, so the required config/secret env vars must be set (even dummy values) to reach the plan.

## Cloudflare tunnel ingress

The tunnel is the only ingress (zero inbound ports). CI renders `deployments/cloudflare/config.yml` via `envsubst` (substituting `CF_TUNNEL_ID` + the four `CF_*_HOSTNAME` vars from `.env.prod`) into the `WREN_CLOUDFLARED_INGRESS` env var, and `docker-compose.tunnel.yml` delivers it as an environment-sourced Compose `config` mounted at `/etc/cloudflared/config.yml` (no file on the box); `cloudflared` runs against it under the `tunnels` profile. Four ingress rules: `usewren.com` → frontend, `api.usewren.com` → backend `:8000`, `mcp.usewren.com` → mcp `:9000`, `docs.usewren.com` → docs `:80`. The MCP host publicly exposes **only** the PRM discovery document and the `/mcp` transport; `/metrics`, `/healthz` and `/readyz` are refused at ingress (scraped in-network only), and the docs host refuses `/healthz` at the edge. Preview the rendered config with `just render-tunnel`.

## Secrets and config

**Committed non-secret config:** `.env.prod` (sourced in the runner). Its keys and meanings mirror `.env.example`'s production values.

**How app config reaches the containers:** the deploy layers a deploy-only overlay (`docker-compose.deploy.yml`) that loads `.env.prod` into backend/mcp via `env_file` (read CLI-side and transmitted over the context: no file on the box) and passes `SESSION_JWT_SECRET`/`INTERNAL_API_TOKEN` through from the runner env. The base file's `env_file: .env` stays the local-dev source; the overlay is never used locally, so a stray dev `.env` cannot leak into a deploy.

**GitHub repo secrets** (CI/CD only): `DEPLOY_SSH_KEY`, `DEPLOY_SERVER_IP`, `POSTGRES_PASSWORD`, `SESSION_JWT_SECRET`, `INTERNAL_API_TOKEN`, `DISCORD_WEBHOOK_URL`, `WREN_OAUTH_PRIVATE_KEY` (RAW PEM), `WREN_CLOUDFLARED_CREDENTIALS` (RAW `credentials.json`, not base64), plus the built-in `GITHUB_TOKEN` (GHCR). CD exports these into the deploy step's environment; Compose transmits them to the daemon as environment-sourced `secrets:`. Nothing is written to the box. (`cert.pem` is a bring-up-only tunnel-management artifact.)

## Rollback (CI-owned)

On a failed health gate the deploy exits non-zero and CD runs a conditional rollback step: it reads the previous `/opt/wren/.deployed-sha` (via `./scripts/deploy.sh read-deployed-sha <ip>`), checks that SHA out in the runner, re-exports the env from that checkout, and re-runs the deploy once with `WREN_IMAGE_TAG=sha-<prev>`. Because the checkout moves to the previous SHA, this restores the previous **images AND config**. If no previous `.deployed-sha` exists (the first deploy), `read-deployed-sha` refuses and the workflow fails: there is nothing to roll back to.

**Forward-only migrations (caveat):** a release carrying a schema migration can block re-deploying the previous image against the already-migrated DB. Migrations are forward-only; down-migrations are manual and out of scope. See `migration.md` and `rollback.md`.

## Host-side ops scripts (`scripts/ops/`)

The box holds no repo checkout, but each successful deploy syncs `scripts/ops/` to `/opt/wren/scripts/` on the box (deploy step 6). This keeps ops scripts version-matched to the running deploy: the scripts always reflect the current schema and container names.

### What goes in `scripts/ops/`

Host-side scripts that run **on the VPS** and operate against the running stack directly (e.g. `docker exec` into the postgres container). They are not Docker-Context scripts and are not run from CI; an operator SSH's in and runs them.

Scripts that run **CLI-side** (like `deploy.sh`, which drives the Docker Context from a checkout) stay in `scripts/` and never reach the box.

### Usage

```sh
ssh deploy@<vps-ip>

# List recent users:
/opt/wren/scripts/list-users.sh 20

# Delete a user (interactive, three confirmation gates):
/opt/wren/scripts/delete-user.sh <username>
```

### Adding a new ops script

1. Put it in `scripts/ops/` and make it executable (`chmod +x`).
2. It is picked up automatically by the next deploy's sync (clean-replace: the directory is wiped and re-extracted, so removed scripts don't linger).
3. Add a test in `scripts/tests/` (the `run_all.sh` harness auto-discovers `*_test.sh`).

## First-time bring-up

One-time VPS bring-up (UFW + SSH hardening, non-root deploy user, Docker install + `daemon.json` + prune cron, creating the tunnel + routing DNS, registering the Docker Context, generating the OAuth key and setting the CD repo secrets) is a separate, human-run procedure: see `bring-up.md`. This runbook covers the repeatable deploy that runs afterward.
