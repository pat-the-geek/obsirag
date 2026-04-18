#!/usr/bin/env bash
# =============================================================
# ObsiRAG — Arrêt API backend + Expo web
# =============================================================
set -euo pipefail

AUTOLEARN_PID_FILE=".obsirag-autolearn.pid"
API_PID_FILE=".obsirag-api.pid"
EXPO_PID_FILE=".obsirag-expo.pid"
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

_stop_pid_file() {
  local name="$1"
  local pid_file="$2"

  if [ ! -f "$pid_file" ]; then
    return 0
  fi

  local pid
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    echo "==> Arrêt de $name (PID $pid)..."
    pkill -P "$pid" 2>/dev/null || true
    kill "$pid" 2>/dev/null || true
  else
    echo "Le processus $name ($pid) n'est plus actif."
  fi

  rm -f "$pid_file"
}

if [ -f "$PLIST_DST" ] && _launchd_is_loaded; then
  echo "==> Arrêt du service launchd Streamlit obsolète (${LABEL})..."
  launchctl unload "$PLIST_DST" 2>/dev/null || true
fi

if [ -f "$AUTOLEARN_PLIST_DST" ] && _autolearn_launchd_is_loaded; then
  echo "==> Auto-learner launchd laissé actif (${AUTOLEARN_LABEL})."
fi

_stop_pid_file "l'API backend" "$API_PID_FILE"
_stop_pid_file "Expo web" "$EXPO_PID_FILE"

# Nettoyage de sécurité : tuer tout processus encore accroché aux ports connus
lsof -ti :8501 2>/dev/null | xargs kill -9 2>/dev/null || true
lsof -ti :8000 2>/dev/null | xargs kill -9 2>/dev/null || true
lsof -ti :8081 2>/dev/null | xargs kill -9 2>/dev/null || true

rm -f "$API_PID_FILE"
rm -f "$EXPO_PID_FILE"
echo "    Arrêté."
