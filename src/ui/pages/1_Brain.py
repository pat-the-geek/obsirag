"""
Page Cerveau — Visualisation interactive du graphe de connaissances.
"""
import base64
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from src.ui.brain_explorer import (
    build_centrality_spotlight,
    build_folder_summary,
    build_recent_notes,
    build_tag_summary,
    filter_brain_notes,
)
from src.ui.note_badges import prefix_note_label, render_note_badge
from src.ui.services_cache import get_services
from src.ui.components.note_bridge_component import note_bridge as _note_bridge
from src.ui.theme import inject_theme, render_theme_toggle

_icon = str(Path(__file__).parent.parent / "static" / "favicon-32x32.png")
_brain_b64 = base64.b64encode(
    (Path(__file__).parent.parent / "static" / "brain_transparent.svg").read_bytes()
).decode()
st.set_page_config(page_title="Cerveau — ObsiRAG", page_icon=_icon, layout="wide")
inject_theme()

svc = get_services()

st.markdown(
    f'<h1 style="display:flex;align-items:center;gap:8px">'
    f'<img src="data:image/svg+xml;base64,{_brain_b64}" width="96" height="96">'
    f'Cerveau</h1>',
    unsafe_allow_html=True,
)
st.caption("Carte interactive des connexions entre vos notes")

notes = svc.chroma.list_notes()

if not notes:
    st.info("Aucune note indexée. Lancez une indexation depuis la page Chat.")
    st.stop()

# ---- Filtres sidebar ----
with st.sidebar:
    # Bridge invisible dans la sidebar — n'affecte pas la hauteur du contenu principal
    _opened_note = _note_bridge(default=None, key="note_bridge_v1")
    if _opened_note:
        st.session_state.viewing_note = _opened_note
        st.session_state.note_nav_request = _opened_note
        st.switch_page("pages/4_Note.py")

    st.markdown("### Filtres")

    folders = sorted({str(Path(n["file_path"]).parent) for n in notes})
    selected_folders = st.multiselect(
        "Dossiers",
        options=["Tous"] + folders,
        default=["Tous"],
    )

    all_tags = sorted({t for n in notes for t in n.get("tags", []) if t})
    selected_tags = st.multiselect("Tags", options=all_tags)
    search_text = st.text_input("Recherche libre", placeholder="Titre, chemin ou tag…")
    recency_label = st.selectbox(
        "Modifiées récemment",
        options=["Toutes", "7 derniers jours", "30 derniers jours", "90 derniers jours"],
        index=0,
    )
    recency_days = {
        "Toutes": None,
        "7 derniers jours": 7,
        "30 derniers jours": 30,
        "90 derniers jours": 90,
    }[recency_label]

    st.divider()
    st.markdown("### Ouvrir une note")
    # Tri alphabétique pour que la liste soit navigable
    sorted_notes = sorted(notes, key=lambda n: n["title"].lower())
    note_opts = {prefix_note_label(n["title"], n["file_path"]): n["file_path"] for n in sorted_notes}
    selected_note_title = st.selectbox(
        "Note (ordre alphabétique)",
        options=list(note_opts.keys()),
        label_visibility="visible",
    )
    if st.button("📖 Ouvrir dans le visualiseur", use_container_width=True):
        _fp = note_opts[selected_note_title]
        st.session_state.viewing_note = _fp
        st.session_state.note_nav_request = _fp
        st.switch_page("pages/4_Note.py")

    render_theme_toggle()
    rebuild = False

# ---- Filtrage ----
notes_with_folder = [
    {**note, "folder": str(Path(note["file_path"]).parent)}
    for note in notes
]
filtered = filter_brain_notes(
    notes_with_folder,
    selected_folders=selected_folders,
    selected_tags=selected_tags,
    search_text=search_text,
    modified_within_days=recency_days,
    now=datetime.now(),
)

st.caption(f"{len(filtered)} / {len(notes)} notes affichées")

# ---- Construction du graphe ----
@st.cache_data(ttl=300, show_spinner="Construction du graphe…")
def build_graph_html(note_fps: tuple[str, ...]) -> tuple[str, dict]:
    notes_subset = svc.chroma.get_notes_by_file_paths(list(note_fps))
    graph = svc.graph.build(notes_subset)
    html = svc.graph.to_pyvis_html(graph, height=650)
    stats = svc.graph.get_stats(graph)
    return html, stats

fps_tuple = tuple(n["file_path"] for n in filtered)
if fps_tuple:
    graph_html, stats = build_graph_html(fps_tuple)

    c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 1])
    c1.metric("Nœuds", stats.get("nodes", 0))
    c2.metric("Connexions", stats.get("edges", 0))
    c3.metric("Densité", stats.get("density", 0))
    c4.metric("Notes filtrées", len(filtered))
    if c5.button("🔄", help="Reconstruire le graphe"):
        st.cache_data.clear()
        st.rerun()

    components.html(graph_html, height=670, scrolling=False)

    spotlight = build_centrality_spotlight(filtered, stats.get("top_connected", []), limit=6)
    recent_notes = build_recent_notes(filtered, limit=6)
    folder_summary = build_folder_summary(filtered, limit=6)
    tag_summary = build_tag_summary(filtered, limit=8)

    col_spotlight, col_recent = st.columns(2)

    with col_spotlight:
        st.markdown("### Parcours par centralité")
        if spotlight:
            for index, item in enumerate(spotlight):
                st.markdown(
                    f"<div style='display:flex;align-items:center;gap:0.55rem;flex-wrap:wrap;'>"
                    f"{render_note_badge(item['file_path'])}"
                    f"<strong>{item['title']}</strong>"
                    f"<span style='opacity:.72;'>centralité <code>{item['score']}</code> · {item['date_modified'] or 'date inconnue'}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                if item.get("tags"):
                    st.caption(" · ".join(f"#{tag}" for tag in item["tags"][:4]))
                if st.button("📖 Ouvrir", key=f"spotlight_{index}_{item['file_path']}", use_container_width=True):
                    st.session_state.viewing_note = item["file_path"]
                    st.session_state.note_nav_request = item["file_path"]
                    st.switch_page("pages/4_Note.py")
        else:
            st.caption("Aucun nœud central disponible avec ces filtres.")

    with col_recent:
        st.markdown("### Parcours récent")
        if recent_notes:
            for index, note in enumerate(recent_notes):
                st.markdown(
                    f"<div style='display:flex;align-items:center;gap:0.55rem;flex-wrap:wrap;'>"
                    f"{render_note_badge(note['file_path'])}"
                    f"<strong>{note['title']}</strong>"
                    f"<span style='opacity:.72;'>{note.get('date_modified', '')[:10] or 'date inconnue'}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                if note.get("tags"):
                    st.caption(" · ".join(f"#{tag}" for tag in note["tags"][:4]))
                if st.button("📖 Ouvrir", key=f"recent_{index}_{note['file_path']}", use_container_width=True):
                    st.session_state.viewing_note = note["file_path"]
                    st.session_state.note_nav_request = note["file_path"]
                    st.switch_page("pages/4_Note.py")
        else:
            st.caption("Aucune note récente ne correspond à ces filtres.")

    with st.expander("### Répartition des filtres", expanded=False):
        col_folders, col_tags = st.columns(2)

        with col_folders:
            st.markdown("**Dossiers dominants**")
            if folder_summary:
                for item in folder_summary:
                    st.markdown(f"**{item['folder']}** · {item['count']} note(s)")
            else:
                st.caption("Aucun dossier à résumer avec ces filtres.")

        with col_tags:
            st.markdown("**Tags dominants**")
            if tag_summary:
                for item in tag_summary:
                    st.markdown(f"**#{item['tag']}** · {item['count']} note(s)")
            else:
                st.caption("Aucun tag à résumer avec ces filtres.")

    if stats.get("top_connected"):
        st.markdown("### Nœuds les plus connectés")
        for idx, item in enumerate(stats["top_connected"][:5]):
            fp = item["file_path"]
            note = next((n for n in filtered if n["file_path"] == fp), None)
            title = note["title"] if note else fp
            score = item["score"]
            col_t, col_b = st.columns([4, 1])
            col_t.markdown(
                f"<div style='display:flex;align-items:center;gap:0.55rem;flex-wrap:wrap;'>"
                f"{render_note_badge(fp)}"
                f"<strong>{title}</strong>"
                f"<span style='opacity:.72;'>centralité <code>{score}</code></span>"
                f"</div>",
                unsafe_allow_html=True,
            )
            if col_b.button("📖", key=f"top_{idx}_{fp}", help="Ouvrir"):
                st.session_state.viewing_note = fp
                st.session_state.note_nav_request = fp
                st.switch_page("pages/4_Note.py")
else:
    st.warning("Aucune note à afficher avec ces filtres.")

# ---- Explication de la densité ----
with st.expander("ℹ️ Comprendre la densité du graphe"):
    st.markdown("""
**La densité** mesure le ratio entre le nombre de connexions existantes et le nombre maximum de connexions possibles entre toutes les notes.

$$\\text{Densité} = \\frac{\\text{connexions réelles}}{n \\times (n-1)}$$

| Densité | Interprétation |
|---|---|
| < 0.01 | Très épars — typique des bases de connaissances personnelles |
| 0.01 – 0.1 | Épars mais structuré |
| 0.1 – 0.5 | Modérément dense |
| > 0.5 | Très dense (rare en pratique) |

Une valeur faible (< 0.01) est **tout à fait normale** pour un vault Obsidian : chaque note n'est naturellement liée qu'à une petite fraction des autres notes.
""")
