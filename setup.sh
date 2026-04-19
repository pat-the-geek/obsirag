#!/usr/bin/env bash
# =============================================================
# ObsiRAG — Setup natif (macOS / Apple Silicon)
# À lancer une seule fois, depuis la racine du projet.
# =============================================================
set -euo pipefail

VENV_DIR=".venv"
PYTHON=${PYTHON_BIN:-python3}

echo "==> Vérification de Python..."
if ! command -v "$PYTHON" &>/dev/null; then
  echo "ERREUR : python3 introuvable. Installe Python 3.11+ via brew ou python.org."
  exit 1
fi

PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "    Python détecté : $PY_VERSION"

# ---- Environnement virtuel -----------------------------------
if [ ! -d "$VENV_DIR" ]; then
  echo "==> Création du venv dans $VENV_DIR..."
  "$PYTHON" -m venv "$VENV_DIR"
else
  echo "==> Venv existant trouvé ($VENV_DIR), mise à jour des dépendances."
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

echo "==> Mise à jour de pip..."
pip install --quiet --upgrade pip

# ---- PyTorch CPU (ou MPS sur Apple Silicon) ------------------
echo "==> Installation de PyTorch..."
if [[ "$(uname -m)" == "arm64" ]]; then
  # Apple Silicon : version standard PyPI inclut le support MPS
  pip install --quiet "torch>=2.4.0"
else
  # Intel Mac : forcé sur l'index CPU pour éviter le build CUDA
  pip install --quiet "torch>=2.4.0" --index-url https://download.pytorch.org/whl/cpu
fi

# ---- Dépendances Python --------------------------------------
echo "==> Installation des dépendances (requirements.txt)..."
pip install --quiet -r requirements.txt

# ---- Modèle spaCy NER multilingue ---------------------------
echo "==> Téléchargement du modèle spaCy xx_ent_wiki_sm..."
python -m spacy download xx_ent_wiki_sm

# ---- Répertoires système ------------------------------------
echo "==> Création des répertoires système..."
mkdir -p data logs

# ---- Fichier .env -------------------------------------------
if [ ! -f ".env" ]; then
  echo "==> Création de .env depuis .env.example..."
  cp .env.example .env
  echo ""
  echo "  !! Edite .env et définis au minimum :"
  echo "       VAULT_PATH=/chemin/absolu/vers/ton/coffre"
  echo "       OLLAMA_BASE_URL=http://localhost:11434/v1  (Ollama)"
  echo "       APP_DATA_DIR=$(pwd)/data"
  echo ""
else
  echo "==> .env existant — aucune modification."
fi

echo ""
echo "✓ Setup terminé. Lance l'app avec : ./start.sh"
