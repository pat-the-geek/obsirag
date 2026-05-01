#!/usr/bin/env bash
# =============================================================
# ObsiRAG — Statut des services principaux
# =============================================================
set -euo pipefail

cd "$(dirname "$0")"

AUTOLEARN_LABEL="com.obsirag.autolearn"
API_PID_FILE=".obsirag-api.pid"
EXPO_PID_FILE=".obsirag-expo.pid"
API_PORT="${OBSIRAG_API_PORT:-8000}"
EXPO_PORT="${EXPO_WEB_PORT:-8081}"

if [ -f ".env" ]; then
  set -o allexport
  source ./.env
  set +o allexport
  API_PORT="${OBSIRAG_API_PORT:-$API_PORT}"
  EXPO_PORT="${EXPO_WEB_PORT:-$EXPO_PORT}"
fi

_print_pid_file_status() {
  local name="$1"
  local pid_file="$2"

  if [ ! -f "$pid_file" ]; then
    echo "$name: aucun pid file"
    return 0
  fi

  local pid
  pid="$(cat "$pid_file")"
  if kill -0 "$pid" 2>/dev/null; then
    echo "$name: PID $pid actif"
  else
    echo "$name: PID $pid stale"
  fi
}

_print_port_status() {
  local name="$1"
  local port="$2"
  local health_url="${3:-}"

  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    local listener
    listener="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN | awk 'NR==2 {print $1 " PID=" $2}')"
    echo "$name: UP sur $port (${listener:-listener inconnu})"
  else
    echo "$name: DOWN sur $port"
    return 0
  fi

  if [ -n "$health_url" ]; then
    local http_code
    http_code="$(curl -sS -m 5 -o /dev/null -w '%{http_code}' "$health_url" || true)"
    echo "$name: HTTP $http_code via $health_url"
  fi
}

echo "== Auto-learner"
if launchctl print "gui/$(id -u)/$AUTOLEARN_LABEL" >/tmp/obsirag_autolearn_status.$$ 2>&1; then
  awk '/state =|pid =|last exit code =|path =/ {print}' /tmp/obsirag_autolearn_status.$$
else
  echo "state = not-loaded"
  cat /tmp/obsirag_autolearn_status.$$
fi
rm -f /tmp/obsirag_autolearn_status.$$

echo ""
echo "== API backend"
_print_pid_file_status "api pid file" "$API_PID_FILE"
_print_port_status "api" "$API_PORT" "http://127.0.0.1:${API_PORT}/api/v1/health"

echo ""
echo "== Expo web"
_print_pid_file_status "expo pid file" "$EXPO_PID_FILE"
_print_port_status "expo" "$EXPO_PORT" "http://127.0.0.1:${EXPO_PORT}"