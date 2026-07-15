# Runbook: one-time production bring-up

The **one-time** procedure that stands up the single production VPS and does the
first live release (spec section 11 §7.1 bring-up, §4.4 hardening, §4.1 tunnel,
§8.3 secrets). Everything here is done **once, by hand, by the operator**, because
it depends on external infrastructure a human must supply. The repeatable deploy
that runs afterward is `deploy.md`; this runbook never has to run again unless the
box is rebuilt.

> The deploy machinery (`scripts/deploy.sh`, `docker-compose.tunnel.yml`, CI/CD)
> is already delivered and tested. This runbook only provisions the infra it runs
> against and performs the first deploy.

## What the operator must supply (prerequisites)

None of these can be produced by the codebase or CI; the operator provides them:

1. **A VPS** (Ubuntu LTS) with root or sudo shell access, and its public IP.
2. **An SSH keypair** for the non-root `deploy` user (CD uses the private half).
3. **A Cloudflare account** with the `usewren.com` zone (DNS managed by Cloudflare)
   and `cloudflared` installed locally to create the tunnel.
4. **Production secret values:** a strong `POSTGRES_PASSWORD`, `SESSION_JWT_SECRET`
   (≥32 bytes), `INTERNAL_API_TOKEN`, a generated OAuth RSA private key, and a real
   Discord Incoming Webhook URL.
5. **Admin rights on the GitHub repo** to set the CD repo secrets.
6. **Authorization to run the live deploy.**

Never commit any of these; `.env`, the OAuth PEM, and the tunnel credentials are
all gitignored. `.env.example` is the canonical description of every variable.

---

## Phase A: provision and harden the VPS

Run as root (or a sudo admin) on the box.

### A1. UFW baseline

The stack publishes **no host ports** (everything is `expose:`-only) and the
tunnel is outbound-only, so the only inbound port ever needed is SSH.

```sh
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw enable
sudo ufw status verbose      # verify: default deny incoming, only OpenSSH allowed
```

### A2. SSH hardening (key-only, no root)

```sh
# /etc/ssh/sshd_config.d/10-wren.conf
PubkeyAuthentication yes
PasswordAuthentication no
PermitRootLogin no
```

```sh
sudo systemctl restart ssh   # keep your current session open until you verify a new key-only login works
```

### A3. Non-root deploy user

`scripts/deploy.sh` connects as `deploy` by default and uses `sudo` for the
system phases (dependency install, `/etc/docker/daemon.json`, the prune cron), so
`deploy` needs passwordless sudo and Docker-group membership.

```sh
sudo adduser --disabled-password --gecos "" deploy
sudo mkdir -p /home/deploy/.ssh
# paste the deploy public key:
echo "ssh-ed25519 AAAA... deploy@wren" | sudo tee /home/deploy/.ssh/authorized_keys
sudo chown -R deploy:deploy /home/deploy/.ssh && sudo chmod 700 /home/deploy/.ssh && sudo chmod 600 /home/deploy/.ssh/authorized_keys
echo "deploy ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/deploy && sudo chmod 440 /etc/sudoers.d/deploy
sudo usermod -aG docker deploy   # (docker is installed by deploy.sh phase 3; re-run if the group did not exist yet)
```

### A4. fail2ban + unattended-upgrades

```sh
sudo apt-get update
sudo apt-get install -y fail2ban unattended-upgrades
sudo systemctl enable --now fail2ban                 # default sshd jail
sudo dpkg-reconfigure -plow unattended-upgrades      # enable automatic security updates
```

Verify a fresh **key-only** login as `deploy@<ip>` works before closing your root
session.

---

## Phase B: create the Cloudflare tunnel and route DNS

Run locally where `cloudflared` is installed and logged into the Cloudflare
account that owns `usewren.com`.

```sh
cloudflared tunnel login                       # authorize the usewren.com zone; writes ~/.cloudflared/cert.pem
cloudflared tunnel create wren                 # prints the tunnel UUID and writes ~/.cloudflared/<UUID>.json
cloudflared tunnel route dns wren usewren.com
cloudflared tunnel route dns wren api.usewren.com
cloudflared tunnel route dns wren mcp.usewren.com
```

Record the **tunnel UUID** (→ `CF_TUNNEL_ID` in `.env`). The two credential files
are `~/.cloudflared/<UUID>.json` (→ `credentials.json`) and `~/.cloudflared/cert.pem`.
The tunnel dials out only; no inbound port is opened.

---

## Phase C: place secrets on the VPS

All files below live under `/opt/wren` and are `chmod 600`. `scripts/deploy.sh`
**asserts they exist and never creates them.**

### C1. `/opt/wren/.env`

Start from the canonical example and fill in production values:

```sh
sudo mkdir -p /opt/wren/secrets
sudo install -m 600 /dev/stdin /opt/wren/.env   # then paste the filled-in file, or scp it and chmod 600
```

Generate the random secrets (avoid URL-breaking characters in the DB password by
using hex):

```sh
openssl rand -base64 48   # SESSION_JWT_SECRET  (≥32 bytes)
openssl rand -base64 48   # INTERNAL_API_TOKEN
openssl rand -hex 32      # POSTGRES_PASSWORD   (hex → safe inside DATABASE_URL)
```

Production values that differ from the dev defaults in `.env.example`:

| Variable | Production value |
|----------|------------------|
| `ENVIRONMENT` | `production` |
| `PUBLIC_BASE_URL` | `https://api.usewren.com` |
| `APP_PUBLIC_URL` | `https://usewren.com` |
| `MCP_PUBLIC_URL` | `https://mcp.usewren.com` |
| `DATABASE_URL` | `postgresql+asyncpg://wren:<POSTGRES_PASSWORD>@postgres:5432/wren` |
| `POSTGRES_USER` / `POSTGRES_DB` | `wren` / `wren` |
| `POSTGRES_PASSWORD` | the generated hex value (must match `DATABASE_URL`) |
| `SESSION_JWT_SECRET` | generated (≥32 bytes) |
| `COOKIE_DOMAIN` | `.usewren.com` |
| `INTERNAL_API_TOKEN` | generated |
| `BACKEND_INTERNAL_URL` | `http://backend:8001` |
| `OAUTH_PRIVATE_KEY_PATH` | `/opt/wren/secrets/oauth_private.pem` |
| `OAUTH_KEY_ID` | e.g. `wren-oauth-1` |
| `CORS_ORIGIN` | `https://usewren.com` |
| `DISCORD_WEBHOOK_URL` | the real Discord Incoming Webhook |
| `CF_TUNNEL_ID` | the tunnel UUID from Phase B |
| `CF_APP_HOSTNAME` / `CF_API_HOSTNAME` / `CF_MCP_HOSTNAME` | `usewren.com` / `api.usewren.com` / `mcp.usewren.com` |
| `GHCR_OWNER` | your GitHub org/owner (lowercase) |
| `WREN_IMAGE_TAG` | `latest` |

`ENVIRONMENT=production` makes the app **fail fast** if `SESSION_JWT_SECRET` is
too short or the OAuth key is missing, and makes cookies `Secure`. All OAuth
issuer/metadata/redirect URLs are built from the pinned `*_PUBLIC_URL` values, not
the request host (the "Site-URL gotcha", section 08).

### C2. OAuth AS private key

```sh
sudo openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out /opt/wren/secrets/oauth_private.pem
sudo chmod 600 /opt/wren/secrets/oauth_private.pem
```

The path must equal `OAUTH_PRIVATE_KEY_PATH`. `docker-compose.tunnel.yml`
bind-mounts this PEM read-only into the backend container **at the same path**, so
the AS reads it where `.env` says it is. The MCP Resource Server verifies agent
tokens against the public JWKS the AS derives from this key.

### C3. Tunnel credentials

For the **first manual deploy** (Phase E), place the two files from Phase B into
your local checkout so `deploy.sh` copies them to the box (they are gitignored):

```sh
cp ~/.cloudflared/<UUID>.json  deployments/cloudflare/credentials.json
cp ~/.cloudflared/cert.pem     deployments/cloudflare/cert.pem
```

`deploy.sh` copies them to `/opt/wren/deployments/cloudflare/` and `chmod 600`s
them on the box. Thereafter CD supplies them from the repo secrets (Phase D).

---

## Phase D: set the GitHub repo secrets (for CD)

CD (`cd.yml`) needs these to build/push images and deploy. Set via the repo
**Settings → Secrets and variables → Actions**, or `gh`:

```sh
gh secret set DEPLOY_SERVER_IP      --body "<vps-ip>"
gh secret set DEPLOY_SSH_KEY        < ~/.ssh/deploy_ed25519          # the deploy user's PRIVATE key
gh secret set CF_TUNNEL_CREDENTIALS --body "$(base64 -w0 ~/.cloudflared/<UUID>.json)"
gh secret set CF_CERT_PEM           --body "$(base64 -w0 ~/.cloudflared/cert.pem)"
```

`GITHUB_TOKEN` is **not** set manually: it is the built-in Actions token. Ensure
Actions is allowed to write packages (repo/org **Settings → Actions → Workflow
permissions**), since `cd.yml` already requests `packages: write` and logs into
GHCR with it.

---

## Phase E: first live deploy

Preview the phase plan first (touches nothing):

```sh
DRY_RUN=1 ./scripts/deploy.sh <vps-ip> deploy
```

Then run the real deploy from your local checkout (credentials placed in C3,
`origin/main` at the commit whose `:latest` images GHCR holds):

```sh
DEPLOY_SHA=$(git rev-parse HEAD) ./scripts/deploy.sh <vps-ip> deploy
```

Alternatively, once the repo secrets (Phase D) are set, push to `main` and CD runs
the same script. The script: installs deps → syncs the repo → copies tunnel creds
→ **asserts `.env` + the OAuth key exist** → renders the tunnel and Alertmanager
configs → runs **migrations pre-traffic** (`alembic upgrade head`; aborts on
failure) → starts the stack under the `tunnels` profile → **health-gates every
service (~60s)** → rolls back on failure.

---

## Phase F: verify the release

### F1. All services healthy, zero open inbound ports

```sh
# on the box, as deploy:
cd /opt/wren
docker compose -f docker-compose.yml -f docker-compose.tunnel.yml --profile tunnels ps   # every service: healthy
sudo ufw status verbose        # only OpenSSH inbound; the tunnel is outbound-only
```

Alertmanager and cloudflared run under the `tunnels` profile; the health gate
covers them. A missing `DISCORD_WEBHOOK_URL` aborts the deploy at the render step
(release-gating), so a green deploy means the webhook rendered.

### F2. All three hostnames reachable through the tunnel

```sh
curl -sI https://usewren.com | head -1                                    # SPA (frontend)
curl -sI https://api.usewren.com/.well-known/oauth-authorization-server   # AS metadata (backend :8000)
curl -sI https://mcp.usewren.com/.well-known/oauth-protected-resource     # PRM (mcp :9000)
```

Confirm the **internal `:8001` boundary holds**: the internal app is
never tunnel-routed, and `mcp.usewren.com` serves **only** the PRM document and
the `/mcp` transport (any other path → 404 at ingress):

```sh
curl -sI https://mcp.usewren.com/metrics    # expect 404 (never tunnel-exposed)
```

### F3. Live end-to-end smoke

Exercise the full spine against production:

1. **Register** a human user in the SPA (`https://usewren.com`).
2. **Agent OAuth connect:** point MCP Inspector at `https://mcp.usewren.com`, walk
   the 401 → PRM → AS `/authorize` (SPA consent) → `/token` flow, and confirm the
   agent gets an `aud=mcp` access token.
3. **Author → publish:** create a roadmap draft via the agent write tools, validate,
   and publish it.
4. **Follow → study loop:** as the human, follow the published roadmap and call
   `get_next` to confirm the study loop returns a next node.

### F4. Synthetic alert reaches Discord

Prove the alert path end to end, then restore:

```sh
docker compose -f docker-compose.yml -f docker-compose.tunnel.yml --profile tunnels stop mcp
# wait ~1-2m → ServiceDown fires → 🚨 FIRING message in Discord
docker compose -f docker-compose.yml -f docker-compose.tunnel.yml --profile tunnels start mcp
# → ✅ RESOLVED message (send_resolved: true)
```

---

## Done

The box is provisioned, hardened, and serving. From here, every change ships
through the repeatable deploy in `deploy.md` (CD on merge to `main`, or a manual
`just deploy`). Post-P0 follow-ups (accepted risks) are off-host `pg_dump`
backups and Grafana dashboards; see section 11.
