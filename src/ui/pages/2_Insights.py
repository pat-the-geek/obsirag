"""
Page Insights — Artefacts générés par l'auto-learner + historique des requêtes.
"""
import json
from datetime import datetime

from pathlib import Path

import streamlit as st

from src.config import settings
from src.ui.insights_browser import (
    build_month_options,
    build_query_day_options,
    filter_markdown_entries,
    filter_queries,
    load_query_history,
)
from src.ui.note_badges import render_note_badge
from src.ui.services_cache import get_services
from src.ui.theme import inject_theme, render_theme_toggle

_PAGE_SIZE = 15  # nombre d'items par page


@st.cache_data(ttl=60)
def _list_md_files(directory: str) -> list[tuple[str, float]]:
    """Retourne la liste triée (path_str, mtime) — mise en cache 60 s."""
    d = Path(directory)
    if not d.exists():
        return []
    entries = []
    for p in d.rglob("*.md"):
        try:
            entries.append((str(p), p.stat().st_mtime))
        except OSError:
            pass
    entries.sort(key=lambda x: x[1], reverse=True)
    return entries


@st.cache_data(ttl=120)
def _read_md_file(path_str: str, mtime: float) -> str:
    """Lecture mise en cache du fichier Markdown (TTL 2 min, invalidée si mtime change)."""
    return Path(path_str).read_text(encoding="utf-8")


def _paginate(key: str, items: list, page_size: int) -> list:
    """Affiche une navigation par pages et retourne la tranche visible."""
    total = len(items)
    n_pages = max(1, (total + page_size - 1) // page_size)
    page = st.session_state.get(key, 0)
    page = max(0, min(page, n_pages - 1))

    start = page * page_size
    slice_ = items[start: start + page_size]

    if n_pages > 1:
        col_info, col_prev, col_next = st.columns([4, 1, 1])
        col_info.caption(f"Page {page + 1} / {n_pages}  ({total} total)")
        if col_prev.button("← Précédent", key=f"{key}_prev", disabled=(page == 0)):
            st.session_state[key] = page - 1
            st.rerun()
        if col_next.button("Suivant →", key=f"{key}_next", disabled=(page == n_pages - 1)):
            st.session_state[key] = page + 1
            st.rerun()

    return slice_

_icon = str(Path(__file__).parent.parent / "static" / "favicon-32x32.png")
st.set_page_config(page_title="Insights — ObsiRAG", page_icon=_icon, layout="wide")
inject_theme()
svc = get_services()

render_theme_toggle()
st.title("💡 Insights")
st.caption("Connaissances générées automatiquement et historique de vos questions")

tab_knowledge, tab_synapses, tab_synthesis, tab_queries = st.tabs(
    ["🧩 Artefacts de connaissance", "⚡ Synapses", "📋 Synthèses hebdomadaires", "🔍 Historique requêtes"]
)

# ---- Artefacts de connaissance (vault/obsirag/insights/) ----
with tab_knowledge:
    artifacts = _list_md_files(str(settings.insights_dir))

    if not artifacts:
        st.info(
            "Aucun artefact généré pour l'instant. "
            "L'auto-learner s'activera dans quelques minutes et créera des notes "
            f"dans `{settings.vault_obsirag_dir.relative_to(settings.vault)}/insights/`."
        )
    else:
        search_col, month_col = st.columns([2, 1])
        search_text = search_col.text_input(
            "Rechercher dans les artefacts",
            placeholder="Titre, fichier ou contenu…",
            key="insights_search",
        )
        month_filter = month_col.selectbox(
            "Mois",
            build_month_options(artifacts),
            key="insights_month_filter",
        )
        filtered_artifacts = filter_markdown_entries(
            artifacts,
            search_text=search_text,
            month_filter=month_filter,
            content_lookup=_read_md_file,
        )
        st.caption(
            f"{len(filtered_artifacts)} / {len(artifacts)} artefact(s) · "
            f"Visibles dans Obsidian sous `obsirag/insights/`"
        )
        for path_str, mtime in _paginate("insights_page", filtered_artifacts, _PAGE_SIZE):
            date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            stem = Path(path_str).stem
            with st.expander(f"💡 {stem} — {date_str}", expanded=False):
                st.markdown(render_note_badge(path_str), unsafe_allow_html=True)
                st.markdown(_read_md_file(path_str, mtime))

# ---- Synapses (vault/obsirag/synapses/) ----
with tab_synapses:
    synapses = _list_md_files(str(settings.synapses_dir))

    if not synapses:
        st.info(
            "Aucune synapse générée pour l'instant. "
            "L'auto-learner découvre des connexions implicites entre notes à chaque cycle. "
            f"Elles apparaîtront dans Obsidian sous `obsirag/synapses/`."
        )
    else:
        search_col, month_col = st.columns([2, 1])
        search_text = search_col.text_input(
            "Rechercher dans les synapses",
            placeholder="Titre, fichier ou contenu…",
            key="synapses_search",
        )
        month_filter = month_col.selectbox(
            "Mois",
            build_month_options(synapses),
            key="synapses_month_filter",
        )
        filtered_synapses = filter_markdown_entries(
            synapses,
            search_text=search_text,
            month_filter=month_filter,
            content_lookup=_read_md_file,
        )
        st.caption(
            f"{len(filtered_synapses)} / {len(synapses)} synapse(s) découverte(s) · "
            f"Visibles dans Obsidian sous `obsirag/synapses/`"
        )
        for path_str, mtime in _paginate("synapses_page", filtered_synapses, _PAGE_SIZE):
            date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            stem = Path(path_str).stem
            with st.expander(f"⚡ {stem} — {date_str}", expanded=False):
                st.markdown(render_note_badge(path_str), unsafe_allow_html=True)
                st.markdown(_read_md_file(path_str, mtime))

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
        synthesis_entries = [(str(s_path), s_path.stat().st_mtime) for s_path in syntheses]
        search_col, month_col = st.columns([2, 1])
        search_text = search_col.text_input(
            "Rechercher dans les synthèses",
            placeholder="Titre, fichier ou contenu…",
            key="synthesis_search",
        )
        month_filter = month_col.selectbox(
            "Mois",
            build_month_options(synthesis_entries),
            key="synthesis_month_filter",
        )
        filtered_syntheses = filter_markdown_entries(
            synthesis_entries,
            search_text=search_text,
            month_filter=month_filter,
            content_lookup=_read_md_file,
        )
        st.caption(f"{len(filtered_syntheses)} / {len(syntheses)} synthèse(s) · Visibles dans Obsidian sous `obsirag/synthesis/`")
        for path_str, mtime in _paginate("synthesis_page", filtered_syntheses, _PAGE_SIZE):
            s_path = Path(path_str)
            with st.expander(f"📋 {s_path.stem}", expanded=(s_path == syntheses[0])):
                st.markdown(render_note_badge(path_str), unsafe_allow_html=True)
                st.markdown(_read_md_file(path_str, mtime))

# ---- Historique des requêtes (volume Docker) ----
with tab_queries:
    q_file = settings.queries_file
    if not q_file.exists():
        st.info("Aucune requête enregistrée.")
    else:
        lines = q_file.read_text(encoding="utf-8").strip().splitlines()
        queries = load_query_history(lines)
        st.caption(f"{len(queries)} requête(s) enregistrée(s)")

        if queries:
            col1, col2 = st.columns(2)
            col1.metric("Total requêtes", len(queries))
            today = datetime.utcnow().strftime("%Y-%m-%d")
            today_count = sum(1 for q in queries if q.get("ts", "").startswith(today))
            col2.metric("Aujourd'hui", today_count)

            search_col, day_col = st.columns([2, 1])
            query_search = search_col.text_input(
                "Rechercher dans l'historique",
                placeholder="Texte de requête…",
                key="queries_search",
            )
            day_filter = day_col.selectbox(
                "Jour",
                build_query_day_options(queries),
                key="queries_day_filter",
            )
            filtered_queries = filter_queries(
                queries,
                search_text=query_search,
                day_filter=day_filter,
            )

            st.caption(f"{len(filtered_queries)} / {len(queries)} requête(s) affichée(s)")

            st.markdown("#### Dernières requêtes")
            for q in _paginate("queries_page", filtered_queries, _PAGE_SIZE):
                ts = q.get("ts", "")[:16].replace("T", " ")
                st.markdown(f"- `{ts}` — {q.get('query', '')}")
