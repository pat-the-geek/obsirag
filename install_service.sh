#!/usr/bin/env bash
# =============================================================
# ObsiRAG — Installation du service macOS (launchd)
# Démarre automatiquement à la connexion de l'utilisateur.
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

LABEL="com.obsirag"
PLIST_DST="$HOME/Library/LaunchAgents/${LABEL}.plist"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$HOME/Library/Logs/ObsiRAG"

# Binaire Python Homebrew (hors Documents, pas bloqué par TCC)
PYTHON_BIN="$(readlink -f "$PROJECT_DIR/.venv/bin/python3.12")"
VENV_SITE_PACKAGES="$PROJECT_DIR/.venv/lib/python3.12/site-packages"

# ---- Désinstallation ----------------------------------------
if [[ "${1:-}" == "uninstall" ]]; then
  echo "==> Désinstallation du service ObsiRAG..."
  launchctl unload "$PLIST_DST" 2>/dev/null || true
  rm -f "$PLIST_DST"
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

# ---- Copier config Streamlit dans ~/.streamlit/ -------------
# ~/.streamlit/ n'est pas dans Documents → accessible par launchd
mkdir -p "$HOME/.streamlit"
cp "$PROJECT_DIR/.streamlit/config.toml" "$HOME/.streamlit/config.toml"

# ---- Lire les variables du .env ----------------------------
# Charger .env pour lire les valeurs (les guillemets sont gérés)
_env_val() {
  grep -E "^${1}=" "$PROJECT_DIR/.env" | head -1 \
    | sed -E "s/^${1}=['\"]?//;s/['\"]?$//"
}

VAULT_PATH="$(_env_val VAULT_PATH)"
APP_DATA_DIR="$(_env_val APP_DATA_DIR)"
OLLAMA_BASE_URL="$(_env_val OLLAMA_BASE_URL)"
OLLAMA_CHAT_MODEL="$(_env_val OLLAMA_CHAT_MODEL)"
OLLAMA_CONTEXT_SIZE="$(_env_val OLLAMA_CONTEXT_SIZE)"
OLLAMA_EMBED_MODEL="$(_env_val OLLAMA_EMBED_MODEL)"
EMBEDDING_MODEL="$(_env_val EMBEDDING_MODEL)"
EMBEDDING_MODEL="${EMBEDDING_MODEL:-paraphrase-multilingual-MiniLM-L12-v2}"
OBSIDIAN_VAULT_NAME="$(_env_val OBSIDIAN_VAULT_NAME)"
LOG_LEVEL="$(_env_val LOG_LEVEL)"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
AUTOLEARN_ENABLED="$(_env_val AUTOLEARN_ENABLED)"
AUTOLEARN_ENABLED="${AUTOLEARN_ENABLED:-true}"
AUTOLEARN_INTERVAL_MINUTES="$(_env_val AUTOLEARN_INTERVAL_MINUTES)"
AUTOLEARN_INTERVAL_MINUTES="${AUTOLEARN_INTERVAL_MINUTES:-60}"

# Remplacer host.docker.internal → localhost
OLLAMA_BASE_URL="${OLLAMA_BASE_URL/host.docker.internal/localhost}"

# APP_DATA_DIR par défaut
APP_DATA_DIR="${APP_DATA_DIR:-$HOME/Library/Application Support/ObsiRAG}"
mkdir -p "$APP_DATA_DIR"

# ---- Écrire le plist ----------------------------------------
cat > "$PLIST_DST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>

    <!-- Appel direct du binaire Python Homebrew (hors Documents, pas bloqué par TCC) -->
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_BIN}</string>
        <string>-m</string>
        <string>streamlit</string>
        <string>run</string>
        <string>${PROJECT_DIR}/src/ui/app.py</string>
        <string>--server.address=127.0.0.1</string>
        <string>--server.port=8501</string>
        <string>--server.headless=true</string>
    </array>

    <!-- Env vars embarquées (lecture du .env au moment de l'installation) -->
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
        <key>OLLAMA_BASE_URL</key>
        <string>${OLLAMA_BASE_URL}</string>
        <key>OLLAMA_CHAT_MODEL</key>
        <string>${OLLAMA_CHAT_MODEL}</string>
        <key>OLLAMA_CONTEXT_SIZE</key>
        <string>${OLLAMA_CONTEXT_SIZE}</string>
        <key>OLLAMA_EMBED_MODEL</key>
        <string>${OLLAMA_EMBED_MODEL}</string>
        <key>EMBEDDING_MODEL</key>
        <string>${EMBEDDING_MODEL}</string>
        <key>OBSIDIAN_VAULT_NAME</key>
        <string>${OBSIDIAN_VAULT_NAME}</string>
        <key>AUTOLEARN_ENABLED</key>
        <string>${AUTOLEARN_ENABLED}</string>
        <key>AUTOLEARN_INTERVAL_MINUTES</key>
        <string>${AUTOLEARN_INTERVAL_MINUTES}</string>
        <key>TRANSFORMERS_CACHE</key>
        <string>${HOME}/.cache/huggingface/transformers</string>
        <key>HF_HOME</key>
        <string>${HOME}/.cache/huggingface</string>
    </dict>

    <!-- Démarrer automatiquement à la connexion -->
    <key>RunAtLoad</key>
    <true/>

    <!-- Redémarrer si le processus s'arrête -->
    <key>KeepAlive</key>
    <true/>

    <!-- Logs dans ~/Library/Logs (hors TCC) -->
    <key>StandardOutPath</key>
    <string>${LOG_DIR}/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${LOG_DIR}/stderr.log</string>
</dict>
</plist>
PLIST

# ---- Charger le service -------------------------------------
launchctl unload "$PLIST_DST" 2>/dev/null || true
launchctl load "$PLIST_DST"

echo ""
echo "✓ Service ObsiRAG installé."
echo ""
echo "  ⚠️  ACTION REQUISE — Full Disk Access pour Python :"
echo "  macOS bloque l'accès à ~/Documents pour les services en arrière-plan."
echo "  Pour autoriser ObsiRAG à lire vos notes :"
echo ""
echo "    1. Ouvre : Réglages Système > Confidentialité et sécurité > Accès complet au disque"
echo "    2. Clique sur + et ajoute ce fichier :"
echo "       $PYTHON_BIN"
echo "    3. Relance ensuite le service :"
echo "       launchctl kickstart -k gui/\$(id -u)/$LABEL"
echo ""
echo "  → Une fois le FDA accordé, accessible sur : http://localhost:8501"
echo ""
echo "  Commandes utiles :"
echo "    Logs          : tail -f $LOG_DIR/stdout.log"
echo "    Logs erreurs  : tail -f $LOG_DIR/stderr.log"
echo "    Redémarrer    : launchctl kickstart -k gui/\$(id -u)/$LABEL"
echo "    Arrêter       : launchctl unload $PLIST_DST"
echo "    Désinstaller  : ./install_service.sh uninstall"

