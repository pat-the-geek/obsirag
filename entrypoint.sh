#!/bin/bash
set -e

# Créer et corriger les permissions sur les volumes Docker (montés en root)
mkdir -p /app/data /app/logs /app/.cache
chown -R obsirag:obsirag /app/data /app/logs /app/.cache

# Passer à l'utilisateur non-root pour démarrer Streamlit
exec gosu obsirag "$@"
