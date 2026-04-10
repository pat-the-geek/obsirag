#!/usr/bin/env bash
# =============================================================
# ObsiRAG — Exécution au premier plan (utilisé par launchd)
# Ne pas appeler directement, utiliser start.sh ou install_service.sh
# =============================================================
set -euo pipefail

# Se placer dans le répertoire du projet (important quand lancé par launchd)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
VENV_STREAMLIT="$SCRIPT_DIR/.venv/bin/streamlit"

if [ ! -x "$VENV_STREAMLIT" ]; then
  echo "ERREUR : streamlit introuvable dans .venv. Exécute ./setup.sh"
  exit 1
fi

# ---- Variables d'environnement depuis .env ------------------
set -o allexport
source "$SCRIPT_DIR/.env"
set +o allexport

# Remplace host.docker.internal → localhost (héritage Docker)
if [[ "${LMSTUDIO_BASE_URL:-}" == *"host.docker.internal"* ]]; then
  export LMSTUDIO_BASE_URL="${LMSTUDIO_BASE_URL/host.docker.internal/localhost}"
fi

export APP_DATA_DIR="${APP_DATA_DIR:-$SCRIPT_DIR/data}"
export LOG_DIR="${LOG_DIR:-$SCRIPT_DIR/logs}"
export PYTHONPATH="$SCRIPT_DIR"

mkdir -p "$APP_DATA_DIR" "$LOG_DIR"

# ---- Streamlit (premier plan — launchd gère le cycle de vie) -
exec "$VENV_STREAMLIT" run src/ui/app.py \
  --server.address=127.0.0.1 \
  --server.port=8501 \
  --server.headless=true
