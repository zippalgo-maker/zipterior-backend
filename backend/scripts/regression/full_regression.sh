#!/usr/bin/env bash
set -euo pipefail
BACKEND="${1:-/srv/zipterior/backend}"
MODE="${2:-full}"
export ZIPTERIOR_BACKEND="$BACKEND"
cd "$BACKEND"
if [[ "$MODE" == "smoke" ]]; then
  "$BACKEND/../venv/bin/python3" "$BACKEND/scripts/regression/full_regression.py" --smoke
else
  "$BACKEND/../venv/bin/python3" "$BACKEND/scripts/regression/full_regression.py"
fi
