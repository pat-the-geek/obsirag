"""
Page Paramètres — Configuration, statistiques, consommation de tokens.
"""
import json
from pathlib import Path
from datetime import datetime

import streamlit as st

from src.config import settings
from src.ui.chroma_compat import list_recent_notes
from src.ui.services_cache import get_services
from src.ui.theme import inject_theme, render_theme_toggle

_icon = str(Path(__file__).parent.parent / "static" / "favicon-32x32.png")


def _load_json_payload(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _format_metric_number(value: float | int) -> str:
    if isinstance(value, float):
        return f"{value:,.3f}"
    return f"{value:,}"


st.set_page_config(page_title="Paramètres — ObsiRAG", page_icon=_icon, layout="wide")
inject_theme()
svc = get_services()

render_theme_toggle()
st.title("⚙️ Paramètres & Statistiques")

tab_config, tab_tokens, tab_runtime_metrics, tab_index, tab_danger = st.tabs(
    ["🔧 Configuration", "📊 Tokens IA", "📈 Métriques runtime", "📂 Index", "⚠️ Données"]
)

# ---- Configuration ----
with tab_config:
    st.markdown("### Modèle de génération (MLX-LM)")
    c1, c2 = st.columns(2)
    c1.text_input("Modèle MLX", value=settings.mlx_chat_model, disabled=True)
    llm_ok = svc.llm.is_available()
    c2.markdown("")  # espaceur
    st.markdown(f"**Statut :** {'🟢 Modèle chargé' if llm_ok else '🔴 Modèle non disponible'}")

    st.divider()
    st.markdown("### Chemins")

    col1, col2 = st.columns(2)
    col1.text_input("Coffre (lecture)", value=settings.vault_path, disabled=True)
    col2.text_input("Données système (volume Docker)", value=settings.app_data_dir, disabled=True)

    st.caption(
        "📁 **Dans le coffre** (visibles dans Obsidian) : "
        f"`obsirag/insights/`, `obsirag/synthesis/`  \n"
        "� **Données système** (hors iCloud) : ChromaDB, index, stats, requêtes"
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
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Activé", "Oui" if settings.autolearn_enabled else "Non")
    c2.metric("Intervalle", f"{settings.autolearn_interval_minutes} min")
    c3.metric("Notes / cycle", settings.autolearn_max_notes_per_run)
    c4.metric("Plage horaire", f"{settings.autolearn_active_hour_start:02d}h – {settings.autolearn_active_hour_end:02d}h")
    c5.metric("Bulk max notes", settings.autolearn_bulk_max_notes if settings.autolearn_bulk_max_notes > 0 else "∞")

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

# ---- Metriques runtime ----
with tab_runtime_metrics:
    st.markdown("### Activité interne d'ObsiRAG")
    metrics_file = settings.data_dir / "stats" / "metrics.json"
    metrics_payload = _load_json_payload(metrics_file)

    if not metrics_payload:
        st.info("Aucune métrique runtime encore enregistrée.")
    else:
        counters = metrics_payload.get("counters", {})
        summaries = metrics_payload.get("summaries", {})
        last_update = datetime.fromtimestamp(metrics_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M")

        c1, c2, c3 = st.columns(3)
        c1.metric("Compteurs suivis", len(counters))
        c2.metric("Agrégats suivis", len(summaries))
        c3.metric("Dernière mise à jour", last_update)

        key_metrics = [
            ("rag_queries_total", "Requêtes RAG"),
            ("rag_sentinel_answers_total", "Réponses sentinelle"),
            ("rag_context_retries_total", "Retries de contexte"),
            ("autolearn_insights_created_total", "Insights créés"),
            ("autolearn_insights_appended_total", "Insights enrichis"),
            ("autolearn_web_search_error_total", "Erreurs web"),
        ]
        available_metrics = [(key, label) for key, label in key_metrics if key in counters]
        if available_metrics:
            st.divider()
            st.markdown("#### Indicateurs clés")
            cols = st.columns(min(3, len(available_metrics)))
            for index, (key, label) in enumerate(available_metrics):
                cols[index % len(cols)].metric(label, _format_metric_number(counters[key]))

        if counters:
            st.divider()
            st.markdown("#### Compteurs cumulés")
            import pandas as pd

            counter_rows = [
                {"Métrique": key, "Valeur": int(value)}
                for key, value in sorted(counters.items(), key=lambda item: (-int(item[1]), item[0]))
            ]
            st.dataframe(pd.DataFrame(counter_rows), use_container_width=True, hide_index=True)

        if summaries:
            st.divider()
            st.markdown("#### Agrégats observés")
            import pandas as pd

            summary_rows = [
                {
                    "Métrique": key,
                    "Observations": int(values.get("count", 0)),
                    "Dernière valeur": _format_metric_number(float(values.get("last", 0.0))),
                    "Moyenne": _format_metric_number(float(values.get("avg", 0.0))),
                    "Total": _format_metric_number(float(values.get("total", 0.0))),
                }
                for key, values in sorted(summaries.items())
            ]
            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

# ---- Index ChromaDB ----
with tab_index:
    st.markdown("### État de l'index vectoriel")
    st.caption(f"Stocké dans le volume Docker `obsirag-app-data` — pas dans iCloud")

    notes = svc.chroma.list_notes()
    recent_notes = list_recent_notes(svc.chroma, limit=20)
    user_notes = svc.chroma.list_user_notes()
    generated_notes = svc.chroma.list_generated_notes()
    c1, c2, c3 = st.columns(3)
    c1.metric("Notes indexées", len(notes))
    c2.metric("Notes utilisateur", len(user_notes))
    c3.metric("Artefacts générés", len(generated_notes))
    st.caption(f"Chunks total : {svc.chroma.count()}")

    if recent_notes:
        st.markdown("#### 20 notes les plus récentes")
        import pandas as pd
        df = pd.DataFrame([
            {
                "Titre": n["title"],
                "Chemin": n["file_path"],
                "Modifié le": n["date_modified"][:10],
                "Tags": ", ".join(n.get("tags", [])[:3]),
            }
            for n in recent_notes
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)

    if st.button("♻️ Re-indexer maintenant", use_container_width=True):
        progress_bar = st.progress(0, text="Démarrage de l'indexation…")
        note_label = st.empty()

        def _on_progress(note: str, processed: int, total: int) -> None:
            pct = processed / total if total > 0 else 0
            progress_bar.progress(pct, text=f"Indexation {processed} / {total}")
            note_label.caption(f"📄 `{note}`")

        stats = svc.indexer.index_vault(on_progress=_on_progress)
        progress_bar.progress(1.0, text="Indexation terminée")
        note_label.empty()
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
