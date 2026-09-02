#!/usr/bin/env bash
# =============================================================================
# Tests for scripts/ops/list-users.sh (VPS user listing, read-only).
#
# Plain-bash harness (no external test runner), mirroring deploy_test.sh.
# Exercises everything verifiable WITHOUT a live VPS or postgres container:
#   - limit validation, the exact query shape, no password_hash
# Live execution against the real box is out of scope for this harness.
#
# Run: scripts/tests/list_users_test.sh
# =============================================================================
#
# Test harness: functions defined here are stubs invoked indirectly by the
# sourced script (via main), and vars set here are consumed by it.
# shellcheck disable=SC1090,SC2034,SC2329,SC2016
set -uo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."
LIST_USERS="${SCRIPTS_DIR}/ops/list-users.sh"
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

# --- list-users.sh ----------------------------------------------------------

test_list_users_queries_recent_users() {
  local out
  docker() { printf 'docker %s\n' "$*"; }
  out="$(source "${LIST_USERS}"; main 5)"
  contains "${out}" "docker exec wren-postgres-1 psql -U wren -d wren -c" || return 1
  contains "${out}" "ORDER BY created_at DESC LIMIT 5" || return 1
  not_contains "${out}" "password_hash" || return 1
}

test_list_users_defaults_to_ten() {
  local out
  docker() { printf 'docker %s\n' "$*"; }
  out="$(source "${LIST_USERS}"; main)"
  contains "${out}" "LIMIT 10" || return 1
}

test_list_users_rejects_non_numeric_limit() {
  local rc
  docker() { :; }
  ( source "${LIST_USERS}"; main abc ) >/dev/null 2>&1
  rc=$?
  [[ ${rc} -ne 0 ]] || { echo "expected non-zero for non-numeric limit"; return 1; }
}

# --- run all ----------------------------------------------------------------

main_tests() {
  run_test test_list_users_queries_recent_users
  run_test test_list_users_defaults_to_ten
  run_test test_list_users_rejects_non_numeric_limit

  echo "-----------------------------------------------------------------------"
  printf '%d passed, %d failed\n' "${PASS}" "${FAIL}"
  [[ ${FAIL} -eq 0 ]]
}

main_tests