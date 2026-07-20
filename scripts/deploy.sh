#!/usr/bin/env bash
# =============================================================================
# scripts/deploy.sh
#
# Stateless Docker Context deploy for Wren. The Compose CLI runs HERE (a CI
# runner or an operator's checkout); the engine runs on the VPS, reached through
# a pre-registered Docker Context (ssh://deploy@<ip>, name `wren`). ALL config
# and secret content is sourced CLI-side (committed .env.prod + files rendered in
# the runner + GitHub Actions secrets, all exported into this process's
# environment) and transmitted to the daemon via environment-sourced Compose
# configs:/secrets:. The box holds no .env, no rendered config, and no secret
# files, which removes the secret-ownership problem entirely.
#
# Usage:
#   DEPLOY_SHA=<git-sha> ./scripts/deploy.sh <server-ip> [ssh-user]
#   ./scripts/deploy.sh read-deployed-sha <server-ip> [ssh-user]
#
# Env:
#   DEPLOY_SHA           git SHA being deployed; recorded on success as the
#                        rollback key. Defaults to the runner checkout's HEAD.
#   DRY_RUN=1            print the phase plan (every compose/ssh line) without
#                        executing.
#   WREN_DOCKER_CONTEXT  Docker context name (default `wren`); CI registers it.
#   WREN_REMOTE_DIR      remote dir holding .deployed-sha (default /opt/wren).
#
# Required config/secret env vars (asserted before ANY compose call, because the
# migration `run` materializes configs/secrets exactly like `up`):
#   WREN_OAUTH_PRIVATE_KEY WREN_CLOUDFLARED_CREDENTIALS WREN_ALERTMANAGER_CONFIG
#   WREN_CLOUDFLARED_INGRESS WREN_PROMETHEUS_CONFIG WREN_PROMETHEUS_ALERTS
#   POSTGRES_PASSWORD SESSION_JWT_SECRET INTERNAL_API_TOKEN
#
# Rollback is owned by CI (cd.yml): on a failed health gate this script exits
# non-zero WITHOUT any internal re-deploy. cd.yml reads the previous SHA
# (`read-deployed-sha`), checks it out in the runner, re-exports env from that
# checkout, and re-runs the deploy once with WREN_IMAGE_TAG=sha-<prev>, which
# restores the previous images AND config.
#
# Not zero-downtime (accepted at ~5 users); a brief per-deploy recreate gap is
# accepted. Concurrency is enforced at the CD layer, not here.
# =============================================================================

# --- Configuration (safe to evaluate when sourced; no args required) --------

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_DIR="${WREN_REMOTE_DIR:-/opt/wren}"
CONTEXT_NAME="${WREN_DOCKER_CONTEXT:-wren}"

# Every compose invocation runs over the Docker Context and layers the tunnel
# overlay (owns ingress) and the deploy overlay (feeds backend/mcp the committed
# .env.prod + app secrets client-side via env_file/environment:, since the box
# has no .env). The tunnels profile keeps cloudflared and alertmanager from
# starting outside a deploy.
COMPOSE="docker --context ${CONTEXT_NAME} compose -f docker-compose.yml -f docker-compose.tunnel.yml -f docker-compose.deploy.yml"
COMPOSE_TUNNEL="${COMPOSE} --profile tunnels"

SSH_OPTS=(-o ConnectTimeout=10 -o BatchMode=yes)
DRY_RUN="${DRY_RUN:-0}"

# Set by configure(); declared here for clarity.
SERVER_IP=""
SSH_USER=""
SSH_TARGET=""
CURRENT_SHA=""

# The config/secret env vars every compose call needs. Asserted up front so a
# missing value fails fast with a clear message instead of a mid-deploy compose
# error (or, worse, a half-migrated stack).
REQUIRED_SECRET_ENV=(
  WREN_OAUTH_PRIVATE_KEY
  WREN_CLOUDFLARED_CREDENTIALS
  WREN_ALERTMANAGER_CONFIG
  WREN_CLOUDFLARED_INGRESS
  WREN_PROMETHEUS_CONFIG
  WREN_PROMETHEUS_ALERTS
  POSTGRES_PASSWORD
  SESSION_JWT_SECRET
  INTERNAL_API_TOKEN
)

# --- Logging & execution helpers --------------------------------------------
# All human-facing output goes to stderr so command-substitution callers
# (read_deployed_sha, health JSON) capture only real data on stdout.

log() { printf '%s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
is_dry_run() { [[ "${DRY_RUN}" == "1" ]]; }

# The ONLY ssh boundary that remains: read/write /opt/wren/.deployed-sha (the
# settled rollback key). Everything else goes through the Docker Context. Kept a
# thin wrapper so the deploy_test.sh harness can stub it.
remote() {
  if is_dry_run; then
    printf '[dry-run][ssh %s] %s\n' "${SSH_TARGET}" "$*" >&2
    return 0
  fi
  # shellcheck disable=SC2029
  ssh "${SSH_OPTS[@]}" "${SSH_TARGET}" "$@"
}

# Run (or, in dry-run, print) a compose command over the context. $1 is the
# compose prefix (COMPOSE or COMPOSE_TUNNEL); the rest are compose args. Config
# and secret content is already in this process's environment; Compose transmits
# it to the remote daemon.
compose_run() {
  local prefix="$1"
  shift
  if is_dry_run; then
    printf '[dry-run] %s %s\n' "${prefix}" "$*" >&2
    return 0
  fi
  # Word-splitting on ${prefix} is intentional: it is a fixed command prefix.
  # shellcheck disable=SC2086
  ${prefix} "$@"
}

# --- Pure helpers (unit-testable without a daemon) --------------------------

# Read image refs (one per line) on stdin; emit unique first-party image bases
# (tag stripped). First-party = ghcr.io/<owner>/wren/*, matched by path so a new
# service is picked up automatically. No production path calls this after the
# context rearchitecture (the former internal re-pull rollback was deleted); it is
# retained as the canonical first-party derivation (mirrored by cd.yml's
# discover-matrix jq) and is covered by a deploy_test.sh case. Keep it and that
# test in sync.
filter_first_party_images() {
  { grep -E '^ghcr\.io/[^/]+/wren/' || true; } | sed -E 's/:[^:/]*$//' | sort -u
}

# Read raw `docker compose ps --format json` on stdin (JSONL or a JSON array;
# `flatten` normalizes both). Print a token for every reason the stack is NOT
# fully healthy, so an EMPTY stdout is the only signal that all is well:
#   - empty / unparseable output, or zero services -> "<no-status>" / "<parse-error>"
#     (a transient blip must never read as healthy: that would let the gate pass
#     and record a bad .deployed-sha)
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

# --- Preflight: required config/secret env vars -----------------------------

assert_secret_env_present() {
  log "==> Preflight: assert required config/secret env vars are set"
  local missing=() var
  for var in "${REQUIRED_SECRET_ENV[@]}"; do
    [[ -n "${!var:-}" ]] || missing+=("${var}")
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    die "missing required config/secret env var(s): ${missing[*]}
  Export these in the runner (from .env.prod + GitHub secrets + rendered files)
  BEFORE deploy.sh: the migration 'run' materializes configs/secrets exactly like
  'up', so every one must be set before the first compose call."
  fi
  log "    all ${#REQUIRED_SECRET_ENV[@]} required config/secret env vars present"
}

# --- Pull ------------------------------------------------------------------

pull_images() {
  log "==> Pull images (docker --context compose pull)"
  compose_run "${COMPOSE_TUNNEL}" pull
}

# --- Migrations (explicit, pre-traffic) -------------------------------------

wait_service_healthy() {
  local svc="$1" attempts="${2:-12}" delay="${3:-5}"
  if is_dry_run; then
    log "    [dry-run] would wait for ${svc} healthy (${attempts}x${delay}s)"
    return 0
  fi
  local i status raw
  for ((i = 1; i <= attempts; i++)); do
    raw="$(${COMPOSE} ps --format json "${svc}" 2>/dev/null || true)"
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
  log "==> Migrations (pre-traffic; postgres -> wait healthy -> alembic upgrade head)"
  compose_run "${COMPOSE}" up -d postgres
  wait_service_healthy postgres 24 5 \
    || die "postgres did not become healthy; aborting before migrations"
  compose_run "${COMPOSE_TUNNEL}" run --rm backend alembic upgrade head \
    || die "migration failed: aborting before app containers start"
  log "    migrations applied"
}

# --- Start ------------------------------------------------------------------

start_stack() {
  log "==> Start stack (docker --context compose --profile tunnels up -d --force-recreate)"
  # --force-recreate: all config and secrets are delivered as environment-sourced
  # Compose configs/secrets, and `up -d` does NOT recreate a service when only
  # that content changes while its image is unchanged (e.g. the pinned cloudflared
  # image + a changed ingress, or an alertmanager/prometheus config edit). A
  # config-only deploy would then silently keep the old config. Force-recreate
  # re-applies the current config/secrets to every service each deploy; the brief
  # recreate gap is already accepted at this scale.
  compose_run "${COMPOSE_TUNNEL}" up -d --force-recreate
}

# --- Health gate (~60s) -----------------------------------------------------

health_gate() {
  log "==> Health gate (poll 'docker --context compose ps' health, ~60s)"
  if is_dry_run; then
    log "    [dry-run] would poll all services' health for ~60s"
    return 0
  fi
  local i raw unhealthy=""
  for ((i = 1; i <= 12; i++)); do
    # `|| true`: a transient error yields empty output, which gate_unhealthy
    # reports as not-healthy (retry) rather than aborting.
    raw="$(${COMPOSE} ps --format json 2>/dev/null || true)"
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

# --- Rollback target helper (CI-owned rollback; see cd.yml) -----------------

# Echo the previously deployed SHA (the rollback target) on stdout, or REFUSE
# (non-zero) when none is recorded. cd.yml calls `deploy.sh read-deployed-sha
# <ip>` on a failed deploy; an empty result means the first deploy has no
# rollback target and the workflow must fail rather than guess.
read_deployed_sha() {
  # `remote`'s command ends in `|| true`, so a non-zero exit here is an SSH/
  # transport failure, NOT an absent file. Distinguish the two: a transport
  # failure is transient (a human retries), while an empty read is a genuine
  # "no rollback target" (e.g. the first deploy). Both refuse (non-zero), so a
  # bad read can never trigger a rollback to the wrong SHA.
  local sha rc
  sha="$(remote "cat ${REMOTE_DIR}/.deployed-sha 2>/dev/null || true")"
  rc=$?
  if [[ ${rc} -ne 0 ]]; then
    log "cannot reach ${SSH_TARGET} to read .deployed-sha (ssh exit ${rc}); cannot roll back"
    return 1
  fi
  sha="$(printf '%s' "${sha}" | tr -d '[:space:]')"
  if [[ -z "${sha}" ]]; then
    log "no previous .deployed-sha recorded on ${SSH_TARGET}; cannot roll back"
    return 1
  fi
  printf '%s\n' "${sha}"
}

# --- Success bookkeeping ----------------------------------------------------

record_deploy() {
  if [[ -z "${CURRENT_SHA}" ]]; then
    log "    no DEPLOY_SHA resolved; skipping .deployed-sha write"
    return 0
  fi
  # The one remaining ssh line: settle the rollback key on the box.
  remote "printf '%s\n' '${CURRENT_SHA}' > ${REMOTE_DIR}/.deployed-sha"
  log "    recorded deployed SHA: ${CURRENT_SHA}"
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
  CURRENT_SHA="${DEPLOY_SHA:-$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || echo "")}"
  log "=== Wren deploy -> context ${CONTEXT_NAME} (${SSH_TARGET}); dry-run=${DRY_RUN} ==="

  assert_secret_env_present
  pull_images
  run_migrations
  start_stack

  if ! health_gate; then
    log "!!! health gate FAILED: deploy.sh exits non-zero (CI owns rollback)"
    die "deploy failed the health gate on context ${CONTEXT_NAME}"
  fi

  record_deploy
  log "=== Deploy complete: ${CURRENT_SHA:-unknown} on context ${CONTEXT_NAME} ==="
}

# Only run when executed directly, so tests can source and exercise functions.
# `read-deployed-sha <ip> [user]` routes to the rollback-target helper (cd.yml
# calls it); any other first arg runs a full deploy.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  if [[ "${1:-}" == "read-deployed-sha" ]]; then
    shift
    configure "$@"
    read_deployed_sha
  else
    main "$@"
  fi
fi
