#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export AUTOLEARN_ALLOW_BACKGROUND_LLM=true

if [ -x ".venv/bin/python" ]; then
  exec .venv/bin/python -m src.learning.worker
fi

exec python3 -m src.learning.worker