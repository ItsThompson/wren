#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"

hosts="$(mktemp)"
trap 'rm -f "$hosts" "$hosts.wren-e2e.bak" /tmp/wren-e2e-compose.json' EXIT
printf '127.0.0.1 unrelated.test\n' > "$hosts"
WREN_E2E_HOSTS_FILE="$hosts" scripts/e2e/setup-hosts.sh >/dev/null
WREN_E2E_HOSTS_FILE="$hosts" scripts/e2e/setup-hosts.sh >/dev/null
test "$(grep -c 'BEGIN WREN E2E MANAGED HOSTS' "$hosts")" -eq 1
grep -q unrelated.test "$hosts"
WREN_E2E_HOSTS_FILE="$hosts" scripts/e2e/reset-hosts.sh >/dev/null
grep -q unrelated.test "$hosts"
! grep -q 'WREN E2E MANAGED HOSTS' "$hosts"

RECORDER_CONTROL_TOKEN=test-token docker compose \
  -f docker-compose.yml -f e2e/docker-compose.e2e.yml config --format json > /tmp/wren-e2e-compose.json
python3 - <<'PY'
import json

services = json.load(open('/tmp/wren-e2e-compose.json'))['services']
assert {'frontend', 'backend', 'mcp', 'postgres', 'recorder', 'ingress'} <= services.keys()
for service in ('frontend', 'backend', 'mcp', 'postgres', 'recorder'):
    assert not services[service].get('ports'), service
assert services['ingress']['ports'][0]['published'] == '443'
assert services['backend']['environment']['ENVIRONMENT'] == 'production'
assert services['mcp']['environment']['ENVIRONMENT'] == 'production'
PY

printf 'e2e topology tests: ok\n'
