#!/bin/bash
set -euo pipefail

# Attente que l'entrypoint ait écrit /app/.env et initialisé LanceDB
sleep 10

export PYTHONPATH=/app
# Le worker autolearn gère son propre LLM Ollama en tâche de fond
export AUTOLEARN_ALLOW_BACKGROUND_LLM=true

echo "$(date -u +%FT%TZ) Démarrage du worker autolearn (PID $$)"
cd /app
exec python -m src.learning.worker
