#!/bin/bash
set -euo pipefail

echo "=== ObsiRAG — démarrage du container ==="

# ── Répertoires obligatoires ──────────────────────────────────────────────────
mkdir -p /app/logs /app/data

# ── Export des variables d'environnement Docker vers /app/.env ───────────────
# pydantic-settings lit /app/.env automatiquement (même pour les processus
# démarrés par cron qui n'héritent pas de l'environnement Docker).
# On filtre les variables système inutiles pour le projet.
env | grep -E '^[A-Z_][A-Z0-9_]*=' \
    | grep -Ev '^(HOME|HOSTNAME|SHLVL|PWD|OLDPWD|TERM|_)=' \
    > /app/.env
echo "Variables d'environnement exportées vers /app/.env"

# ── Daemon cron ───────────────────────────────────────────────────────────────
# L'entrée @reboot dans /etc/cron.d/obsirag lancera le worker autolearn
# dès que cron démarre.
cron
echo "Cron démarré — le worker autolearn sera lancé dans ~10 s"

# ── API FastAPI (processus principal / PID 1) ─────────────────────────────────
export PYTHONPATH=/app
# Le worker autolearn tourne en processus séparé (cron) ;
# l'API ne doit pas le démarrer en interne.
export AUTOLEARN_ALLOW_BACKGROUND_LLM=false

API_PORT="${OBSIRAG_API_PORT:-8080}"
LOG_LEVEL_LOWER="$(echo "${LOG_LEVEL:-INFO}" | tr '[:upper:]' '[:lower:]')"

echo "Démarrage de l'API ObsiRAG sur le port ${API_PORT}…"
exec python -m uvicorn src.api.main:app \
    --host 0.0.0.0 \
    --port "${API_PORT}" \
    --log-level "${LOG_LEVEL_LOWER}"
