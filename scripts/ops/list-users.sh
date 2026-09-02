#!/usr/bin/env bash
# =============================================================================
# scripts/ops/list-users.sh
#
# List the most recent Wren users (read-only). Runs ON the VPS, where the
# postgres container lives; it is not a Docker-Context script. Synced to the
# box at /opt/wren/scripts/ by deploy.sh after each healthy deploy, so it is
# available for an operator SSH'd in as deploy@<ip>.
#
# Usage (on the VPS):
#   /opt/wren/scripts/list-users.sh [limit]
#
# Env:
#   WREN_PG_CONTAINER  postgres container name (default wren-postgres-1)
# =============================================================================

PG_CONTAINER="${WREN_PG_CONTAINER:-wren-postgres-1}"

log() { printf '%s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

main() {
  set -euo pipefail
  local limit="${1:-10}"
  [[ "${limit}" =~ ^[0-9]+$ ]] || die "invalid limit '${limit}' (expected a number)"
  # Explicit columns, never password_hash: the hash is noise for an ops listing.
  docker exec "${PG_CONTAINER}" psql -U wren -d wren -c \
    "SELECT id, username, email, created_at, has_completed_onboarding
     FROM users ORDER BY created_at DESC LIMIT ${limit};"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
