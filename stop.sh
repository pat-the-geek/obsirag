#!/usr/bin/env bash
# =============================================================
# ObsiRAG — Arrêt sans Docker
# =============================================================
set -euo pipefail

PID_FILE=".obsirag.pid"
AUTOLEARN_PID_FILE=".obsirag-autolearn.pid"
LABEL="com.obsirag"
AUTOLEARN_LABEL="com.obsirag.autolearn"
PLIST_DST="$HOME/Library/LaunchAgents/${LABEL}.plist"
AUTOLEARN_PLIST_DST="$HOME/Library/LaunchAgents/${AUTOLEARN_LABEL}.plist"

_launchd_is_loaded() {
  launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1
}

_autolearn_launchd_is_loaded() {
  launchctl print "gui/$(id -u)/$AUTOLEARN_LABEL" >/dev/null 2>&1
}

if [ -f "$PLIST_DST" ] && _launchd_is_loaded; then
  echo "==> Arrêt du service launchd ObsiRAG (${LABEL})..."
  launchctl unload "$PLIST_DST"
  if [ -f "$AUTOLEARN_PLIST_DST" ] && _autolearn_launchd_is_loaded; then
    echo "==> Arrêt du service launchd auto-learner (${AUTOLEARN_LABEL})..."
    launchctl unload "$AUTOLEARN_PLIST_DST"
  fi
  lsof -ti :8501 2>/dev/null | xargs kill -9 2>/dev/null || true
  rm -f "$PID_FILE"
  rm -f "$AUTOLEARN_PID_FILE"
  echo "    Arrêté."
  exit 0
fi

if [ ! -f "$PID_FILE" ]; then
  echo "Aucun processus ObsiRAG trouvé (pas de fichier $PID_FILE)."
else
  PID=$(cat "$PID_FILE")

  if kill -0 "$PID" 2>/dev/null; then
    echo "==> Arrêt d'ObsiRAG (PID $PID)..."
    pkill -P "$PID" 2>/dev/null || true
    kill "$PID" 2>/dev/null || true
  else
    echo "Le processus $PID n'est plus actif."
  fi
fi

if [ -f "$AUTOLEARN_PID_FILE" ]; then
  AUTOLEARN_PID=$(cat "$AUTOLEARN_PID_FILE")
  if kill -0 "$AUTOLEARN_PID" 2>/dev/null; then
    echo "==> Arrêt de l'auto-learner (PID $AUTOLEARN_PID)..."
    pkill -P "$AUTOLEARN_PID" 2>/dev/null || true
    kill "$AUTOLEARN_PID" 2>/dev/null || true
  fi
fi

# Nettoyage de sécurité : tuer tout processus encore accroché au port 8501
lsof -ti :8501 2>/dev/null | xargs kill -9 2>/dev/null || true

rm -f "$PID_FILE"
rm -f "$AUTOLEARN_PID_FILE"
echo "    Arrêté."
