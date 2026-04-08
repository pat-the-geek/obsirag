"""
ObsiRAG — Système de thèmes VS Code (Light+ / Dark+).

Usage dans chaque page, juste après set_page_config() :

    from src.ui.theme import inject_theme, render_theme_toggle
    inject_theme()                # injecte le CSS dans la page
    render_theme_toggle()         # affiche le sélecteur dans la sidebar

Le thème est stocké dans st.session_state["vsc_theme"] :
  - "auto"  → suit prefers-color-scheme du navigateur (CSS @media)
  - "light" → VS Code Light+ forcé
  - "dark"  → VS Code Dark+ forcé
"""

from __future__ import annotations
from datetime import datetime
import streamlit as st
import streamlit.components.v1 as components


# ── Palette Dark+ (inspirée Claude Code Dark / VS Code Dark+) ─────────────────
# Fond : bleu-nuit profond, texte blanc cassé, accents bleus vifs.
# Police : system-ui — même mise en page que Light+, juste les couleurs changent.
_D = {
    "bg":         "#0d1117",   # bleu-nuit GitHub / Claude Code dark
    "bg2":        "#161b22",   # sidebar / cards
    "bg3":        "#21262d",   # code blocks, inputs
    "text":       "#e6edf3",   # blanc cassé très lisible
    "text_dim":   "#8b949e",   # gris moyen
    "accent":     "#58a6ff",   # bleu clair vif (GitHub dark accent)
    "accent_dim": "#1f3a5f",   # bleu foncé discret pour hover/focus
    "border":     "#30363d",   # bordure subtile
    "input_bg":   "#0d1117",
    "code_fg":    "#79c0ff",   # bleu-cyan pour le code
    "tag_bg":     "#1f3a5f",
    "btn_fg":     "#e6edf3",
    "metric_val": "#58a6ff",
    "warn":       "#d29922",
    "err":        "#f85149",
    "ok":         "#3fb950",
    # Même police sistema que Light+ — cohérence de mise en page
    "font":       "system-ui, -apple-system, 'Segoe UI', 'Inter', Helvetica, Arial, sans-serif",
    "font_code":  "'Menlo', 'Consolas', 'Courier New', monospace",
}

# ── Palette Light+ (inspirée Claude Code / VS Code Light+) ─────────────────────
# Fond : blanc pur + gris très fin, à la manière du shell Claude Code.
# Police : system-ui (SF Pro macOS, Segoe UI Windows) — jamais monospace
# sauf pour les blocs de code inline/block.
_L = {
    "bg":         "#ffffff",
    "bg2":        "#f7f7f7",   # sidebar / cards — très léger
    "bg3":        "#efefef",   # code blocks, tags
    "text":       "#1a1a1a",   # quasi-noir, lecture confortable
    "text_dim":   "#6b7280",   # slate-500
    "accent":     "#0066b8",   # bleu VS Code Light+ exact
    "accent_dim": "#e8f1fb",   # survol / focus subtil
    "border":     "#e2e2e2",   # ultra-discret comme Claude Code
    "input_bg":   "#ffffff",
    "code_fg":    "#a31515",   # rouge VS Code Light+ pour strings
    "tag_bg":     "#e8f1fb",
    "btn_fg":     "#1a1a1a",
    "metric_val": "#0066b8",
    "warn":       "#795e26",
    "err":        "#cd3131",
    "ok":         "#008000",
    # Police sans-serif système : SF Pro (macOS), Segoe UI (Windows)
    "font":       "system-ui, -apple-system, 'Segoe UI', 'Inter', Helvetica, Arial, sans-serif",
    "font_code":  "'Menlo', 'Consolas', 'Courier New', monospace",
}


def _css_block(p: dict) -> str:
    """Génère le bloc CSS pour une palette donnée."""
    return f"""
    /* ── Police de caractères ── */
    html, body, .stApp, [data-testid="stAppViewContainer"],
    [data-testid="stSidebar"], input, textarea, select,
    p, li, label, h1, h2, h3, h4, h5, h6,
    [data-testid="stMarkdownContainer"] *,
    [data-testid="stChatMessageContent"] * {{
        font-family: {p["font"]} !important;
    }}
    code, pre, pre code, kbd, samp,
    [data-testid="stChatInput"] textarea {{
        font-family: {p["font_code"]} !important;
    }}
    /* Restaure la police icônes Material Symbols de Streamlit
       (les icônes sont des ligatures texte — si on écrase la font, _arrow_down_ s'affiche) */
    .material-symbols-rounded,
    .material-symbols-outlined,
    .material-symbols-sharp,
    [class*="material-symbols"],
    [data-testid="stIconMaterial"],
    [data-testid="stIconEmoji"] {{
        font-family: 'Material Symbols Rounded', 'Material Symbols Outlined',
                     'Material Symbols Sharp', 'Material Icons' !important;
    }}

    /* ── Racine & variables Streamlit ── */
    :root {{
        --primary-color:                {p["accent"]} !important;
        --background-color:             {p["bg"]}    !important;
        --secondary-background-color:   {p["bg2"]}   !important;
        --text-color:                   {p["text"]}  !important;
        --user-bubble-bg:               {p["accent_dim"]};
        --user-bubble-border:           {p["accent"]};
    }}

    /* ── App principal ── */
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    [data-testid="block-container"] {{
        background-color: {p["bg"]} !important;
        color: {p["text"]} !important;
    }}

    /* ── Header ── */
    [data-testid="stHeader"] {{
        background-color: {p["bg2"]} !important;
        border-bottom: 1px solid {p["border"]} !important;
    }}

    /* ── Sidebar ── */
    [data-testid="stSidebar"],
    [data-testid="stSidebarContent"],
    section[data-testid="stSidebar"] > div:first-child {{
        background-color: {p["bg2"]} !important;
        border-right: 1px solid {p["border"]} !important;
    }}

    /* ── Texte général ── */
    p, li, label, td, th,
    [data-testid="stMarkdownContainer"],
    [data-testid="stText"] {{
        color: {p["text"]} !important;
    }}
    [data-testid="stMarkdownContainer"] span,
    [data-testid="stChatMessageContent"] span,
    [data-testid="stCaptionContainer"] span {{
        color: inherit !important;
    }}
    h1, h2, h3, h4, h5, h6 {{
        color: {p["text"]} !important;
    }}
    .stCaption, [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] p {{
        color: {p["text_dim"]} !important;
    }}
    small {{ color: {p["text_dim"]} !important; }}

    /* ── Inputs ── */
    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-testid="stNumberInput"] input,
    [data-baseweb="input"] input,
    [data-baseweb="textarea"] textarea {{
        background-color: {p["input_bg"]} !important;
        color: {p["text"]} !important;
        border-color: {p["border"]} !important;
    }}
    [data-baseweb="input"],
    [data-baseweb="textarea"] {{
        background-color: {p["input_bg"]} !important;
        border-color: {p["border"]} !important;
    }}

    /* ── Chat input ── */
    /* Aligner sur le bord gauche du bloc de contenu (block-container padding = 1rem) */
    [data-testid="stBottom"] {{
        padding: 8px 1rem 12px !important;
    }}
    [data-testid="stChatInput"] {{
        border-radius: 10px !important;
        border: 1px solid {p["accent"]} !important;
        box-shadow: 0 0 0 2px {p["accent_dim"]} !important;
        background-color: {p["input_bg"]} !important;
        overflow: hidden !important;
    }}
    [data-testid="stChatInput"] > div,
    [data-testid="stChatInput"] textarea {{
        background-color: {p["input_bg"]} !important;
        color: {p["text"]} !important;
    }}
    [data-testid="stChatInput"]:focus-within {{
        border-color: {p["accent"]} !important;
        box-shadow: 0 0 0 3px {p["accent_dim"]} !important;
    }}

    /* ── Selectbox / Multiselect ── */
    [data-baseweb="select"] > div,
    [data-baseweb="select"] [data-baseweb="select"] > div {{
        background-color: {p["input_bg"]} !important;
        border-color: {p["border"]} !important;
        color: {p["text"]} !important;
    }}
    [data-baseweb="menu"],
    [data-baseweb="popover"] {{
        background-color: {p["bg2"]} !important;
        border-color: {p["border"]} !important;
    }}
    [role="option"],
    [data-baseweb="menu"] li {{
        background-color: {p["bg2"]} !important;
        color: {p["text"]} !important;
    }}
    [role="option"]:hover,
    [data-baseweb="menu"] li:hover {{
        background-color: {p["accent_dim"]} !important;
    }}
    [data-testid="stTag"] {{
        background-color: {p["tag_bg"]} !important;
        color: {p["text"]} !important;
        border-color: {p["border"]} !important;
    }}

    /* ── Boutons ── */
    .stButton > button,
    [data-testid="stBaseButton-secondary"],
    [data-testid="stBaseButton-secondaryFormSubmit"] {{
        background-color: {p["bg2"]} !important;
        color: {p["text"]} !important;
        border-color: {p["border"]} !important;
    }}
    .stButton > button:hover,
    [data-testid="stBaseButton-secondary"]:hover {{
        background-color: {p["accent_dim"]} !important;
        border-color: {p["accent"]} !important;
        color: {p["accent"]} !important;
    }}
    .stButton > button[kind="primary"],
    [data-testid="stBaseButton-primary"],
    [data-testid="stBaseButton-primaryFormSubmit"] {{
        background-color: {p["accent"]} !important;
        color: #ffffff !important;
        border-color: {p["accent"]} !important;
    }}
    .stButton > button[kind="primary"]:hover,
    [data-testid="stBaseButton-primary"]:hover {{
        filter: brightness(1.15);
    }}

    /* ── Métriques ── */
    [data-testid="metric-container"],
    [data-testid="stMetric"] {{
        background-color: {p["bg2"]} !important;
        border: 1px solid {p["border"]} !important;
        border-radius: 6px !important;
        padding: 10px 14px !important;
    }}
    [data-testid="stMetricValue"] > div,
    [data-testid="stMetricLabel"] > div,
    [data-testid="stMetricDelta"] > div {{
        color: {p["text"]} !important;
    }}
    [data-testid="stMetricValue"] > div {{
        color: {p["metric_val"]} !important;
    }}

    /* ── Expanders ── */
    [data-testid="stExpander"] {{
        background-color: {p["bg2"]} !important;
        border: 1px solid {p["border"]} !important;
        border-radius: 6px !important;
        overflow: hidden !important;
    }}
    [data-testid="stExpander"] details,
    [data-testid="stExpander"] summary,
    [data-testid="stExpander"] > details > summary,
    [data-testid="stExpanderHeader"] {{
        background-color: {p["bg2"]} !important;
        color: {p["text"]} !important;
    }}
    [data-testid="stExpanderDetails"],
    [data-testid="stExpanderDetails"] > div {{
        background-color: {p["bg2"]} !important;
    }}
    /* Empêche le titre SVG de l'icône d'afficher en texte via CSS */
    details summary svg title, details summary svg desc {{
        display: none !important;
    }}
    [data-testid="stExpanderHeader"] p,
    .streamlit-expanderHeader {{
        color: {p["text"]} !important;
        background-color: transparent !important;
    }}

    /* ── Tabs ── */
    [data-baseweb="tab-list"] {{
        background-color: transparent !important;
        border-bottom: 1px solid {p["border"]} !important;
    }}
    [data-baseweb="tab"] {{
        background-color: transparent !important;
        color: {p["text_dim"]} !important;
    }}
    [data-baseweb="tab"]:hover {{
        color: {p["text"]} !important;
        background-color: {p["bg2"]} !important;
    }}
    [aria-selected="true"][data-baseweb="tab"] {{
        color: {p["accent"]} !important;
        border-bottom-color: {p["accent"]} !important;
        background-color: transparent !important;
    }}
    [data-baseweb="tab-panel"] {{
        background-color: {p["bg"]} !important;
    }}

    /* ── Alertes / Info / Succès ── */
    [data-testid="stAlert"] {{
        background-color: {p["bg2"]} !important;
        border-radius: 6px !important;
    }}
    [data-testid="stAlert"] p,
    [data-testid="stAlert"] span {{
        color: {p["text"]} !important;
    }}
    .stAlert[data-baseweb="notification"] {{
        background-color: {p["bg2"]} !important;
    }}

    /* ── Code / Pre ── */
    code {{
        background-color: {p["bg3"]} !important;
        color: {p["code_fg"]} !important;
        border-radius: 3px !important;
        padding: 1px 4px !important;
    }}
    pre, pre code {{
        background-color: {p["bg3"]} !important;
        color: {p["code_fg"]} !important;
        border: 1px solid {p["border"]} !important;
        border-radius: 6px !important;
        padding: 1px 0 !important;
    }}

    /* ── Dataframe / Table ── */
    [data-testid="stDataFrame"],
    [data-testid="stTable"] {{
        background-color: {p["bg2"]} !important;
        border: 1px solid {p["border"]} !important;
        border-radius: 6px !important;
    }}
    .dvn-scroller,
    [class*="glideDataEditor"] {{
        background-color: {p["bg2"]} !important;
    }}

    /* ── Progress bar ── */
    [data-testid="stProgressBar"] > div,
    .stProgress > div > div > div > div {{
        background-color: {p["accent"]} !important;
    }}
    [data-testid="stProgressBar"] {{
        background-color: {p["bg3"]} !important;
    }}

    /* ── Bottom bar (chat input container) ── */
    [data-testid="stBottom"],
    [data-testid="stBottom"] > div,
    [data-testid="stBottom"] > div > div {{
        background-color: {p["bg"]} !important;
        border-top: 1px solid {p["border"]} !important;
    }}

    /* ── Chat messages : conteneur colonne flex ── */
    [data-testid="stVerticalBlockBorderWrapper"]:has([data-testid="stChatMessage"]),
    [data-testid="stVerticalBlock"]:has([data-testid="stChatMessage"]) {{
        display: flex !important;
        flex-direction: column !important;
        align-items: stretch !important;
    }}

    /* ── Chat messages : bulles ── */
    [data-testid="stChatMessage"] {{
        border-radius: 14px !important;
        border: 1px solid {p["border"]} !important;
        background-color: {p["bg2"]} !important;
        padding: 10px 16px !important;
        margin-bottom: 8px !important;
        max-width: 78% !important;
        width: fit-content !important;
        display: flex !important;
        align-items: flex-start !important;
        gap: 10px !important;
    }}
    /* Message user → droite */
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {{
        background-color: {p["accent_dim"]} !important;
        border-color: {p["accent"]} !important;
        align-self: flex-end !important;
        margin-left: auto !important;
        margin-right: 4px !important;
        flex-direction: row-reverse !important;
        border-top-right-radius: 4px !important;
        text-align: right !important;
    }}
    /* Message assistant → gauche */
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {{
        align-self: flex-start !important;
        margin-right: auto !important;
        margin-left: 4px !important;
        border-top-left-radius: 4px !important;
    }}
    [data-testid="stChatMessage"] p,
    [data-testid="stChatMessageContent"] p {{
        color: {p["text"]} !important;
    }}

    /* ── Dividers ── */
    hr {{ border-color: {p["border"]} !important; }}

    /* ── Scrollbar ── */
    ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
    ::-webkit-scrollbar-track {{ background: {p["bg"]}; }}
    ::-webkit-scrollbar-thumb {{ background: {p["border"]}; border-radius: 3px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: {p["accent"]}; }}
    """


# ── CSS pré-compilés ───────────────────────────────────────────────────────────

_CSS_DARK = f"<style>\n{_css_block(_D)}\n</style>"

_CSS_LIGHT = f"<style>\n{_css_block(_L)}\n</style>"

_CSS_AUTO = f"""<style>
@media (prefers-color-scheme: dark) {{
{_css_block(_D)}
}}
@media (prefers-color-scheme: light) {{
{_css_block(_L)}
}}
</style>"""

# ── Clé localStorage partagée avec les iframes Mermaid ────────────────────────
_LS_KEY = "obsirag_diag_theme_v2"


def inject_theme() -> None:
    """
    Initialise st.session_state["vsc_theme"] (si absent) et injecte le CSS.
    À appeler sur chaque page, juste après st.set_page_config().
    """
    if "vsc_theme" not in st.session_state:
        st.session_state["vsc_theme"] = "auto"

    pref = st.session_state["vsc_theme"]
    if pref == "dark":
        st.markdown(_CSS_DARK, unsafe_allow_html=True)
    elif pref == "light":
        st.markdown(_CSS_LIGHT, unsafe_allow_html=True)
    else:
        st.markdown(_CSS_AUTO, unsafe_allow_html=True)

    # Synchronise localStorage pour les iframes Mermaid (même clé)
    _sync_localstorage(pref)


def _sync_localstorage(pref: str) -> None:
    """Écrit le thème dans localStorage du navigateur via un iframe invisible."""
    components.html(
        f"""<script>
        try {{ localStorage.setItem({repr(_LS_KEY)}, {repr(pref)}); }} catch(e) {{}}
        </script>""",
        height=0,
    )


def render_theme_toggle() -> None:
    """
    Affiche le sélecteur de thème dans st.sidebar.
    À appeler dans la sidebar de chaque page.
    """
    pref = st.session_state.get("vsc_theme", "auto")
    st.sidebar.divider()
    st.sidebar.markdown(
        "<span style='font-size:11px;opacity:0.6;font-family:Consolas,monospace'>THÈME</span>",
        unsafe_allow_html=True,
    )
    c1, c2, c3 = st.sidebar.columns(3)
    options = [("auto", "🌓 Auto", c1), ("light", "☀️ Light+", c2), ("dark", "🌙 Dark+", c3)]
    for key, label, col in options:
        btn_type = "primary" if pref == key else "secondary"
        if col.button(label, key=f"_theme_btn_{key}", type=btn_type, use_container_width=True):
            st.session_state["vsc_theme"] = key
            st.rerun()
