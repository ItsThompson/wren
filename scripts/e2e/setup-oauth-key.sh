#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
KEY_DIR="${ROOT_DIR}/e2e/keys"
KEY_PATH="${KEY_DIR}/oauth-private.pem"
TOKEN_PATH="${KEY_DIR}/recorder-control-token"
mkdir -p "$KEY_DIR"
chmod 700 "$KEY_DIR"

if [[ ! -s "$KEY_PATH" ]]; then
  if ! command -v openssl >/dev/null 2>&1; then
    printf 'oauth: openssl is required to generate the E2E signing key\n' >&2
    exit 1
  fi
  umask 077
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "$KEY_PATH" >/dev/null 2>&1
fi
if [[ ! -s "$TOKEN_PATH" ]]; then
  umask 077
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32 > "$TOKEN_PATH"
  else
    TOKEN=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
    printf '%s\n' "$TOKEN" > "$TOKEN_PATH"
  fi
fi
chmod 600 "$KEY_PATH" "$TOKEN_PATH"
printf 'oauth: E2E signing key and recorder control token are ready\n'
