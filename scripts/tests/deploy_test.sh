#!/usr/bin/env bash
# =============================================================================
# Tests for scripts/deploy.sh.
#
# Plain-bash harness (no external test runner) so it runs anywhere bash does,
# including CI. Exercises everything verifiable WITHOUT a live VPS:
#   - pure helpers (image filtering, health parsing)
#   - the dry-run phase plan and ordering
#   - the rollback path (via a stubbed SSH boundary)
# Live execution against a real box is Ticket 32.
#
# Run: scripts/tests/deploy_test.sh   (or: just test-deploy)
# =============================================================================
#
# Test harness: functions defined here are stubs invoked indirectly by the
# sourced deploy.sh (via main/rollback), and vars set here are consumed by it.
# shellcheck disable=SC1090,SC2034,SC2329
set -uo pipefail

DEPLOY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../deploy.sh"
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

make_cred_dir() {
  local d="${BATS_TMP:-${TMPDIR:-/tmp}}/wren-cred.$$.${RANDOM}"
  mkdir -p "${d}"
  printf '{}\n' > "${d}/credentials.json"
  printf 'FAKE\n' > "${d}/cert.pem"
  printf '%s' "${d}"
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
  # A transient SSH blip (empty output) must NOT read as healthy, or the gate
  # would falsely pass and suppress the rollback that is its whole purpose.
  local empty_out garbage_out
  empty_out="$(printf '' | gate_unhealthy)"
  garbage_out="$(printf 'not json at all' | gate_unhealthy)"
  [[ -n "${empty_out}" ]] || { echo "empty input read as healthy"; return 1; }
  [[ -n "${garbage_out}" ]] || { echo "unparseable input read as healthy"; return 1; }
}

# --- dry-run phase plan & ordering ------------------------------------------

test_dry_run_full_phase_sequence() {
  source "${DEPLOY}"
  CRED_DIR="$(make_cred_dir)"
  DRY_RUN=1
  DEPLOY_SHA="cafef00d"
  local out
  out="$(main 203.0.113.10 deploy 2>&1)"
  contains "${out}" "Phase 1: preflight" || return 1
  contains "${out}" "Phase 2: SSH probe" || return 1
  contains "${out}" "Phase 3: idempotent dependency install" || return 1
  contains "${out}" "Phase 4: docker daemon config" || return 1
  contains "${out}" "Phase 5: daily docker prune cron" || return 1
  contains "${out}" "Phase 6: repo sync" || return 1
  contains "${out}" "Phase 7: copy tunnel credentials" || return 1
  contains "${out}" "Phase 8: assert .env + OAuth key" || return 1
  contains "${out}" "Phase 9a: render tunnel config" || return 1
  contains "${out}" "Phase 9a: render Alertmanager config" || return 1
  contains "${out}" "Phase 10: migrations" || return 1
  contains "${out}" "Phase 11: start stack" || return 1
  contains "${out}" "Phase 12: health gate" || return 1
  contains "${out}" "Deploy complete" || return 1
}

test_dry_run_migrations_before_start() {
  source "${DEPLOY}"
  CRED_DIR="$(make_cred_dir)"
  DRY_RUN=1
  local out mig start
  out="$(main 203.0.113.10 deploy 2>&1)"
  mig="$(printf '%s\n' "${out}" | grep -n 'alembic upgrade head' | head -1 | cut -d: -f1)"
  start="$(printf '%s\n' "${out}" | grep -n 'Phase 11: start stack' | head -1 | cut -d: -f1)"
  [[ -n "${mig}" && -n "${start}" ]] || { echo "missing markers mig=${mig} start=${start}"; return 1; }
  [[ "${mig}" -lt "${start}" ]] || { echo "migrations (${mig}) not before start (${start})"; return 1; }
}

test_dry_run_pull_and_start_use_overlay_and_profile() {
  source "${DEPLOY}"
  CRED_DIR="$(make_cred_dir)"
  DRY_RUN=1
  local out
  out="$(main 203.0.113.10 deploy 2>&1)"
  contains "${out}" "-f docker-compose.yml -f docker-compose.tunnel.yml --profile tunnels pull" || return 1
  contains "${out}" "-f docker-compose.yml -f docker-compose.tunnel.yml --profile tunnels up -d" || return 1
}

test_preflight_fails_on_missing_credential() {
  source "${DEPLOY}"
  CRED_DIR="${TMPDIR:-/tmp}/wren-empty.$$.${RANDOM}"
  mkdir -p "${CRED_DIR}"
  DRY_RUN=1
  local out rc
  out="$(preflight_credentials 2>&1)"
  rc=$?
  [[ ${rc} -ne 0 ]] || { echo "expected non-zero exit"; return 1; }
  contains "${out}" "tunnel credential not found" || return 1
}

# --- rollback ---------------------------------------------------------------

test_rollback_repulls_all_first_party_pins_git_and_up() {
  source "${DEPLOY}"
  DRY_RUN=0
  REMOTE_DIR="/opt/wren"
  COMPOSE_TUNNEL="docker compose -f docker-compose.yml -f docker-compose.tunnel.yml --profile tunnels"
  local calls="${TMPDIR:-/tmp}/wren-calls.$$.${RANDOM}"
  : > "${calls}"
  # Stub the SSH boundary and the derived image list.
  remote() { printf '%s\n' "$*" >> "${calls}"; }
  first_party_images() { printf '%s\n' "ghcr.io/o/wren/backend" "ghcr.io/o/wren/mcp" "ghcr.io/o/wren/frontend"; }
  render_configs() { :; }

  rollback "abc123" >/dev/null 2>&1

  grep -qF "docker pull ghcr.io/o/wren/backend:sha-abc123" "${calls}" || { echo "backend not re-pulled"; return 1; }
  grep -qF "docker pull ghcr.io/o/wren/mcp:sha-abc123" "${calls}" || { echo "mcp not re-pulled"; return 1; }
  grep -qF "docker pull ghcr.io/o/wren/frontend:sha-abc123" "${calls}" || { echo "frontend not re-pulled"; return 1; }
  grep -qF "git -C /opt/wren reset --hard abc123" "${calls}" || { echo "git not pinned"; return 1; }
  grep -qF "WREN_IMAGE_TAG=sha-abc123" "${calls}" || { echo "up not tagged to prev sha"; return 1; }
  grep -q "up -d" "${calls}" || { echo "stack not brought up"; return 1; }
  rm -f "${calls}"
}

test_rollback_without_prev_sha_cannot_proceed() {
  source "${DEPLOY}"
  DRY_RUN=0
  local out rc
  out="$(rollback "" 2>&1)"
  rc=$?
  [[ ${rc} -ne 0 ]] || { echo "expected non-zero exit"; return 1; }
  contains "${out}" "cannot roll back" || return 1
}

test_failed_health_gate_triggers_rollback_and_nonzero_exit() {
  source "${DEPLOY}"
  CRED_DIR="$(make_cred_dir)"
  DRY_RUN=1
  local rbfile="${TMPDIR:-/tmp}/wren-rb.$$.${RANDOM}"
  : > "${rbfile}"
  # Pin a known previous SHA (real sync_repo derives it from the box), force the
  # gate to fail, and record that rollback ran with that SHA.
  sync_repo() { PREV_SHA="oldsha99"; CURRENT_SHA="newsha00"; }
  health_gate() { return 1; }
  rollback() { printf 'ROLLBACK prev=%s\n' "$1" >> "${rbfile}"; return 0; }
  local out rc
  out="$(main 203.0.113.10 deploy 2>&1)"
  rc=$?
  [[ ${rc} -ne 0 ]] || { echo "expected non-zero exit"; return 1; }
  contains "${out}" "health gate FAILED" || return 1
  contains "${out}" "rolled back to oldsha99" || return 1
  grep -qF "ROLLBACK prev=oldsha99" "${rbfile}" || { echo "rollback not invoked with prev sha"; return 1; }
  rm -f "${rbfile}"
}

# --- run all ----------------------------------------------------------------

main_tests() {
  run_test test_filter_first_party_images
  run_test test_gate_unhealthy_jsonl
  run_test test_gate_unhealthy_flags_exited_container_with_empty_health
  run_test test_gate_unhealthy_array_and_all_healthy
  run_test test_gate_unhealthy_empty_or_unparseable_is_not_healthy
  run_test test_dry_run_full_phase_sequence
  run_test test_dry_run_migrations_before_start
  run_test test_dry_run_pull_and_start_use_overlay_and_profile
  run_test test_preflight_fails_on_missing_credential
  run_test test_rollback_repulls_all_first_party_pins_git_and_up
  run_test test_rollback_without_prev_sha_cannot_proceed
  run_test test_failed_health_gate_triggers_rollback_and_nonzero_exit

  echo "-----------------------------------------------------------------------"
  printf '%d passed, %d failed\n' "${PASS}" "${FAIL}"
  [[ ${FAIL} -eq 0 ]]
}

main_tests