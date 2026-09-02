#!/usr/bin/env bash
# =============================================================================
# scripts/ops/user-counts.sh
#
# Show per-table row counts for a single Wren user, read-only. Runs ON the VPS,
# where the postgres container lives; it is not a Docker-Context script. Synced
# to the box at /opt/wren/scripts/ by deploy.sh after each healthy deploy, so it
# is available for an operator SSH'd in as deploy@<ip>.
#
# The argument is the user's internal id (a 32-char uuid4 hex, as minted by
# wren.accounts.injection.new_hex_id). It is NOT the username; resolve the id
# first with list-users.sh or the API if you only have the username.
#
# Usage (on the VPS):
#   /opt/wren/scripts/user-counts.sh <user_id>
#
# Env:
#   WREN_PG_CONTAINER  postgres container name (default wren-postgres-1)
# =============================================================================

PG_CONTAINER="${WREN_PG_CONTAINER:-wren-postgres-1}"

log() { printf '%s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# Run psql inside the postgres container. The only DB boundary; tests stub it.
pg() {
  docker exec "${PG_CONTAINER}" psql -U wren -d wren "$@"
}

# The per-table count query for a single user. USER_ID is validated by main()
# before this is ever interpolated, so it is safe against SQL injection.
counts_sql() {
  cat <<SQL
SELECT 'users' AS tbl, count(*) FROM users WHERE id = '${USER_ID}'
UNION ALL SELECT 'roadmaps', count(*) FROM roadmaps WHERE owner = '${USER_ID}'
UNION ALL SELECT 'progress', count(*) FROM progress WHERE user_id = '${USER_ID}'
UNION ALL SELECT 'oauth_grants', count(*) FROM oauth_grants WHERE user_id = '${USER_ID}'
UNION ALL SELECT 'oauth_authorization_codes', count(*) FROM oauth_authorization_codes WHERE user_id = '${USER_ID}'
UNION ALL SELECT 'oauth_refresh_tokens', count(*) FROM oauth_refresh_tokens WHERE user_id = '${USER_ID}'
UNION ALL SELECT 'oauth_audit_log', count(*) FROM oauth_audit_log WHERE user_id = '${USER_ID}'
UNION ALL SELECT 'revoked_sessions', count(*) FROM revoked_sessions WHERE user_id = '${USER_ID}';
SQL
}

main() {
  set -euo pipefail
  USER_ID="${1:-}"
  [[ -n "${USER_ID}" ]] || die "Usage: $0 <user_id>"
  # The app mints user ids as uuid4().hex: 32 lowercase hex chars, no dashes.
  # Reject anything else so the value is safe to interpolate into the SQL.
  [[ "${USER_ID}" =~ ^[0-9a-f]{32}$ ]] \
    || die "invalid user_id '${USER_ID}' (expected 32-char uuid4 hex)"

  pg -c "$(counts_sql)"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi