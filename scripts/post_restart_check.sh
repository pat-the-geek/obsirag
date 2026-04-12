#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

APP_URL="http://127.0.0.1:8501"
LOG_FILE="logs/obsirag.log"
MAX_ATTEMPTS=30
SLEEP_SECONDS=1

echo "==> Cycle stop/start"
./stop.sh || true
./start.sh

echo "==> Vérification HTTP (${APP_URL})"
status_code=""
for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  status_code="$(curl -s -o /dev/null -w "%{http_code}" "$APP_URL" || true)"
  if [ "$status_code" = "200" ]; then
    echo "    OK (HTTP 200) après ${attempt} tentative(s)."
    break
  fi
  if [ "$attempt" -eq "$MAX_ATTEMPTS" ]; then
    echo "    ECHEC: statut HTTP final=${status_code:-N/A}"
    exit 1
  fi
  sleep "$SLEEP_SECONDS"
done

echo "==> Dernières lignes de logs"
if [ -f "$LOG_FILE" ]; then
  tail -n 40 "$LOG_FILE"
else
  echo "    Aucun log trouvé (${LOG_FILE})"
fi

echo "==> Contrôle post-redémarrage terminé"