"""
Page Paramètres — Configuration, statistiques, consommation de tokens.
"""
import json
from pathlib import Path
from datetime import datetime

import streamlit as st

from src.config import settings
from src.ui.services_cache import get_services

_icon = str(Path(__file__).parent.parent / "static" / "favicon-32x32.png")
st.set_page_config(page_title="Paramètres — ObsiRAG", page_icon=_icon, layout="wide")
svc = get_services()

st.title("⚙️ Paramètres & Statistiques")

tab_config, tab_tokens, tab_index, tab_danger = st.tabs(
    ["🔧 Configuration", "📊 Tokens IA", "📂 Index", "⚠️ Données"]
)

# ---- Configuration ----
with tab_config:
    st.markdown("### Connexion LM Studio")
    c1, c2 = st.columns(2)
    c1.text_input("URL de l'API", value=settings.lmstudio_base_url, disabled=True)
    c2.text_input("Modèle de chat", value=settings.lmstudio_chat_model or "(auto)", disabled=True)

    llm_ok = svc.llm.is_available()
    st.markdown(f"**Statut :** {'🟢 LM Studio accessible' if llm_ok else '🔴 LM Studio non accessible'}")

    st.divider()
    st.markdown("### Chemins")

    col1, col2 = st.columns(2)
    col1.text_input("Coffre (lecture)", value=settings.vault_path, disabled=True)
    col2.text_input("Données système (volume Docker)", value=settings.app_data_dir, disabled=True)

    st.caption(
        "📁 **Dans le coffre** (visibles dans Obsidian) : "
        f"`obsirag/insights/`, `obsirag/synthesis/`  \n"
        "🐳 **Volume Docker** (hors iCloud) : ChromaDB, index, stats, requêtes"
    )

    st.divider()
    st.markdown("### RAG & Contexte")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Chunks max / réponse", settings.max_context_chunks)
    c2.metric("Chars max contexte", f"{settings.max_context_chars:,}")
    c3.metric("Chars max / chunk", settings.max_chunk_chars)
    c4.metric("Résultats recherche", settings.search_top_k)

    st.divider()
    st.markdown("### Auto-apprentissage")
    c1, c2, c3 = st.columns(3)
    c1.metric("Activé", "Oui" if settings.autolearn_enabled else "Non")
    c2.metric("Intervalle", f"{settings.autolearn_interval_minutes} min")
    c3.metric("Notes / cycle", settings.autolearn_max_notes_per_run)

    st.divider()
    st.markdown("### Modèles IA locaux")
    c1, c2 = st.columns(2)
    c1.text_input("Embedding", value=settings.embedding_model, disabled=True)
    c2.text_input("NER (spaCy)", value=settings.ner_model, disabled=True)

# ---- Statistiques tokens ----
with tab_tokens:
    st.markdown("### Consommation de tokens par appel LLM")

    token_file = settings.token_stats_file
    if not token_file.exists():
        st.info("Aucune donnée de tokens encore enregistrée.")
    else:
        data = json.loads(token_file.read_text())
        cumul = data.get("cumulative", {})

        c1, c2, c3 = st.columns(3)
        c1.metric("Tokens prompt (total)", f"{cumul.get('prompt', 0):,}")
        c2.metric("Tokens completion (total)", f"{cumul.get('completion', 0):,}")
        c3.metric("Appels LLM (total)", f"{cumul.get('calls', 0):,}")

        st.divider()
        st.markdown("#### Détail par jour et par opération")

        days = sorted([k for k in data.keys() if k != "cumulative"], reverse=True)
        for day in days[:14]:
            with st.expander(f"📅 {day}"):
                day_data = data[day]
                rows = []
                for op, stats in day_data.items():
                    rows.append({
                        "Opération": op,
                        "Prompt": stats.get("prompt", 0),
                        "Completion": stats.get("completion", 0),
                        "Total": stats.get("prompt", 0) + stats.get("completion", 0),
                        "Appels": stats.get("calls", 0),
                    })
                if rows:
                    import pandas as pd
                    st.dataframe(pd.DataFrame(rows), use_container_width=True)

# ---- Index ChromaDB ----
with tab_index:
    st.markdown("### État de l'index vectoriel")
    st.caption(f"Stocké dans le volume Docker `obsirag-app-data` — pas dans iCloud")

    notes = svc.chroma.list_notes()
    c1, c2 = st.columns(2)
    c1.metric("Notes indexées", len(notes))
    c2.metric("Chunks total", svc.chroma.count())

    if notes:
        st.markdown("#### 20 notes les plus récentes")
        import pandas as pd
        df = pd.DataFrame([
            {
                "Titre": n["title"],
                "Chemin": n["file_path"],
                "Modifié le": n["date_modified"][:10],
                "Tags": ", ".join(n.get("tags", [])[:3]),
            }
            for n in notes[:20]
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)

    if st.button("♻️ Re-indexer maintenant", use_container_width=True):
        with st.spinner("Indexation complète en cours…"):
            stats = svc.indexer.index_vault()
        st.success(
            f"Terminé — +{stats['added']} ajoutées, "
            f"~{stats['updated']} mises à jour, "
            f"🗑 {stats['deleted']} supprimées"
        )

# ---- Zone dangereuse ----
with tab_danger:
    st.warning("⚠️ Ces actions sont irréversibles.")

    st.markdown("#### Réinitialiser l'index vectoriel")
    st.caption(
        "Supprime ChromaDB et l'état d'indexation du volume Docker. "
        "Le coffre Obsidian n'est pas modifié. "
        "Une re-indexation complète se lancera au prochain démarrage."
    )
    confirm = st.text_input("Tapez **RESET** pour confirmer", key="reset_confirm")
    if st.button("🗑 Réinitialiser l'index", type="primary") and confirm == "RESET":
        import shutil
        chroma_dir = Path(settings.chroma_persist_dir)
        if chroma_dir.exists():
            shutil.rmtree(chroma_dir)
        if settings.index_state_file.exists():
            settings.index_state_file.unlink()
        st.success("Index réinitialisé. Redémarrez l'application pour recréer la base.")

    st.divider()
    st.markdown("#### Supprimer les notes ObsiRAG du coffre")
    st.caption(
        "Supprime `obsirag/insights/` et `obsirag/synthesis/` de votre coffre. "
        "L'index et les données système ne sont pas affectés."
    )
    confirm2 = st.text_input("Tapez **DELETE NOTES** pour confirmer", key="delete_notes_confirm")
    if st.button("🗑 Supprimer les notes ObsiRAG", type="primary") and confirm2 == "DELETE NOTES":
        import shutil
        for d in [settings.insights_dir, settings.synthesis_dir]:
            if d.exists():
                shutil.rmtree(d)
        st.success("Notes ObsiRAG supprimées du coffre.")

    st.divider()
    st.markdown("#### Nettoyer l'ancien dossier `obsirag/data/`")
    st.caption(
        "Si vous migrez depuis une ancienne version, l'ancien dossier "
        "`obsirag/data/` peut encore exister dans votre coffre. "
        "Vous pouvez le supprimer manuellement depuis Obsidian ou votre Finder."
    )
    st.code(
        f"rm -rf \"{settings.vault_path}/obsirag/data\"",
        language="bash"
    )
