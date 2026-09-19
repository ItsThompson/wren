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
mkdir -p "$RAW_DIR/log" "$RAW_DIR/report" "$RAW_DIR/trace" "$RAW_DIR/screenshot" "$RAW_DIR/attachment" "$RAW_DIR/recorder"

for service in ingress frontend backend mcp postgres recorder; do
  docker compose "${COMPOSE[@]}" logs --no-color "$service" > "$RAW_DIR/log/$service.log" 2>&1 || true
done

if [[ -d "$ROOT_DIR/e2e/playwright-report" ]]; then
  cp -R "$ROOT_DIR/e2e/playwright-report/." "$RAW_DIR/report/"
else
  printf '{"error":"playwright_report_missing"}\n' > "$RAW_DIR/report/missing.json"
fi

copy_test_results() {
  local kind=$1
  local source_root=$2
  shift 2
  [[ -d "$source_root" ]] || return 0
  while IFS= read -r -d '' source_path; do
    local relative_path=${source_path#"$source_root/"}
    local target_path="$RAW_DIR/$kind/$relative_path"
    mkdir -p "$(dirname "$target_path")"
    cp "$source_path" "$target_path"
  done < <(find "$source_root" -type f "$@" -print0)
}

# The HTML report links to these files, but Playwright stores the originals in
# test-results. Keep each diagnostic class explicit so the sanitizer can apply
# the right binary, archive, or structured-content policy.
copy_test_results trace "$ROOT_DIR/e2e/test-results" -name '*.zip'
copy_test_results screenshot "$ROOT_DIR/e2e/test-results" \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.gif' -o -iname '*.webp' \)
copy_test_results attachment "$ROOT_DIR/e2e/test-results" \( ! -name '*.zip' ! -iname '*.png' ! -iname '*.jpg' ! -iname '*.jpeg' ! -iname '*.gif' ! -iname '*.webp' ! -iname '*.webm' ! -name '.last-run.json' ! -name 'error-context.md' \)

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
const categoryAliases = new Map([
  ['token', 'bearer-token'],
  ['authorization-code', 'oauth-code'],
  ['code-verifier', 'pkce-verifier'],
  ['client-secret', 'internal-api-token'],
])
const categories = new Set([
  'session-cookie', 'authorization-header', 'bearer-token', 'password', 'oauth-code',
  'refresh-token', 'pkce-verifier', 'control-token', 'internal-api-token', 'session-secret',
  'postgres-password', 'oauth-private-key', 'tls-private-key', 'email', 'username',
  'token', 'authorization-code', 'code-verifier', 'client-secret',
])
const add = (category, value) => {
  if (typeof value !== 'string' || value.length === 0) return
  const entries = values[category] ?? []
  if (!entries.includes(value)) entries.push(value)
  values[category] = entries
}
const readRequired = (path) => {
  try { return readFileSync(path, 'utf8') } catch (error) { throw new Error(`unable to read sensitive value file: ${path}`, { cause: error }) }
}
const addSnapshot = (name) => {
  if (!name.startsWith('worker-') || !name.endsWith('.json')) return
  const path = join(process.env.SENSITIVE_VALUES_DIR, name)
  let snapshot
  try { snapshot = JSON.parse(readRequired(path)) } catch (error) { throw new Error(`malformed sensitive snapshot: ${name}`, { cause: error }) }
  if (snapshot === null || typeof snapshot !== 'object' || Array.isArray(snapshot)) throw new Error(`malformed sensitive snapshot: ${name}`)
  for (const [category, entries] of Object.entries(snapshot)) {
    if (!categories.has(category) || !Array.isArray(entries) || entries.some((value) => typeof value !== 'string' || value.length === 0)) {
      throw new Error(`malformed sensitive snapshot: ${name}`)
    }
    const resolvedCategory = categoryAliases.get(category) ?? category
    for (const value of entries) add(resolvedCategory, value)
  }
}
const defaults = {
  'control-token': process.env.RECORDER_CONTROL_TOKEN ?? '',
  'postgres-password': process.env.POSTGRES_PASSWORD ?? 'wren',
  'internal-api-token': process.env.E2E_INTERNAL_API_TOKEN ?? process.env.INTERNAL_API_TOKEN ?? 'wren-e2e-internal-token',
  'session-secret': process.env.E2E_SESSION_JWT_SECRET ?? process.env.SESSION_JWT_SECRET ?? 'wren-e2e-session-secret-at-least-32-bytes',
}
for (const [category, value] of Object.entries(defaults)) add(category, value)
const addFileIfPresent = (category, path) => {
  if (existsSync(path)) add(category, readRequired(path))
}
addFileIfPresent('oauth-private-key', process.env.OAUTH_PRIVATE_KEY_PATH ?? join(process.env.ROOT_DIR, 'e2e/keys/oauth-private.pem'))
addFileIfPresent('tls-private-key', process.env.TLS_PRIVATE_KEY_PATH ?? join(process.env.ROOT_DIR, 'e2e/ingress/certificates/wren-e2e-key.pem'))
if (existsSync(process.env.SENSITIVE_VALUES_DIR)) {
  for (const name of readdirSync(process.env.SENSITIVE_VALUES_DIR)) {
    if (join(process.env.SENSITIVE_VALUES_DIR, name) !== process.env.VALUES_FILE) addSnapshot(name)
  }
}
writeFileSync(process.env.VALUES_FILE, JSON.stringify(values))
NODE

if ! ARTIFACT_INPUT_DIR="$RAW_DIR" ARTIFACT_OUTPUT_DIR="$SAFE_DIR" SENSITIVE_VALUES_FILE="$VALUES_FILE" \
  node --experimental-strip-types "$ROOT_DIR/e2e/artifacts/artifact-sanitizer.ts"; then
  # A failed scan may leave approved siblings in the output directory. Remove
  # the entire bundle so CI cannot upload a partial result after a safety failure.
  rm -rf -- "$SAFE_DIR"
  exit 1
fi
printf 'artifact capture: approved safe bundle at %s\n' "$SAFE_DIR"
