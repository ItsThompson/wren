#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CA="${ROOT_DIR}/e2e/ingress/certificates/caroot/rootCA.pem"
APP_URL="${FRONTEND_BASE_URL:-https://app.wren.test}"
API_URL="${API_BASE_URL:-https://api.wren.test}"
MCP_URL="${MCP_BASE_URL:-https://mcp.wren.test}"
RECORDER_TOKEN="${RECORDER_CONTROL_TOKEN:-}"
MAX_ATTEMPTS=${E2E_READY_ATTEMPTS:-60}
INTERVAL_SECONDS=${E2E_READY_INTERVAL_SECONDS:-2}

if [[ ! -r "$CA" ]]; then
  printf 'node-trust: Wren CA is missing: %s\n' "$CA" >&2
  exit 1
fi
if [[ "$APP_URL" != https://* || "$API_URL" != https://* || "$MCP_URL" != https://* ]]; then
  printf 'hosts: readiness URLs must use HTTPS under the Wren E2E hosts\n' >&2
  exit 1
fi
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
  [[ "$response" == *'https://api.wren.test'* && "$response" == *'jwks_uri'* ]]
}
check_mcp_prm() {
  response=$(curl --fail --silent --show-error --cacert "$CA" "$MCP_URL/.well-known/oauth-protected-resource")
  [[ "$response" == *'https://mcp.wren.test'* && "$response" == *'https://api.wren.test'* ]]
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
  container="$(docker compose -f docker-compose.yml -f e2e/docker-compose.e2e.yml ps -q mcp)"
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
