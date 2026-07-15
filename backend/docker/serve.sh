#!/usr/bin/env bash
# Launches both backend ASGI apps in a single container:
# the external app on :8000 and the internal app on :8001, over one image and
# one service layer. Kept out of src/ because it is deployment glue, not app code.
#
# Behavior:
#   - Forwards SIGTERM/SIGINT to both servers for a graceful shutdown.
#   - Exits as soon as either server exits, so a crashed app takes the container
#     down (surfacing to the compose health gate) instead of running half-broken.
#   - UVICORN_RELOAD=true enables --reload for the containerized dev stack
#     (docker-compose.dev.yml bind-mounts src/ over the image's editable install).
set -uo pipefail

reload=""
if [ "${UVICORN_RELOAD:-false}" = "true" ]; then
  reload="--reload"
fi

# shellcheck disable=SC2086  # $reload is an intentional word-split flag toggle.
uvicorn wren.api.main:app --host "${HOST:-0.0.0.0}" --port "${EXTERNAL_PORT:-8000}" $reload &
external_pid=$!
# shellcheck disable=SC2086
uvicorn wren.api_internal.main:app --host "${HOST:-0.0.0.0}" --port "${INTERNAL_PORT:-8001}" $reload &
internal_pid=$!

shutdown() {
  trap - TERM INT
  kill -TERM "$external_pid" "$internal_pid" 2>/dev/null || true
  wait
}
trap shutdown TERM INT

# Wait for the first server to exit, then tear the other down and propagate.
wait -n
exit_code=$?
shutdown
exit "$exit_code"
