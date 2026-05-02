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

API_LABEL="com.obsirag.api"
API_PLIST_DST="$HOME/Library/LaunchAgents/${API_LABEL}.plist"
AUTOLEARN_LABEL="com.obsirag.autolearn"
AUTOLEARN_PLIST_DST="$HOME/Library/LaunchAgents/${AUTOLEARN_LABEL}.plist"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$HOME/Library/Logs/ObsiRAG"

# Python du venv courant. On évite toute version figée pour rester compatible
# avec les reconstructions du virtualenv (3.12, 3.14, etc.).
PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
VENV_SITE_PACKAGES=""

# ---- Désinstallation ----------------------------------------
if [[ "${1:-}" == "uninstall" ]]; then
  echo "==> Désinstallation du service ObsiRAG..."
  launchctl unload "$API_PLIST_DST" 2>/dev/null || true
  launchctl unload "$AUTOLEARN_PLIST_DST" 2>/dev/null || true
  rm -f "$HOME/Library/LaunchAgents/com.obsirag.plist"
  rm -f "$API_PLIST_DST"
  rm -f "$AUTOLEARN_PLIST_DST"
  echo "    Services supprimés."
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

VENV_SITE_PACKAGES="$($PYTHON_BIN -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
if [ -z "$VENV_SITE_PACKAGES" ] || [ ! -d "$VENV_SITE_PACKAGES" ]; then
  echo "ERREUR : site-packages introuvable pour $PYTHON_BIN"
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
EURIA_URL="$(_env_val EURIA_URL)"
EURIA_URL="${EURIA_URL:-$(_env_val EURIA_API_URL)}"
EURIA_URL="${EURIA_URL:-$(_env_val INFOMANIAK_EURIA_URL)}"
EURIA_BEARER="$(_env_val EURIA_BEARER)"
EURIA_BEARER="${EURIA_BEARER:-$(_env_val EURIA_API_KEY)}"
EURIA_BEARER="${EURIA_BEARER:-$(_env_val EURIA_TOKEN)}"
EURIA_BEARER="${EURIA_BEARER:-$(_env_val INFOMANIAK_API_KEY)}"
EURIA_MODEL="$(_env_val EURIA_MODEL)"
EURIA_MODEL="${EURIA_MODEL:-$(_env_val EURIA_LLM_MODEL)}"
EURIA_MODEL="${EURIA_MODEL:-openai/gpt-oss-120b}"
OBSIDIAN_VAULT_NAME="$(_env_val OBSIDIAN_VAULT_NAME)"
LOG_LEVEL="$(_env_val LOG_LEVEL)"
LOG_LEVEL="${LOG_LEVEL:-INFO}"
AUTOLEARN_ENABLED="$(_env_val AUTOLEARN_ENABLED)"
AUTOLEARN_ENABLED="${AUTOLEARN_ENABLED:-true}"
AUTOLEARN_ALLOW_BACKGROUND_LLM="$(_env_val AUTOLEARN_ALLOW_BACKGROUND_LLM)"
AUTOLEARN_ALLOW_BACKGROUND_LLM="${AUTOLEARN_ALLOW_BACKGROUND_LLM:-false}"
AUTOLEARN_INTERVAL_MINUTES="$(_env_val AUTOLEARN_INTERVAL_MINUTES)"
AUTOLEARN_INTERVAL_MINUTES="${AUTOLEARN_INTERVAL_MINUTES:-60}"
API_PORT="$(_env_val OBSIRAG_API_PORT)"
API_PORT="${API_PORT:-8000}"
SSL_CERT_FILE="$(_env_val SSL_CERT_FILE)"
REQUESTS_CA_BUNDLE="$(_env_val REQUESTS_CA_BUNDLE)"
CURL_CA_BUNDLE="$(_env_val CURL_CA_BUNDLE)"
PIP_CERT="$(_env_val PIP_CERT)"

if [ -z "$SSL_CERT_FILE" ] && [ -f "$PROJECT_DIR/.certs/ca-bundle.pem" ]; then
  SSL_CERT_FILE="$PROJECT_DIR/.certs/ca-bundle.pem"
fi
REQUESTS_CA_BUNDLE="${REQUESTS_CA_BUNDLE:-$SSL_CERT_FILE}"
CURL_CA_BUNDLE="${CURL_CA_BUNDLE:-$SSL_CERT_FILE}"
PIP_CERT="${PIP_CERT:-$SSL_CERT_FILE}"
# APP_DATA_DIR par défaut
APP_DATA_DIR="${APP_DATA_DIR:-$HOME/Library/Application Support/ObsiRAG}"
mkdir -p "$APP_DATA_DIR"

cat > "$API_PLIST_DST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${API_LABEL}</string>

  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON_BIN}</string>
    <string>-m</string>
    <string>uvicorn</string>
    <string>src.api.main:app</string>
    <string>--host</string>
    <string>0.0.0.0</string>
    <string>--port</string>
    <string>${API_PORT}</string>
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
    <key>APP_DATA_DIR</key>
    <string>${APP_DATA_DIR}</string>
    <key>VAULT_PATH</key>
    <string>${VAULT_PATH}</string>
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
    <key>EURIA_URL</key>
    <string>${EURIA_URL}</string>
    <key>EURIA_BEARER</key>
    <string>${EURIA_BEARER}</string>
    <key>EURIA_MODEL</key>
    <string>${EURIA_MODEL}</string>
    <key>OBSIRAG_API_PORT</key>
    <string>${API_PORT}</string>
    <key>TRANSFORMERS_CACHE</key>
    <string>${HOME}/.cache/huggingface/transformers</string>
    <key>HF_HOME</key>
    <string>${HOME}/.cache/huggingface</string>
    <key>TZ</key>
    <string>Europe/Zurich</string>
    <key>SSL_CERT_FILE</key>
    <string>${SSL_CERT_FILE}</string>
    <key>REQUESTS_CA_BUNDLE</key>
    <string>${REQUESTS_CA_BUNDLE}</string>
    <key>CURL_CA_BUNDLE</key>
    <string>${CURL_CA_BUNDLE}</string>
    <key>PIP_CERT</key>
    <string>${PIP_CERT}</string>
  </dict>

  <key>RunAtLoad</key>
  <true/>

  <key>KeepAlive</key>
  <dict>
    <key>SuccessfulExit</key>
    <false/>
  </dict>

  <key>StandardOutPath</key>
  <string>${LOG_DIR}/api.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/api.stderr.log</string>
</dict>
</plist>
PLIST

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
        <key>EURIA_URL</key>
        <string>${EURIA_URL}</string>
        <key>EURIA_BEARER</key>
        <string>${EURIA_BEARER}</string>
        <key>EURIA_MODEL</key>
        <string>${EURIA_MODEL}</string>
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
        <key>SSL_CERT_FILE</key>
        <string>${SSL_CERT_FILE}</string>
        <key>REQUESTS_CA_BUNDLE</key>
        <string>${REQUESTS_CA_BUNDLE}</string>
        <key>CURL_CA_BUNDLE</key>
        <string>${CURL_CA_BUNDLE}</string>
        <key>PIP_CERT</key>
        <string>${PIP_CERT}</string>
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
launchctl unload "$API_PLIST_DST" 2>/dev/null || true
launchctl unload "$AUTOLEARN_PLIST_DST" 2>/dev/null || true
launchctl load "$API_PLIST_DST"
if [ "$AUTOLEARN_ENABLED" = "true" ]; then
  launchctl load "$AUTOLEARN_PLIST_DST"
fi

echo ""
echo "✓ Services launchd ObsiRAG installés."
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
echo "  → L'API et l'auto-learner resteront actifs via launchd tant que la session utilisateur est ouverte"
echo ""
echo "  Commandes utiles :"
echo "    Logs API      : tail -f $LOG_DIR/api.stdout.log"
echo "    Redémarrer API   : launchctl kickstart -k gui/\$(id -u)/$API_LABEL"
echo "    Arrêter API      : launchctl unload $API_PLIST_DST"
echo "    Logs worker   : tail -f $LOG_DIR/autolearn.stdout.log"
echo "    Redémarrer worker : launchctl kickstart -k gui/\$(id -u)/$AUTOLEARN_LABEL"
echo "    Arrêter worker    : launchctl unload $AUTOLEARN_PLIST_DST"
echo "    Désinstaller  : ./install_service.sh uninstall"

