#!/usr/bin/env bash
# =============================================================================
# scripts/tests/run_all.sh
#
# Run every *_test.sh harness in this directory. New harnesses are picked up
# automatically -- CI calls this, not individual files, so adding a test never
# requires a ci.yml edit.
#
# Run: scripts/tests/run_all.sh
# =============================================================================
set -uo pipefail

dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
failed=0

for f in "${dir}"/*_test.sh; do
  [[ -f "$f" ]] || continue
  # Run each harness in its own bash so set -e inside it can't abort the loop.
  bash "$f" || failed=1
done

exit "$failed"