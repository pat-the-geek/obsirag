"""
Page Visualiseur de Note — rendu Markdown complet avec diagrammes Mermaid.
Accessible depuis les sources du chat, le Cerveau et via le sélecteur intégré.
"""
from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

from src.config import settings
from src.storage.safe_read import read_text_file
from src.ui.html_embed import render_html_document, run_inline_script
from src.ui.mermaid_embed import build_mermaid_html_document, estimate_mermaid_height
from src.ui.note_viewer import (
    count_mermaid_blocks,
    extract_note_outline,
    find_note_matches,
    inject_line_anchors,
    make_note_anchor,
)
from src.ui.note_badges import prefix_note_label, render_note_badge
from src.ui.path_resolver import normalize_vault_relative_path, resolve_vault_path
from src.ui.note_ui_fragments import (
    build_obsidian_open_link_html,
    build_outline_item_html,
    build_search_match_html,
)

from src.ui.services_cache import get_services
from src.ui.theme import inject_theme, render_theme_toggle
from src.ui.side_menu import render_mobile_main_menu, render_side_menu

_icon = str(Path(__file__).parent.parent / "static" / "favicon-32x32.png")
st.set_page_config(page_title="Note — ObsiRAG", page_icon=_icon, layout="wide", initial_sidebar_state="expanded")

inject_theme()
render_mobile_main_menu()
# Ajout à l'historique navigation
HISTO_KEY = "obsirag_historique"
st.session_state.setdefault(HISTO_KEY, [])
note_fp = st.session_state.get("viewing_note")
if note_fp and (not st.session_state[HISTO_KEY] or st.session_state[HISTO_KEY][-1] != note_fp):
    st.session_state[HISTO_KEY].append(note_fp)
render_side_menu()
svc = get_services()

# ---------------------------------------------------------------------------
# Rendu Markdown + Mermaid
# ---------------------------------------------------------------------------

_MERMAID_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]*)?\]\]")


def _scroll_to_anchor(anchor_id: str) -> None:
    import json

    run_inline_script(
        f"""
const anchorId = {json.dumps(anchor_id)};
const target = window.parent.document.getElementById(anchorId);
if (target) {{
  target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
}}
"""
    )


def render_note(content: str, anchor_lines: set[int] | None = None) -> None:
    """Découpe le contenu en blocs texte / Mermaid et rend chacun."""
    content = inject_line_anchors(content, anchor_lines or set())

    last = 0
    idx = 0
    for match in _MERMAID_RE.finditer(content):
        before = content[last: match.start()].strip()
        if before:
            st.markdown(before, unsafe_allow_html=True)

        mermaid_code = match.group(1).strip()
        height = estimate_mermaid_height(mermaid_code)
        st.caption("📊 Diagramme Mermaid")
        render_html_document(build_mermaid_html_document(mermaid_code, idx), height=height)
        idx += 1
        last = match.end()

    remainder = content[last:].strip()
    if remainder:
        st.markdown(remainder, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Sidebar — sélecteur de note
# ---------------------------------------------------------------------------

notes = svc.chroma.list_notes_sorted_by_title()
notes_by_path = {normalize_vault_relative_path(note["file_path"]): note for note in notes}

with st.sidebar:
    # Composant invisible pour empêcher la fermeture totale de la sidebar
    st.markdown('<div style="height:1px;opacity:0;">.</div>', unsafe_allow_html=True)
    st.markdown("### 📄 Sélectionner une note")

    search_term = st.text_input("🔍 Rechercher", placeholder="Titre ou chemin…")

    filtered = notes
    if search_term:
        t = search_term.lower()
        filtered = [
            n for n in notes
            if t in n["title"].lower() or t in n["file_path"].lower()
            or any(t in tag.lower() for tag in n.get("tags", []))
        ]

    # Labels uniques : si doublon de titre, on ajoute le chemin entre parenthèses
    labels = []
    seen_titles: dict[str, int] = {}
    for n in filtered:
        title = n["title"]
        display_title = prefix_note_label(title, n["file_path"])
        if title in seen_titles:
            seen_titles[title] += 1
            labels.append(f"{display_title} ({n['file_path']})")
        else:
            seen_titles[title] = 1
            labels.append(display_title)
    label_to_fp = {lbl: n["file_path"] for lbl, n in zip(labels, filtered)}

    _SELECTOR_KEY = "note_page_selector"
    _NAV_KEY = "note_nav_request"  # navigation externe (Brain, wikilinks…)

    if labels:
        # Navigation externe : une autre page a positionné note_nav_request
        _nav_fp = st.session_state.pop(_NAV_KEY, None)
        # Synchronisation avec viewing_note si défini
        _viewing_fp = st.session_state.get("viewing_note")
        if _nav_fp:
            normalized_nav_fp = normalize_vault_relative_path(_nav_fp)
            _nav_label = next(
                (lbl for lbl, fp in label_to_fp.items() if normalize_vault_relative_path(fp) == normalized_nav_fp),
                None,
            )
            if _nav_label:
                st.session_state[_SELECTOR_KEY] = _nav_label
        elif _viewing_fp:
            normalized_viewing_fp = normalize_vault_relative_path(_viewing_fp)
            _viewing_label = next(
                (lbl for lbl, fp in label_to_fp.items() if normalize_vault_relative_path(fp) == normalized_viewing_fp),
                None,
            )
            if _viewing_label:
                st.session_state[_SELECTOR_KEY] = _viewing_label
        elif st.session_state.get(_SELECTOR_KEY) not in labels:
            # Premier chargement ou liste filtrée ne contient plus la sélection
            st.session_state[_SELECTOR_KEY] = labels[0]

        selected_label = st.selectbox(
            "Note",
            options=labels,
            key=_SELECTOR_KEY,
            label_visibility="collapsed",
        )
        selected_fp = normalize_vault_relative_path(label_to_fp.get(selected_label, ""))
        st.session_state.viewing_note = selected_fp
    else:
        selected_fp = ""
        st.info("Aucune note ne correspond à la recherche.")

    st.divider()
    st.page_link("app.py", label="← Retour au chat", icon="💬")
    render_theme_toggle()

# ---------------------------------------------------------------------------
# Affichage principal
# ---------------------------------------------------------------------------

if not selected_fp:
    st.info("Aucune note sélectionnée. Utilisez le sélecteur dans la barre latérale.")
    st.stop()

note_abs = resolve_vault_path(selected_fp)
if not note_abs.exists():
    st.error(f"Fichier introuvable : `{selected_fp}`")
    st.stop()

# Métadonnées de la note depuis le store vecteurs
note_meta = notes_by_path.get(selected_fp) or svc.chroma.get_note_by_file_path(selected_fp) or {}
tags = note_meta.get("tags", [])
wikilinks = note_meta.get("wikilinks", [])
date_mod = note_meta.get("date_modified", "")[:10]
date_cre = note_meta.get("date_created", "")[:10]

# Lien Obsidian deep-link
_vault_name = settings.obsidian_vault
_file_encoded = selected_fp.replace("%", "%25").replace(" ", "%20")
_obsidian_url = f"obsidian://open?vault={_vault_name}&file={_file_encoded}"

# En-tête
col_title, col_meta = st.columns([3, 1])
with col_title:
    st.title(note_meta.get("title", note_abs.stem))
    st.markdown(render_note_badge(selected_fp), unsafe_allow_html=True)
    st.caption(f"`{selected_fp}`")
    st.markdown(
        build_obsidian_open_link_html(_obsidian_url),
        unsafe_allow_html=True,
    )
with col_meta:
    st.caption(f"📅 Créé : {date_cre}")
    st.caption(f"✏️ Modifié : {date_mod}")
    if tags:
        st.caption("🏷 " + " · ".join(f"`{t}`" for t in tags[:8]))

st.divider()

# Contenu
content = read_text_file(note_abs, default="", errors="replace")
outline = extract_note_outline(content)
local_search = st.text_input("🔎 Rechercher dans cette note", placeholder="Titre de section ou texte…")
matches = find_note_matches(content, local_search) if local_search.strip() else []
anchor_lines = {int(item["line"]) for item in outline[:60]}
anchor_lines.update(int(match["line"]) for match in matches)

summary_cols = st.columns(4)
summary_cols[0].metric("Sections", len(outline))
summary_cols[1].metric("Diagrammes", count_mermaid_blocks(content))
summary_cols[2].metric("Liens sortants", len(wikilinks))
backlinks = svc.chroma.get_backlinks(selected_fp)
summary_cols[3].metric("Rétroliens", len(backlinks))

if outline:
    with st.expander("🧭 Structure de la note", expanded=False):
        for index, item in enumerate(outline[:30]):
            anchor_id = make_note_anchor(int(item["line"]))
            col_info, col_button = st.columns([8, 1])
            col_info.markdown(
                build_outline_item_html(item["title"], int(item["line"]), int(item["level"])),
                unsafe_allow_html=True,
            )
            if col_button.button("↘", key=f"outline_jump_{index}_{item['line']}", help="Aller à cette section"):
                st.session_state["_note_focus_anchor"] = anchor_id
                st.rerun()

if local_search.strip():
    if matches:
        with st.expander(f"📍 Résultats dans la note ({len(matches)})", expanded=True):
            for index, match in enumerate(matches):
                anchor_id = make_note_anchor(int(match["line"]))
                col_info, col_button = st.columns([8, 1])
                col_info.markdown(
                    build_search_match_html(match["section"], int(match["line"]), match["snippet"]),
                    unsafe_allow_html=True,
                )
                if col_button.button("↘", key=f"search_jump_{index}_{match['line']}", help="Aller à cet extrait"):
                    st.session_state["_note_focus_anchor"] = anchor_id
                    st.rerun()
    else:
        st.info("Aucun passage correspondant dans cette note.")

st.divider()
render_note(content, anchor_lines=anchor_lines)
focus_anchor = st.session_state.pop("_note_focus_anchor", None)
if focus_anchor:
    _scroll_to_anchor(focus_anchor)

# Wikilinks & rétroliens
if wikilinks or True:
    st.divider()
    col_links, col_back = st.columns(2)

    with col_links:
        if wikilinks:
            st.markdown("**🔗 Liens sortants**")
            for link in wikilinks[:20]:
                target = next((n for n in notes if link.lower() in n["title"].lower()), None)
                if target:
                    if st.button(f"→ {target['title']}", key=f"wl_{link}", use_container_width=True):
                        st.session_state.viewing_note = target["file_path"]
                        st.session_state.note_nav_request = target["file_path"]
                        st.rerun()
                else:
                    st.caption(f"↗ {link} *(non indexé)*")

    with col_back:
        # Rétroliens : notes qui pointent vers cette note
        if backlinks:
            st.markdown("**🔙 Rétroliens**")
            for bl in backlinks[:10]:
                if st.button(f"← {bl['title']}", key=f"bl_{bl['file_path']}", use_container_width=True):
                    st.session_state.viewing_note = bl["file_path"]
                    st.session_state.note_nav_request = bl["file_path"]
                    st.rerun()
