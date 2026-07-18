#!/usr/bin/env bash
# =============================================================================
# Tests for scripts/deploy.sh (Docker Context deploy).
#
# Plain-bash harness (no external test runner) so it runs anywhere bash does,
# including CI. Exercises everything verifiable WITHOUT a live VPS or daemon:
#   - pure helpers (image filtering, health parsing)
#   - the required-secret-env preflight
#   - the dry-run phase plan and ordering (context transport, no ssh heredoc)
#   - the compose overlay/base shape (environment-sourced configs/secrets)
#   - the rollback-target helper and the failed-gate contract (CI owns rollback)
# Live execution against a real box is out of scope for this harness.
#
# Run: scripts/tests/deploy_test.sh   (or: just test-deploy)
# =============================================================================
#
# Test harness: functions defined here are stubs invoked indirectly by the
# sourced deploy.sh (via main), and vars set here are consumed by it.
# shellcheck disable=SC1090,SC2034,SC2329,SC2016
set -uo pipefail

DEPLOY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../deploy.sh"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0

# Run a test function in a subshell so its stubs/vars never leak.
run_test() {
  local name="$1"
  local out rc
  out="$( "$name" 2>&1 )"
  rc=$?
  if [[ ${rc} -eq 0 ]]; then
    printf 'ok   - %s\n' "${name#test_}"
    PASS=$((PASS + 1))
  else
    printf 'FAIL - %s\n' "${name#test_}"
    printf '%s\n' "${out}" | sed 's/^/       /'
    FAIL=$((FAIL + 1))
  fi
}

# Assertion helpers: echo a diagnostic and return 1 on failure.
contains() { [[ "$1" == *"$2"* ]] || { echo "expected to contain: $2"; return 1; }; }
not_contains() { [[ "$1" != *"$2"* ]] || { echo "expected NOT to contain: $2"; return 1; }; }
equals() { [[ "$1" == "$2" ]] || { echo "expected '$2', got '$1'"; return 1; }; }

# Export the config/secret env vars deploy.sh asserts before any compose call so
# a dry-run gets past the preflight.
export_required_secret_env() {
  export WREN_OAUTH_PRIVATE_KEY="pem" WREN_CLOUDFLARED_CREDENTIALS='{"c":1}'
  export WREN_ALERTMANAGER_CONFIG="global: {}" WREN_CLOUDFLARED_INGRESS="tunnel: x"
  export WREN_PROMETHEUS_CONFIG="global: {}" WREN_PROMETHEUS_ALERTS="groups: []"
  export POSTGRES_PASSWORD="pw" SESSION_JWT_SECRET="s" INTERNAL_API_TOKEN="t"
}

# --- pure helpers -----------------------------------------------------------

test_filter_first_party_images() {
  source "${DEPLOY}"
  local out
  out="$(printf '%s\n' \
    'ghcr.io/wren-platform/wren/backend:latest' \
    'postgres:17-alpine' \
    'cloudflare/cloudflared:2026.7.1' \
    'ghcr.io/acme/wren/mcp:sha-abc' \
    'ghcr.io/wren-platform/wren/frontend:latest' | filter_first_party_images)"
  contains "${out}" "ghcr.io/acme/wren/mcp" || return 1
  contains "${out}" "ghcr.io/wren-platform/wren/backend" || return 1
  contains "${out}" "ghcr.io/wren-platform/wren/frontend" || return 1
  not_contains "${out}" "postgres" || return 1
  not_contains "${out}" "cloudflared" || return 1
  equals "$(printf '%s\n' "${out}" | wc -l | tr -d ' ')" "3" || return 1
}

test_gate_unhealthy_jsonl() {
  source "${DEPLOY}"
  local out
  out="$(printf '%s\n' \
    '{"Service":"backend","State":"running","Health":"healthy"}' \
    '{"Service":"mcp","State":"running","Health":"starting"}' \
    '{"Service":"postgres","State":"running","Health":""}' \
    '{"Service":"frontend","State":"running","Health":"unhealthy"}' | gate_unhealthy)"
  contains "${out}" "mcp" || return 1
  contains "${out}" "frontend" || return 1
  not_contains "${out}" "backend" || return 1
  not_contains "${out}" "postgres" || return 1
}

test_gate_unhealthy_flags_exited_container_with_empty_health() {
  source "${DEPLOY}"
  local out
  # An exited container reports empty Health; keying on State alone must catch it.
  out="$(printf '%s\n' \
    '{"Service":"backend","State":"running","Health":"healthy"}' \
    '{"Service":"mcp","State":"exited","Health":""}' | gate_unhealthy)"
  contains "${out}" "mcp" || return 1
  not_contains "${out}" "backend" || return 1
}

test_gate_unhealthy_array_and_all_healthy() {
  source "${DEPLOY}"
  local out
  out="$(printf '%s' '[{"Service":"backend","State":"running","Health":"healthy"},{"Service":"mcp","State":"running","Health":"healthy"}]' | gate_unhealthy)"
  equals "${out}" "" || return 1
}

test_gate_unhealthy_empty_or_unparseable_is_not_healthy() {
  source "${DEPLOY}"
  # A transient blip (empty output) must NOT read as healthy, or the gate would
  # falsely pass and record a bad .deployed-sha.
  local empty_out garbage_out
  empty_out="$(printf '' | gate_unhealthy)"
  garbage_out="$(printf 'not json at all' | gate_unhealthy)"
  [[ -n "${empty_out}" ]] || { echo "empty input read as healthy"; return 1; }
  [[ -n "${garbage_out}" ]] || { echo "unparseable input read as healthy"; return 1; }
}

# --- preflight (replaces the old credential-file preflight) -----------------

test_assert_secret_env_present() {
  source "${DEPLOY}"
  export_required_secret_env
  assert_secret_env_present >/dev/null 2>&1 || { echo "expected pass with all set"; return 1; }
  # Unset one required var -> fails with a clear message naming it.
  unset WREN_ALERTMANAGER_CONFIG
  local out rc
  out="$(assert_secret_env_present 2>&1)"
  rc=$?
  [[ ${rc} -ne 0 ]] || { echo "expected non-zero exit with a var unset"; return 1; }
  contains "${out}" "WREN_ALERTMANAGER_CONFIG" || return 1
  contains "${out}" "missing required" || return 1
}

# --- dry-run phase plan & ordering ------------------------------------------

test_dry_run_uses_docker_context_and_no_ssh_heredoc() {
  source "${DEPLOY}"
  export_required_secret_env
  DRY_RUN=1
  DEPLOY_SHA="cafef00d"
  local out
  out="$(main 203.0.113.10 deploy 2>&1)"
  # Transport is the Docker Context, not ssh-bash.
  contains "${out}" "docker --context wren compose" || return 1
  # The ONLY ssh line is the .deployed-sha write.
  contains "${out}" ".deployed-sha" || return 1
  not_contains "${out}" "bash -s" || return 1
  not_contains "${out}" "REMOTE" || return 1
  not_contains "${out}" "envsubst" || return 1
  not_contains "${out}" "scp" || return 1
  not_contains "${out}" "chown" || return 1
}

test_dry_run_migrations_before_start() {
  source "${DEPLOY}"
  export_required_secret_env
  DRY_RUN=1
  local out mig start
  out="$(main 203.0.113.10 deploy 2>&1)"
  mig="$(printf '%s\n' "${out}" | grep -n 'alembic upgrade head' | head -1 | cut -d: -f1)"
  start="$(printf '%s\n' "${out}" | grep -n 'Start stack' | head -1 | cut -d: -f1)"
  [[ -n "${mig}" && -n "${start}" ]] || { echo "missing markers mig=${mig} start=${start}"; return 1; }
  [[ "${mig}" -lt "${start}" ]] || { echo "migrations (${mig}) not before start (${start})"; return 1; }
}

test_dry_run_pull_migrate_up_use_overlay_and_profile() {
  source "${DEPLOY}"
  export_required_secret_env
  DRY_RUN=1
  local out overlays
  out="$(main 203.0.113.10 deploy 2>&1)"
  overlays="-f docker-compose.yml -f docker-compose.tunnel.yml -f docker-compose.deploy.yml"
  contains "${out}" "${overlays} --profile tunnels pull" || return 1
  contains "${out}" "${overlays} --profile tunnels run --rm backend alembic upgrade head" || return 1
  contains "${out}" "${overlays} --profile tunnels up -d --force-recreate" || return 1
}

# --- compose overlay / base shape -------------------------------------------

test_compose_tunnel_overlay_declares_environment_sourced_secrets_and_ingress() {
  local overlay
  overlay="$(cat "${REPO_DIR}/docker-compose.tunnel.yml")"
  contains "${overlay}" "environment: WREN_OAUTH_PRIVATE_KEY" || return 1
  contains "${overlay}" "environment: WREN_CLOUDFLARED_CREDENTIALS" || return 1
  contains "${overlay}" "environment: WREN_ALERTMANAGER_CONFIG" || return 1
  contains "${overlay}" "environment: WREN_CLOUDFLARED_INGRESS" || return 1
  # The rendered-file bind mount is gone.
  not_contains "${overlay}" "config.rendered.yml" || return 1
}

test_compose_tunnel_overlay_targets_uids_modes_no_file_source() {
  local overlay
  overlay="$(cat "${REPO_DIR}/docker-compose.tunnel.yml")"
  contains "${overlay}" "target: /run/secrets/oauth_private_key" || return 1
  contains "${overlay}" "target: /etc/cloudflared/credentials.json" || return 1
  contains "${overlay}" "target: /etc/cloudflared/config.yml" || return 1
  contains "${overlay}" "target: /etc/alertmanager/alertmanager.yml" || return 1
  contains "${overlay}" "mode: 0400" || return 1
  # No leftover host bind source for the OAuth key.
  not_contains "${overlay}" '${OAUTH_PRIVATE_KEY_PATH}:' || return 1
}

test_compose_base_declares_environment_sourced_prometheus_configs() {
  local base
  base="$(cat "${REPO_DIR}/docker-compose.yml")"
  contains "${base}" "environment: WREN_PROMETHEUS_CONFIG" || return 1
  contains "${base}" "environment: WREN_PROMETHEUS_ALERTS" || return 1
  contains "${base}" "target: /etc/prometheus/prometheus.yml" || return 1
  contains "${base}" "target: /etc/prometheus/alerts.yml" || return 1
  # No bind mount for the Prometheus config files (promdata volume stays).
  not_contains "${base}" "prometheus.yml:/etc/prometheus/prometheus.yml" || return 1
  not_contains "${base}" "alerts.yml:/etc/prometheus/alerts.yml" || return 1
}

test_compose_deploy_overlay_feeds_app_env_from_env_prod_and_secrets() {
  local overlay
  overlay="$(cat "${REPO_DIR}/docker-compose.deploy.yml")"
  # Non-secret prod config comes from the committed .env.prod (client-side
  # env_file), NOT a stray local dev .env; both backend and mcp load it.
  contains "${overlay}" "path: .env.prod" || return 1
  # App secrets are passed through from the runner env (GitHub secrets).
  contains "${overlay}" 'SESSION_JWT_SECRET: ${SESSION_JWT_SECRET' || return 1
  contains "${overlay}" 'INTERNAL_API_TOKEN: ${INTERNAL_API_TOKEN' || return 1
  # The base file's env_file: .env is the local-dev source; .env.prod is layered
  # on top here for the deploy (base file itself is untouched).
  local base
  base="$(cat "${REPO_DIR}/docker-compose.yml")"
  contains "${base}" "path: .env" || return 1
}

test_cd_frontend_image_bakes_prod_api_and_mcp_origins() {
  local workflow
  workflow="$(cat "${REPO_DIR}/.github/workflows/cd.yml")"
  contains "${workflow}" "id: frontend-build-args" || return 1
  contains "${workflow}" 'if [[ "${{ matrix.service }}" != "frontend" ]]; then' || return 1
  contains "${workflow}" "source .env.prod" || return 1
  contains "${workflow}" 'VITE_API_BASE_URL=${PUBLIC_BASE_URL' || return 1
  contains "${workflow}" 'VITE_MCP_BASE_URL=${MCP_PUBLIC_URL' || return 1
  contains "${workflow}" 'build-args: ${{ steps.frontend-build-args.outputs.value }}' || return 1
}

# --- rollback target helper (CI owns rollback) ------------------------------

test_read_deployed_sha_returns_prev_and_refuses_on_empty() {
  source "${DEPLOY}"
  # Present: echoes the prev SHA on stdout, exit 0.
  remote() { printf '%s\n' "abc123"; }
  local out rc
  out="$(read_deployed_sha)"
  rc=$?
  [[ ${rc} -eq 0 ]] || { echo "expected success when sha present"; return 1; }
  equals "${out}" "abc123" || return 1
  # Empty file (ssh ok, no rollback target): refuses with the no-prev message.
  remote() { printf '%s' ""; }
  out="$(read_deployed_sha 2>&1)"
  rc=$?
  [[ ${rc} -ne 0 ]] || { echo "expected non-zero when .deployed-sha empty"; return 1; }
  contains "${out}" "no previous .deployed-sha" || return 1
  contains "${out}" "cannot roll back" || return 1
  # SSH/transport failure (non-zero ssh): refuses with a DISTINCT message, not
  # conflated with an absent file.
  remote() { return 1; }
  out="$(read_deployed_sha 2>&1)"
  rc=$?
  [[ ${rc} -ne 0 ]] || { echo "expected non-zero on ssh failure"; return 1; }
  contains "${out}" "cannot reach" || return 1
}

# --- failed gate: non-zero exit, no internal re-deploy, no sha recorded -----

test_failed_gate_no_internal_redeploy() {
  source "${DEPLOY}"
  export_required_secret_env
  DRY_RUN=0
  DEPLOY_SHA="newsha00"
  local ccalls="${TMPDIR:-/tmp}/wren-cc.$$.${RANDOM}"
  local rcalls="${TMPDIR:-/tmp}/wren-rc.$$.${RANDOM}"
  : > "${ccalls}"; : > "${rcalls}"
  # Stub the daemon + ssh boundary; force the gate to fail.
  compose_run() { shift; printf '%s\n' "$*" >> "${ccalls}"; }
  wait_service_healthy() { return 0; }
  health_gate() { return 1; }
  remote() { printf '%s\n' "$*" >> "${rcalls}"; }
  local rc
  ( main 203.0.113.10 deploy ) >/dev/null 2>&1
  rc=$?
  [[ ${rc} -ne 0 ]] || { echo "expected non-zero exit on failed gate"; return 1; }
  # Exactly the four forward-path compose calls; NO re-pull / re-up rollback.
  equals "$(wc -l < "${ccalls}" | tr -d ' ')" "4" || { echo "compose calls: $(cat "${ccalls}")"; rm -f "${ccalls}" "${rcalls}"; return 1; }
  grep -qx 'pull' "${ccalls}" || { echo "no pull"; rm -f "${ccalls}" "${rcalls}"; return 1; }
  grep -qx 'up -d postgres' "${ccalls}" || { echo "no postgres up"; rm -f "${ccalls}" "${rcalls}"; return 1; }
  grep -qx 'run --rm backend alembic upgrade head' "${ccalls}" || { echo "no migrate"; rm -f "${ccalls}" "${rcalls}"; return 1; }
  grep -qx 'up -d --force-recreate' "${ccalls}" || { echo "no start"; rm -f "${ccalls}" "${rcalls}"; return 1; }
  # .deployed-sha is NEVER written on a failed gate.
  not_contains "$(cat "${rcalls}")" ".deployed-sha" || { rm -f "${ccalls}" "${rcalls}"; return 1; }
  rm -f "${ccalls}" "${rcalls}"
}

test_failed_gate_nonzero_exit_and_no_deployed_sha_write() {
  source "${DEPLOY}"
  export_required_secret_env
  DRY_RUN=0
  DEPLOY_SHA="newsha00"
  local rcalls="${TMPDIR:-/tmp}/wren-rc2.$$.${RANDOM}"
  : > "${rcalls}"
  compose_run() { :; }
  wait_service_healthy() { return 0; }
  health_gate() { return 1; }
  remote() { printf '%s\n' "$*" >> "${rcalls}"; }
  local out rc
  out="$(main 203.0.113.10 deploy 2>&1)"
  rc=$?
  [[ ${rc} -ne 0 ]] || { echo "expected non-zero exit"; rm -f "${rcalls}"; return 1; }
  contains "${out}" "health gate FAILED" || { rm -f "${rcalls}"; return 1; }
  not_contains "$(cat "${rcalls}")" ".deployed-sha" || { echo ".deployed-sha written on failed gate"; rm -f "${rcalls}"; return 1; }
  rm -f "${rcalls}"
}

# --- ingress posture (observability surface not tunnel-routed) --------------

test_api_ingress_blocks_observability_surface_before_backend() {
  local cfg
  cfg="${REPO_DIR}/deployments/cloudflare/config.yml"
  # The AS host (api.usewren.com) must block the observability/health surface at
  # ingress so internal Prometheus data is never tunnel-reachable (mirrors the
  # mcp host; §08). cloudflared is first-match, so the block MUST precede the
  # unrestricted api -> backend:8000 rule, else /metrics routes through to :8000.
  grep -Fq 'metrics|healthz|readyz' "${cfg}" || { echo "no api observability-block rule"; return 1; }
  local block_line backend_line
  block_line="$(grep -n 'metrics|healthz|readyz' "${cfg}" | head -1 | cut -d: -f1)"
  backend_line="$(grep -n 'service: http://backend:8000' "${cfg}" | head -1 | cut -d: -f1)"
  [[ -n "${block_line}" && -n "${backend_line}" && "${block_line}" -lt "${backend_line}" ]] \
    || { echo "block(${block_line}) must precede api->backend(${backend_line})"; return 1; }
  # The block resolves to a 404, not a service route.
  grep -A1 'metrics|healthz|readyz' "${cfg}" | grep -q 'http_status:404' \
    || { echo "observability block is not http_status:404"; return 1; }
  # Regression guard: the mcp host still allow-lists only /mcp + the PRM doc
  # (so its /metrics stays blocked too).
  grep -Fq 'oauth-protected-resource)$' "${cfg}" || { echo "mcp allow-list changed"; return 1; }
}

# --- run all ----------------------------------------------------------------

main_tests() {
  run_test test_filter_first_party_images
  run_test test_gate_unhealthy_jsonl
  run_test test_gate_unhealthy_flags_exited_container_with_empty_health
  run_test test_gate_unhealthy_array_and_all_healthy
  run_test test_gate_unhealthy_empty_or_unparseable_is_not_healthy
  run_test test_assert_secret_env_present
  run_test test_dry_run_uses_docker_context_and_no_ssh_heredoc
  run_test test_dry_run_migrations_before_start
  run_test test_dry_run_pull_migrate_up_use_overlay_and_profile
  run_test test_compose_tunnel_overlay_declares_environment_sourced_secrets_and_ingress
  run_test test_compose_tunnel_overlay_targets_uids_modes_no_file_source
  run_test test_compose_base_declares_environment_sourced_prometheus_configs
  run_test test_compose_deploy_overlay_feeds_app_env_from_env_prod_and_secrets
  run_test test_cd_frontend_image_bakes_prod_api_and_mcp_origins
  run_test test_read_deployed_sha_returns_prev_and_refuses_on_empty
  run_test test_failed_gate_no_internal_redeploy
  run_test test_failed_gate_nonzero_exit_and_no_deployed_sha_write
  run_test test_api_ingress_blocks_observability_surface_before_backend

  echo "-----------------------------------------------------------------------"
  printf '%d passed, %d failed\n' "${PASS}" "${FAIL}"
  [[ ${FAIL} -eq 0 ]]
}

main_tests
