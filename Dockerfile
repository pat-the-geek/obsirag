# =============================================================
# Stage 1 — Build du frontend Expo web
# =============================================================
FROM node:22-alpine AS expo-builder

WORKDIR /expo

COPY obsirag-expo/package*.json ./
RUN npm ci --prefer-offline

COPY obsirag-expo/ ./

# Export statique (SPA)
RUN npx expo export --platform web

# Icône PWA / macOS Dock
COPY obsirag-expo/public/apple-touch-icon.png dist/apple-touch-icon.png

# Correction de l'index.html généré par Expo (ignore +html.tsx lors de l'export statique)
COPY docker/patch-html.js ./patch-html.js
RUN node patch-html.js

# =============================================================
# Stage 2 — Runtime Python
# =============================================================
FROM python:3.12-slim

# Dépendances système : cron + compilateurs pour les bindings natifs
RUN apt-get update && apt-get install -y --no-install-recommends \
    cron \
    curl \
    gcc \
    g++ \
    libgomp1 \
    procps \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dépendances Python — on exclut les paquets Apple Silicon (mlx-*) et Streamlit
# (remplacé par FastAPI + Expo).
COPY requirements.txt /tmp/requirements.txt
RUN grep -Ev '^(mlx-lm|mlx|streamlit)[>=<]' /tmp/requirements.txt > /tmp/requirements-docker.txt \
    && pip install --no-cache-dir -r /tmp/requirements-docker.txt

# Modèle spaCy NER multilingue
RUN python -m spacy download xx_ent_wiki_sm

# Pré-téléchargement du modèle d'embedding (~500 MB baked dans l'image).
# Évite un téléchargement lent au premier démarrage du container.
RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"

# Sources de l'application
COPY src/ ./src/

# Frontend compilé depuis le builder
COPY --from=expo-builder /expo/dist ./obsirag-expo/dist/

# Scripts Docker
COPY docker/ ./docker/
RUN chmod +x docker/entrypoint.sh docker/run-worker.sh docker/check-worker.sh

# Crontab (entrée @reboot + check toutes les 5 min)
COPY docker/crontab /etc/cron.d/obsirag
RUN chmod 0644 /etc/cron.d/obsirag

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD curl -f http://localhost:8080/api/v1/health || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]
