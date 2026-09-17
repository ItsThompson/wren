#!/usr/bin/env bash
# Tests for scripts/sentry-release.sh. These tests replace only the external
# Sentry API and CLI boundaries; release state and idempotency stay real.
set -uo pipefail

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../sentry-release.sh"
PASS=0
FAIL=0

run_test() {
  local name="$1" output rc
  output="$("${name}" 2>&1)"
  rc=$?
  if [[ ${rc} -eq 0 ]]; then
    printf 'ok   - %s\n' "${name#test_}"
    PASS=$((PASS + 1))
  else
    printf 'FAIL - %s\n%s\n' "${name#test_}" "${output}" | sed 's/^/       /'
    FAIL=$((FAIL + 1))
  fi
}

contains() { [[ "$1" == *"$2"* ]] || { echo "expected to contain: $2"; return 1; }; }
not_contains() { [[ "$1" != *"$2"* ]] || { echo "expected not to contain: $2"; return 1; }; }
equals() { [[ "$1" == "$2" ]] || { echo "expected '$2', got '$1'"; return 1; }; }

setup_state() {
  source "${SCRIPT}"
  set +e
  SENTRY_ORG=t-industries
  SENTRY_AUTH_TOKEN=secret-token
  SENTRY_CLI_BIN=true
  STATE_FILE="${TMPDIR:-/tmp}/wren-sentry-state.$$.${RANDOM}"
  : > "${STATE_FILE}"
  CLI_CALLS=0
  inspect_release() {
    local release="$1" project="$2" row
    row="$(grep -F "${release}|${project}|" "${STATE_FILE}" | head -1 || true)"
    [[ -n "${row}" ]] || return 10
    RELEASE_FINALIZED="$(printf '%s' "${row}" | cut -d'|' -f3)"
    return 0
  }
  run_cli() {
    CLI_CALLS=$((CLI_CALLS + 1))
    local release="${@: -1}" project
    if [[ "${1:-}" == "--org" && "${4:-}" == "finalize" ]]; then
      sed "s#^${release}|#${release}|#" "${STATE_FILE}" | sed 's/|false$/|true/' > "${STATE_FILE}.tmp"
      mv "${STATE_FILE}.tmp" "${STATE_FILE}"
    else
      project="${6:-}"
      printf '%s|%s|false\n' "${release}" "${project}" >> "${STATE_FILE}"
    fi
  }
}

test_release_names_are_exact_and_sha_is_not_prefixed_twice() {
  setup_state
  equals "$(release_name backend abc123)" "wren-backend@abc123" || return 1
  equals "$(release_name mcp abc123)" "wren-mcp@abc123" || return 1
  equals "$(release_name web abc123)" "wren-web@abc123" || return 1
  for_each_release prepare abc123
  grep -Fq 'wren-backend@abc123|wren-backend|' "${STATE_FILE}" || return 1
  grep -Fq 'wren-mcp@abc123|wren-mcp|' "${STATE_FILE}" || return 1
  grep -Fq 'wren-web@abc123|wren-frontend|' "${STATE_FILE}" || return 1
}

test_prepare_is_idempotent_and_only_creates_missing_release() {
  setup_state
  printf '%s\n' 'wren-backend@abc123|wren-backend|false' 'wren-mcp@abc123|wren-mcp|false' > "${STATE_FILE}"
  for_each_release prepare abc123
  equals "${CLI_CALLS}" "1" || return 1
  grep -Fq 'wren-web@abc123|wren-frontend|' "${STATE_FILE}" || return 1
  for_each_release prepare abc123
  equals "${CLI_CALLS}" "1" || return 1
}

test_create_failure_is_accepted_only_when_postcondition_exists() {
  setup_state
  run_cli() { return 1; }
  inspect_release() {
    grep -Fq "$1|$2|" "${STATE_FILE}" || return 10
    RELEASE_FINALIZED=false
  }
  # A failed CLI with no exact release remains a hard failure.
  local output rc
  output="$(ensure_prepared wren-backend@abc123 wren-backend 2>&1)"
  rc=$?
  [[ ${rc} -ne 0 ]] || return 1
  contains "${output}" "release creation did not produce" || return 1

  # A lost create response is safe when the API now shows the exact release.
  printf '%s\n' 'wren-backend@abc123|wren-backend|false' >> "${STATE_FILE}"
  ensure_prepared wren-backend@abc123 wren-backend
}

test_wrong_project_is_rejected_without_leaking_token() {
  setup_state
  printf '%s\n' 'wren-backend@abc123|another-project|false' > "${STATE_FILE}"
  inspect_release() {
    grep -Fq "${1}|" "${STATE_FILE}" && return 1
    return 10
  }
  local output rc
  output="$(ensure_prepared wren-backend@abc123 wren-backend 2>&1)"
  rc=$?
  [[ ${rc} -ne 0 ]] || return 1
  contains "${output}" "cannot inspect release before preparation" || return 1
  not_contains "${output}" "secret-token" || return 1
}

test_finalize_is_idempotent_and_preserves_finalized_release() {
  setup_state
  printf '%s\n' 'wren-backend@abc123|wren-backend|false' > "${STATE_FILE}"
  ensure_finalized wren-backend@abc123 wren-backend
  equals "${CLI_CALLS}" "1" || return 1
  ensure_finalized wren-backend@abc123 wren-backend
  equals "${CLI_CALLS}" "1" || return 1
}

test_finalize_requires_existing_release() {
  setup_state
  local output rc
  output="$(ensure_finalized wren-backend@abc123 wren-backend 2>&1)"
  rc=$?
  [[ ${rc} -ne 0 ]] || return 1
  contains "${output}" "cannot finalize an absent" || return 1
}

main_tests() {
  run_test test_release_names_are_exact_and_sha_is_not_prefixed_twice
  run_test test_prepare_is_idempotent_and_only_creates_missing_release
  run_test test_create_failure_is_accepted_only_when_postcondition_exists
  run_test test_wrong_project_is_rejected_without_leaking_token
  run_test test_finalize_is_idempotent_and_preserves_finalized_release
  run_test test_finalize_requires_existing_release
  printf '%s\n' '---------------------------------------------------------------'
  printf '%d passed, %d failed\n' "${PASS}" "${FAIL}"
  [[ ${FAIL} -eq 0 ]]
}

main_tests
