#!/usr/bin/env bash
# =============================================================
# ObsiRAG — Démarrage manuel (arrière-plan)
# Pour un démarrage automatique au login : ./install_service.sh
# =============================================================
set -euo pipefail

cd "$(dirname "$0")"

PID_FILE=".obsirag.pid"
LABEL="com.obsirag"
PLIST_DST="$HOME/Library/LaunchAgents/${LABEL}.plist"

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

_launchd_is_loaded() {
  launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1
}

_wait_for_port() {
  local attempts=20
  while [ "$attempts" -gt 0 ]; do
    if lsof -ti :8501 >/dev/null 2>&1; then
      return 0
    fi
    attempts=$((attempts - 1))
    sleep 0.5
  done
  return 1
}

if [ -f "$PLIST_DST" ]; then
  echo "==> Service launchd détecté (${LABEL})"
  if _launchd_is_loaded; then
    launchctl kickstart -k "gui/$(id -u)/$LABEL"
  else
    launchctl load "$PLIST_DST"
  fi

  if ! _wait_for_port; then
    echo "ERREUR : le service launchd n'a pas ouvert le port 8501."
    exit 1
  fi

  APP_PID="$(lsof -ti :8501 | head -n 1)"
  rm -f "$PID_FILE"
  echo "==> ObsiRAG démarré via launchd (PID $APP_PID) — http://localhost:8501"
  echo "    Logs  : tail -f $HOME/Library/Logs/ObsiRAG/stdout.log"
  echo "    Arrêt : ./stop.sh"
  exit 0
fi

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
if ! _wait_for_port; then
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    rm -f "$PID_FILE"
    echo "ERREUR : échec du démarrage d'ObsiRAG. Consulte logs/obsirag_error.log"
    exit 1
  fi
fi
if [ "$STREAMLIT_SERVER_ADDRESS" = "0.0.0.0" ]; then
  echo "==> ObsiRAG démarré (PID $APP_PID) — http://localhost:8501"
  echo "    Exposition reseau active : utilise l'IP de cette machine ou l'IP Tailscale sur le port 8501"
else
  echo "==> ObsiRAG démarré (PID $APP_PID) — http://localhost:8501"
fi
echo "    Logs  : tail -f logs/obsirag.log"
echo "    Arrêt : ./stop.sh"
