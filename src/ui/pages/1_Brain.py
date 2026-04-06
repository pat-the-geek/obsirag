"""
Page Cerveau — Visualisation interactive du graphe de connaissances.
"""
import base64
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from src.ui.services_cache import get_services
from src.ui.components.note_bridge_component import note_bridge as _note_bridge

_icon = str(Path(__file__).parent.parent / "static" / "favicon-32x32.png")
_icon_b64 = base64.b64encode((Path(__file__).parent.parent / "static" / "favicon-32x32.png").read_bytes()).decode()
st.set_page_config(page_title="Cerveau — ObsiRAG", page_icon=_icon, layout="wide")

svc = get_services()

st.markdown(
    f'<h1 style="display:flex;align-items:center;gap:12px">'
    f'<img src="data:image/png;base64,{_icon_b64}" width="144" style="border-radius:6px">'
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
        st.switch_page("pages/4_Note.py")

    st.markdown("### Filtres")

    from pathlib import Path
    folders = sorted({str(Path(n["file_path"]).parent) for n in notes})
    selected_folders = st.multiselect(
        "Dossiers",
        options=["Tous"] + folders,
        default=["Tous"],
    )

    all_tags = sorted({t for n in notes for t in n.get("tags", []) if t})
    selected_tags = st.multiselect("Tags", options=all_tags)

    st.divider()
    st.markdown("### Ouvrir une note")
    # Tri alphabétique pour que la liste soit navigable
    sorted_notes = sorted(notes, key=lambda n: n["title"].lower())
    note_opts = {n["title"]: n["file_path"] for n in sorted_notes}
    selected_note_title = st.selectbox(
        "Note (ordre alphabétique)",
        options=list(note_opts.keys()),
        label_visibility="visible",
    )
    if st.button("📖 Ouvrir dans le visualiseur", use_container_width=True):
        st.session_state.viewing_note = note_opts[selected_note_title]
        st.switch_page("pages/4_Note.py")

    rebuild = False

# ---- Filtrage ----
filtered = notes
if selected_folders and "Tous" not in selected_folders:
    filtered = [n for n in filtered if str(Path(n["file_path"]).parent) in selected_folders]
if selected_tags:
    tag_set = set(selected_tags)
    filtered = [n for n in filtered if tag_set & set(n.get("tags", []))]

st.caption(f"{len(filtered)} / {len(notes)} notes affichées")

# ---- Construction du graphe ----
@st.cache_data(ttl=300, show_spinner="Construction du graphe…")
def build_graph_html(note_fps: tuple[str, ...]) -> tuple[str, dict]:
    notes_subset = [n for n in svc.chroma.list_notes() if n["file_path"] in note_fps]
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

    if stats.get("top_connected"):
        st.markdown("### Nœuds les plus connectés")
        for idx, item in enumerate(stats["top_connected"][:5]):
            fp = item["file_path"]
            note = next((n for n in filtered if n["file_path"] == fp), None)
            title = note["title"] if note else fp
            score = item["score"]
            col_t, col_b = st.columns([4, 1])
            col_t.markdown(f"**{title}** — centralité `{score}`")
            if col_b.button("📖", key=f"top_{idx}_{fp}", help="Ouvrir"):
                st.session_state.viewing_note = fp
                st.switch_page("pages/4_Note.py")
else:
    st.warning("Aucune note à afficher avec ces filtres.")
