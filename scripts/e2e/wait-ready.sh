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
CURL_CONNECT_TIMEOUT_SECONDS=${E2E_READY_CURL_CONNECT_TIMEOUT_SECONDS:-5}
CURL_MAX_TIME_SECONDS=${E2E_READY_CURL_MAX_TIME_SECONDS:-10}
NODE_FETCH_TIMEOUT_MS=${E2E_READY_NODE_FETCH_TIMEOUT_MS:-10000}

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
  local deadline=$(( $(date +%s) + MAX_ATTEMPTS * INTERVAL_SECONDS ))
  for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt += 1)); do
    local remaining=$((deadline - $(date +%s)))
    if (( remaining <= 0 )); then break; fi
    if output="$(READY_REQUEST_TIMEOUT_SECONDS="$remaining" READY_REQUEST_DEADLINE="$deadline" "$@" 2>/dev/null)"; then
      printf '%s: ready (attempt %d/%d)\n' "$label" "$attempt" "$MAX_ATTEMPTS"
      printf '%s' "$output"
      return 0
    fi
    if (( attempt < MAX_ATTEMPTS )); then
      remaining=$((deadline - $(date +%s)))
      if (( remaining > 0 )); then
        sleep "$(( INTERVAL_SECONDS < remaining ? INTERVAL_SECONDS : remaining ))"
      fi
    fi
  done
  printf '%s: readiness check failed after %ss\n' "$label" "$((MAX_ATTEMPTS * INTERVAL_SECONDS))" >&2
  exit 1
}

request_timeout_seconds() {
  local timeout=$CURL_MAX_TIME_SECONDS
  if [[ -n "${READY_REQUEST_TIMEOUT_SECONDS:-}" && READY_REQUEST_TIMEOUT_SECONDS -lt timeout ]]; then
    timeout=$READY_REQUEST_TIMEOUT_SECONDS
  fi
  if [[ -n "${READY_REQUEST_DEADLINE:-}" ]]; then
    local deadline_remaining=$((READY_REQUEST_DEADLINE - $(date +%s)))
    if (( deadline_remaining <= 0 )); then return 1; fi
    if (( deadline_remaining < timeout )); then timeout=$deadline_remaining; fi
  fi
  if (( timeout < 1 )); then timeout=1; fi
  local connect_timeout=$CURL_CONNECT_TIMEOUT_SECONDS
  if (( connect_timeout > timeout )); then connect_timeout=$timeout; fi
  printf '%s %s' "$connect_timeout" "$timeout"
}

check_app() {
  read -r connect_timeout max_time <<< "$(request_timeout_seconds)"
  response=$(curl --fail --silent --show-error --connect-timeout "$connect_timeout" --max-time "$max_time" --cacert "$CA" "$APP_URL/")
  [[ "$response" == *'id="root"'* ]]
}
check_api_metadata() {
  read -r connect_timeout max_time <<< "$(request_timeout_seconds)"
  response=$(curl --fail --silent --show-error --connect-timeout "$connect_timeout" --max-time "$max_time" --cacert "$CA" "$API_URL/.well-known/oauth-authorization-server")
  printf '%s' "$response" | python3 "$ROOT_DIR/scripts/e2e/public_contracts.py" authorization "$API_URL"
}
check_mcp_prm() {
  read -r connect_timeout max_time <<< "$(request_timeout_seconds)"
  response=$(curl --fail --silent --show-error --connect-timeout "$connect_timeout" --max-time "$max_time" --cacert "$CA" "$MCP_URL/.well-known/oauth-protected-resource")
  printf '%s' "$response" | python3 "$ROOT_DIR/scripts/e2e/public_contracts.py" protected-resource "$MCP_URL" "$API_URL"
}
check_recorder() {
  read -r connect_timeout max_time <<< "$(request_timeout_seconds)"
  curl --fail --silent --show-error --connect-timeout "$connect_timeout" --max-time "$max_time" --cacert "$CA" \
    -H "X-Recorder-Token: $RECORDER_TOKEN" "$APP_URL/_e2e/recorder/ready" | grep -q '"ready":true'
}
check_node_trust() {
  local timeout_ms=$NODE_FETCH_TIMEOUT_MS
  if [[ -n "${READY_REQUEST_TIMEOUT_SECONDS:-}" ]]; then
    local request_timeout_ms=$((READY_REQUEST_TIMEOUT_SECONDS * 1000))
    if (( request_timeout_ms < timeout_ms )); then timeout_ms=$request_timeout_ms; fi
  fi
  if [[ -n "${READY_REQUEST_DEADLINE:-}" ]]; then
    local deadline_remaining_ms=$(( (READY_REQUEST_DEADLINE - $(date +%s)) * 1000 ))
    if (( deadline_remaining_ms < timeout_ms )); then timeout_ms=$deadline_remaining_ms; fi
  fi
  if (( timeout_ms < 1 )); then timeout_ms=1; fi
  E2E_READY_NODE_FETCH_TIMEOUT_MS="$timeout_ms" NODE_EXTRA_CA_CERTS="$CA" node --input-type=module -e "const r = await fetch('${APP_URL}/', { signal: AbortSignal.timeout(Number(process.env.E2E_READY_NODE_FETCH_TIMEOUT_MS)) }); if (!r.ok) process.exit(1); const t = await r.text(); if (!t.includes('id=\\\"root\\\"')) process.exit(1)"
}
check_public_path() {
  local url=$1
  local connect_timeout max_time
  read -r connect_timeout max_time <<< "$(request_timeout_seconds)"
  [[ "$(curl --silent --connect-timeout "$connect_timeout" --max-time "$max_time" --output /dev/null --write-out '%{http_code}' --cacert "$CA" "$url")" == 404 ]]
}
check_public_allowlist() {
  for path in /healthz /readyz /metrics; do
    check_public_path "$API_URL$path"
  done
  for path in /healthz /readyz /metrics /not-allowlisted; do
    check_public_path "$MCP_URL$path"
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
