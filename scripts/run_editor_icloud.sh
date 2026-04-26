#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export FGB_WORKSPACE_DATA_ROOT="${FGB_WORKSPACE_DATA_ROOT:-$HOME/Library/Mobile Documents/com~apple~CloudDocs/workspace_data}"
PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x ".venvs/paddleocr311/bin/python" ]]; then
    PYTHON_BIN=".venvs/paddleocr311/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

echo "workspace_data: $FGB_WORKSPACE_DATA_ROOT"
echo "database:       $(pwd)/data/genealogy.sqlite"
echo "python:         $PYTHON_BIN"
exec "$PYTHON_BIN" scripts/run_gen_review_server.py "$@"
