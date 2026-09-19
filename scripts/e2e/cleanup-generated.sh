#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
rm -f "$ROOT_DIR/e2e/keys/oauth-private.pem" "$ROOT_DIR/e2e/keys/recorder-control-token"
rmdir "$ROOT_DIR/e2e/keys" 2>/dev/null || true
printf 'cleanup: removed generated OAuth signing material and recorder token\n'
