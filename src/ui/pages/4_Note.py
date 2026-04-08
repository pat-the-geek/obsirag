"""
Page Visualiseur de Note — rendu Markdown complet avec diagrammes Mermaid.
Accessible depuis les sources du chat, le Cerveau et via le sélecteur intégré.
"""
from __future__ import annotations

import re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from src.config import settings
from src.ui.services_cache import get_services

_icon = str(Path(__file__).parent.parent / "static" / "favicon-32x32.png")
st.set_page_config(page_title="Note — ObsiRAG", page_icon=_icon, layout="wide")
svc = get_services()

# ---------------------------------------------------------------------------
# Rendu Mermaid
# ---------------------------------------------------------------------------

def _mermaid_html(code: str, idx: int) -> str:
    """HTML autonome pour un diagramme Mermaid rendu via CDN.

    Le code est sérialisé en JSON pour éviter tout problème d'échappement
    (balises HTML, backticks, guillemets dans le code Mermaid).
    On utilise mermaid.render() explicitement plutôt que startOnLoad.
    """
    import json
    code_json = json.dumps(code)   # serialisation sûre, gère tous les caractères spéciaux

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body  {{ background: #16213E; padding: 12px; }}
    #out  {{ display: flex; justify-content: center; align-items: flex-start; }}
    #out svg {{ max-width: 100%; height: auto; }}
    #err  {{ color: #F87171; font-family: monospace; font-size: 12px;
             white-space: pre-wrap; padding: 8px;
             background: #1f1f2e; border-radius: 4px; }}
  </style>
</head>
<body>
  <div id="out"></div>
  <div id="err"></div>
  <script>
    (async function() {{
      const code = {code_json};
      try {{
        mermaid.initialize({{
          startOnLoad: false,
          theme: 'dark',
          securityLevel: 'loose',
          fontFamily: 'ui-sans-serif, system-ui, sans-serif',
          fontSize: 14
        }});
        const {{ svg }} = await mermaid.render('mg{idx}', code);
        document.getElementById('out').innerHTML = svg;
      }} catch(e) {{
        document.getElementById('err').textContent =
          '⚠ Erreur Mermaid\\n' + e.message + '\\n\\n' + code;
      }}
    }})();
  </script>
</body>
</html>"""


def _estimate_mermaid_height(code: str) -> int:
    lines = len(code.strip().splitlines())
    return max(200, min(600, 120 + lines * 22))


# ---------------------------------------------------------------------------
# Rendu Markdown + Mermaid
# ---------------------------------------------------------------------------

_MERMAID_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)
_FM_RE = re.compile(r"^\s*---\n.*?\n---\n?", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]*)?\]\]")


def render_note(content: str) -> None:
    """Découpe le contenu en blocs texte / Mermaid et rend chacun."""
    # Supprime le frontmatter YAML
    content = _FM_RE.sub("", content, count=1)

    last = 0
    idx = 0
    for match in _MERMAID_RE.finditer(content):
        before = content[last: match.start()].strip()
        if before:
            st.markdown(before, unsafe_allow_html=False)

        mermaid_code = match.group(1).strip()
        height = _estimate_mermaid_height(mermaid_code)
        st.caption("📊 Diagramme Mermaid")
        components.html(_mermaid_html(mermaid_code, idx), height=height, scrolling=False)
        idx += 1
        last = match.end()

    remainder = content[last:].strip()
    if remainder:
        st.markdown(remainder, unsafe_allow_html=False)


# ---------------------------------------------------------------------------
# Sidebar — sélecteur de note
# ---------------------------------------------------------------------------

notes = svc.chroma.list_notes()

with st.sidebar:
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

    options = {f"{n['title']}": n["file_path"] for n in filtered}

    preselected = st.session_state.get("viewing_note", "")
    pre_title = next((n["title"] for n in notes if n["file_path"] == preselected), None)

    selected_label = st.selectbox(
        "Note",
        options=list(options.keys()),
        index=(list(options.keys()).index(pre_title) if pre_title and pre_title in options else 0),
        label_visibility="collapsed",
    )
    selected_fp = options.get(selected_label, "")
    if selected_fp:
        st.session_state.viewing_note = selected_fp

    st.divider()
    st.page_link("app.py", label="← Retour au chat", icon="💬")

# ---------------------------------------------------------------------------
# Affichage principal
# ---------------------------------------------------------------------------

if not selected_fp:
    st.info("Aucune note sélectionnée. Utilisez le sélecteur dans la barre latérale.")
    st.stop()

note_abs = settings.vault / selected_fp
if not note_abs.exists():
    st.error(f"Fichier introuvable : `{selected_fp}`")
    st.stop()

# Métadonnées de la note depuis ChromaDB
note_meta = next((n for n in notes if n["file_path"] == selected_fp), {})
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
    st.caption(f"`{selected_fp}`")
    st.markdown(
        f'<a href="{_obsidian_url}" target="_blank" style="'
        'display:inline-flex;align-items:center;gap:6px;'
        'background:#7C3AED;color:#fff;border-radius:6px;'
        'padding:4px 12px;font-size:13px;font-weight:600;'
        'text-decoration:none;">'
        '🟣 Ouvrir dans Obsidian</a>',
        unsafe_allow_html=True,
    )
with col_meta:
    st.caption(f"📅 Créé : {date_cre}")
    st.caption(f"✏️ Modifié : {date_mod}")
    if tags:
        st.caption("🏷 " + " · ".join(f"`{t}`" for t in tags[:8]))

st.divider()

# Contenu
content = note_abs.read_text(encoding="utf-8", errors="replace")
render_note(content)

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
                        st.rerun()
                else:
                    st.caption(f"↗ {link} *(non indexé)*")

    with col_back:
        # Rétroliens : notes qui pointent vers cette note
        backlinks = [
            n for n in notes
            if note_abs.stem.lower() in [w.lower() for w in n.get("wikilinks", [])]
            and n["file_path"] != selected_fp
        ]
        if backlinks:
            st.markdown("**🔙 Rétroliens**")
            for bl in backlinks[:10]:
                if st.button(f"← {bl['title']}", key=f"bl_{bl['file_path']}", use_container_width=True):
                    st.session_state.viewing_note = bl["file_path"]
                    st.rerun()
