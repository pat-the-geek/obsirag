#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

use_reload="${OBSIRAG_API_RELOAD:-0}"

if [ -x ".venv/bin/python" ]; then
  if [[ "$use_reload" == "1" ]]; then
    exec .venv/bin/python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
  fi
  exec .venv/bin/python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
fi

if [[ "$use_reload" == "1" ]]; then
  exec python3 -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
fi

exec python3 -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000