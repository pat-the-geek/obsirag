#!/usr/bin/env bash
# =============================================================
# ObsiRAG — Lanceur de l'UI Streamlit heritee au premier plan
# Surface legacy conservee pour maintenance locale, distincte du runtime principal Expo + FastAPI
# Ne pas appeler directement, utiliser start.sh ou install_service.sh seulement si cette UI legacy doit etre executee
# =============================================================
set -euo pipefail

# Se placer dans le répertoire du projet (important quand lancé par launchd)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
VENV_STREAMLIT="$SCRIPT_DIR/.venv/bin/streamlit"

if [ ! -x "$VENV_STREAMLIT" ]; then
  echo "ERREUR : streamlit introuvable dans .venv pour l'UI legacy. Exécute ./setup.sh"
  exit 1
fi

# ---- Variables d'environnement depuis .env ------------------
# Nettoyer les anciens noms de variables (migration LM Studio → Ollama)
unset LMSTUDIO_BASE_URL LMSTUDIO_CHAT_MODEL LMSTUDIO_CONTEXT_SIZE LMSTUDIO_EMBED_MODEL 2>/dev/null || true
set -o allexport
source "$SCRIPT_DIR/.env"
set +o allexport

STREAMLIT_SERVER_ADDRESS="${STREAMLIT_SERVER_ADDRESS:-127.0.0.1}"

# Remplace host.docker.internal → localhost (héritage Docker)
if [[ "${OLLAMA_BASE_URL:-}" == *"host.docker.internal"* ]]; then
  export OLLAMA_BASE_URL="${OLLAMA_BASE_URL/host.docker.internal/localhost}"
fi

export APP_DATA_DIR="${APP_DATA_DIR:-$SCRIPT_DIR/data}"
export LOG_DIR="${LOG_DIR:-$SCRIPT_DIR/logs}"
export PYTHONPATH="$SCRIPT_DIR"

mkdir -p "$APP_DATA_DIR" "$LOG_DIR"

# Remplace l'icône statique par défaut de Streamlit avant le démarrage.
"$VENV_PYTHON" -m src.ui.streamlit_branding || true

# ---- Streamlit legacy (premier plan) ------------------------
exec "$VENV_STREAMLIT" run src/ui/app.py \
  --server.address="$STREAMLIT_SERVER_ADDRESS" \
  --server.port=8501 \
  --server.headless=true
