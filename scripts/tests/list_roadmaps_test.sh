#!/usr/bin/env bash
# =============================================================================
# Tests for scripts/ops/list-roadmaps.sh (VPS roadmap listing, read-only).
#
# Plain-bash harness (no external test runner), mirroring list_users_test.sh.
# Exercises the query shape without a live VPS or postgres container.
#
# Run: scripts/tests/list_roadmaps_test.sh
# =============================================================================
#
# Test harness: docker is stubbed and invoked indirectly by the sourced script.
# shellcheck disable=SC1090,SC2329
set -uo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/.."
LIST_ROADMAPS="${SCRIPTS_DIR}/ops/list-roadmaps.sh"
PASS=0
FAIL=0

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

contains() { [[ "$1" == *"$2"* ]] || { echo "expected to contain: $2"; return 1; }; }
test_list_roadmaps_queries_recent_roadmaps() {
  local out
  docker() { printf 'docker %s\n' "$*"; }
  out="$(source "${LIST_ROADMAPS}"; main)"
  contains "${out}" "docker exec wren-postgres-1 psql -U wren -d wren -c" || return 1
  contains "${out}" "SELECT id, title, owner, status, published_visibility, revision, created_at, updated_at" || return 1
  contains "${out}" "FROM roadmaps" || return 1
  contains "${out}" "ORDER BY updated_at DESC" || return 1
}

test_list_roadmaps_uses_container_override() {
  local out
  docker() { printf 'docker %s\n' "$*"; }
  out="$(WREN_PG_CONTAINER=custom-postgres source "${LIST_ROADMAPS}"; main)"
  contains "${out}" "docker exec custom-postgres psql" || return 1
}

main_tests() {
  run_test test_list_roadmaps_queries_recent_roadmaps
  run_test test_list_roadmaps_uses_container_override

  echo "-----------------------------------------------------------------------"
  printf '%d passed, %d failed\n' "${PASS}" "${FAIL}"
  [[ ${FAIL} -eq 0 ]]
}

main_tests
