#!/usr/bin/env bash
# =============================================================
# ObsiRAG — Arrêt sans Docker
# =============================================================
set -euo pipefail

PID_FILE=".obsirag.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "Aucun processus ObsiRAG trouvé (pas de fichier $PID_FILE)."
  exit 0
fi

PID=$(cat "$PID_FILE")

if kill -0 "$PID" 2>/dev/null; then
  echo "==> Arrêt d'ObsiRAG (PID $PID)..."
  kill "$PID"
  rm -f "$PID_FILE"
  echo "    Arrêté."
else
  echo "Le processus $PID n'est plus actif."
  rm -f "$PID_FILE"
fi
