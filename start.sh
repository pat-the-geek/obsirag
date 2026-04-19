#!/usr/bin/env bash
# =============================================================
# ObsiRAG — Démarrage API backend + Expo web
# =============================================================
set -euo pipefail

cd "$(dirname "$0")"

AUTOLEARN_PID_FILE=".obsirag-autolearn.pid"
API_PID_FILE=".obsirag-api.pid"
EXPO_PID_FILE=".obsirag-expo.pid"
EXPO_DIST_DIR="obsirag-expo/dist"
LABEL="com.obsirag"
API_LABEL="com.obsirag.api"
AUTOLEARN_LABEL="com.obsirag.autolearn"
PLIST_DST="$HOME/Library/LaunchAgents/${LABEL}.plist"
API_PLIST_DST="$HOME/Library/LaunchAgents/${API_LABEL}.plist"
AUTOLEARN_PLIST_DST="$HOME/Library/LaunchAgents/${AUTOLEARN_LABEL}.plist"

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

AUTOLEARN_ENABLED="${AUTOLEARN_ENABLED:-true}"
API_PORT="${OBSIRAG_API_PORT:-8000}"
EXPO_PORT="${EXPO_WEB_PORT:-8081}"

_launchd_is_loaded() {
  launchctl print "gui/$(id -u)/$LABEL" >/dev/null 2>&1
}

_autolearn_launchd_is_loaded() {
  launchctl print "gui/$(id -u)/$AUTOLEARN_LABEL" >/dev/null 2>&1
}

_api_launchd_is_loaded() {
  launchctl print "gui/$(id -u)/$API_LABEL" >/dev/null 2>&1
}

_wait_for_port() {
  local port="$1"
  local attempts="${2:-20}"
  while [ "$attempts" -gt 0 ]; do
    if lsof -ti :"$port" >/dev/null 2>&1; then
      return 0
    fi
    attempts=$((attempts - 1))
    sleep 0.5
  done
  return 1
}

_cleanup_stale_pid_file() {
  local pid_file="$1"
  if [ ! -f "$pid_file" ]; then
    return 0
  fi

  local old_pid
  old_pid="$(cat "$pid_file")"
  if kill -0 "$old_pid" 2>/dev/null; then
    return 1
  fi

  rm -f "$pid_file"
  return 0
}

_wait_for_pid() {
  local pid="$1"
  local attempts="${2:-10}"
  while [ "$attempts" -gt 0 ]; do
    if kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    attempts=$((attempts - 1))
    sleep 0.5
  done
  return 1
}

_stop_existing_port_listener() {
  local name="$1"
  local port="$2"

  local listeners
  listeners="$(lsof -ti :"$port" 2>/dev/null || true)"
  if [ -z "$listeners" ]; then
    return 0
  fi

  echo "==> Arrêt du listener existant pour $name sur le port $port"
  printf '%s\n' "$listeners" | xargs kill 2>/dev/null || true

  local attempts=10
  while [ "$attempts" -gt 0 ]; do
    if ! lsof -ti :"$port" >/dev/null 2>&1; then
      return 0
    fi
    attempts=$((attempts - 1))
    sleep 0.5
  done

  listeners="$(lsof -ti :"$port" 2>/dev/null || true)"
  if [ -n "$listeners" ]; then
    echo "==> Forçage de l'arrêt du listener existant pour $name sur le port $port"
    printf '%s\n' "$listeners" | xargs kill -9 2>/dev/null || true
  fi
}

_start_background_service() {
  local name="$1"
  local pid_file="$2"
  local port="$3"
  local log_file="$4"
  local error_file="$5"
  local command="$6"
  local attempts="${7:-20}"

  if ! _cleanup_stale_pid_file "$pid_file"; then
    local existing_pid
    existing_pid="$(cat "$pid_file")"
    echo "$name tourne déjà (PID $existing_pid)."
    return 0
  fi

  if lsof -ti :"$port" >/dev/null 2>&1; then
    _stop_existing_port_listener "$name" "$port"
  fi

  bash -lc "$command" >> "$log_file" 2>> "$error_file" &
  local service_pid=$!
  echo "$service_pid" > "$pid_file"

  if ! _wait_for_port "$port" "$attempts"; then
    if ! kill -0 "$service_pid" 2>/dev/null; then
      rm -f "$pid_file"
      echo "ERREUR : échec du démarrage de $name. Consulte $error_file"
      return 1
    fi
    echo "ATTENTION : $name n'a pas encore ouvert le port $port. Consulte $log_file"
    return 0
  fi

  echo "$name démarré (PID $service_pid) — http://localhost:$port"
}

_start_autolearn() {
  if [ "$AUTOLEARN_ENABLED" != "true" ]; then
    echo "==> Auto-learner désactivé par AUTOLEARN_ENABLED=$AUTOLEARN_ENABLED"
    rm -f "$AUTOLEARN_PID_FILE"
    return 0
  fi

  if [ -f "$PLIST_DST" ] && _launchd_is_loaded; then
    echo "==> Arrêt du service launchd Streamlit obsolète (${LABEL})"
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    lsof -ti :8501 2>/dev/null | xargs kill -9 2>/dev/null || true
  fi

  if [ -f "$AUTOLEARN_PLIST_DST" ]; then
    echo "==> Vérification de l'auto-learner via launchd"
    if _autolearn_launchd_is_loaded; then
      launchctl kickstart -k "gui/$(id -u)/$AUTOLEARN_LABEL"
    else
      launchctl load "$AUTOLEARN_PLIST_DST"
    fi
    rm -f "$AUTOLEARN_PID_FILE"
    echo "    Logs worker : tail -f $HOME/Library/Logs/ObsiRAG/autolearn.stdout.log"
    return 0
  fi

  echo "ERREUR : plist launchd auto-learner introuvable ($AUTOLEARN_PLIST_DST). Lance ./install_service.sh pour installer le worker persistant."
  return 1
}

_start_api() {
  if [ -f "$API_PLIST_DST" ]; then
    echo "==> Vérification de l'API via launchd"
    if ! _api_launchd_is_loaded && lsof -ti :"$API_PORT" >/dev/null 2>&1; then
      _stop_existing_port_listener "API backend" "$API_PORT"
    fi
    if _api_launchd_is_loaded; then
      launchctl kickstart -k "gui/$(id -u)/$API_LABEL"
    else
      launchctl load "$API_PLIST_DST"
    fi
    if ! _wait_for_port "$API_PORT" 40; then
      echo "ERREUR : l'API launchd n'a pas ouvert le port $API_PORT. Consulte $HOME/Library/Logs/ObsiRAG/api.stderr.log"
      return 1
    fi
    rm -f "$API_PID_FILE"
    echo "API backend démarré via launchd — http://localhost:$API_PORT"
    echo "    Logs API    : tail -f $HOME/Library/Logs/ObsiRAG/api.stdout.log"
    return 0
  fi

  echo "==> Démarrage local de l'API backend"
  _start_background_service \
    "API backend" \
    "$API_PID_FILE" \
    "$API_PORT" \
    "logs/obsirag-api.log" \
    "logs/obsirag-api_error.log" \
    "cd '$PWD' && ./scripts/run_api.sh" \
    40
}

mkdir -p logs

_start_autolearn

echo "==> Démarrage de l'API backend"
_start_api

if [ -f "$EXPO_DIST_DIR/index.html" ]; then
  echo "==> Frontend web statique détecté"
  rm -f "$EXPO_PID_FILE"
  echo "Frontend Expo servi par l'API — http://localhost:$API_PORT"
else
  echo "==> Démarrage d'Expo web (mode développement)"
  _start_background_service \
    "Expo web" \
    "$EXPO_PID_FILE" \
    "$EXPO_PORT" \
    "logs/obsirag-expo.log" \
    "logs/obsirag-expo_error.log" \
    "cd '$PWD' && ./scripts/run_expo_web.sh" \
    40
fi

if [ -f "$API_PLIST_DST" ]; then
  echo "    Logs API   : tail -f $HOME/Library/Logs/ObsiRAG/api.stdout.log"
elif [ -f "$API_PID_FILE" ]; then
  echo "    Logs API   : tail -f logs/obsirag-api.log"
fi
if [ -f "$EXPO_DIST_DIR/index.html" ]; then
  echo "    Frontend   : servi par l'API sur http://localhost:$API_PORT"
elif [ -f "$EXPO_PID_FILE" ]; then
  echo "    Logs Expo  : tail -f logs/obsirag-expo.log"
fi
echo "    Arrêt : ./stop.sh"
