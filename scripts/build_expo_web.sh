#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
EXPO_DIR="$ROOT_DIR/obsirag-expo"

cd "$EXPO_DIR"

if [ ! -d "node_modules" ]; then
  echo "ERREUR : dépendances Expo introuvables. Lance d'abord 'cd obsirag-expo && npm install'."
  exit 1
fi

rm -rf dist
npx expo export --platform web

if [ ! -f "dist/index.html" ]; then
  echo "ERREUR : build web Expo incomplet (dist/index.html manquant)."
  exit 1
fi

echo "✓ Build web Expo généré dans $EXPO_DIR/dist"