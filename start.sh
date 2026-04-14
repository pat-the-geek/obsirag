#!/usr/bin/env bash
# =============================================================
# ObsiRAG — Démarrage manuel (arrière-plan)
# Pour un démarrage automatique au login : ./install_service.sh
# =============================================================
set -euo pipefail

cd "$(dirname "$0")"

PID_FILE=".obsirag.pid"

if [ ! -d ".venv" ]; then
  echo "ERREUR : venv introuvable. Exécute d'abord ./setup.sh"
  exit 1
fi

if [ ! -f ".env" ]; then
  echo "ERREUR : fichier .env manquant. Copie .env.example et configure-le."
  exit 1
fi

set -o allexport
source ./.env
set +o allexport

STREAMLIT_SERVER_ADDRESS="${STREAMLIT_SERVER_ADDRESS:-127.0.0.1}"

if [ -f "$PID_FILE" ]; then
  OLD_PID=$(cat "$PID_FILE")
  if kill -0 "$OLD_PID" 2>/dev/null; then
    echo "ObsiRAG tourne déjà (PID $OLD_PID). Lance ./stop.sh pour l'arrêter."
    exit 1
  else
    rm -f "$PID_FILE"
  fi
fi

mkdir -p logs

./run.sh >> logs/obsirag.log 2>> logs/obsirag_error.log &

APP_PID=$!
echo "$APP_PID" > "$PID_FILE"
if [ "$STREAMLIT_SERVER_ADDRESS" = "0.0.0.0" ]; then
  echo "==> ObsiRAG démarré (PID $APP_PID) — http://localhost:8501"
  echo "    Exposition reseau active : utilise l'IP de cette machine ou l'IP Tailscale sur le port 8501"
else
  echo "==> ObsiRAG démarré (PID $APP_PID) — http://localhost:8501"
fi
echo "    Logs  : tail -f logs/obsirag.log"
echo "    Arrêt : ./stop.sh"
