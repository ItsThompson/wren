#!/usr/bin/env bash
# =============================================================================
# Tests for scripts/ops/user-counts.sh (VPS per-user row counts, read-only).
#
# Plain-bash harness (no external test runner), mirroring list_users_test.sh / delete_user_test.sh.
# Exercises everything verifiable WITHOUT a live VPS or postgres container:
#   - the argument is required and must be a 32-char uuid4 hex
#   - the exact counts query shape, including all eight tables
#   - the WREN_PG_CONTAINER override is honored
# Live execution against the real box is out of scope for this harness.
#
# Run: scripts/tests/user_counts_test.sh
# =============================================================================
#
# Test harness: functions defined here are stubs invoked indirectly by the
# sourced script (via main), and vars set here are consumed by it.
# shellcheck disable=SC1090,SC2034,SC2329,SC2016
set -uo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."
USER_COUNTS="${SCRIPTS_DIR}/ops/user-counts.sh"
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

# --- user-counts.sh ---------------------------------------------------------

source "${USER_COUNTS}"

# Stub the docker boundary (the real call is `docker exec ... psql ...`). The
# script only calls `pg -c "<SQL>"`, so capture the SQL for assertions. Every
# call is appended to PG_LOG (a file, which survives subshells).
docker() {
  if [[ -n "${PG_LOG:-}" ]]; then printf 'docker %s\n' "${*//$'\n'/ }" >> "${PG_LOG}"; fi
  printf '%s\n' "${PG_OUT:-}"
}

test_main_requires_user_id() {
  local rc
  ( main ) >/dev/null 2>&1
  rc=$?
  [[ ${rc} -ne 0 ]] || { echo "expected non-zero without user_id"; return 1; }
}

test_main_rejects_empty_user_id() {
  local rc
  ( main "" ) >/dev/null 2>&1
  rc=$?
  [[ ${rc} -ne 0 ]] || { echo "expected non-zero for empty user_id"; return 1; }
}

test_main_rejects_non_hex_user_id() {
  local rc
  ( main "not-a-real-id-zzzzzzzzzzzzzzz" ) >/dev/null 2>&1
  rc=$?
  [[ ${rc} -ne 0 ]] || { echo "expected non-zero for non-hex user_id"; return 1; }
}

test_main_rejects_short_user_id() {
  local rc
  ( main "abc123" ) >/dev/null 2>&1
  rc=$?
  [[ ${rc} -ne 0 ]] || { echo "expected non-zero for short user_id"; return 1; }
}

test_main_rejects_dashed_uuid() {
  local rc
  # The app uses uuid4().hex (no dashes); a canonical dashed uuid must be
  # rejected so it is never silently interpolated.
  ( main "8c31dcfb-91dc-420f-8bbe-5e63a7c631f2" ) >/dev/null 2>&1
  rc=$?
  [[ ${rc} -ne 0 ]] || { echo "expected non-zero for dashed uuid"; return 1; }
}

test_counts_sql_covers_all_tables() {
  USER_ID="8c31dcfb91dc420f8bbe5e63a7c631f2"
  local sql tbl
  sql="$(counts_sql)"
  for tbl in users roadmaps progress oauth_grants oauth_authorization_codes \
             oauth_refresh_tokens oauth_audit_log revoked_sessions; do
    contains "${sql}" "${tbl}" || return 1
  done
}

test_counts_sql_interpolates_user_id() {
  USER_ID="8c31dcfb91dc420f8bbe5e63a7c631f2"
  local sql
  sql="$(counts_sql)"
  contains "${sql}" "WHERE id = '8c31dcfb91dc420f8bbe5e63a7c631f2'" || return 1
  contains "${sql}" "WHERE owner = '8c31dcfb91dc420f8bbe5e63a7c631f2'" || return 1
  contains "${sql}" "WHERE user_id = '8c31dcfb91dc420f8bbe5e63a7c631f2'" || return 1
}

test_counts_sql_is_union_all() {
  USER_ID="8c31dcfb91dc420f8bbe5e63a7c631f2"
  local sql
  sql="$(counts_sql)"
  # Eight rows => seven UNION ALL separators.
  local n
  n="$(printf '%s' "${sql}" | grep -c 'UNION ALL' || true)"
  equals "${n}" "7" || return 1
}

test_main_runs_counts_query() {
  PG_LOG="$(mktemp)"
  PG_OUT="users|1"
  main "8c31dcfb91dc420f8bbe5e63a7c631f2" >/dev/null 2>&1
  local sql
  sql="$(sed -n '1p' "${PG_LOG}")"
  contains "${sql}" "docker exec wren-postgres-1 psql -U wren -d wren -c" || { rm -f "${PG_LOG}"; return 1; }
  contains "${sql}" "SELECT 'users' AS tbl" || { rm -f "${PG_LOG}"; return 1; }
  rm -f "${PG_LOG}"
}

# PG_CONTAINER is bound at source time from WREN_PG_CONTAINER, so the override
# can only be observed by re-sourcing the script with the env set. Do that in a
# subshell with a local docker stub that records the call into PG_LOG.
test_main_honors_container_override() {
  PG_LOG="$(mktemp)"
  local sql
  sql="$(
    WREN_PG_CONTAINER="custom-pg"
    docker() { printf 'docker %s\n' "${*//$'\n'/ }" >> "${PG_LOG}"; }
    source "${USER_COUNTS}"
    main "8c31dcfb91dc420f8bbe5e63a7c631f2" >/dev/null 2>&1
  )"
  contains "$(sed -n '1p' "${PG_LOG}")" "docker exec custom-pg psql" \
    || { rm -f "${PG_LOG}"; return 1; }
  rm -f "${PG_LOG}"
}

test_main_outputs_psql_result() {
  PG_LOG="$(mktemp)"
  PG_OUT="users|1
roadmaps|0
progress|0
oauth_grants|0
oauth_authorization_codes|0
oauth_refresh_tokens|0
oauth_audit_log|0
revoked_sessions|0"
  local out
  out="$(main "8c31dcfb91dc420f8bbe5e63a7c631f2")"
  contains "${out}" "users|1" || { rm -f "${PG_LOG}"; return 1; }
  rm -f "${PG_LOG}"
}

# --- run all ----------------------------------------------------------------

main_tests() {
  run_test test_main_requires_user_id
  run_test test_main_rejects_empty_user_id
  run_test test_main_rejects_non_hex_user_id
  run_test test_main_rejects_short_user_id
  run_test test_main_rejects_dashed_uuid
  run_test test_counts_sql_covers_all_tables
  run_test test_counts_sql_interpolates_user_id
  run_test test_counts_sql_is_union_all
  run_test test_main_runs_counts_query
  run_test test_main_honors_container_override
  run_test test_main_outputs_psql_result

  echo "-----------------------------------------------------------------------"
  printf '%d passed, %d failed\n' "${PASS}" "${FAIL}"
  [[ ${FAIL} -eq 0 ]]
}

main_tests