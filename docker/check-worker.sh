#!/bin/bash
# Redémarre le worker autolearn s'il ne tourne plus.
# Exécuté toutes les 5 minutes par cron.

# Vérifie à la fois le worker python ET le script de démarrage (qui dort 10 s au boot)
if pgrep -f "src.learning.worker" > /dev/null 2>&1 || pgrep -f "run-worker.sh" > /dev/null 2>&1; then
    exit 0
fi

echo "$(date -u +%FT%TZ) Worker autolearn absent — relance en cours…"
export PYTHONPATH=/app
export AUTOLEARN_ALLOW_BACKGROUND_LLM=true
cd /app
python -m src.learning.worker >> /app/logs/worker.log 2>&1 &
echo "$(date -u +%FT%TZ) Worker autolearn relancé (PID $!)"
