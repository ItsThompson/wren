#!/usr/bin/env bash
# Manage the three Wren Sentry releases for one deploy SHA.
#
# Usage:
#   SENTRY_AUTH_TOKEN=... SENTRY_ORG=... ./scripts/sentry-release.sh prepare <sha>
#   SENTRY_AUTH_TOKEN=... SENTRY_ORG=... ./scripts/sentry-release.sh finalize <sha>
#
# The API is the source of truth for existence and project association. The
# CLI performs mutations so the same pinned binary used by the frontend owns
# release creation and finalization. API responses are kept in mode-0600 temp
# files and never printed, which prevents project metadata or credentials from
# entering workflow logs.

set -euo pipefail

SENTRY_API_ROOT="${SENTRY_API_ROOT:-${SENTRY_API_URL:-https://sentry.io/api/0}}"
SENTRY_API_ROOT="${SENTRY_API_ROOT%/}"
SENTRY_ORG="${SENTRY_ORG:-}"
SENTRY_AUTH_TOKEN="${SENTRY_AUTH_TOKEN:-}"
SENTRY_CLI_BIN="${SENTRY_CLI_BIN:-sentry-cli}"
SENTRY_PROJECT_BACKEND="${SENTRY_PROJECT_BACKEND:-wren-backend}"
SENTRY_PROJECT_MCP="${SENTRY_PROJECT_MCP:-wren-mcp}"
SENTRY_PROJECT_FRONTEND="${SENTRY_PROJECT_FRONTEND:-wren-frontend}"

log() { printf '%s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

require_config() {
  [[ -n "${SENTRY_ORG}" ]] || die "SENTRY_ORG is required"
  [[ -n "${SENTRY_AUTH_TOKEN}" ]] || die "SENTRY_AUTH_TOKEN is required"
  command -v "${SENTRY_CLI_BIN}" >/dev/null 2>&1 \
    || die "Sentry CLI not found: ${SENTRY_CLI_BIN}"
}

validate_sha() {
  local sha="$1"
  [[ "${sha}" =~ ^[0-9a-f]{40}$ ]] \
    || die "release SHA must be 40 lowercase hexadecimal characters"
}

release_name() {
  local family="$1" sha="$2"
  printf 'wren-%s@%s\n' "${family}" "${sha}"
}

url_encode() {
  jq -nr --arg value "$1" '$value | @uri'
}

# Set RELEASE_FINALIZED for the caller. Return 0 when present, 10 when absent.
inspect_release() {
  local release="$1" project="$2" encoded body status
  encoded="$(url_encode "${release}")" || die "cannot encode release name"
  umask 077
  body="$(mktemp)" || die "cannot create temporary API response"
  trap 'rm -f "${body}"' RETURN

  if ! status="$(curl -sS --connect-timeout 10 --max-time 30 \
    -H "Authorization: Bearer ${SENTRY_AUTH_TOKEN}" \
    -H 'Accept: application/json' \
    -o "${body}" -w '%{http_code}' \
    "${SENTRY_API_ROOT}/organizations/${SENTRY_ORG}/releases/${encoded}/" 2>/dev/null)"; then
    rm -f "${body}"
    trap - RETURN
    die "Sentry release lookup failed"
  fi

  case "${status}" in
    404)
      RELEASE_FINALIZED="false"
      rm -f "${body}"
      trap - RETURN
      return 10
      ;;
    200)
      if ! jq -e --arg release "${release}" --arg project "${project}" '
        (.version == $release)
        and (.projects | type == "array")
        and any(.projects[]; ((.slug // "") == $project or (.name // "") == $project))
      ' "${body}" >/dev/null 2>&1; then
        rm -f "${body}"
        trap - RETURN
        die "Sentry release has an unexpected version or project association"
      fi
      if jq -e '(.dateReleased // null) != null and (.dateReleased // "") != ""' \
        "${body}" >/dev/null 2>&1; then
        RELEASE_FINALIZED="true"
      else
        RELEASE_FINALIZED="false"
      fi
      rm -f "${body}"
      trap - RETURN
      return 0
      ;;
    *)
      rm -f "${body}"
      trap - RETURN
      die "Sentry release lookup returned HTTP ${status}"
      ;;
  esac
}

run_cli() {
  local output rc
  output="$(mktemp)" || die "cannot create temporary CLI output"
  if "${SENTRY_CLI_BIN}" "$@" >"${output}" 2>&1; then
    rc=0
  else
    rc=$?
  fi
  rm -f "${output}"
  return "${rc}"
}

ensure_prepared() {
  local release="$1" project="$2"
  if inspect_release "${release}" "${project}"; then
    log "release already prepared: ${release}"
    return 0
  else
    local inspect_rc=$?
    [[ "${inspect_rc}" -eq 10 ]] \
      || die "cannot inspect release before preparation: ${release}"
  fi

  log "preparing release: ${release}"
  run_cli releases --org "${SENTRY_ORG}" new --project "${project}" "${release}" || true
  # A lost response or create race is accepted only when the exact postcondition
  # now holds. An unrelated release or project never satisfies this check.
  inspect_release "${release}" "${project}" \
    || die "release creation did not produce the expected release: ${release}"
}

ensure_finalized() {
  local release="$1" project="$2"
  inspect_release "${release}" "${project}" \
    || die "cannot finalize an absent or invalid release: ${release}"
  if [[ "${RELEASE_FINALIZED}" == "true" ]]; then
    log "release already finalized: ${release}"
    return 0
  fi

  log "finalizing release: ${release}"
  run_cli releases --org "${SENTRY_ORG}" --project "${project}" finalize "${release}" || true
  inspect_release "${release}" "${project}" \
    || die "release finalization did not produce the expected release: ${release}"
  [[ "${RELEASE_FINALIZED}" == "true" ]] \
    || die "release remains unfinalized: ${release}"
}

for_each_release() {
  local action="$1" sha="$2" family project release
  while IFS='|' read -r family project; do
    release="$(release_name "${family}" "${sha}")"
    if [[ "${action}" == "prepare" ]]; then
      ensure_prepared "${release}" "${project}"
    else
      ensure_finalized "${release}" "${project}"
    fi
  done <<EOF
api|${SENTRY_PROJECT_BACKEND}
mcp|${SENTRY_PROJECT_MCP}
web|${SENTRY_PROJECT_FRONTEND}
EOF
}

main() {
  local action="${1:-}" sha="${2:-}"
  [[ "${action}" == "prepare" || "${action}" == "finalize" ]] \
    || die "usage: $0 {prepare|finalize} <sha>"
  validate_sha "${sha}"
  require_config
  for_each_release "${action}" "${sha}"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
