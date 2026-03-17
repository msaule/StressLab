#!/bin/sh
set -eu

set -- python -m stresslab.cli.main serve "${STRESSLAB_WORKSPACE:-/data/runs}" \
  --host "${STRESSLAB_HOST:-0.0.0.0}" \
  --port "${STRESSLAB_PORT:-8765}"

if [ "${STRESSLAB_REFRESH:-0}" = "1" ]; then
  set -- "$@" --refresh
fi

if [ -n "${STRESSLAB_API_TOKEN:-}" ]; then
  set -- "$@" --api-token "$STRESSLAB_API_TOKEN"
fi

exec "$@"
