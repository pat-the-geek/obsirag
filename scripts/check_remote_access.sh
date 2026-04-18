#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

HOST=""
API_PORT="8000"
EXPO_PORT="8081"
TIMEOUT_SECONDS="5"

usage() {
  echo "Usage: ./scripts/check_remote_access.sh --host HOST [--api-port PORT] [--expo-port PORT] [--timeout SECONDS]"
  echo ""
  echo "Examples:"
  echo "  ./scripts/check_remote_access.sh --host tailscale-host.example.ts.net"
  echo "  ./scripts/check_remote_access.sh --host nom-de-machine.local --api-port 8000 --expo-port 8081"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --host)
      if [ $# -lt 2 ]; then
        echo "Option --host attend une valeur"
        exit 1
      fi
      HOST="$2"
      shift
      ;;
    --api-port)
      if [ $# -lt 2 ]; then
        echo "Option --api-port attend une valeur"
        exit 1
      fi
      API_PORT="$2"
      shift
      ;;
    --expo-port)
      if [ $# -lt 2 ]; then
        echo "Option --expo-port attend une valeur"
        exit 1
      fi
      EXPO_PORT="$2"
      shift
      ;;
    --timeout)
      if [ $# -lt 2 ]; then
        echo "Option --timeout attend une valeur"
        exit 1
      fi
      TIMEOUT_SECONDS="$2"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Argument non reconnu: $1"
      usage
      exit 1
      ;;
  esac
  shift
done

if [ -z "$HOST" ]; then
  echo "Le parametre --host est obligatoire"
  usage
  exit 1
fi

if [ -f ".env" ]; then
  set -o allexport
  source ./.env
  set +o allexport
  API_PORT="${OBSIRAG_API_PORT:-$API_PORT}"
  EXPO_PORT="${EXPO_WEB_PORT:-$EXPO_PORT}"
fi

API_PUBLIC_BASE_URL_VALUE="${API_PUBLIC_BASE_URL:-}"
EXPECTED_PUBLIC_BASE_URL="http://${HOST}:${API_PORT}"

check_http_code() {
  local url="$1"
  curl -sS -m "$TIMEOUT_SECONDS" -o /dev/null -w '%{http_code}' "$url" || true
}

print_listener() {
  local label="$1"
  local port="$2"

  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    local listener
    listener="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN | awk 'NR==2 {print $1 " PID=" $2 " " $9}')"
    echo "$label: UP sur $port (${listener:-listener inconnu})"
  else
    echo "$label: DOWN sur $port"
  fi
}

echo "== Verification configuration publique"
echo "Host cible             : $HOST"
echo "API attendue           : $EXPECTED_PUBLIC_BASE_URL"
echo "API_PUBLIC_BASE_URL    : ${API_PUBLIC_BASE_URL_VALUE:-non definie}"
if [ -n "$API_PUBLIC_BASE_URL_VALUE" ] && [ "$API_PUBLIC_BASE_URL_VALUE" != "$EXPECTED_PUBLIC_BASE_URL" ]; then
  echo "ATTENTION: API_PUBLIC_BASE_URL ne correspond pas au host fourni."
fi

echo ""
echo "== Verification des listeners locaux"
print_listener "api" "$API_PORT"
print_listener "expo" "$EXPO_PORT"

echo ""
echo "== Verification HTTP locale"
echo "api local  : HTTP $(check_http_code "http://127.0.0.1:${API_PORT}/api/v1/health") via http://127.0.0.1:${API_PORT}/api/v1/health"
echo "expo local : HTTP $(check_http_code "http://127.0.0.1:${EXPO_PORT}") via http://127.0.0.1:${EXPO_PORT}"

echo ""
echo "== Verification HTTP via host public"
echo "api public : HTTP $(check_http_code "http://${HOST}:${API_PORT}/api/v1/health") via http://${HOST}:${API_PORT}/api/v1/health"
echo "expo public: HTTP $(check_http_code "http://${HOST}:${EXPO_PORT}") via http://${HOST}:${EXPO_PORT}"

echo ""
echo "== Controle termine"
echo "Si les checks locaux sont OK mais pas les checks publics, verifier Tailscale, le pare-feu macOS ou la resolution DNS du host fourni depuis la machine distante."