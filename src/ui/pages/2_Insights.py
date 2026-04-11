"""
Page Insights — Artefacts générés par l'auto-learner + historique des requêtes.
"""
import json
from datetime import datetime

from pathlib import Path

import streamlit as st

from src.config import settings
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
        st.caption(
            f"{len(artifacts)} artefact(s) · "
            f"Visibles dans Obsidian sous `obsirag/insights/`"
        )
        for path_str, mtime in _paginate("insights_page", artifacts, _PAGE_SIZE):
            date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            stem = Path(path_str).stem
            with st.expander(f"📄 {stem} — {date_str}", expanded=False):
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
        st.caption(
            f"{len(synapses)} synapse(s) découverte(s) · "
            f"Visibles dans Obsidian sous `obsirag/synapses/`"
        )
        for path_str, mtime in _paginate("synapses_page", synapses, _PAGE_SIZE):
            date_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            stem = Path(path_str).stem
            with st.expander(f"⚡ {stem} — {date_str}", expanded=False):
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
        st.caption(f"Visibles dans Obsidian sous `obsirag/synthesis/`")
        for s_path in syntheses[:10]:
            mtime = s_path.stat().st_mtime
            with st.expander(f"📊 {s_path.stem}", expanded=(s_path == syntheses[0])):
                st.markdown(_read_md_file(str(s_path), mtime))

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
