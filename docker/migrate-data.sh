#!/usr/bin/env bash
# =============================================================
# migrate-data.sh — Copie les données ObsiRAG existantes (macOS)
# vers le volume Docker obsirag-data.
#
# À exécuter UNE SEULE FOIS avant le premier `docker compose up`.
# Le container ne doit pas tourner pendant la migration.
# =============================================================
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f ".env" ]; then
  echo "ERREUR : fichier .env introuvable. Lance ce script depuis la racine du projet."
  exit 1
fi

set -o allexport
source ./.env
set +o allexport

SRC_DATA_DIR="${APP_DATA_DIR:-}"

if [ -z "$SRC_DATA_DIR" ] || [ ! -d "$SRC_DATA_DIR" ]; then
  echo "ERREUR : APP_DATA_DIR='${SRC_DATA_DIR}' introuvable ou non défini dans .env"
  exit 1
fi

echo "==> Source des données : $SRC_DATA_DIR"
echo "==> Destination        : volume Docker 'obsirag-data' (monté sur /app/data)"

# Vérification que le volume existe (il est créé par docker compose)
if ! docker volume inspect obsirag-data >/dev/null 2>&1; then
  echo "Création du volume Docker obsirag-data…"
  docker volume create obsirag-data
fi

# Copie via un container temporaire Alpine
echo "==> Copie en cours…"
docker run --rm \
  -v "${SRC_DATA_DIR}:/src:ro" \
  -v "obsirag-data:/dst" \
  alpine \
  sh -c "cp -a /src/. /dst/ && echo 'Copie terminée.'"

echo ""
echo "Migration réussie. Tu peux maintenant lancer :"
echo "  docker compose up -d"
