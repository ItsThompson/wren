#!/usr/bin/env bash
set -euo pipefail

HOSTS_FILE=${WREN_E2E_HOSTS_FILE:-/etc/hosts}
MARKER_START="# BEGIN WREN E2E MANAGED HOSTS"
MARKER_END="# END WREN E2E MANAGED HOSTS"
LOCK_DIR="${HOSTS_FILE}.wren-e2e.lock"

if [[ ! -f "$HOSTS_FILE" ]]; then
  printf 'hosts: file not found: %s\n' "$HOSTS_FILE" >&2
  exit 1
fi
if [[ "$(id -u)" -ne 0 && ! -w "$HOSTS_FILE" ]]; then
  printf 'hosts: write access required for %s (run with sudo)\n' "$HOSTS_FILE" >&2
  exit 1
fi
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  printf 'hosts: another Wren setup/reset is running\n' >&2
  exit 1
fi
trap 'rmdir "$LOCK_DIR"' EXIT

if ! grep -q -F "$MARKER_START" "$HOSTS_FILE"; then
  printf 'hosts: no Wren-managed block found\n'
  exit 0
fi
if [[ "$(grep -c -F "$MARKER_START" "$HOSTS_FILE")" != "$(grep -c -F "$MARKER_END" "$HOSTS_FILE" || true)" ]]; then
  printf 'hosts: managed block markers are unbalanced; refusing to edit %s\n' "$HOSTS_FILE" >&2
  exit 1
fi

backup="${HOSTS_FILE}.wren-e2e.bak"
cp "$HOSTS_FILE" "$backup"
tmp="$(mktemp "${HOSTS_FILE}.wren-e2e.XXXXXX")"
cleanup() { rm -f "$tmp"; }
trap 'cleanup; rmdir "$LOCK_DIR"' EXIT

awk -v start="$MARKER_START" -v end="$MARKER_END" '
  $0 == start { inside=1; next }
  $0 == end { inside=0; next }
  !inside { print }
' "$HOSTS_FILE" > "$tmp"

if grep -q -F "$MARKER_START" "$tmp"; then
  printf 'hosts: reset validation failed; original preserved at %s\n' "$backup" >&2
  exit 1
fi
mv "$tmp" "$HOSTS_FILE"
printf 'hosts: removed Wren-managed entries; unrelated entries preserved\n'
