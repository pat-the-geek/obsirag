#!/usr/bin/env bash
# =============================================================
# ObsiRAG — Installation du service macOS (launchd)
# Installe le worker auto-learner persistant.
#
# Sur macOS, ~/Documents est protégé par TCC. Ce script :
#   - Appelle Python (Homebrew, hors Documents) directement
#   - Embarque toutes les variables d'env dans le plist
#   - Copie la config Streamlit dans ~/.streamlit/ (emplacement standard)
#
# Usage :
#   ./install_service.sh          # installe et démarre
#   ./install_service.sh uninstall  # désinstalle
# =============================================================
set -euo pipefail

AUTOLEARN_LABEL="com.obsirag.autolearn"
AUTOLEARN_PLIST_DST="$HOME/Library/LaunchAgents/${AUTOLEARN_LABEL}.plist"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$HOME/Library/Logs/ObsiRAG"

# Binaire Python Homebrew (hors Documents, pas bloqué par TCC)
PYTHON_BIN="$(readlink -f "$PROJECT_DIR/.venv/bin/python3.12")"
VENV_SITE_PACKAGES="$PROJECT_DIR/.venv/lib/python3.12/site-packages"

# ---- Désinstallation ----------------------------------------
if [[ "${1:-}" == "uninstall" ]]; then
  echo "==> Désinstallation du service ObsiRAG..."
  launchctl unload "$AUTOLEARN_PLIST_DST" 2>/dev/null || true
  rm -f "$HOME/Library/LaunchAgents/com.obsirag.plist"
  rm -f "$AUTOLEARN_PLIST_DST"
  echo "    Service supprimé."
  exit 0
fi

# ---- Vérifications ------------------------------------------
if [ ! -d "$PROJECT_DIR/.venv" ]; then
  echo "ERREUR : venv introuvable. Exécute d'abord : ./setup.sh"
  exit 1
fi

if [ ! -f "$PROJECT_DIR/.env" ]; then
  echo "ERREUR : fichier .env manquant. Configure-le avant d'installer le service."
  exit 1
fi

if [ ! -x "$PYTHON_BIN" ]; then
  echo "ERREUR : Python introuvable à $PYTHON_BIN"
  exit 1
fi

mkdir -p "$LOG_DIR"
mkdir -p "$HOME/Library/LaunchAgents"

# ---- Lire les variables du .env ----------------------------
# Charger .env pour lire les valeurs (les guillemets sont gérés)
# grep retourne exit 1 si rien trouvé — le || true empêche set -e de tout arrêter
_env_val() {
  grep -E "^${1}=" "$PROJECT_DIR/.env" 2>/dev/null | head -1 \
    | sed -E "s/^${1}=['\"]?//;s/['\"]?$//" || true
}

VAULT_PATH="$(_env_val VAULT_PATH)"
APP_DATA_DIR="$(_env_val APP_DATA_DIR)"
MLX_CHAT_MODEL="$(_env_val MLX_CHAT_MODEL)"
MLX_CHAT_MODEL="${MLX_CHAT_MODEL:-mlx-community/Qwen2.5-7B-Instruct-4bit}"
OLLAMA_EMBED_MODEL="$(_env_val OLLAMA_EMBED_MODEL)"
EMBEDDING_MODEL="$(_env_val EMBEDDING_MODEL)"
EMBEDDING_MODEL="${EMBEDDING_MODEL:-paraphrase-multilingual-MiniLM-L12-v2}"
OBSIDIAN_VAULT_NAME="$(_env_val OBSIDIAN_VAULT_NAME)"
LOG_LEVEL="$(_env_val LOG_LEVEL)"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
AUTOLEARN_ENABLED="$(_env_val AUTOLEARN_ENABLED)"
AUTOLEARN_ENABLED="${AUTOLEARN_ENABLED:-true}"
AUTOLEARN_ALLOW_BACKGROUND_LLM="$(_env_val AUTOLEARN_ALLOW_BACKGROUND_LLM)"
AUTOLEARN_ALLOW_BACKGROUND_LLM="${AUTOLEARN_ALLOW_BACKGROUND_LLM:-false}"
AUTOLEARN_INTERVAL_MINUTES="$(_env_val AUTOLEARN_INTERVAL_MINUTES)"
AUTOLEARN_INTERVAL_MINUTES="${AUTOLEARN_INTERVAL_MINUTES:-60}"
# APP_DATA_DIR par défaut
APP_DATA_DIR="${APP_DATA_DIR:-$HOME/Library/Application Support/ObsiRAG}"
mkdir -p "$APP_DATA_DIR"

cat > "$AUTOLEARN_PLIST_DST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${AUTOLEARN_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
    <string>${PYTHON_BIN}</string>
    <string>-m</string>
    <string>src.learning.worker</string>
    </array>

  <key>WorkingDirectory</key>
  <string>${PROJECT_DIR}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>${PROJECT_DIR}:${VENV_SITE_PACKAGES}</string>
        <key>VIRTUAL_ENV</key>
        <string>${PROJECT_DIR}/.venv</string>
        <key>PATH</key>
        <string>${PROJECT_DIR}/.venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key>
        <string>${HOME}</string>
        <key>VAULT_PATH</key>
        <string>${VAULT_PATH}</string>
        <key>APP_DATA_DIR</key>
        <string>${APP_DATA_DIR}</string>
        <key>LOG_DIR</key>
        <string>${PROJECT_DIR}/logs</string>
        <key>LOG_LEVEL</key>
        <string>${LOG_LEVEL}</string>
        <key>MLX_CHAT_MODEL</key>
        <string>${MLX_CHAT_MODEL}</string>
        <key>OLLAMA_EMBED_MODEL</key>
        <string>${OLLAMA_EMBED_MODEL}</string>
        <key>EMBEDDING_MODEL</key>
        <string>${EMBEDDING_MODEL}</string>
        <key>OBSIDIAN_VAULT_NAME</key>
        <string>${OBSIDIAN_VAULT_NAME}</string>
        <key>AUTOLEARN_ENABLED</key>
        <string>${AUTOLEARN_ENABLED}</string>
        <key>AUTOLEARN_ALLOW_BACKGROUND_LLM</key>
        <string>true</string>
        <key>AUTOLEARN_INTERVAL_MINUTES</key>
        <string>${AUTOLEARN_INTERVAL_MINUTES}</string>
        <key>TRANSFORMERS_CACHE</key>
        <string>${HOME}/.cache/huggingface/transformers</string>
        <key>HF_HOME</key>
        <string>${HOME}/.cache/huggingface</string>
        <key>TZ</key>
        <string>Europe/Zurich</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>StandardOutPath</key>
    <string>${LOG_DIR}/autolearn.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/autolearn.stderr.log</string>
</dict>
</plist>
PLIST

# ---- Charger le service -------------------------------------
launchctl unload "$HOME/Library/LaunchAgents/com.obsirag.plist" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/com.obsirag.plist"
launchctl unload "$AUTOLEARN_PLIST_DST" 2>/dev/null || true
if [ "$AUTOLEARN_ENABLED" = "true" ]; then
  launchctl load "$AUTOLEARN_PLIST_DST"
fi

echo ""
echo "✓ Service auto-learner ObsiRAG installé."
echo ""
echo "  ⚠️  ACTION REQUISE — Full Disk Access pour Python :"
echo "  macOS bloque l'accès à ~/Documents pour les services en arrière-plan."
echo "  Pour autoriser ObsiRAG à lire vos notes :"
echo ""
echo "    1. Ouvre : Réglages Système > Confidentialité et sécurité > Accès complet au disque"
echo "    2. Clique sur + et ajoute ce fichier :"
echo "       $PYTHON_BIN"
echo "    3. Relance ensuite le service :"
echo "       launchctl kickstart -k gui/\$(id -u)/$AUTOLEARN_LABEL"
echo ""
echo "  → L'auto-learner restera actif via launchd tant que la session utilisateur est ouverte"
echo ""
echo "  Commandes utiles :"
echo "    Logs worker   : tail -f $LOG_DIR/autolearn.stdout.log"
echo "    Redémarrer worker : launchctl kickstart -k gui/\$(id -u)/$AUTOLEARN_LABEL"
echo "    Arrêter worker    : launchctl unload $AUTOLEARN_PLIST_DST"
echo "    Désinstaller  : ./install_service.sh uninstall"

