"""
Page Insights — Artefacts générés par l'auto-learner + historique des requêtes.
"""
import json
from datetime import datetime

import streamlit as st

from src.config import settings
from src.ui.services_cache import get_services

st.set_page_config(page_title="Insights — ObsiRAG", page_icon="💡", layout="wide")
svc = get_services()

st.title("💡 Insights")
st.caption("Connaissances générées automatiquement et historique de vos questions")

tab_knowledge, tab_synthesis, tab_queries = st.tabs(
    ["🧩 Artefacts de connaissance", "📋 Synthèses hebdomadaires", "🔍 Historique requêtes"]
)

# ---- Artefacts de connaissance (vault/obsirag/insights/) ----
with tab_knowledge:
    insights_dir = settings.insights_dir
    artifacts = sorted(insights_dir.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True) \
        if insights_dir.exists() else []

    if not artifacts:
        st.info(
            "Aucun artefact généré pour l'instant. "
            "L'auto-learner s'activera dans quelques minutes et créera des notes "
            f"dans `{settings.vault_obsirag_dir.relative_to(settings.vault)}/insights/`."
        )
    else:
        st.caption(
            f"{len(artifacts)} artefact(s) · "
            f"Visibles dans Obsidian sous `obsirag/insights/`"
        )
        for art_path in artifacts[:30]:
            date_str = datetime.fromtimestamp(art_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            with st.expander(f"📄 {art_path.stem} — {date_str}", expanded=False):
                st.markdown(art_path.read_text(encoding="utf-8"))

# ---- Synthèses hebdomadaires (vault/obsirag/synthesis/) ----
with tab_synthesis:
    synth_dir = settings.synthesis_dir
    syntheses = sorted(synth_dir.glob("*.md"), reverse=True) if synth_dir.exists() else []

    if not syntheses:
        st.info(
            "Aucune synthèse générée. La première sera créée dimanche soir. "
            f"Elle apparaîtra dans Obsidian sous `obsirag/synthesis/`."
        )
    else:
        st.caption(f"Visibles dans Obsidian sous `obsirag/synthesis/`")
        for s_path in syntheses[:10]:
            with st.expander(f"📊 {s_path.stem}", expanded=(s_path == syntheses[0])):
                st.markdown(s_path.read_text(encoding="utf-8"))

# ---- Historique des requêtes (volume Docker) ----
with tab_queries:
    q_file = settings.queries_file
    if not q_file.exists():
        st.info("Aucune requête enregistrée.")
    else:
        lines = q_file.read_text(encoding="utf-8").strip().splitlines()
        queries = []
        for line in lines:
            try:
                queries.append(json.loads(line))
            except Exception:
                pass

        queries.sort(key=lambda x: x.get("ts", ""), reverse=True)
        st.caption(f"{len(queries)} requête(s) enregistrée(s)")

        if queries:
            col1, col2 = st.columns(2)
            col1.metric("Total requêtes", len(queries))
            today = datetime.utcnow().strftime("%Y-%m-%d")
            today_count = sum(1 for q in queries if q.get("ts", "").startswith(today))
            col2.metric("Aujourd'hui", today_count)

            st.markdown("#### Dernières requêtes")
            for q in queries[:20]:
                ts = q.get("ts", "")[:16].replace("T", " ")
                st.markdown(f"- `{ts}` — {q.get('query', '')}")
