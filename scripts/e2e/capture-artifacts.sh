#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE=(-f "$ROOT_DIR/docker-compose.yml" -f "$ROOT_DIR/e2e/docker-compose.e2e.yml")
RAW_DIR="$(mktemp -d "${TMPDIR:-/tmp}/wren-e2e-raw.XXXXXX")"
SAFE_DIR="/tmp/wren-safe-artifacts"
SENSITIVE_VALUES_DIR="${E2E_SENSITIVE_VALUES_DIR:-/tmp/wren-e2e-sensitive}"
if [[ "${ARTIFACT_OUTPUT_DIR:-$SAFE_DIR}" != "$SAFE_DIR" ]]; then
  printf 'artifact capture: output directory must be %s\n' "$SAFE_DIR" >&2
  exit 1
fi
case "$SENSITIVE_VALUES_DIR" in
  /tmp/wren-e2e-sensitive|/tmp/wren-e2e-sensitive.*) ;;
  *) printf 'artifact capture: sensitive-value directory is outside the safe temporary root\n' >&2; exit 1 ;;
esac
trap 'rm -rf -- "$RAW_DIR" "$SENSITIVE_VALUES_DIR"' EXIT
rm -rf -- "$SAFE_DIR"
mkdir -p "$RAW_DIR/log" "$RAW_DIR/report" "$RAW_DIR/recorder"

for service in ingress frontend backend mcp postgres recorder; do
  docker compose "${COMPOSE[@]}" logs --no-color "$service" > "$RAW_DIR/log/$service.log" 2>&1 || true
done

if [[ -d "$ROOT_DIR/e2e/playwright-report" ]]; then
  cp -R "$ROOT_DIR/e2e/playwright-report/." "$RAW_DIR/report/"
else
  printf '{"error":"playwright_report_missing"}\n' > "$RAW_DIR/report/missing.json"
fi

if [[ -n "${RECORDER_CONTROL_TOKEN:-}" ]]; then
  curl --fail --silent --show-error --cacert "${NODE_EXTRA_CA_CERTS:?NODE_EXTRA_CA_CERTS is required}" \
    -H "X-Recorder-Token: $RECORDER_CONTROL_TOKEN" \
    "https://app.wren.test/_e2e/recorder/artifacts" > "$RAW_DIR/recorder/export.json"
else
  printf '{"error":"recorder_control_token_missing"}\n' > "$RAW_DIR/recorder/missing.json"
fi

mkdir -p "$SENSITIVE_VALUES_DIR"
VALUES_FILE="$SENSITIVE_VALUES_DIR/merged-values.json"
export VALUES_FILE SENSITIVE_VALUES_DIR ROOT_DIR
node --input-type=module <<'NODE'
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
const values = {}
const add = (category, value) => {
  if (typeof value !== 'string' || value.length === 0) return
  const entries = values[category] ?? []
  if (!entries.includes(value)) entries.push(value)
  values[category] = entries
}
const read = (path) => { try { return readFileSync(path, 'utf8') } catch { return '' } }
const defaults = {
  'control-token': process.env.RECORDER_CONTROL_TOKEN ?? '',
  'postgres-password': process.env.POSTGRES_PASSWORD ?? 'wren',
  'internal-api-token': process.env.E2E_INTERNAL_API_TOKEN ?? process.env.INTERNAL_API_TOKEN ?? 'wren-e2e-internal-token',
  'session-secret': process.env.E2E_SESSION_JWT_SECRET ?? process.env.SESSION_JWT_SECRET ?? 'wren-e2e-session-secret-at-least-32-bytes',
  'oauth-private-key': read(process.env.OAUTH_PRIVATE_KEY_PATH ?? join(process.env.ROOT_DIR, 'e2e/keys/oauth-private.pem')),
  'tls-private-key': read(process.env.TLS_PRIVATE_KEY_PATH ?? join(process.env.ROOT_DIR, 'e2e/ingress/certificates/wren-e2e-key.pem')),
}
for (const [category, value] of Object.entries(defaults)) add(category, value)
if (existsSync(process.env.SENSITIVE_VALUES_DIR)) {
  for (const name of readdirSync(process.env.SENSITIVE_VALUES_DIR)) {
    if (!name.endsWith('.json')) continue
    try {
      const snapshot = JSON.parse(read(join(process.env.SENSITIVE_VALUES_DIR, name)))
      for (const [category, entries] of Object.entries(snapshot)) {
        if (Array.isArray(entries)) for (const value of entries) add(category, value)
      }
    } catch { /* malformed snapshots make the sanitizer fail closed through missing values */ }
  }
}
writeFileSync(process.env.VALUES_FILE, JSON.stringify(values))
NODE

ARTIFACT_INPUT_DIR="$RAW_DIR" ARTIFACT_OUTPUT_DIR="$SAFE_DIR" SENSITIVE_VALUES_FILE="$VALUES_FILE" \
  node --experimental-strip-types "$ROOT_DIR/e2e/artifacts/artifact-sanitizer.ts"
printf 'artifact capture: approved safe bundle at %s\n' "$SAFE_DIR"
