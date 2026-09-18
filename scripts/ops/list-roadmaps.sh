#!/usr/bin/env bash
# =============================================================================
# scripts/ops/list-roadmaps.sh
#
# List Wren roadmaps by most recent update (read-only). Runs ON the VPS, where
# the postgres container lives; it is not a Docker-Context script. Synced to the
# box at /opt/wren/scripts/ by deploy.sh after each healthy deploy, so it is
# available for an operator SSH'd in as deploy@<ip>.
#
# Usage (on the VPS):
#   /opt/wren/scripts/list-roadmaps.sh
#
# Env:
#   WREN_PG_CONTAINER  postgres container name (default wren-postgres-1)
# =============================================================================

PG_CONTAINER="${WREN_PG_CONTAINER:-wren-postgres-1}"

main() {
  set -euo pipefail
  docker exec "${PG_CONTAINER}" psql -U wren -d wren -c \
    "SELECT id, title, owner, status, published_visibility, revision, created_at, updated_at
     FROM roadmaps
     ORDER BY updated_at DESC;"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
