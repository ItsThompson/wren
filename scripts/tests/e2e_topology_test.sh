#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$root"
python3 scripts/e2e/test_public_contracts.py >/dev/null

hosts="$(mktemp)"
key_dir="$(mktemp -d)"
trap 'rm -f "$hosts" "$hosts.wren-e2e.bak" /tmp/wren-e2e-compose.json; rm -rf "$key_dir"' EXIT
printf '127.0.0.1 unrelated.test\n' > "$hosts"
case "$(uname -s)" in
  Darwin) original_mode="$(stat -f '%Lp' "$hosts")" ;;
  Linux) original_mode="$(stat -c '%a' "$hosts")" ;;
esac
WREN_E2E_HOSTS_FILE="$hosts" scripts/e2e/setup-hosts.sh >/dev/null
case "$(uname -s)" in
  Darwin) updated_mode="$(stat -f '%Lp' "$hosts")" ;;
  Linux) updated_mode="$(stat -c '%a' "$hosts")" ;;
esac
test "$updated_mode" = "$original_mode"
WREN_E2E_HOSTS_FILE="$hosts" scripts/e2e/setup-hosts.sh >/dev/null
test "$(grep -c 'BEGIN WREN E2E MANAGED HOSTS' "$hosts")" -eq 1
grep -q unrelated.test "$hosts"
WREN_E2E_HOSTS_FILE="$hosts" scripts/e2e/reset-hosts.sh >/dev/null
case "$(uname -s)" in
  Darwin) reset_mode="$(stat -f '%Lp' "$hosts")" ;;
  Linux) reset_mode="$(stat -c '%a' "$hosts")" ;;
esac
test "$reset_mode" = "$original_mode"
grep -q unrelated.test "$hosts"
! grep -q 'WREN E2E MANAGED HOSTS' "$hosts"

assert_malformed_markers_are_preserved() {
  local content=$1
  printf '%b' "$content" > "$hosts"
  local before after
  before="$(cat "$hosts")"
  if WREN_E2E_HOSTS_FILE="$hosts" scripts/e2e/setup-hosts.sh >/dev/null 2>&1; then
    printf 'malformed marker setup unexpectedly succeeded\n' >&2
    exit 1
  fi
  after="$(cat "$hosts")"
  test "$after" = "$before"
  if WREN_E2E_HOSTS_FILE="$hosts" scripts/e2e/reset-hosts.sh >/dev/null 2>&1; then
    printf 'malformed marker reset unexpectedly succeeded\n' >&2
    exit 1
  fi
  after="$(cat "$hosts")"
  test "$after" = "$before"
}

assert_malformed_markers_are_preserved $'# END WREN E2E MANAGED HOSTS\nkeep-before\n# BEGIN WREN E2E MANAGED HOSTS\nkeep-after\n'
assert_malformed_markers_are_preserved $'# BEGIN WREN E2E MANAGED HOSTS\n# BEGIN WREN E2E MANAGED HOSTS\nkeep\n# END WREN E2E MANAGED HOSTS\n# END WREN E2E MANAGED HOSTS\n'
assert_malformed_markers_are_preserved $'# BEGIN WREN E2E MANAGED HOSTS\nkeep-without-end\n'

E2E_KEY_DIR="$key_dir" scripts/e2e/setup-oauth-key.sh >/dev/null
case "$(uname -s)" in
  Darwin) key_mode="$(stat -f '%Lp' "$key_dir/oauth-private.pem")"; token_mode="$(stat -f '%Lp' "$key_dir/recorder-control-token")" ;;
  Linux) key_mode="$(stat -c '%a' "$key_dir/oauth-private.pem")"; token_mode="$(stat -c '%a' "$key_dir/recorder-control-token")" ;;
esac
test "$key_mode" = 644
test "$token_mode" = 600

RECORDER_CONTROL_TOKEN=test-token docker compose \
  -f docker-compose.yml -f e2e/docker-compose.e2e.yml config --format json > /tmp/wren-e2e-compose.json
python3 - <<'PY'
import json

services = json.load(open('/tmp/wren-e2e-compose.json'))['services']
expected = {'frontend', 'backend', 'mcp', 'postgres', 'recorder', 'ingress'}

def dependency_closure(service: str, seen: set[str]) -> None:
    if service in seen:
        return
    seen.add(service)
    for dependency in services[service].get('depends_on', {}):
        dependency_closure(dependency, seen)

focused = set()
dependency_closure('ingress', focused)
assert focused == expected, focused
for service in ('frontend', 'backend', 'mcp', 'postgres', 'recorder'):
    assert not services[service].get('ports'), service
assert services['ingress']['ports'][0]['published'] == '443'
assert services['backend']['environment']['ENVIRONMENT'] == 'production'
assert services['mcp']['environment']['ENVIRONMENT'] == 'production'
assert services['ingress']['depends_on']['mcp']['condition'] == 'service_started'
assert services['backend']['depends_on']['postgres']['condition'] == 'service_healthy'
assert services['mcp']['depends_on']['backend']['condition'] == 'service_healthy'
PY

startup_plan="$(just --dry-run e2e-up 2>&1)"
python3 - "$startup_plan" <<'PY'
import sys

plan = sys.argv[1]
postgres = plan.index('up -d --wait postgres')
migration = plan.index('run --rm --no-deps backend alembic upgrade head')
ingress = plan.index('up -d ingress')
assert postgres < migration < ingress
PY

printf 'e2e topology tests: ok\n'
