#!/usr/bin/env bash
# =============================================================
# ObsiRAG — Arrêt API backend + Expo web
# =============================================================
set -euo pipefail

cd "$(dirname "$0")"

AUTOLEARN_PID_FILE=".obsirag-autolearn.pid"
API_PID_FILE=".obsirag-api.pid"
EXPO_PID_FILE=".obsirag-expo.pid"
LABEL="com.obsirag"
API_LABEL="com.obsirag.api"
AUTOLEARN_LABEL="com.obsirag.autolearn"
PLIST_DST="$HOME/Library/LaunchAgents/${LABEL}.plist"
API_PLIST_DST="$HOME/Library/LaunchAgents/${API_LABEL}.plist"
AUTOLEARN_PLIST_DST="$HOME/Library/LaunchAgents/${AUTOLEARN_LABEL}.plist"

_launchd_is_loaded() {
  launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1
}

_autolearn_launchd_is_loaded() {
  launchctl print "gui/$(id -u)/$AUTOLEARN_LABEL" >/dev/null 2>&1
}

_api_launchd_is_loaded() {
  launchctl print "gui/$(id -u)/$API_LABEL" >/dev/null 2>&1
}

_stop_launchd_service() {
  local name="$1"
  local label="$2"
  local plist="$3"

  if ! launchctl print "gui/$(id -u)/$label" >/dev/null 2>&1; then
    return 0
  fi

  echo "==> Arrêt du service launchd $name ($label)..."
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  if [ -f "$plist" ]; then
    launchctl unload "$plist" 2>/dev/null || true
  fi
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
  _stop_launchd_service "Streamlit obsolète" "$LABEL" "$PLIST_DST"
fi

if [ -f "$API_PLIST_DST" ] && _api_launchd_is_loaded; then
  _stop_launchd_service "API" "$API_LABEL" "$API_PLIST_DST"
fi

if [ -f "$AUTOLEARN_PLIST_DST" ] && _autolearn_launchd_is_loaded; then
  _stop_launchd_service "auto-learner" "$AUTOLEARN_LABEL" "$AUTOLEARN_PLIST_DST"
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
