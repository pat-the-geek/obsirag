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
  # Tuer les processus enfants d'abord, puis le parent
  pkill -P "$PID" 2>/dev/null || true
  kill "$PID" 2>/dev/null || true
else
  echo "Le processus $PID n'est plus actif."
fi

# Nettoyage de sécurité : tuer tout processus encore accroché au port 8501
lsof -ti :8501 2>/dev/null | xargs kill -9 2>/dev/null || true

rm -f "$PID_FILE"
echo "    Arrêté."
