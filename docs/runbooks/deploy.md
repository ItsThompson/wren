# Runbook: deploy

Docker Context deploy of the whole stack to the single VPS. The Compose CLI runs in CI (or an operator checkout); the engine runs on the VPS, reached over a Docker Context (`ssh://deploy@<ip>`). All config and secret content is sourced CLI-side and transmitted to the daemon, so the box holds no `.env`, OAuth key, or rendered config. Driven by `scripts/deploy.sh`; run automatically by CD on merge to `main`, or manually.

## What a deploy does

CD registers the context, exports the config/secret env (committed `.env.prod` + files rendered in the runner + GitHub secrets), and runs `scripts/deploy.sh <server-ip>`, which:

1. **Preflight:** assert every required config/secret env var is set (fail fast).
2. **Pull:** `docker --context wren compose ... pull`.
3. **Migrations (pre-traffic):** start postgres, wait healthy, then `... run --rm backend alembic upgrade head`. Aborts the deploy on failure. See `migration.md`.
4. **Start:** `docker --context wren compose --profile tunnels up -d`.
5. **Health gate:** poll `docker --context wren compose ps` health across all services (~60s).
6. **Record on success:** the ONE remaining `ssh` line writes the deployed SHA to `/opt/wren/.deployed-sha` (the rollback key). On a failed gate the script exits non-zero and CD owns the rollback (below); the script never re-deploys itself.

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

**GitHub repo secrets** (CI/CD only): `DEPLOY_SSH_KEY`, `DEPLOY_SERVER_IP`, `POSTGRES_PASSWORD`, `SESSION_JWT_SECRET`, `INTERNAL_API_TOKEN`, `DISCORD_WEBHOOK_URL`, `WREN_OAUTH_PRIVATE_KEY` (RAW PEM), `WREN_CLOUDFLARED_CREDENTIALS` (RAW `credentials.json`, not base64), plus the built-in `GITHUB_TOKEN` (GHCR). CD exports these into the deploy step's environment; Compose transmits them to the daemon as environment-sourced `secrets:`. Nothing is written to the box. The old `CF_TUNNEL_CREDENTIALS` and `CF_CERT_PEM` secrets are retired (`cert.pem` is a bring-up-only tunnel-management artifact).

## Rollback (CI-owned)

On a failed health gate the deploy exits non-zero and CD runs a conditional rollback step: it reads the previous `/opt/wren/.deployed-sha` (via `./scripts/deploy.sh read-deployed-sha <ip>`), checks that SHA out in the runner, re-exports the env from that checkout, and re-runs the deploy once with `WREN_IMAGE_TAG=sha-<prev>`. Because the checkout moves to the previous SHA, this restores the previous **images AND config**. If no previous `.deployed-sha` exists (the first deploy), `read-deployed-sha` refuses and the workflow fails: there is nothing to roll back to.

**Forward-only migrations (caveat):** a release carrying a schema migration can block re-deploying the previous image against the already-migrated DB. Migrations are forward-only; down-migrations are manual and out of scope. See `migration.md` and `rollback.md`.

**First-deploy caveat:** on the very first rearchitected deploy the previous `.deployed-sha` (if the box was deployed under the old model) points at pre-rearchitecture code whose `deploy.sh` is incompatible with the context model; that rollback aborts cleanly at the old credential preflight. Clear the stale key at cutover (see `bring-up.md`) and treat the first deploy as fix-forward-only.

## First-time bring-up

One-time VPS bring-up (UFW + SSH hardening, non-root deploy user, Docker install + `daemon.json` + prune cron, creating the tunnel + routing DNS, registering the Docker Context, generating the OAuth key and setting the CD repo secrets) is a separate, human-run procedure: see `bring-up.md`. This runbook covers the repeatable deploy that runs afterward.
