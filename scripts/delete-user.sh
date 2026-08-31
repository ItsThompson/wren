#!/usr/bin/env bash
# =============================================================================
# scripts/delete-user.sh
#
# Delete a Wren user account from the production database. Runs ON the VPS,
# where the postgres container lives; it is not a Docker-Context script.
#
# Every destructive step requires an explicit `y`:
#   1. Dry run: rows that would be deleted, per table (prompt)
#   2. Review: run the deletes in a transaction WITHOUT commit (prompt)
#   3. Commit: run the deletes WITH commit, verify the user is gone
#
# Usage:
#   ./scripts/delete-user.sh <username>
#
# Env:
#   WREN_PG_CONTAINER  postgres container name (default wren-postgres-1)
# =============================================================================

# --- Configuration ----------------------------------------------------------

PG_CONTAINER="${WREN_PG_CONTAINER:-wren-postgres-1}"

# Set by resolve_user(); consumed by the delete/verify steps.
USER_ID=""
USER_EMAIL=""

# --- Helpers ----------------------------------------------------------------

log() { printf '%s\n' "$*" >&2; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# Run psql inside the postgres container. The only DB boundary; tests stub it.
pg() {
  docker exec "${PG_CONTAINER}" psql -U wren -d wren "$@"
}

# Prompt for an explicit `y`; anything else (including EOF) is a refusal.
confirm() {
  local prompt="$1" reply
  printf '%s [y/N] ' "${prompt}" >&2
  read -r reply || return 1
  [[ "${reply}" == "y" || "${reply}" == "Y" ]]
}

# --- Steps ------------------------------------------------------------------

resolve_user() {
  local username="$1" out
  out="$(pg -t -A -F '|' -c "SELECT id, email FROM users WHERE username = '${username}';")"
  [[ -n "${out}" ]] || die "no user with username '${username}'"
  USER_ID="${out%%|*}"
  USER_EMAIL="${out#*|}"
}

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

dry_run() {
  log "==> Dry run: rows that would be deleted"
  pg -c "$(counts_sql)"
  # Flag any table beyond `users` with rows: the account is not empty, and the
  # deletion is permanent.
  local non_user
  non_user="$(pg -t -A -F '|' -c "$(counts_sql)" | grep -v '^users|' | grep -vE '\|0$' || true)"
  if [[ -n "${non_user}" ]]; then
    log "WARNING: this account has data beyond the users row; deletion is permanent:"
    printf '%s\n' "${non_user}" >&2
  fi
}

delete_sql() {
  local commit="$1"
  cat <<SQL
BEGIN;
DELETE FROM revoked_sessions          WHERE user_id = '${USER_ID}';
DELETE FROM oauth_refresh_tokens     WHERE user_id = '${USER_ID}';
DELETE FROM oauth_authorization_codes WHERE user_id = '${USER_ID}';
DELETE FROM oauth_audit_log          WHERE user_id = '${USER_ID}';
DELETE FROM oauth_grants             WHERE user_id = '${USER_ID}';
DELETE FROM progress                 WHERE user_id = '${USER_ID}';
DELETE FROM roadmaps                 WHERE owner   = '${USER_ID}';
DELETE FROM users                    WHERE id      = '${USER_ID}';
${commit:+COMMIT;}
SELECT 'users_remaining' AS check, count(*) FROM users WHERE id = '${USER_ID}';
SQL
}

# Review pass: the same deletes as the commit, but the transaction is left open
# and rolls back when the psql session ends, so the dev sees the counts first.
review_delete() {
  log "==> Review pass (transaction NOT committed; rolls back when this session ends)"
  pg -c "$(delete_sql "")"
}

commit_delete() {
  log "==> Committing deletion"
  pg -c "$(delete_sql commit)"
}

verify_deleted() {
  local remaining
  remaining="$(pg -t -A -c "SELECT count(*) FROM users WHERE id = '${USER_ID}';")"
  [[ "${remaining}" == "0" ]] || die "verification failed: ${remaining} users row(s) remain"
}

# --- Orchestration ----------------------------------------------------------

main() {
  set -euo pipefail
  USERNAME="${1:-}"
  [[ -n "${USERNAME}" ]] || die "Usage: $0 <username>"
  # The app enforces 3-32 chars of [a-z0-9_-]; reject anything else so the value
  # is safe to interpolate into the SQL below.
  [[ "${USERNAME}" =~ ^[a-z0-9_-]{3,32}$ ]] || die "invalid username '${USERNAME}'"

  resolve_user "${USERNAME}"
  log "Found: ${USERNAME} <${USER_EMAIL}> (id ${USER_ID})"

  dry_run
  confirm "Proceed with deleting '${USERNAME}' <${USER_EMAIL}>?" || die "aborted by user"

  review_delete
  confirm "Review the delete counts above. Commit the deletion?" || die "aborted by user"

  commit_delete
  verify_deleted
  log "User '${USERNAME}' (${USER_ID}) deleted."
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
