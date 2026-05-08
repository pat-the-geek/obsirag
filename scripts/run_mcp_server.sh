#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -x ".venv/bin/python" ]; then
  echo "ERREUR : venv introuvable. Exécute d'abord ./setup.sh" >&2
  exit 1
fi

exec "$ROOT_DIR/.venv/bin/python" -m src.mcp.server
