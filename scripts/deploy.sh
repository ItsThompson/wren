#!/usr/bin/env bash
# =============================================================================
# scripts/deploy.sh
#
# Push-based SSH deploy orchestration for Wren (spec section 11, §7.2 phases
# 1-14), collapsed to the modular-monolith topology and hardened for a non-root
# deploy user.
#
# Runs from a checkout of this repo (CI runner or an operator's machine) and
# orchestrates a single VPS over SSH. It never creates secrets on the box: it
# asserts /opt/wren/.env and the OAuth key already exist (placed at one-time
# bring-up, Ticket 32).
#
# Usage:
#   DEPLOY_SHA=<git-sha> ./scripts/deploy.sh <server-ip> [ssh-user]
#
# Env:
#   DEPLOY_SHA       git SHA being deployed (recorded for future rollback).
#                    Defaults to the resolved HEAD after repo sync.
#   DRY_RUN=1        print the phase plan (every ssh/scp) without executing.
#   WREN_REMOTE_DIR  remote checkout dir (default /opt/wren).
#   WREN_REPO_URL    git remote to clone on first deploy
#                    (default https://github.com/${GITHUB_REPOSITORY:-wren-platform/wren}.git).
#
# Phases: preflight -> ssh probe -> dep install -> docker daemon config ->
# prune cron -> repo sync -> copy tunnel credentials -> assert secrets ->
# render deploy configs + pull -> pre-traffic migrations -> start ->
# health gate -> (rollback on failure) -> cleanup on success.
#
# Not zero-downtime (accepted at ~5 users). Concurrency (a manual dispatch vs a
# push-deploy) is enforced at the CD layer (Ticket 30), not here.
# =============================================================================

# --- Configuration (safe to evaluate when sourced; no args required) --------

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CRED_DIR="${REPO_ROOT}/deployments/cloudflare"
REMOTE_DIR="${WREN_REMOTE_DIR:-/opt/wren}"
REPO_URL="${WREN_REPO_URL:-https://github.com/${GITHUB_REPOSITORY:-wren-platform/wren}.git}"

# Every compose invocation layers the tunnel overlay (Ticket 29 owns it; the
# base docker-compose.yml, Ticket 28, is untouched). The tunnels profile keeps
# cloudflared from starting outside a deploy.
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.tunnel.yml"
COMPOSE_TUNNEL="${COMPOSE} --profile tunnels"

SSH_OPTS=(-o ConnectTimeout=10 -o BatchMode=yes)
DRY_RUN="${DRY_RUN:-0}"

# Set by configure()/ssh_probe()/sync_repo(); declared here for clarity.
SERVER_IP=""
SSH_USER=""
SSH_TARGET=""
SUDO="sudo"
PREV_SHA=""
CURRENT_SHA=""

# --- Logging & execution helpers --------------------------------------------
# All human-facing output goes to stderr so command-substitution callers (image
# derivation, health JSON) capture only real data on stdout.

log() { printf '%s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
is_dry_run() { [[ "${DRY_RUN}" == "1" ]]; }

# Run a single command string on the remote host. Command strings are assembled
# CLIENT-SIDE on purpose (REMOTE_DIR and the compose flags are deploy config);
# anything that must expand on the box goes through remote_script's quoted
# heredoc, never here.
remote() {
  if is_dry_run; then
    printf '[dry-run][ssh %s] %s\n' "${SSH_TARGET}" "$*" >&2
    return 0
  fi
  # shellcheck disable=SC2029
  ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" "$@"
}

# Run a bash script (read from stdin) on the remote host. Extra args are
# forwarded as positional params ($1, $2, ...) to the remote script; use a
# quoted heredoc (<<'REMOTE') so nothing expands locally.
remote_script() {
  if is_dry_run; then
    {
      printf '[dry-run][ssh %s] bash -s -- %s <<REMOTE\n' "${SSH_TARGET}" "$*"
      cat
      printf 'REMOTE\n'
    } >&2
    return 0
  fi
  ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" bash -s -- "$@"
}

# Copy a local file to the remote host.
copy_to_remote() {
  local src="$1" dest="$2"
  if is_dry_run; then
    printf '[dry-run][scp] %s -> %s:%s\n' "${src}" "${SSH_TARGET}" "${dest}" >&2
    return 0
  fi
  scp "${SSH_OPTS[@]}" "${src}" "${SSH_TARGET}:${dest}"
}

# --- Pure helpers (unit-testable without SSH) -------------------------------

# Read image refs (one per line) on stdin; emit unique first-party image bases
# (tag stripped). First-party = ghcr.io/<owner>/wren/*, matched by path so a new
# service is picked up automatically. Never hard-code the service list.
filter_first_party_images() {
  { grep -E '^ghcr\.io/[^/]+/wren/' || true; } | sed -E 's/:[^:/]*$//' | sort -u
}

# Read raw `docker compose ps --format json` on stdin (JSONL or a JSON array;
# `flatten` normalizes both). Print a token for every reason the stack is NOT
# fully healthy, so an EMPTY stdout is the only signal that all is well:
#   - empty / unparseable output, or zero services -> "<no-status>" / "<parse-error>"
#     (a transient SSH blip must never read as healthy: that would suppress the
#     rollback the gate exists to trigger)
#   - any service not in State=running                        -> its .Service
#     (an exited container with empty Health is caught here, not ignored)
#   - any service whose Health is defined and not "healthy"   -> its .Service
gate_unhealthy() {
  jq -rs '
    (flatten) as $svcs
    | if ($svcs | length) == 0 then "<no-status>"
      else
        $svcs[]
        | select(
            (.State // "") != "running"
            or ((.Health // "") != "" and (.Health // "") != "healthy")
          )
        | .Service
      end
  ' 2>/dev/null || echo "<parse-error>"
}

# --- Phase 1: preflight ------------------------------------------------------

preflight_credentials() {
  log "==> Phase 1: preflight (assert tunnel credentials exist locally)"
  local f
  for f in "${CRED_DIR}/credentials.json" "${CRED_DIR}/cert.pem"; do
    [[ -f "${f}" ]] || die "tunnel credential not found: ${f}
  Decode CF_TUNNEL_CREDENTIALS / CF_CERT_PEM into deployments/cloudflare/ first.
  See docs/runbooks/deploy.md."
  done
  log "    present: ${CRED_DIR}/{credentials.json,cert.pem}"
}

# --- Phase 2: ssh probe (and detect whether remote needs sudo) --------------

ssh_probe() {
  log "==> Phase 2: SSH probe (${SSH_TARGET})"
  if is_dry_run; then
    remote "echo ok"
    SUDO="sudo"
    return 0
  fi
  ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" "echo ok" >/dev/null 2>&1 \
    || die "cannot SSH into ${SSH_TARGET} (ensure key-based auth is set up)"
  local uid
  uid="$(ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" "id -u" 2>/dev/null || echo 1000)"
  if [[ "${uid}" == "0" ]]; then SUDO=""; else SUDO="sudo"; fi
  log "    connected; privileged prefix: '${SUDO:-<none, root>}'"
}

# --- Phase 3: idempotent dependency install ---------------------------------

install_dependencies() {
  log "==> Phase 3: idempotent dependency install (docker, git, gettext-base, jq)"
  remote_script "${SUDO}" <<'REMOTE'
set -euo pipefail
SUDO="$1"
ensure() {
  # ensure <command> <apt-package>
  if command -v "$1" >/dev/null 2>&1; then
    echo "    $1 already installed"
  else
    echo "    installing $2 ..."
    ${SUDO} apt-get update -qq
    ${SUDO} apt-get install -y -qq "$2"
  fi
}
if command -v docker >/dev/null 2>&1; then
  echo "    docker already installed"
else
  echo "    installing docker ..."
  curl -fsSL https://get.docker.com | ${SUDO} sh
fi
ensure git git
ensure envsubst gettext-base
ensure jq jq
REMOTE
}

# --- Phase 4: docker daemon config (log rotation; restart only if changed) --

configure_docker_daemon() {
  log "==> Phase 4: docker daemon config (log rotation)"
  copy_to_remote "${REPO_ROOT}/deployments/docker/daemon.json" "/tmp/wren-daemon.json"
  remote_script "${SUDO}" <<'REMOTE'
set -euo pipefail
SUDO="$1"
if cmp -s /tmp/wren-daemon.json /etc/docker/daemon.json 2>/dev/null; then
  rm -f /tmp/wren-daemon.json
  echo "    daemon.json unchanged; no restart"
else
  ${SUDO} mkdir -p /etc/docker
  ${SUDO} mv /tmp/wren-daemon.json /etc/docker/daemon.json
  ${SUDO} systemctl restart docker
  echo "    daemon.json updated; docker restarted"
fi
REMOTE
}

# --- Phase 5: daily docker prune cron ---------------------------------------

install_prune_cron() {
  log "==> Phase 5: daily docker prune cron"
  remote_script "${SUDO}" <<'REMOTE'
set -euo pipefail
SUDO="$1"
${SUDO} tee /etc/cron.daily/wren-docker-prune >/dev/null <<'CRON'
#!/bin/sh
# Remove images and build cache unused for >72h (installed by scripts/deploy.sh).
echo "$(date -Is): docker system prune" >> /var/log/wren-docker-prune.log
docker system prune -af --filter until=72h >> /var/log/wren-docker-prune.log 2>&1
CRON
${SUDO} chmod +x /etc/cron.daily/wren-docker-prune
echo "    /etc/cron.daily/wren-docker-prune installed"
REMOTE
}

# --- Phase 6: repo sync (captures the previous SHA for rollback) ------------

sync_repo() {
  log "==> Phase 6: repo sync (git fetch && reset --hard origin/main)"
  # The last successfully deployed SHA (its :sha-<prev> images exist in GHCR) is
  # the rollback target. Capture it before the checkout moves.
  PREV_SHA="$(remote "cat ${REMOTE_DIR}/.deployed-sha 2>/dev/null || true")"
  PREV_SHA="$(printf '%s' "${PREV_SHA}" | tr -d '[:space:]')"
  remote_script "${SUDO}" "${REMOTE_DIR}" "${REPO_URL}" <<'REMOTE'
set -euo pipefail
SUDO="$1"; DIR="$2"; URL="$3"
if [ -d "$DIR/.git" ]; then
  echo "    repo exists; fetching origin/main"
  git -C "$DIR" fetch origin
  git -C "$DIR" reset --hard origin/main
else
  echo "    cloning $URL"
  ${SUDO} mkdir -p "$DIR"
  ${SUDO} chown "$(id -u):$(id -g)" "$DIR"
  git clone "$URL" "$DIR"
fi
REMOTE
  CURRENT_SHA="${DEPLOY_SHA:-}"
  if [[ -z "${CURRENT_SHA}" ]]; then
    CURRENT_SHA="$(remote "git -C ${REMOTE_DIR} rev-parse HEAD 2>/dev/null || true")"
    CURRENT_SHA="$(printf '%s' "${CURRENT_SHA}" | tr -d '[:space:]')"
  fi
  log "    previous SHA: ${PREV_SHA:-<none>} ; deploying: ${CURRENT_SHA:-<unknown>}"
}

# --- Phase 7: copy tunnel credentials (chmod 600) ---------------------------

copy_tunnel_credentials() {
  log "==> Phase 7: copy tunnel credentials (chmod 600)"
  remote "mkdir -p ${REMOTE_DIR}/deployments/cloudflare"
  copy_to_remote "${CRED_DIR}/credentials.json" "${REMOTE_DIR}/deployments/cloudflare/credentials.json"
  copy_to_remote "${CRED_DIR}/cert.pem" "${REMOTE_DIR}/deployments/cloudflare/cert.pem"
  remote "chmod 600 ${REMOTE_DIR}/deployments/cloudflare/credentials.json ${REMOTE_DIR}/deployments/cloudflare/cert.pem"
}

# --- Phase 8: assert secrets exist (never created by this script) -----------

assert_secrets_present() {
  log "==> Phase 8: assert .env + OAuth key exist (never created here)"
  remote_script "${REMOTE_DIR}" <<'REMOTE'
set -euo pipefail
DIR="$1"
if [ ! -f "$DIR/.env" ]; then
  echo "ERROR: $DIR/.env not found. Create it at bring-up; deploy.sh never creates it." >&2
  exit 1
fi
set -a; . "$DIR/.env"; set +a
if [ -z "${OAUTH_PRIVATE_KEY_PATH:-}" ]; then
  echo "ERROR: OAUTH_PRIVATE_KEY_PATH is not set in $DIR/.env." >&2
  exit 1
fi
if [ ! -f "$OAUTH_PRIVATE_KEY_PATH" ]; then
  echo "ERROR: OAuth key file missing at $OAUTH_PRIVATE_KEY_PATH (place it at bring-up)." >&2
  exit 1
fi
echo "    .env and OAuth key present"
REMOTE
}

# --- Phase 9: render deploy configs (envsubst) + pull -----------------------

render_tunnel_config() {
  log "==> Phase 9a: render tunnel config (envsubst)"
  remote_script "${REMOTE_DIR}" <<'REMOTE'
set -euo pipefail
cd "$1"
set -a; . ./.env; set +a
# Substitute ONLY the tunnel vars so the ingress path regex (which contains $)
# survives untouched.
envsubst '${CF_TUNNEL_ID} ${CF_APP_HOSTNAME} ${CF_API_HOSTNAME} ${CF_MCP_HOSTNAME}' \
  < deployments/cloudflare/config.yml \
  > deployments/cloudflare/config.rendered.yml
echo "    rendered deployments/cloudflare/config.rendered.yml"
REMOTE
}

render_alertmanager_config() {
  log "==> Phase 9a: render Alertmanager config (envsubst DISCORD_WEBHOOK_URL)"
  remote_script "${REMOTE_DIR}" <<'REMOTE'
set -euo pipefail
cd "$1"
set -a; . ./.env; set +a
# Alertmanager v0.27 EXITS on config load if webhook_url is not a valid URL, and
# the tunnels profile the deploy activates DOES start alertmanager, so a missing
# webhook is release-gating: fail here with a clear message rather than let the
# container crash-loop until the health gate times out and rolls back.
: "${DISCORD_WEBHOOK_URL:?DISCORD_WEBHOOK_URL must be set in /opt/wren/.env (bring-up)}"
# Substitute ONLY the webhook token (single-var allow-list) so the Go templating
# ({{ ... }}) in title/message survives. The rendered file holds a real secret,
# so chmod 600; it is gitignored and mounted by the alertmanager service.
envsubst '${DISCORD_WEBHOOK_URL}' \
  < deployments/alertmanager/alertmanager.yml \
  > deployments/alertmanager/alertmanager.rendered.yml
chmod 600 deployments/alertmanager/alertmanager.rendered.yml
echo "    rendered deployments/alertmanager/alertmanager.rendered.yml (chmod 600)"
REMOTE
}

# Render every deploy-time config the stack mounts (tunnel ingress + Alertmanager
# webhook) from /opt/wren/.env before any `up`.
render_configs() {
  render_tunnel_config
  render_alertmanager_config
}

render_and_pull() {
  render_configs
  log "==> Phase 9b: docker compose pull"
  remote "cd ${REMOTE_DIR} && ${COMPOSE_TUNNEL} pull"
}

# --- Phase 10: migrations (explicit, pre-traffic) ---------------------------

wait_service_healthy() {
  local svc="$1" attempts="${2:-12}" delay="${3:-5}"
  if is_dry_run; then
    log "    [dry-run] would wait for ${svc} healthy (${attempts}x${delay}s)"
    return 0
  fi
  local i status raw
  for ((i = 1; i <= attempts; i++)); do
    raw="$(remote "cd ${REMOTE_DIR} && ${COMPOSE} ps --format json ${svc}" 2>/dev/null || true)"
    status="$(printf '%s' "${raw}" | jq -rs 'flatten | .[0].Health // ""' 2>/dev/null || true)"
    if [[ "${status}" == "healthy" ]]; then
      log "    ${svc} healthy"
      return 0
    fi
    log "    waiting for ${svc} (${i}/${attempts}) ..."
    sleep "${delay}"
  done
  return 1
}

run_migrations() {
  log "==> Phase 10: migrations (pre-traffic; postgres -> wait healthy -> alembic upgrade head)"
  remote "cd ${REMOTE_DIR} && ${COMPOSE} up -d postgres"
  wait_service_healthy postgres 24 5 \
    || die "postgres did not become healthy; aborting before migrations"
  remote "cd ${REMOTE_DIR} && ${COMPOSE} run --rm backend alembic upgrade head" \
    || die "migration failed: aborting before app containers start"
  log "    migrations applied"
}

# --- Phase 11: start --------------------------------------------------------

start_stack() {
  log "==> Phase 11: start stack (docker compose --profile tunnels up -d)"
  remote "cd ${REMOTE_DIR} && ${COMPOSE_TUNNEL} up -d"
}

# --- Phase 12: health gate (~60s) -------------------------------------------

health_gate() {
  log "==> Phase 12: health gate (poll 'docker compose ps' health, ~60s)"
  if is_dry_run; then
    log "    [dry-run] would poll all services' health for ~60s"
    return 0
  fi
  local i raw unhealthy=""
  for ((i = 1; i <= 12; i++)); do
    # `|| true`: a failed/transient SSH call yields empty output, which
    # gate_unhealthy reports as not-healthy (retry) rather than aborting.
    raw="$(remote "cd ${REMOTE_DIR} && ${COMPOSE} ps --format json" 2>/dev/null || true)"
    unhealthy="$(printf '%s' "${raw}" | gate_unhealthy)"
    if [[ -z "${unhealthy}" ]]; then
      log "    all services healthy"
      return 0
    fi
    log "    waiting for: $(printf '%s' "${unhealthy}" | tr '\n' ' ')(${i}/12)"
    sleep 5
  done
  log "    still unhealthy after ~60s: $(printf '%s' "${unhealthy}" | tr '\n' ' ')"
  return 1
}

# --- Phase 13: rollback (image-only, git-consistent) ------------------------

first_party_images() {
  remote "cd ${REMOTE_DIR} && ${COMPOSE} config --images" | filter_first_party_images
}

rollback() {
  local prev="$1"
  log "==> Phase 13: ROLLBACK to ${prev:-<none>}"
  if [[ -z "${prev}" ]]; then
    log "    no previous SHA recorded (.deployed-sha empty); cannot roll back automatically"
    return 1
  fi
  local images
  images="$(first_party_images)"
  if [[ -z "${images}" ]] && ! is_dry_run; then
    die "rollback: no first-party images derived from 'docker compose config'"
  fi
  log "    re-pulling :sha-${prev} for all first-party images:"
  local img
  while IFS= read -r img; do
    [[ -z "${img}" ]] && continue
    log "      ${img}:sha-${prev}"
    remote "docker pull ${img}:sha-${prev}"
  done <<< "${images}"
  log "    pinning git checkout to ${prev}"
  remote "git -C ${REMOTE_DIR} reset --hard ${prev}"
  render_configs
  log "    bringing the stack back up on :sha-${prev}"
  remote "cd ${REMOTE_DIR} && WREN_IMAGE_TAG=sha-${prev} ${COMPOSE_TUNNEL} up -d"
}

# --- Phase 14: success bookkeeping ------------------------------------------

record_deploy() {
  [[ -z "${CURRENT_SHA}" ]] && return 0
  remote "printf '%s\n' '${CURRENT_SHA}' > ${REMOTE_DIR}/.deployed-sha"
  log "    recorded deployed SHA: ${CURRENT_SHA}"
}

cleanup() {
  log "==> Phase 14: cleanup (success path)"
  # Best-effort: a cleanup failure never fails an already-successful deploy.
  remote_script <<'REMOTE'
set -uo pipefail
docker builder prune -af --filter until=24h >/dev/null 2>&1 || true
docker image prune -af --filter until=72h >/dev/null 2>&1 || true
journalctl --vacuum-size=50M >/dev/null 2>&1 || true
echo "    cleanup done"
REMOTE
}

# --- Orchestration ----------------------------------------------------------

configure() {
  SERVER_IP="${1:?Usage: DEPLOY_SHA=<sha> $0 <server-ip> [ssh-user]}"
  SSH_USER="${2:-deploy}"
  SSH_TARGET="${SSH_USER}@${SERVER_IP}"
}

main() {
  set -euo pipefail
  configure "$@"
  log "=== Wren deploy -> ${SSH_TARGET} (dry-run=${DRY_RUN}) ==="

  preflight_credentials
  ssh_probe
  install_dependencies
  configure_docker_daemon
  install_prune_cron
  sync_repo
  copy_tunnel_credentials
  assert_secrets_present
  render_and_pull
  run_migrations
  start_stack

  if ! health_gate; then
    log "!!! health gate FAILED: initiating rollback"
    if rollback "${PREV_SHA}"; then
      die "deploy failed the health gate; rolled back to ${PREV_SHA}"
    fi
    die "deploy failed the health gate AND rollback could not proceed"
  fi

  record_deploy
  cleanup
  log "=== Deploy complete: ${CURRENT_SHA:-unknown} on ${SSH_TARGET} ==="
}

# Only run when executed directly, so tests can source and exercise functions.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
