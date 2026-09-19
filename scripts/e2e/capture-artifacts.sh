#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE=(-f "$ROOT_DIR/docker-compose.yml" -f "$ROOT_DIR/e2e/docker-compose.e2e.yml")
RAW_DIR="$(mktemp -d "${TMPDIR:-/tmp}/wren-e2e-raw.XXXXXX")"
SAFE_DIR="${ARTIFACT_OUTPUT_DIR:-/tmp/wren-safe-artifacts}"
trap 'rm -rf "$RAW_DIR"' EXIT
rm -rf "$SAFE_DIR"
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

VALUES_FILE="$RAW_DIR/sensitive-values.json"
export VALUES_FILE
node --input-type=module <<'NODE'
import { readFileSync, writeFileSync } from 'node:fs'
const read = (path) => { try { return readFileSync(path, 'utf8') } catch { return '' } }
const values = {
  'control-token': [process.env.RECORDER_CONTROL_TOKEN ?? ''],
  'postgres-password': [process.env.POSTGRES_PASSWORD ?? ''],
  'internal-api-token': [process.env.INTERNAL_API_TOKEN ?? ''],
  'session-secret': [process.env.SESSION_SECRET ?? ''],
  'oauth-private-key': [read(process.env.OAUTH_PRIVATE_KEY_PATH ?? '')],
  'tls-private-key': [read(process.env.TLS_PRIVATE_KEY_PATH ?? '')],
}
writeFileSync(process.env.VALUES_FILE, JSON.stringify(values))
NODE

ARTIFACT_INPUT_DIR="$RAW_DIR" ARTIFACT_OUTPUT_DIR="$SAFE_DIR" SENSITIVE_VALUES_FILE="$VALUES_FILE" \
  node --experimental-strip-types "$ROOT_DIR/e2e/artifacts/artifact-sanitizer.ts"
printf 'artifact capture: approved safe bundle at %s\n' "$SAFE_DIR"
