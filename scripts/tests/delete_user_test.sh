#!/usr/bin/env bash
# =============================================================================
# Tests for scripts/ops/delete-user.sh (VPS user deletion, destructive).
#
# Plain-bash harness (no external test runner), mirroring deploy_test.sh.
# Exercises everything verifiable WITHOUT a live VPS or postgres container:
#   - username resolution, dry-run table coverage,
#     review-vs-commit SQL (BEGIN without COMMIT vs COMMIT), the two
#     confirmation gates, and the post-delete verification
# Live execution against the real box is out of scope for this harness.
#
# Run: scripts/tests/delete_user_test.sh
# =============================================================================
#
# Test harness: functions defined here are stubs invoked indirectly by the
# sourced script (via main), and vars set here are consumed by it.
# shellcheck disable=SC1090,SC2034,SC2329,SC2016
set -uo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."
DELETE_USER="${SCRIPTS_DIR}/ops/delete-user.sh"
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

# --- delete-user.sh ---------------------------------------------------------

source "${DELETE_USER}"

# Stub the docker boundary (the real call is `docker exec ... psql ...`). The
# response is keyed on the SQL content, so no cross-subshell state is needed:
# the scripts call pg inside $(...) subshells, where variable mutations would
# be lost. Every call is appended to PG_LOG (a file, which survives subshells)
# for tests that inspect the SQL that was sent.
docker() {
  # One log line per call (newlines flattened) so tests can address calls by line.
  if [[ -n "${PG_LOG:-}" ]]; then printf '%s\n' "${*//$'\n'/ }" >> "${PG_LOG}"; fi
  case "$*" in
    *"SELECT id, email FROM users"*) printf '%s\n' "${PG_RESOLVE:-}";;
    *"SELECT 'users' AS tbl"*) printf '%s\n' "${PG_COUNTS:-}";;
    *"BEGIN;"*"COMMIT;"*) printf '%s\n' "${PG_COMMIT_OUT:-DELETE 1}";;
    *"BEGIN;"*) printf '%s\n' "${PG_REVIEW_OUT:-DELETE 1}";;
    *"SELECT count(*) FROM users"*) printf '%s\n' "${PG_VERIFY:-0}";;
    *) printf '%s\n' "";;
  esac
}
# Stub the confirmation gate: CONFIRM_RC=0 accepts, 1 refuses.
confirm() { return "${CONFIRM_RC:-0}"; }

EMPTY_COUNTS="users|1
roadmaps|0
progress|0
oauth_grants|0
oauth_authorization_codes|0
oauth_refresh_tokens|0
oauth_audit_log|0
revoked_sessions|0"

test_resolve_user_found() {
  PG_LOG="$(mktemp)"
  PG_RESOLVE="8c31dcfb91dc420f8bbe5e63a7c631f2|idk@example.com"
  resolve_user "idk"
  equals "${USER_ID}" "8c31dcfb91dc420f8bbe5e63a7c631f2" || { rm -f "${PG_LOG}"; return 1; }
  equals "${USER_EMAIL}" "idk@example.com" || { rm -f "${PG_LOG}"; return 1; }
  contains "$(cat "${PG_LOG}")" "SELECT id, email FROM users WHERE username = 'idk'" \
    || { rm -f "${PG_LOG}"; return 1; }
  rm -f "${PG_LOG}"
}

test_resolve_user_not_found() {
  PG_LOG="$(mktemp)"
  PG_RESOLVE=""
  local rc
  ( resolve_user "ghost" ) >/dev/null 2>&1
  rc=$?
  [[ ${rc} -ne 0 ]] || { echo "expected non-zero for unknown user"; rm -f "${PG_LOG}"; return 1; }
  rm -f "${PG_LOG}"
}

test_dry_run_covers_all_tables() {
  PG_LOG="$(mktemp)"
  PG_COUNTS="${EMPTY_COUNTS}"
  USER_ID="8c31dcfb91dc420f8bbe5e63a7c631f2"
  dry_run >/dev/null 2>&1
  local sql tbl
  sql="$(sed -n '1p' "${PG_LOG}")"
  for tbl in users roadmaps progress oauth_grants oauth_authorization_codes oauth_refresh_tokens oauth_audit_log revoked_sessions; do
    contains "${sql}" "${tbl}" || { rm -f "${PG_LOG}"; return 1; }
  done
  rm -f "${PG_LOG}"
}

test_dry_run_warns_on_non_empty_account() {
  PG_LOG="$(mktemp)"
  PG_COUNTS="users|1
roadmaps|2
progress|0
oauth_grants|0
oauth_authorization_codes|0
oauth_refresh_tokens|0
oauth_audit_log|0
revoked_sessions|0"
  USER_ID="8c31dcfb91dc420f8bbe5e63a7c631f2"
  local out
  out="$(dry_run 2>&1)"
  contains "${out}" "WARNING" || { rm -f "${PG_LOG}"; return 1; }
  contains "${out}" "roadmaps|2" || { rm -f "${PG_LOG}"; return 1; }
  rm -f "${PG_LOG}"
}

test_delete_sql_review_has_begin_no_commit() {
  USER_ID="8c31dcfb91dc420f8bbe5e63a7c631f2"
  local sql
  sql="$(delete_sql "")"
  contains "${sql}" "BEGIN;" || return 1
  not_contains "${sql}" "COMMIT" || return 1
  contains "${sql}" "DELETE FROM users" || return 1
}

test_delete_sql_commit_has_commit() {
  USER_ID="8c31dcfb91dc420f8bbe5e63a7c631f2"
  local sql
  sql="$(delete_sql commit)"
  contains "${sql}" "COMMIT;" || return 1
}

test_verify_deleted_passes_when_zero() {
  PG_LOG="$(mktemp)"
  PG_VERIFY="0"
  USER_ID="8c31dcfb91dc420f8bbe5e63a7c631f2"
  verify_deleted || { echo "expected pass when 0 remain"; rm -f "${PG_LOG}"; return 1; }
  rm -f "${PG_LOG}"
}

test_verify_deleted_fails_when_rows_remain() {
  PG_LOG="$(mktemp)"
  PG_VERIFY="1"
  USER_ID="8c31dcfb91dc420f8bbe5e63a7c631f2"
  local rc
  ( verify_deleted ) >/dev/null 2>&1
  rc=$?
  [[ ${rc} -ne 0 ]] || { echo "expected non-zero when rows remain"; rm -f "${PG_LOG}"; return 1; }
  rm -f "${PG_LOG}"
}

test_main_requires_username() {
  local rc
  ( main ) >/dev/null 2>&1
  rc=$?
  [[ ${rc} -ne 0 ]] || { echo "expected non-zero without username"; return 1; }
}

test_main_rejects_invalid_username() {
  local rc
  ( main "bad'name" ) >/dev/null 2>&1
  rc=$?
  [[ ${rc} -ne 0 ]] || { echo "expected non-zero for invalid username"; return 1; }
}

test_main_aborts_when_confirmation_refused() {
  PG_LOG="$(mktemp)"
  PG_RESOLVE="8c31dcfb91dc420f8bbe5e63a7c631f2|idk@example.com"
  PG_COUNTS="${EMPTY_COUNTS}"
  CONFIRM_RC=1
  local rc
  ( main "idk" ) >/dev/null 2>&1
  rc=$?
  [[ ${rc} -ne 0 ]] || { echo "expected non-zero when confirmation refused"; rm -f "${PG_LOG}"; return 1; }
  # No delete SQL was ever sent (only resolve + the two dry-run calls).
  equals "$(grep -c 'DELETE FROM' "${PG_LOG}" || true)" "0" \
    || { rm -f "${PG_LOG}"; return 1; }
  rm -f "${PG_LOG}"
}

test_main_full_flow_with_confirmations() {
  PG_LOG="$(mktemp)"
  PG_RESOLVE="8c31dcfb91dc420f8bbe5e63a7c631f2|idk@example.com"
  PG_COUNTS="${EMPTY_COUNTS}"
  PG_REVIEW_OUT="DELETE 1"
  PG_COMMIT_OUT="DELETE 1"
  PG_VERIFY="0"
  CONFIRM_RC=0
  local rc review_line commit_line
  ( main "idk" ) >/dev/null 2>&1
  rc=$?
  [[ ${rc} -eq 0 ]] || { echo "expected success"; rm -f "${PG_LOG}"; return 1; }
  # The two BEGIN lines are the review (no COMMIT) and the commit (has COMMIT).
  review_line="$(grep 'BEGIN;' "${PG_LOG}" | sed -n '1p')"
  commit_line="$(grep 'BEGIN;' "${PG_LOG}" | sed -n '2p')"
  not_contains "${review_line}" "COMMIT" || { rm -f "${PG_LOG}"; return 1; }
  contains "${commit_line}" "COMMIT" || { rm -f "${PG_LOG}"; return 1; }
  rm -f "${PG_LOG}"
}

# --- run all ----------------------------------------------------------------

main_tests() {
  run_test test_resolve_user_found
  run_test test_resolve_user_not_found
  run_test test_dry_run_covers_all_tables
  run_test test_dry_run_warns_on_non_empty_account
  run_test test_delete_sql_review_has_begin_no_commit
  run_test test_delete_sql_commit_has_commit
  run_test test_verify_deleted_passes_when_zero
  run_test test_verify_deleted_fails_when_rows_remain
  run_test test_main_requires_username
  run_test test_main_rejects_invalid_username
  run_test test_main_aborts_when_confirmation_refused
  run_test test_main_full_flow_with_confirmations

  echo "-----------------------------------------------------------------------"
  printf '%d passed, %d failed\n' "${PASS}" "${FAIL}"
  [[ ${FAIL} -eq 0 ]]
}

main_tests