#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CERT_DIR="${E2E_CERT_DIR:-${ROOT_DIR}/e2e/ingress/certificates}"
CAROOT="${CERT_DIR}/caroot"
CA="${CAROOT}/rootCA.pem"

if [[ -d "$CAROOT" && -r "$CA" ]]; then
  if ! command -v openssl >/dev/null 2>&1; then
    printf 'tls: openssl is required to verify the managed CA before reset\n' >&2
    exit 1
  fi
  if ! fingerprint="$(openssl x509 -in "$CA" -noout -fingerprint -sha256 | tr -d '\r')"; then
    printf 'tls: managed CA is not a valid certificate; refusing reset\n' >&2
    exit 1
  fi
  case "$fingerprint" in
    SHA256\ Fingerprint=*) ;;
    *) printf 'tls: managed CA fingerprint could not be validated; refusing reset\n' >&2; exit 1 ;;
  esac
  MKCERT_BIN="${E2E_MKCERT_BIN:-mkcert}"
  if ! command -v "$MKCERT_BIN" >/dev/null 2>&1; then
    printf 'tls: mkcert is required to remove the managed CA from OS trust\n' >&2
    exit 1
  fi
  CAROOT="$CAROOT" "$MKCERT_BIN" -uninstall >/dev/null
  rm -rf "$CAROOT"
fi
rm -f "$CERT_DIR/wren-e2e.pem" "$CERT_DIR/wren-e2e-key.pem"
printf 'tls: removed only the Wren-managed CA and leaf material (%s)\n' "${fingerprint:-not present}"
