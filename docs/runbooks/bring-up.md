# Runbook: one-time production bring-up

The **one-time** procedure that stands up the single production VPS and does the
first live release. Everything here is done **once, by hand, by the operator**, because
it depends on external infrastructure a human must supply. The repeatable deploy
that runs afterward is `deploy.md`; this runbook never has to run again unless the
box is rebuilt.

> The deploy machinery (`scripts/deploy.sh`, `docker-compose.tunnel.yml`, CI/CD)
> is already delivered and tested. This runbook provisions the infra it runs
> against, owns the one-time host bootstrap (Docker install, daemon config, prune
> cron) and Docker Context registration, and performs the first deploy. The
> repeatable deploy afterward (`deploy.md`) drives everything over a Docker
> Context: the box holds NO `.env`, OAuth key, or rendered config.

## What the operator must supply (prerequisites)

None of these can be produced by the codebase or CI; the operator provides them:

1. **A VPS** (Ubuntu LTS) with root or sudo shell access, and its public IP.
   **Chosen box: Hetzner CX33** (x86 shared vCPU, 4 vCPU / 8 GB RAM / 80 GB NVMe).
   Select a Hetzner Cloud EU location and the current Ubuntu LTS image at order.
   Why CX33:
   - **8 GB RAM** clears the ~3.75 GiB sum of compose memory ceilings with OS +
     Docker-daemon + burst headroom; a 4 GB box sits *below* that sum and risks
     OOM under the always-on Postgres + Prometheus tenants.
   - **x86_64** is a drop-in for the current amd64-only first-party images: no
     multi-arch `cd.yml` change needed (an ARM box would require one).
   - **4 vCores** match the 4.0 vCPU ceiling budget; ample at ~5 users since
     limits are ceilings, not reservations, and builds run in CI, not here.
   - **80 GB NVMe** is enough for the current named volumes plus short-term Docker
     image churn; the prune cron in Phase A5 keeps unused layers bounded.
2. **An SSH keypair** for the non-root `deploy` user (CD uses the private half).
3. **A Cloudflare account** with the `usewren.com` zone (DNS managed by Cloudflare)
   and `cloudflared` installed locally to create the tunnel.
4. **Production secret values:** a strong `POSTGRES_PASSWORD`, `SESSION_JWT_SECRET`
   (≥32 bytes), `INTERNAL_API_TOKEN`, a generated OAuth RSA private key, and a real
   Discord Incoming Webhook URL.
5. **Admin rights on the GitHub repo** to set the CD repo secrets.
6. **Authorization to run the live deploy.**

Never commit the secret values; they live only in GitHub Actions secrets (Phase
D). Non-secret production config is committed in `.env.prod`; the box holds no
`.env`, no OAuth PEM, and no tunnel credentials. `.env.example` describes the
dev/local variables; `.env.prod` is the committed production (non-secret) config.

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

`scripts/deploy.sh` connects as `deploy` over an SSH Docker Context, so `deploy`
needs Docker-group membership. Host bootstrap (Docker install,
`/etc/docker/daemon.json`, the prune cron) is a one-time step in Phase A5 below,
not part of the repeatable deploy, so passwordless sudo is only needed here at
bring-up.

```sh
sudo adduser --disabled-password --gecos "" deploy
sudo mkdir -p /home/deploy/.ssh
# paste the deploy public key:
echo "ssh-ed25519 AAAA... deploy@wren" | sudo tee /home/deploy/.ssh/authorized_keys
sudo chown -R deploy:deploy /home/deploy/.ssh && sudo chmod 700 /home/deploy/.ssh && sudo chmod 600 /home/deploy/.ssh/authorized_keys
echo "deploy ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/deploy && sudo chmod 440 /etc/sudoers.d/deploy
sudo usermod -aG docker deploy   # (docker is installed in Phase A5; re-run if the group did not exist yet)
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

### A5. Host bootstrap (Docker, daemon config, prune cron)

The repeatable deploy no longer mutates the host, so install Docker and its
runtime config once here (as root/sudo on the box).

```sh
curl -fsSL https://get.docker.com | sudo sh          # Docker Engine + CLI
sudo usermod -aG docker deploy                        # log out/in for it to take effect

# Log rotation (mirror deployments/docker/daemon.json in the repo):
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json >/dev/null <<'JSON'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "50m", "max-file": "5" }
}
JSON
sudo systemctl restart docker

# Daily image/build-cache prune (was a deploy.sh phase; now a one-time cron):
sudo tee /etc/cron.daily/wren-docker-prune >/dev/null <<'CRON'
#!/bin/sh
echo "$(date -Is): docker system prune" >> /var/log/wren-docker-prune.log
docker system prune -af --filter until=72h >> /var/log/wren-docker-prune.log 2>&1
CRON
sudo chmod +x /etc/cron.daily/wren-docker-prune

# The box only needs a dir for the rollback key; named volumes are created by
# Compose over the context on the first deploy.
sudo mkdir -p /opt/wren && sudo chown deploy:deploy /opt/wren
```

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

Record the **tunnel UUID** → set `CF_TUNNEL_ID` in the committed `.env.prod`
(non-secret) and commit it. The credentials file `~/.cloudflared/<UUID>.json`
becomes the `WREN_CLOUDFLARED_CREDENTIALS` GitHub secret (RAW JSON, Phase D);
`~/.cloudflared/cert.pem` is a tunnel-management artifact only (used for `tunnel
create`/`route` here) and is NOT needed at runtime, so it never leaves your
machine. The tunnel dials out only; no inbound port is opened.

---

## Phase C: prepare the production config and secret values

Under the Docker Context model the box stores **no** secrets and no `.env`. This
phase produces the values that become GitHub secrets (Phase D) and finalizes the
committed non-secret config.

### C1. Finalize `.env.prod` (committed, non-secret)

`.env.prod` in the repo holds the non-secret production config. Set the one
environment-specific value and commit it:

- `CF_TUNNEL_ID` = the tunnel UUID from Phase B (non-secret).
- Confirm `GHCR_OWNER` matches your GitHub owner (lowercase), and the hostnames
  and public URLs are correct.

`DATABASE_URL` is assembled from `POSTGRES_*` in the compose `environment:` block,
so only the password is a secret; do not put it in `.env.prod`. `.env.prod`
already sets `ENVIRONMENT=production` (fail-fast on a short `SESSION_JWT_SECRET`
or missing OAuth key, `Secure` cookies) and `OAUTH_PRIVATE_KEY_PATH` to the
container secret path `/run/secrets/oauth_private_key`.

### C2. Generate the OAuth AS private key (→ a GitHub secret, not the box)

```sh
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out oauth_private.pem
```

The PEM content becomes the `WREN_OAUTH_PRIVATE_KEY` GitHub secret (Phase D).
Compose materializes it as a `0400` file at `/run/secrets/oauth_private_key`
inside the backend container (the path `OAUTH_PRIVATE_KEY_PATH` points at), so the
key never lands on the box. Store the PEM in your password manager as the source
of truth; the MCP Resource Server verifies agent tokens against the public JWKS
the AS derives from this key.

### C3. Generate the remaining secret values

```sh
openssl rand -base64 48   # SESSION_JWT_SECRET  (≥32 bytes)
openssl rand -base64 48   # INTERNAL_API_TOKEN
openssl rand -hex 32      # POSTGRES_PASSWORD   (hex → safe inside DATABASE_URL)
```

Also have ready the real `DISCORD_WEBHOOK_URL` and the tunnel `credentials.json`
from Phase B (its RAW content). All of these are set as GitHub secrets in Phase
D; none is placed on the box.

---

## Phase D: set the GitHub repo secrets (for CD)

CD (`cd.yml`) needs these to build/push images and deploy. Set via the repo
**Settings → Secrets and variables → Actions**, or `gh`:

```sh
gh secret set DEPLOY_SERVER_IP             --body "<vps-ip>"
gh secret set DEPLOY_SSH_KEY               < ~/.ssh/deploy_ed25519         # deploy user's PRIVATE key
gh secret set POSTGRES_PASSWORD            --body "<generated hex>"
gh secret set SESSION_JWT_SECRET           --body "<generated>"
gh secret set INTERNAL_API_TOKEN           --body "<generated>"
gh secret set DISCORD_WEBHOOK_URL          --body "<real discord webhook>"
gh secret set WREN_OAUTH_PRIVATE_KEY       < oauth_private.pem             # RAW PEM content
gh secret set WREN_CLOUDFLARED_CREDENTIALS < ~/.cloudflared/<UUID>.json    # RAW credentials.json (NOT base64)
```

> `WREN_CLOUDFLARED_CREDENTIALS` holds the RAW, unencoded `credentials.json`
> (environment-sourced secrets transmit raw content). Do NOT reuse the old
> base64 `CF_TUNNEL_CREDENTIALS` value; retire `CF_TUNNEL_CREDENTIALS` and
> `CF_CERT_PEM` (cert.pem is not needed at runtime).

`GITHUB_TOKEN` is **not** set manually: it is the built-in Actions token. Ensure
Actions is allowed to write packages (repo/org **Settings → Actions → Workflow
permissions**), since `cd.yml` already requests `packages: write` and logs into
GHCR with it.

---

## Phase E: first live deploy

The simplest path: once the repo secrets (Phase D) are set and `.env.prod` is
committed (C1), push to `main` (or run the CD **workflow_dispatch**). CD registers
the Docker Context, exports the config/secrets, and runs `scripts/deploy.sh`.

To deploy manually from a local checkout instead, register the context and export
the same environment yourself (mirroring `cd.yml`):

```sh
# One-time on your machine: register the context (CD does this per-run):
docker context create wren --docker "host=ssh://deploy@<vps-ip>"

set -a
source .env.prod
WREN_PROMETHEUS_CONFIG="$(cat deployments/prometheus/prometheus.yml)"
WREN_PROMETHEUS_ALERTS="$(cat deployments/prometheus/alerts.yml)"
WREN_CLOUDFLARED_INGRESS="$(envsubst '$CF_TUNNEL_ID $CF_APP_HOSTNAME $CF_API_HOSTNAME $CF_MCP_HOSTNAME' < deployments/cloudflare/config.yml)"
WREN_ALERTMANAGER_CONFIG="$(DISCORD_WEBHOOK_URL='<webhook>' envsubst '$DISCORD_WEBHOOK_URL' < deployments/alertmanager/alertmanager.yml)"
WREN_OAUTH_PRIVATE_KEY="$(cat oauth_private.pem)"
WREN_CLOUDFLARED_CREDENTIALS="$(cat ~/.cloudflared/<UUID>.json)"
POSTGRES_PASSWORD='<hex>'; SESSION_JWT_SECRET='<gen>'; INTERNAL_API_TOKEN='<gen>'
set +a

DRY_RUN=1 DEPLOY_SHA=$(git rev-parse HEAD) ./scripts/deploy.sh <vps-ip> deploy   # preview
DEPLOY_SHA=$(git rev-parse HEAD) ./scripts/deploy.sh <vps-ip> deploy             # real
```

The script asserts every required config/secret env var is set → pulls → runs
**migrations pre-traffic** (`alembic upgrade head`; aborts on failure) → starts
the stack under the `tunnels` profile over the context → **health-gates every
service (~60s)** → records `/opt/wren/.deployed-sha` on success. On a failed gate
it exits non-zero; CD (not the script) owns the rollback re-run.

**Cutover caveat (one-time).** If the box was previously deployed under the old
model it still holds a `/opt/wren/.deployed-sha` pointing at a **pre-rearchitecture**
commit. A failed first deploy would check that SHA out and run the OLD `deploy.sh`,
which aborts at its local-credential preflight (CD no longer stages
`credentials.json`/`cert.pem`), so the rollback fails cleanly without mutating the
box. Treat the first rearchitected deploy as **fix-forward-only**, and clear the
stale key first so a failure refuses rollback cleanly rather than running
incompatible old code:

```sh
ssh deploy@<vps-ip> 'rm -f /opt/wren/.deployed-sha'
```

Run the cutover in a low-traffic window (containers recreate; `pgdata`/`promdata`
persist).

---

## Phase F: verify the release

### F1. All services healthy, zero open inbound ports

```sh
# from your checkout / the runner, over the context (the box has no repo):
docker --context wren compose -f docker-compose.yml -f docker-compose.tunnel.yml --profile tunnels ps   # every service: healthy
ssh deploy@<vps-ip> 'sudo ufw status verbose'        # only OpenSSH inbound; the tunnel is outbound-only
```

Alertmanager and cloudflared run under the `tunnels` profile; the health gate
covers them. `WREN_ALERTMANAGER_CONFIG` is rendered in CI from
`DISCORD_WEBHOOK_URL`; a blank webhook makes Alertmanager exit on config load and
the health gate fails, so a green deploy means the webhook rendered.

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
docker --context wren compose -f docker-compose.yml -f docker-compose.tunnel.yml --profile tunnels stop mcp
# wait ~1-2m → ServiceDown fires → 🚨 FIRING message in Discord
docker --context wren compose -f docker-compose.yml -f docker-compose.tunnel.yml --profile tunnels start mcp
# → ✅ RESOLVED message (send_resolved: true)
```

---

## Done

The box is provisioned, hardened, and serving. From here, every change ships
through the repeatable deploy in `deploy.md` (CD on merge to `main`, or a manual
`just deploy`). Post-P0 follow-ups (accepted risks) are off-host `pg_dump`
backups and Grafana dashboards.
