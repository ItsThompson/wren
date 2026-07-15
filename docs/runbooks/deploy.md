# Runbook: deploy

Push-based SSH deploy of the whole stack to the single VPS. Driven by
`scripts/deploy.sh`; run automatically by CD on merge to `main`, or manually.

## What a deploy does

`scripts/deploy.sh <server-ip> [ssh-user]` orchestrates the VPS over SSH and runs
the section-11 phase sequence:

1. **Preflight:** assert the tunnel credential files exist locally.
2. **SSH probe** (and detect whether the remote user needs `sudo`).
3. **Dependency install:** Docker, git, `gettext-base` (envsubst), `jq`, each
   `command -v`-guarded (idempotent).
4. **Docker daemon config:** install `deployments/docker/daemon.json` (log
   rotation); restart Docker only if the file changed.
5. **Daily prune cron:** `docker system prune -af --filter until=72h`.
6. **Repo sync:** `git fetch && git reset --hard origin/main` (clone on first run).
7. **Copy tunnel credentials** (`credentials.json` + `cert.pem`), `chmod 600`.
8. **Assert secrets exist:** `/opt/wren/.env` and the OAuth key file. The script
   **never creates** these: they are placed once at bring-up.
9. **Render tunnel config** (`envsubst`) and `docker compose pull`.
10. **Migrations (pre-traffic):** see `migration.md`. Aborts the deploy on failure.
11. **Start:** `docker compose --profile tunnels up -d`.
12. **Health gate:** poll `docker compose ps` health across all services (~60s).
13. **Rollback on failure:** see `rollback.md`.
14. **Cleanup** (success only): prune build cache/images, vacuum journald, and
    record the deployed SHA to `/opt/wren/.deployed-sha`.

Not zero-downtime: there is a brief per-deploy gap while containers recreate,
accepted at this scale (~5 users).

## Triggering a deploy

- **Automatic:** CD (`cd.yml`, Ticket 30) builds/pushes `:latest` + `:sha-<sha>`
  images, then runs `./scripts/deploy.sh <ip>` with `DEPLOY_SHA` set. A
  concurrency lock at the CD layer prevents a manual dispatch and a push-deploy
  racing onto the box.
- **Manual:** `DEPLOY_SHA=$(git rev-parse HEAD) just deploy <server-ip>` (or call
  the script directly). Set `DEPLOY_SHA` to the SHA whose images CD pushed.
- **Preview only:** `just deploy-plan <server-ip>` (or `DRY_RUN=1
  ./scripts/deploy.sh <ip>`) prints every ssh/scp the deploy would run, without
  touching a server.

## Cloudflare tunnel ingress

The tunnel is the only ingress (zero inbound ports). `deploy.sh` renders
`deployments/cloudflare/config.yml` to `config.rendered.yml` via `envsubst`
(substituting `CF_TUNNEL_ID` + the three `CF_*_HOSTNAME` vars from `.env`), and
`docker-compose.tunnel.yml` runs `cloudflared` against it under the `tunnels`
profile. Three ingress rules: `usewren.com` → frontend, `api.usewren.com` →
backend `:8000`, `mcp.usewren.com` → mcp `:9000`. The MCP host publicly exposes
**only** the PRM discovery document and the `/mcp` transport; `/metrics`,
`/healthz` and `/readyz` are refused at ingress (scraped over `monitoring-net`
only). Preview the rendered config with `just render-tunnel`.

## Secrets

**GitHub repo secrets** (CI/CD only): `DEPLOY_SSH_KEY`, `DEPLOY_SERVER_IP`,
`CF_TUNNEL_CREDENTIALS` (base64), `CF_CERT_PEM` (base64), `GITHUB_TOKEN` (GHCR).
CD decodes `CF_TUNNEL_CREDENTIALS`/`CF_CERT_PEM` into
`deployments/cloudflare/{credentials.json,cert.pem}` before invoking the script;
the script asserts they exist (preflight) and copies them to the box.

**VPS `/opt/wren/.env`** (never in CI, `chmod 600`) and the **OAuth private-key
PEM** are provisioned once at bring-up and are **never created by the deploy
script**. All variables and their meanings live in `.env.example` (the canonical
config source); the deploy-time Cloudflare variables are in its Cloudflare tunnel
section.

## First-time bring-up

One-time VPS bring-up (UFW + SSH hardening, non-root deploy user, creating
`/opt/wren/.env` and the OAuth key, creating the tunnel + routing DNS, placing
tunnel credentials, and setting the CD repo secrets) is a separate, human-run
procedure: see `bring-up.md`. This runbook covers the repeatable deploy that runs
afterward.
