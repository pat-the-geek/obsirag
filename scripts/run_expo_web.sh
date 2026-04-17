#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
EXPO_DIR="$ROOT_DIR/obsirag-expo"
EXPO_PORT="${EXPO_WEB_PORT:-8081}"

cd "$EXPO_DIR"

if lsof -ti :"$EXPO_PORT" >/dev/null 2>&1; then
	echo "Expo web already running on http://localhost:$EXPO_PORT"
	exit 0
fi

exec ./node_modules/.bin/expo start --web -c --port "$EXPO_PORT"