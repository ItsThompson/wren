#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
read -r APP_HOST API_HOST MCP_HOST <<< "$(python3 "$SCRIPT_DIR/contract-hosts.py" app api mcp)"
CA="${ROOT_DIR}/e2e/ingress/certificates/caroot/rootCA.pem"
APP_URL="${FRONTEND_BASE_URL:-https://${APP_HOST}}"
API_URL="${API_BASE_URL:-https://${API_HOST}}"
MCP_URL="${MCP_BASE_URL:-https://${MCP_HOST}}"
RECORDER_TOKEN="${RECORDER_CONTROL_TOKEN:-}"
MAX_ATTEMPTS=${E2E_READY_ATTEMPTS:-60}
INTERVAL_SECONDS=${E2E_READY_INTERVAL_SECONDS:-2}

if [[ ! -r "$CA" ]]; then
  printf 'node-trust: Wren CA is missing: %s\n' "$CA" >&2
  exit 1
fi

canonical_urls="$(python3 - "$APP_URL" "$API_URL" "$MCP_URL" "$APP_HOST" "$API_HOST" "$MCP_HOST" <<'PY'
import sys
from urllib.parse import urlsplit

expected_hosts = tuple(sys.argv[4:])
canonical_urls = []
for raw_url, expected_host in zip(sys.argv[1:4], expected_hosts):
    try:
        parsed = urlsplit(raw_url)
        port = parsed.port
    except ValueError:
        raise SystemExit(f"hosts: URL for {expected_host} has an invalid port")
    if (
        parsed.scheme != "https"
        or parsed.hostname != expected_host
        or port is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise SystemExit(f"hosts: URL must be the canonical HTTPS origin https://{expected_host}")
    canonical_urls.append(f"https://{expected_host}")
print(*canonical_urls)
PY
)"
read -r APP_URL API_URL MCP_URL <<< "$canonical_urls"

if [[ -z "$RECORDER_TOKEN" ]]; then
  printf 'recorder: RECORDER_CONTROL_TOKEN is required\n' >&2
  exit 1
fi

check() {
  local label=$1
  shift
  for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1)); do
    if output="$($@ 2>/dev/null)"; then
      printf '%s: ready (attempt %d/%d)\n' "$label" "$attempt" "$MAX_ATTEMPTS"
      printf '%s' "$output"
      return 0
    fi
    sleep "$INTERVAL_SECONDS"
  done
  printf '%s: readiness check failed after %ss\n' "$label" "$((MAX_ATTEMPTS * INTERVAL_SECONDS))" >&2
  exit 1
}

check_app() {
  response=$(curl --fail --silent --show-error --cacert "$CA" "$APP_URL/")
  [[ "$response" == *'id="root"'* ]]
}
check_api_metadata() {
  response=$(curl --fail --silent --show-error --cacert "$CA" "$API_URL/.well-known/oauth-authorization-server")
  printf '%s' "$response" | python3 "$ROOT_DIR/scripts/e2e/public_contracts.py" authorization "$API_URL"
}
check_mcp_prm() {
  response=$(curl --fail --silent --show-error --cacert "$CA" "$MCP_URL/.well-known/oauth-protected-resource")
  printf '%s' "$response" | python3 "$ROOT_DIR/scripts/e2e/public_contracts.py" protected-resource "$MCP_URL" "$API_URL"
}
check_recorder() {
  curl --fail --silent --show-error --cacert "$CA" \
    -H "X-Recorder-Token: $RECORDER_TOKEN" "$APP_URL/_e2e/recorder/ready" | grep -q '"ready":true'
}
check_node_trust() {
  NODE_EXTRA_CA_CERTS="$CA" node --input-type=module -e "const r = await fetch('${APP_URL}/'); if (!r.ok) process.exit(1); const t = await r.text(); if (!t.includes('id=\\\"root\\\"')) process.exit(1)"
}
check_public_allowlist() {
  for path in /healthz /readyz /metrics; do
    [[ "$(curl --silent --output /dev/null --write-out '%{http_code}' --cacert "$CA" "$API_URL$path")" == 404 ]]
  done
  for path in /healthz /readyz /metrics /not-allowlisted; do
    [[ "$(curl --silent --output /dev/null --write-out '%{http_code}' --cacert "$CA" "$MCP_URL$path")" == 404 ]]
  done
}
check_mcp_health() {
  local container
  container="$(docker compose --project-directory "$ROOT_DIR" -f "$ROOT_DIR/docker-compose.yml" -f "$ROOT_DIR/e2e/docker-compose.e2e.yml" ps -q mcp)"
  [[ -n "$container" && "$(docker inspect --format '{{.State.Health.Status}}' "$container")" == healthy ]]
}

check app-root check_app
check node-trust check_node_trust
check as-metadata check_api_metadata
check mcp-prm check_mcp_prm
check mcp-jwks check_mcp_health
check public-path-allowlist check_public_allowlist
check recorder check_recorder
printf 'readiness: public HTTPS contracts are ready\n'
