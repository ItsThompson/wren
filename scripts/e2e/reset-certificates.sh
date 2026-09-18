#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CERT_DIR="${ROOT_DIR}/e2e/ingress/certificates"
CAROOT="${CERT_DIR}/caroot"
CA="${CAROOT}/rootCA.pem"

if [[ -d "$CAROOT" && -r "$CA" ]]; then
  if ! command -v openssl >/dev/null 2>&1; then
    printf 'tls: openssl is required to verify the managed CA before reset\n' >&2
    exit 1
  fi
  fingerprint="$(openssl x509 -in "$CA" -noout -fingerprint -sha256 | tr -d '\r')"
  case "$fingerprint" in
    SHA256\ Fingerprint=*) ;;
    *) printf 'tls: managed CA fingerprint could not be validated; refusing reset\n' >&2; exit 1 ;;
  esac
  if ! command -v mkcert >/dev/null 2>&1; then
    printf 'tls: mkcert is required to remove the managed CA from OS trust\n' >&2
    exit 1
  fi
  CAROOT="$CAROOT" mkcert -uninstall >/dev/null
  rm -rf "$CAROOT"
fi
rm -f "$CERT_DIR/wren-e2e.pem" "$CERT_DIR/wren-e2e-key.pem"
printf 'tls: removed only the Wren-managed CA and leaf material (%s)\n' "${fingerprint:-not present}"
