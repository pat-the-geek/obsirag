"""
Composant de menu latéral ObsiRAG — accès rapide dashboard, cerveau, insights, paramètres, favoris, historique.
"""
import streamlit as st
from pathlib import Path

PAGES = [
    {"label": "Tableau de bord", "icon": "📊", "page": "pages/0_Dashboard.py"},
    {"label": "Chat", "icon": "💬", "page": "app.py"},
    {"label": "Cerveau", "icon": "🧠", "page": "pages/1_Brain.py"},
    {"label": "Insights", "icon": "💡", "page": "pages/2_Insights.py"},
    {"label": "Paramètres", "icon": "⚙️", "page": "pages/3_Settings.py"},
]

FAVORIS_KEY = "obsirag_favoris"
HISTO_KEY = "obsirag_historique"
MAX_HISTORY_ITEMS = 20


def render_mobile_main_menu() -> None:
    """Menu hamburger mobile avec navigation Streamlit native, invisible sur desktop."""
    st.markdown(
        """
        <style>
        /* ---- Desktop (défaut) : menu mobile totalement masqué ---- */
        .st-key-obsirag-mobile-menu {
            display: none !important;
            visibility: hidden !important;
            width: 0 !important;
            height: 0 !important;
            overflow: hidden !important;
            pointer-events: none !important;
            position: absolute !important;
            opacity: 0 !important;
        }

        /* ---- Mobile ---- */
        @media (max-width: 768px) {
            .st-key-obsirag-mobile-menu {
                display: block !important;
                visibility: visible !important;
                opacity: 1 !important;
                width: min(4.5rem, calc(100vw - 1.5rem)) !important;
                height: auto !important;
                overflow: visible !important;
                pointer-events: auto !important;
                position: fixed;
                top: 0.75rem;
                right: 0.75rem;
                z-index: 1001;
                margin: 0 !important;
            }
            .st-key-obsirag-mobile-menu > div {
                justify-content: flex-end;
            }
            .st-key-obsirag-mobile-menu button {
                min-height: 2.8rem !important;
                border-radius: 999px !important;
                border: 1px solid rgba(0, 95, 204, 0.18);
                background: rgba(255, 255, 255, 0.94);
                color: #0f172a !important;
                box-shadow: 0 12px 30px rgba(15, 23, 42, 0.16);
                backdrop-filter: blur(12px);
            }
            .st-key-obsirag-mobile-menu [data-testid="stExpander"] {
                background: transparent !important;
                border: none !important;
                box-shadow: none !important;
            }
            .st-key-obsirag-mobile-menu [data-testid="stExpander"] details {
                overflow: visible !important;
            }
            .st-key-obsirag-mobile-menu [data-testid="stExpander"] summary {
                min-height: 2.8rem !important;
                border-radius: 999px !important;
                border: 1px solid rgba(0, 95, 204, 0.18) !important;
                background: rgba(255, 255, 255, 0.94) !important;
                color: #0f172a !important;
                box-shadow: 0 12px 30px rgba(15, 23, 42, 0.16) !important;
                backdrop-filter: blur(12px) !important;
            }
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] {
                position: absolute !important;
                top: 3.05rem;
                right: 0;
                z-index: 1002 !important;
                background: #fff !important;
                border: 1.5px solid #bbb !important;
                border-radius: 8px !important;
                box-shadow: 0 18px 40px rgba(15, 23, 42, 0.22) !important;
                padding: 0.5rem !important;
                min-width: 13rem !important;
            }
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] > div,
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] > div > div,
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] > div > div > div {
                background: #fff !important;
                color: #111 !important;
            }
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] *,
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] [data-testid="stMarkdownContainer"],
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] [data-testid="stMarkdownContainer"] *,
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] [data-testid="stCaptionContainer"],
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] [data-testid="stCaptionContainer"] *,
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] [data-testid="stPageLink"],
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] [data-testid="stPageLink"] *,
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] .stButton > button,
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] .stButton > button p,
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] .stButton > button span {
                color: #111 !important;
                fill: #111 !important;
                -webkit-text-fill-color: #111 !important;
                opacity: 1 !important;
            }
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] [data-testid="stPageLink"] {
                width: 100% !important;
            }
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] [data-testid="stPageLink"] a {
                width: 100% !important;
                justify-content: flex-start !important;
                min-height: 2.6rem !important;
                padding-inline: 0.85rem !important;
                margin-bottom: 2px !important;
                background: #fff !important;
                border: 1.5px solid #bbb !important;
                border-radius: 6px !important;
                box-shadow: none !important;
                text-decoration: none !important;
            }
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] [data-testid="stPageLink"] a:hover,
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] [data-testid="stPageLink"] a:focus-visible,
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] .stButton > button:hover,
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] .stButton > button:focus-visible {
                background: #e6f0fa !important;
                color: #005fcc !important;
                border: 2px solid #005fcc !important;
            }
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] [data-testid="stPageLink"] a:hover *,
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] [data-testid="stPageLink"] a:focus-visible *,
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] .stButton > button:hover p,
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] .stButton > button:focus-visible p,
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] .stButton > button:hover span,
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] .stButton > button:focus-visible span {
                color: #005fcc !important;
                -webkit-text-fill-color: #005fcc !important;
            }
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] [data-testid="stCaptionContainer"],
            .st-key-obsirag-mobile-menu [data-testid="stExpanderDetails"] .stCaption {
                color: #555 !important;
                -webkit-text-fill-color: #555 !important;
            }
            /* Espace en haut de page pour ne pas superposer le contenu */
            .block-container,
            div.block-container,
            section.main div.block-container {
                padding-top: 4.25rem !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    with st.container(key="obsirag-mobile-menu"):
        with st.expander("☰", expanded=False, width="stretch"):
            st.caption("Navigation")
            for entry in PAGES:
                st.page_link(
                    entry["page"],
                    label=entry["label"],
                    icon=entry["icon"],
                    use_container_width=True,
                )


def render_sidebar_toggle_button(label: str = "☰ Menu", variant: str = "floating") -> None:
    if variant == "inline":
        button_css = """
        .obsirag-open-sidebar-btn {
            float: right;
            margin-top: 8px;
            margin-bottom: 8px;
        }
        .obsirag-open-sidebar-btn.visible {
            display: inline-block;
        }
        """
    else:
        button_css = """
        .obsirag-open-sidebar-btn {
            position: fixed;
            top: 16px;
            left: 16px;
            z-index: 9999;
        }
        .obsirag-open-sidebar-btn.visible {
            display: block;
        }
        """

    st.markdown(
        f"""
        <style>
        .obsirag-open-sidebar-btn {{
            display: none;
            background: #005fcc;
            color: #fff;
            border: none;
            border-radius: 6px;
            padding: 7px 16px;
            font-size: 1em;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            cursor: pointer;
            opacity: 0.92;
            transition: opacity 0.2s;
        }}
        .obsirag-open-sidebar-btn:hover {{ opacity: 1; background: #0074e0; }}
        {button_css}
        </style>
        <button id="obsiragOpenSidebarBtn" class="obsirag-open-sidebar-btn" onclick="window.obsiragOpenSidebar && window.obsiragOpenSidebar()">{label}</button>
        <script>
        (() => {{
            const rootDocument = window.parent?.document || document;

            function getSidebar() {{
                return rootDocument.querySelector('[data-testid="stSidebar"]')
                    || rootDocument.querySelector('section.stSidebar');
            }}

            function getExpandButton() {{
                return rootDocument.querySelector('[data-testid="stExpandSidebarButton"]')
                    || rootDocument.querySelector('[data-testid="collapsedControl"]')
                    || rootDocument.querySelector('button[aria-label="Expand sidebar"]');
            }}

            function syncVisibility() {{
                const sidebar = getSidebar();
                const openButton = document.getElementById('obsiragOpenSidebarBtn');
                if (!openButton) return;
                const isCollapsed = !sidebar
                    || sidebar.getAttribute('aria-expanded') === 'false'
                    || sidebar.offsetWidth < 60;
                openButton.classList.toggle('visible', isCollapsed);
            }}

            window.obsiragOpenSidebar = () => {{
                const expandButton = getExpandButton();
                if (expandButton) {{
                    expandButton.click();
                    window.setTimeout(syncVisibility, 150);
                    window.setTimeout(syncVisibility, 500);
                    return;
                }}

                const sidebar = getSidebar();
                if (sidebar) {{
                    sidebar.style.display = 'block';
                    sidebar.style.visibility = 'visible';
                    sidebar.style.transform = 'translateX(0)';
                    sidebar.setAttribute('aria-expanded', 'true');
                }}
                syncVisibility();
            }};

            syncVisibility();
            window.setTimeout(syncVisibility, 300);
            if (!window.__obsiragSidebarToggleInterval) {{
                window.__obsiragSidebarToggleInterval = window.setInterval(syncVisibility, 1200);
            }}
        }})();
        </script>
        """,
        unsafe_allow_html=True,
    )


def render_side_menu():
    # Composant invisible pour empêcher la fermeture totale de la sidebar
    st.sidebar.markdown('<div style="height:1px;opacity:0;">.</div>', unsafe_allow_html=True)
    # Affiche le logo ObsiRAG tout en haut du menu latéral
    logo_path = str(Path(__file__).parent / "static" / "obsirag_icon.svg")
    try:
        st.sidebar.image(logo_path, width=55)
    except Exception:
        st.sidebar.markdown("# ObsiRAG")

    # Recherche globale
    st.sidebar.markdown("<hr style='border:1px solid #bbb;margin:0.5em 0;'>", unsafe_allow_html=True)
    st.sidebar.markdown("<div class='sidebar-section'><span style='font-size:1.1em;'>🔎 Recherche globale</span></div>", unsafe_allow_html=True)
    query = st.sidebar.text_input("Rechercher dans les notes...", key="global_search_input", help="Recherche plein texte dans toutes les notes du coffre")
    if query and len(query) > 2:
        import re
        # Correction : accès au vrai vault_path depuis settings si possible
        try:
            from src.config import settings
            vault_dir = Path(getattr(settings, 'vault_path', '/vault'))
        except Exception:
            vault_dir = Path('/vault')
        results = []
        # Recherche simple dans tous les fichiers .md du vault
        if vault_dir.exists():
            for md_file in vault_dir.rglob("*.md"):
                try:
                    content = md_file.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                if re.search(re.escape(query), content, re.IGNORECASE):
                    results.append(md_file)
                if len(results) >= 10:
                    break
        if results:
            st.sidebar.caption(f"{len(results)} résultat(s) trouvé(s) :")
            st.markdown("""
                <style>
                .sidebar-search-result {
                    display: flex;
                    align-items: center;
                    border: 1px solid #e0e0e0;
                    border-radius: 5px;
                    padding: 1px 6px 1px 3px;
                    margin-bottom: 3px;
                    background: #fafbfc;
                    font-size: 0.91em;
                    color: #555;
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    min-height: 20px;
                    max-width: 98%;
                }
                .stSidebar .stButton>button {
                    font-size: 0.95em !important;
                    padding: 0 0.1em !important;
                    min-width: 0.7em !important;
                    width: 1.1em !important;
                    height: 1.1em !important;
                    line-height: 1.1 !important;
                }
                </style>
            """, unsafe_allow_html=True)
            for res in results:
                file_fullname = str(res)
                label = f"📝 {res.stem}"
                btn = st.sidebar.button(label, key=f"searchres_{res}", help=file_fullname)
                if btn:
                    st.session_state.viewing_note = str(res)
                    st.switch_page("pages/4_Note.py")
        else:
            st.sidebar.caption("Aucun résultat trouvé.")

    # Responsive largeur
    st.markdown("""
        <style>
        [data-testid="stSidebar"] { min-width: 220px; max-width: 340px; }
        button:focus { outline: 2px solid #005fcc !important; }
        .stButton>button, .stButton>button:focus { background: #fff; color: #111; border-radius: 6px; border: 1.5px solid #bbb; margin-bottom: 2px; }
        .stButton>button:hover { background: #e6f0fa; color: #005fcc; border: 2px solid #005fcc; }
        .sidebar-section { margin-bottom: 1.2em; }
        /* Historique : police discrète */
        .sidebar-history-label { font-size: 0.8em; color: #555; font-weight: normal; }
        .stSidebar div[data-testid="stMarkdownContainer"]:has(.sidebar-history-marker) + div[data-testid="stButton"] > button,
        .stSidebar div[data-testid="stMarkdownContainer"]:has(.sidebar-history-marker) + div.element-container div[data-testid="stButton"] > button {
            font-size: 0.78em !important;
            min-height: 1.7rem !important;
            line-height: 1.05 !important;
            padding: 0.08rem 0.42rem !important;
            margin-bottom: 0.1rem !important;
            border-radius: 5px !important;
        }
        /* Résultats recherche : police discrète */
        .sidebar-search-label { font-size: 0.92em; color: #555; font-weight: normal; }
        </style>
    """, unsafe_allow_html=True)

    st.sidebar.markdown("<div class='sidebar-section'><span style='font-size:1.2em;font-weight:bold;'>Navigation</span></div>", unsafe_allow_html=True)
    for entry in PAGES:
        label = f"{entry['icon']} {entry['label'] }"
        help_text = f"Aller à la page {entry['label']}"
        if st.sidebar.button(label, key=f"nav_{entry['page']}", help=help_text):
            st.switch_page(entry["page"])

    st.sidebar.markdown("<hr style='border:1px solid #bbb;margin:0.5em 0;'>", unsafe_allow_html=True)
    st.sidebar.markdown("<div class='sidebar-section'><span style='font-size:1.1em;'>⭐ Favoris</span></div>", unsafe_allow_html=True)
    favoris = st.session_state.get(FAVORIS_KEY, [])
    if not favoris:
        st.sidebar.caption("Aucun favori.")
    else:
        for fav in favoris:
            label = f"⭐ {fav}"
            help_text = f"Ouvrir le favori {fav}"
            if st.sidebar.button(label, key=f"fav_{fav}", help=help_text):
                st.session_state.viewing_note = fav
                st.switch_page("pages/4_Note.py")

    st.sidebar.markdown("<hr style='border:1px solid #bbb;margin:0.5em 0;'>", unsafe_allow_html=True)
    st.sidebar.markdown("<div class='sidebar-section'><span style='font-size:1.1em;'>🕑 Historique</span></div>", unsafe_allow_html=True)
    historique = st.session_state.get(HISTO_KEY, [])
    if len(historique) > MAX_HISTORY_ITEMS:
        historique = historique[-MAX_HISTORY_ITEMS:]
        st.session_state[HISTO_KEY] = historique
    if not historique:
        st.sidebar.caption("Aucune requête récente.")
    else:
        import hashlib
        import os
        histo_full = historique[::-1]
        for idx, h in enumerate(histo_full):
            abs_idx = len(historique) - 1 - idx
            h_hash = hashlib.md5(f"{h}_{abs_idx}".encode()).hexdigest()[:8]
            short_name = os.path.basename(h)
            label = f"🕑 {short_name}"
            help_text = f"Ouvrir l'historique {h}"
            key_view = f"histo_{abs_idx}_{h_hash}"
            st.sidebar.markdown("<span class='sidebar-history-marker' style='display:none'></span>", unsafe_allow_html=True)
            if st.sidebar.button(label, key=key_view, help=help_text):
                st.session_state.viewing_note = h
                st.switch_page("pages/4_Note.py")
