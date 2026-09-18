#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CERT_DIR="${E2E_CERT_DIR:-${ROOT_DIR}/e2e/ingress/certificates}"
CAROOT="${CERT_DIR}/caroot"
LEAF="${CERT_DIR}/wren-e2e.pem"
KEY="${CERT_DIR}/wren-e2e-key.pem"
CA="${CAROOT}/rootCA.pem"

MKCERT_BIN="${E2E_MKCERT_BIN:-mkcert}"
if ! command -v "$MKCERT_BIN" >/dev/null 2>&1; then
  printf 'tls: mkcert is required. Install it with Homebrew (macOS) or apt (Ubuntu), then rerun setup.\n' >&2
  exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
  printf 'tls: openssl is required to validate the generated certificate\n' >&2
  exit 1
fi

case "$(uname -s)" in
  Darwin|Linux) ;;
  *) printf 'tls: supported hosts setup requires macOS or Ubuntu/Linux\n' >&2; exit 1 ;;
esac

mkdir -p "$CERT_DIR" "$CAROOT"
chmod 700 "$CAROOT" "$CERT_DIR"
CAROOT="$CAROOT" "$MKCERT_BIN" -install
CAROOT="$CAROOT" "$MKCERT_BIN" \
  -cert-file "$LEAF" \
  -key-file "$KEY" \
  app.wren.test api.wren.test mcp.wren.test

if [[ ! -r "$CA" || ! -r "$LEAF" || ! -r "$KEY" ]]; then
  printf 'tls: mkcert did not create the isolated CA and leaf files\n' >&2
  exit 1
fi

if ! openssl x509 -in "$LEAF" -noout -checkend 86400 >/dev/null; then
  printf 'tls: generated leaf certificate is expired or expires within 24 hours\n' >&2
  exit 1
fi
for host in app.wren.test api.wren.test mcp.wren.test; do
  if ! openssl verify -CAfile "$CA" -verify_hostname "$host" "$LEAF" >/dev/null 2>&1; then
    printf 'tls: certificate SAN validation failed for %s\n' "$host" >&2
    exit 1
  fi
done

chmod 644 "$CA" "$LEAF"
chmod 600 "$KEY"
printf 'tls: isolated Wren CA and three-host certificate are ready\n'
printf 'tls: NODE_EXTRA_CA_CERTS=%s\n' "$CA"
