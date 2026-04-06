# Image Bookworm = Debian 12, mieux patchée contre les CVE
FROM python:3.11-slim-bookworm

WORKDIR /app

# Dépendances système
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gosu \
    build-essential \
    && pip install --no-cache-dir \
        "torch>=2.4.0" \
        --index-url https://download.pytorch.org/whl/cpu \
    && apt-get purge -y build-essential \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Modèle NER multilingue spaCy — FR, EN et ~20 autres langues
RUN python -m spacy download xx_ent_wiki_sm

# Code applicatif
COPY src/ src/
COPY .streamlit/ .streamlit/
COPY obsirag_icon.svg obsirag_icon.svg
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Créer l'utilisateur non-root (les répertoires sont créés par l'entrypoint)
RUN useradd -m -u 1000 obsirag

ENV PYTHONPATH=/app
ENV TRANSFORMERS_CACHE=/app/.cache/transformers
ENV HF_HOME=/app/.cache/huggingface

EXPOSE 8501

ENTRYPOINT ["/entrypoint.sh"]
CMD ["streamlit", "run", "src/ui/app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true"]
