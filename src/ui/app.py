"""
ObsiRAG — Page principale : Chat
"""
import base64
import json
import re
import time
import unicodedata
from datetime import datetime
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components

from src.ui.services_cache import get_services
from src.ui.components.note_bridge_component import note_bridge as _note_bridge

# ---- Configuration de la page ----
_icon = str(Path(__file__).parent / "static" / "favicon-32x32.png")
_icon_b64 = base64.b64encode((Path(__file__).parent / "static" / "android-chrome-512x512.png").read_bytes()).decode()
st.set_page_config(
    page_title="ObsiRAG",
    page_icon=_icon,
    layout="wide",
)

svc = get_services()


# ---- Helpers rendu ----

_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FFFF"
    "\U00002600-\U000027BF"
    "\U0001F300-\U0001F9FF"
    "\U00002702-\U000027B0]+",
    flags=re.UNICODE,
)


def _clean_mermaid(code: str) -> str:
    """Supprime accents, émojis et caractères spéciaux non ASCII dans du code Mermaid."""
    # Supprimer les émojis
    code = _EMOJI_RE.sub("", code)
    lines = []
    for line in code.splitlines():
        # Normaliser les caractères accentués -> ASCII de base
        normalized = unicodedata.normalize("NFD", line)
        ascii_line = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
        # Supprimer tout caractère non imprimable non ASCII (hors tab/espace)
        ascii_line = re.sub(r"[^\x09\x20-\x7E]", "", ascii_line)
        lines.append(ascii_line)
    code = "\n".join(lines)
    # Wrapper en guillemets les labels de nœuds contenant des parenthèses ou accolades
    # Ex: A[Titre (sous-titre)] --> A["Titre (sous-titre)"]
    # On ne touche pas les labels déjà entre guillemets
    code = re.sub(
        r'\[([^"\]\[]*[(){][^"\]\[]*)\]',
        lambda m: '["' + m.group(1).replace('"', "'") + '"]',
        code,
    )
    return code


_NER_COLORS = {
    "PERSON":  ("#eef5ff", "#3b6ea8"),   # bleu pâle
    "GPE":     ("#fefce8", "#a16207"),   # jaune très pâle (pays/ville)
    "PRODUCT": ("#f5f3ff", "#6d4fa0"),   # violet pâle
    # ORG, LOC, EVENT, NORP, FAC : non mis en évidence
}

_WUDDAI_TYPE_TO_CAT = {
    "PERSON":  "personne",
    "ORG":     "organisation",
    "GPE":     "lieu",
    "LOC":     "lieu",
    "PRODUCT": "produit",
    "EVENT":   "événement",
    "NORP":    "groupe",
    "FAC":     "lieu",
}

# Mots courants à ne jamais surligner même s'ils sont dans le cache WUDD.ai
_NER_STOPWORDS = {
    "outil", "outils", "chose", "choses", "point", "points", "fois",
    "place", "part", "plus", "type", "types", "base", "bien",
    "aide", "aides", "sens", "art", "clé", "clés", "cas", "lot",
    "set", "get", "run", "use", "new", "one", "two", "top", "pro",
    "max", "min", "end", "api", "url", "key", "id",
}


@st.cache_data(ttl=3600, show_spinner=False)
def _load_wuddai_index() -> dict[str, dict]:
    """Charge le cache WUDD.ai depuis le disque. Retourne {value_lower: {type, value}}."""
    from src.config import settings as _s
    cache_file = _s.data_dir / "wuddai_entities_cache.json"
    if not cache_file.exists():
        return {}
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        return {
            e["value"].lower(): e
            for e in data.get("entities", [])
            if e.get("value")
        }
    except Exception:
        return {}


def _highlight_ner(text: str) -> str:
    """Surligne dans le texte les entités officielles WUDD.ai avec du HTML coloré."""
    wuddai = _load_wuddai_index()
    if not wuddai:
        return text

    # Trier par longueur décroissante pour éviter les chevauchements
    sorted_entries = sorted(wuddai.items(), key=lambda kv: len(kv[0]), reverse=True)

    # Séparer les blocs code/mermaid ET les balises HTML pour ne pas les modifier
    parts = re.split(r"(```.*?```|<[^>]+>)", text, flags=re.DOTALL)
    result_parts = []
    for part in parts:
        if part.startswith("```") or part.startswith("<"):
            result_parts.append(part)
            continue
        for value_lower, entity in sorted_entries:
            ent_type = entity.get("type", "")
            if ent_type not in _NER_COLORS:
                continue
            official_value = entity["value"]
            # Filtrer les mots courants et les entités trop courtes (< 4 chars)
            if official_value.lower() in _NER_STOPWORDS or len(official_value) < 4:
                continue
            bg, fg = _NER_COLORS[ent_type]
            cat_label = _WUDDAI_TYPE_TO_CAT.get(ent_type, ent_type.lower())
            span = (
                f'<span style="background:{bg};color:{fg};border-radius:3px;'
                f'padding:1px 4px;font-weight:600" '
                f'title="{cat_label}">{official_value}</span>'
            )
            part = re.sub(
                rf"(?<![>\w]){re.escape(official_value)}(?![\w<])",
                span,
                part,
                # Pas de re.IGNORECASE : évite les faux positifs (ex: "Ces" ≠ "CES")
            )
        result_parts.append(part)
    return "".join(result_parts)


_MERMAID_SPLIT_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)


@st.cache_data(ttl=60, show_spinner=False)
def _build_title_to_fp() -> dict[str, str]:
    """Index titre + stem + préfixe 30 chars (minuscule) → file_path depuis ChromaDB."""
    result: dict[str, str] = {}
    for note in svc.chroma.list_notes():
        fp = note.get("file_path", "")
        title = note.get("title") or Path(fp).stem
        if not fp:
            continue
        result[title.lower()] = fp
        stem = Path(fp).stem
        result[stem.lower()] = fp
        # Préfixe des 30 premiers chars pour matcher les titres abrégés par le LLM
        for key in (title.lower(), stem.lower()):
            if len(key) > 30:
                result[key[:30]] = fp
    return result


def _linkify_wikilinks(text: str) -> str:
    """Convertit [[Titre]] et [Titre] (citations LLM) en liens cliquables vers le visualiseur."""
    title_to_fp = _build_title_to_fp()

    def _make_link(file_name: str, display: str) -> str:
        key = file_name.lower()
        fp = title_to_fp.get(key, "")
        if not fp:
            # Fallback préfixe : cherche une entrée qui commence par les 30 premiers chars
            prefix = key[:30]
            for k, v in title_to_fp.items():
                if k.startswith(prefix) or prefix.startswith(k[:30]):
                    fp = v
                    break
        if not fp:
            # Non résolu : rendu neutre, pas de lien
            return f"[[{display}]]" if display != file_name else f"[{display}]"
        fp_js = fp.replace("\\", "\\\\").replace("'", "\\'")
        onclick = (
            f"localStorage.setItem('obsirag_open_note','{fp_js}');"
            "return false;"
        )
        return (
            f'<a href="#" onclick="{onclick}" '
            f'style="color:#7c3aed;text-decoration:none;font-weight:600;'
            f'border-bottom:1px dotted #7c3aed;cursor:pointer" '
            f'title="Voir la note">Voir la note ↗</a>'
        )

    def _repl_double(m: re.Match) -> str:
        inner = m.group(1).strip()
        parts = inner.split("|", 1)
        file_name = parts[0].strip()
        display = parts[1].strip() if len(parts) > 1 else file_name
        return _make_link(file_name, display)

    def _repl_single(m: re.Match) -> str:
        inner = m.group(1).strip()
        if not inner or inner.startswith("http") or "<" in inner:
            return m.group(0)
        return _make_link(inner, inner)

    # Traiter [[...]] (double crochet Obsidian) puis [...] (citations simples du LLM)
    # Limite 200 chars pour couvrir les titres longs
    text = re.sub(r"\[\[([^\]]+)\]\]", _repl_double, text)
    text = re.sub(r"(?<!\[)\[([^\]\n<>]{3,200})\](?!\(|\[)", _repl_single, text)
    return text


def _open_note_cb(fp: str) -> None:
    """Callback on_click : mémorise la note à ouvrir, déclenche navigate après rerun."""
    st.session_state.viewing_note = fp
    st.session_state._goto_note = True


def _mermaid_html_chat(code: str, idx: int) -> str:
    """HTML autonome pour rendu Mermaid dans le chat — clic = plein écran scrollable."""
    code_json = json.dumps(code)
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
  <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
  <style>
    * {{ box-sizing:border-box; margin:0; padding:0; }}
    body {{ background:transparent; padding:8px 0; }}
    #out {{ display:flex; justify-content:center; cursor:zoom-in; }}
    #out svg {{ max-width:100%; height:auto; }}
    #err {{ color:#F87171; font-family:monospace; font-size:12px; white-space:pre-wrap; padding:8px; }}

    /* Overlay plein écran */
    #overlay {{
      display:none; position:fixed; inset:0; z-index:9999;
      background:rgba(0,0,0,0.82); overflow:auto;
      cursor:zoom-out;
    }}
    #overlay.open {{ display:block; }}
    #overlay-inner {{
      min-width:100%; min-height:100%;
      display:flex; align-items:flex-start; justify-content:center;
      padding:40px 20px;
    }}
    #overlay-inner svg {{
      max-width:none !important; width:auto; height:auto;
      background:#fff; border-radius:8px; padding:24px;
      box-shadow:0 8px 40px rgba(0,0,0,0.5);
    }}
    #close-btn {{
      position:fixed; top:16px; right:24px; z-index:10000;
      background:#fff; color:#111; border:none; border-radius:50%;
      width:36px; height:36px; font-size:20px; cursor:pointer;
      display:none; align-items:center; justify-content:center;
      box-shadow:0 2px 8px rgba(0,0,0,0.4);
    }}
    #overlay.open ~ #close-btn {{ display:flex; }}
    #hint {{
      font-size:11px; color:#888; text-align:center; margin-top:4px;
      font-family:ui-sans-serif,system-ui,sans-serif;
    }}
  </style>
</head><body>
  <div id="out"></div>
  <div id="hint">🔍 Cliquer pour agrandir</div>
  <div id="err"></div>
  <div id="overlay"><div id="overlay-inner"></div></div>
  <button id="close-btn" title="Fermer">✕</button>
  <script>
    (async function() {{
      const code = {code_json};
      try {{
        mermaid.initialize({{ startOnLoad:false, theme:'neutral', securityLevel:'loose',
                              fontFamily:'ui-sans-serif,system-ui,sans-serif', fontSize:13 }});
        const {{ svg }} = await mermaid.render('mc{idx}', code);
        document.getElementById('out').innerHTML = svg;

        // Rendu haute résolution pour l'overlay (même SVG, taille libre)
        const {{ svg: svgFull }} = await mermaid.render('mc{idx}f', code);

        const overlay = document.getElementById('overlay');
        const inner   = document.getElementById('overlay-inner');
        const closeBtn = document.getElementById('close-btn');

        function openOverlay() {{
          inner.innerHTML = svgFull;
          overlay.classList.add('open');
          closeBtn.style.display = 'flex';
          // Agrandir l'iframe Streamlit pour couvrir l'écran
          try {{
            const frame = window.frameElement;
            if (frame) {{
              frame._origHeight = frame.style.height;
              frame.style.cssText = 'position:fixed;inset:0;width:100vw;height:100vh;z-index:9998;border:none;';
            }}
          }} catch(e) {{}}
        }}
        function closeOverlay() {{
          overlay.classList.remove('open');
          closeBtn.style.display = 'none';
          try {{
            const frame = window.frameElement;
            if (frame && frame._origHeight !== undefined) {{
              frame.style.cssText = '';
              frame.style.height = frame._origHeight || '';
            }}
          }} catch(e) {{}}
        }}

        document.getElementById('out').addEventListener('click', openOverlay);
        overlay.addEventListener('click', function(e) {{
          if (e.target === overlay || e.target === inner) closeOverlay();
        }});
        closeBtn.addEventListener('click', closeOverlay);
        document.addEventListener('keydown', function(e) {{
          if (e.key === 'Escape') closeOverlay();
        }});
      }} catch(e) {{
        document.getElementById('err').textContent = '\u26a0 Mermaid: ' + e.message;
      }}
    }})();
  </script>
</body></html>"""


def _copy_button_html(text: str) -> str:
    """Petit bouton 📋 autonome qui copie le texte brut dans le presse-papier."""
    text_json = json.dumps(text)
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  body{{margin:0;padding:2px 0;background:transparent;display:flex;align-items:center}}
  button{{
    background:none;border:1px solid #d1d5db;border-radius:6px;
    padding:3px 10px;font-size:12px;cursor:pointer;color:#6b7280;
    display:flex;align-items:center;gap:5px;transition:all .15s;
    font-family:ui-sans-serif,system-ui,sans-serif;
  }}
  button:hover{{background:#f3f4f6;border-color:#9ca3af;color:#374151}}
  button.ok{{border-color:#10b981;color:#10b981}}
</style></head><body>
  <button id="b" onclick="copy()">📋 Copier</button>
  <script>
    const txt = {text_json};
    function copy() {{
      const btn = document.getElementById('b');
      (navigator.clipboard
        ? navigator.clipboard.writeText(txt)
        : Promise.resolve(document.execCommand('copy', false,
            (()=>{{const t=document.createElement('textarea');
              t.value=txt;document.body.appendChild(t);t.select();
              document.execCommand('copy');document.body.removeChild(t)}})()))
      ).then(()=>{{
        btn.textContent='✓ Copié';btn.classList.add('ok');
        setTimeout(()=>{{btn.innerHTML='📋 Copier';btn.classList.remove('ok')}},2000);
      }}).catch(()=>{{btn.textContent='⚠ Échec';}});
    }}
  </script>
</body></html>"""


def _render_text_segment(segment: str) -> None:
    """Rend un segment texte avec liens + NER.
    Utilise components.html() si HTML présent (onclick préservé, pas de sanitisation)."""
    if not segment.strip():
        return
    processed = _highlight_ner(_linkify_wikilinks(segment))
    if '<a ' not in processed and '<span ' not in processed:
        st.markdown(processed, unsafe_allow_html=True)
        return
    # Estimation hauteur : nb lignes * 26px + marge
    lines = segment.count('\n') + sum(
        max(1, (len(l) + 79) // 80) for l in segment.split('\n')
    )
    height = max(60, min(1500, lines * 26 + 30))
    components.html(f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/marked@9/marked.min.js"></script>
<style>
:root{{
  --txt:#262730; --bg:transparent;
  --code-bg:#f0f2f6; --quote-color:#6b7280; --quote-border:#d1d5db;
}}
@media(prefers-color-scheme:dark){{
  :root{{--txt:#fafafa; --code-bg:#2d2d3a; --quote-color:#a0a0b0; --quote-border:#4a4a5a;}}
}}
body{{margin:0;padding:4px 0;font-family:ui-sans-serif,system-ui,-apple-system,sans-serif;
     font-size:16px;line-height:1.7;color:var(--txt);background:var(--bg);
     word-wrap:break-word;overflow-x:hidden;}}
p{{margin:0 0 .7em;}}ul,ol{{margin:0 0 .7em 1.4em;padding:0;}}
h1,h2,h3{{margin:.8em 0 .4em;color:var(--txt);}}h4,h5,h6{{margin:.6em 0 .3em;color:var(--txt);}}
code{{background:var(--code-bg);padding:1px 4px;border-radius:3px;font-size:14px;font-family:monospace;color:var(--txt);}}
pre{{background:var(--code-bg);padding:10px;border-radius:6px;overflow-x:auto;color:var(--txt);}}
blockquote{{margin:0 0 .7em;padding:0 0 0 1em;border-left:3px solid var(--quote-border);color:var(--quote-color);}}
strong{{font-weight:700;}}em{{font-style:italic;}}
a{{color:#a78bfa;text-decoration:none;font-weight:600;border-bottom:1px dotted #a78bfa;cursor:pointer;}}
span[title]{{border-radius:3px;padding:1px 4px;}}
</style></head><body id="bd">
<script>
marked.use({{breaks:true,gfm:true}});
const raw={json.dumps(processed)};
document.getElementById('bd').innerHTML=marked.parse(raw);
function resize(){{try{{const h=document.body.scrollHeight;const f=window.frameElement;if(f)f.style.height=(h+10)+'px';}}catch(e){{}}}}
setTimeout(resize,30);setTimeout(resize,200);
</script></body></html>""", height=height, scrolling=False)


def _render_chat_response(text: str) -> None:
    """Rend la réponse dans Streamlit : texte NER-highlighté + blocs Mermaid visuels."""
    # Cleanup accents/émojis dans les blocs Mermaid
    def _clean_block(m: re.Match) -> str:
        return f"```mermaid\n{_clean_mermaid(m.group(1))}\n```"
    text = _MERMAID_SPLIT_RE.sub(_clean_block, text)

    # Découper : indices pairs = texte, indices impairs = code Mermaid
    segments = _MERMAID_SPLIT_RE.split(text)
    mermaid_idx = 0
    for i, segment in enumerate(segments):
        if i % 2 == 0:
            _render_text_segment(segment)
        else:
            lines = segment.strip().splitlines()
            height = max(220, min(600, 120 + len(lines) * 22))
            st.caption("📊 Diagramme Mermaid")
            components.html(_mermaid_html_chat(segment.strip(), mermaid_idx),
                            height=height, scrolling=False)
            mermaid_idx += 1
    # Bouton copier le texte brut (sans HTML)
    components.html(_copy_button_html(text), height=36, scrolling=False)


def _render_response(text: str, sources: list[dict] = []) -> str:
    """Retourne le texte post-traité (cleanup Mermaid + NER) sans rendu Streamlit."""
    def _clean_block(m: re.Match) -> str:
        lang = m.group(1)
        code = m.group(2)
        if "mermaid" in lang.lower():
            code = _clean_mermaid(code)
        return f"```{lang}\n{code}\n```"
    text = re.sub(r"```([^\n]*)\n(.*?)```", _clean_block, text, flags=re.DOTALL)
    return _highlight_ner(text)


# ---- Statut auto-learner (fragment auto-rafraîchi toutes les 5s) ----
@st.fragment(run_every=5)
def _autolearn_live_status():
    import json as _json
    from src.config import settings as _s

    # Compteur notes (recalculé à chaque refresh)
    _notes = svc.chroma.list_notes()
    _user_notes = [n for n in _notes if "/obsirag/" not in n["file_path"].replace("\\", "/") and not n["file_path"].replace("\\", "/").startswith("obsirag/")]
    _user_fps = {n["file_path"] for n in _user_notes}
    _total = len(_user_notes)
    _pf = _s.processed_notes_file
    _processed_map = _json.loads(_pf.read_text(encoding="utf-8")) if _pf.exists() else {}
    _processed = len([fp for fp in _processed_map if fp in _user_fps])
    _insights = len(list(_s.insights_dir.rglob("*.md"))) if _s.insights_dir.exists() else 0
    _synapses = len(list(_s.synapses_dir.rglob("*.md"))) if _s.synapses_dir.exists() else 0

    if _processed < _total:
        st.progress(_processed / _total if _total else 0,
                    text=f"Insights {_processed}/{_total} notes")
        st.caption(f"💡 {_insights} insight(s) · ⚡ {_synapses} synapse(s)")
    else:
        st.caption(f"{_processed}/{_total} notes · 💡 {_insights} insights · ⚡ {_synapses} synapses")

    # Statut traitement en cours
    ps = svc.learner.processing_status
    if ps.get("active"):
        note = ps.get("note", "")
        step = ps.get("step", "")
        st.info(f"⚙️ **Traitement en cours**\n\n📄 *{note}*\n\n`{step}`")
        log_entries = ps.get("log", [])
        if log_entries:
            st.caption("📋 **Journal de traitement**")
            st.code("\n".join(log_entries), language=None)
    else:
        log_entries = ps.get("log", [])
        if log_entries:
            st.success("✅ **Dernier traitement terminé**")
            st.caption("📋 **Journal**")
            st.code("\n".join(log_entries), language=None)
        else:
            try:
                job = svc.learner._scheduler.get_job("autolearn_cycle")
                if job and job.next_run_time:
                    from zoneinfo import ZoneInfo
                    import os
                    tz = ZoneInfo(os.environ.get("TZ", "UTC"))
                    next_run = job.next_run_time.astimezone(tz).strftime("%H:%M:%S")
                    st.caption(f"⏳ Prochain cycle : **{next_run}**")
            except Exception:
                pass

# ---- Sidebar ----
with st.sidebar:
    st.markdown(
        f'<h2 style="display:flex;align-items:center;gap:10px;margin:0">'
        f'<img src="data:image/png;base64,{_icon_b64}" width="96" style="border-radius:4px">'
        f'ObsiRAG</h2>',
        unsafe_allow_html=True,
    )
    st.caption("Votre coffre Obsidian, augmenté par l'IA locale")
    st.divider()

    notes = svc.chroma.list_notes()
    st.metric("Notes indexées", len(notes))
    st.metric("Chunks vectorisés", svc.chroma.count())

    # Compteur + statut auto-learner (auto-rafraîchi toutes les 5s)
    _autolearn_live_status()

    # Progression de l'indexation initiale (thread background)
    idx = svc.indexing_status
    if idx.get("running"):
        total = idx.get("total", 0)
        processed = idx.get("processed", 0)
        current = idx.get("current", "")
        st.progress(processed / total if total else 0, text=f"⏳ Indexation {processed}/{total}")
        if current:
            st.caption(f"…{current[-40:]}" if len(current) > 40 else current)

    llm_ok = svc.llm.is_available()
    st.markdown(f"**Ollama** : {'🟢 Connecté' if llm_ok else '🔴 Non disponible'}")

    # Dernières stats de génération
    if st.session_state.get("last_gen_stats"):
        s = st.session_state.last_gen_stats
        st.divider()
        st.caption("**Dernière génération**")
        c1, c2 = st.columns(2)
        c1.metric("Tokens", s["tokens"])
        c2.metric("Tok/s", f"{s['tps']:.0f}")
        st.caption(
            f"TTFT {s['ttft']:.1f}s · total {s['total']:.1f}s"
        )

    st.divider()

    if st.button("♻️ Re-indexer le coffre", use_container_width=True):
        with st.spinner("Indexation en cours…"):
            idx_stats = svc.indexer.index_vault()
        st.success(
            f"✅ +{idx_stats['added']} ajoutées, "
            f"~{idx_stats['updated']} mises à jour, "
            f"🗑 {idx_stats['deleted']} supprimées"
        )
        st.rerun()

    # ---- Historique des prompts dans la sidebar ----
    if "prompt_history" not in st.session_state:
        st.session_state.prompt_history = []

    st.divider()
    ph_label = f"📜 Prompts ({len(st.session_state.prompt_history)})" if st.session_state.prompt_history else "📜 Historique prompts"
    with st.expander(ph_label, expanded=False):
        if not st.session_state.prompt_history:
            st.caption("Aucun prompt pour l'instant.")
        for _pi, _ph in enumerate(st.session_state.prompt_history):
            _col_t, _col_b = st.columns([5, 1])
            with _col_t:
                st.caption(_ph[:80] + ("…" if len(_ph) > 80 else ""))
            with _col_b:
                if st.button("↩", key=f"ph_{_pi}", help="Réutiliser"):
                    st.session_state._pending_query = _ph
                    st.rerun()

# ---- Zone de chat ----
st.title("💬 Chat avec votre coffre")

if not llm_ok:
    st.warning(
        "⚠️ Ollama n'est pas accessible. "
        "Vérifiez qu'Ollama est démarré et que l'URL est correcte dans `.env`."
    )

if "messages" not in st.session_state:
    st.session_state.messages = []

# Bridge invisible : écoute localStorage 'obsirag_open_note' (wikilinks du chat)
_bridge_val = _note_bridge(default=None, key="chat_note_bridge")
if _bridge_val:
    st.session_state.viewing_note = _bridge_val
    st.switch_page("pages/4_Note.py")

# Navigation différée : déclenchée par on_click des boutons 📖
if st.session_state.pop("_goto_note", False):
    st.switch_page("pages/4_Note.py")

# Affiche l'historique
for mi, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            _render_chat_response(msg["content"])
        else:
            st.markdown(msg["content"])
        if msg.get("stats"):
            s = msg["stats"]
            st.caption(
                f"⚡ {s['tokens']} tokens · TTFT {s['ttft']:.1f}s · "
                f"{s['total']:.1f}s total · {s['tps']:.0f} tok/s"
            )
        if msg.get("sources"):
            with st.expander(f"📚 {len(msg['sources'])} source(s)", expanded=False):
                for hi, src in enumerate(msg["sources"]):
                    _m = src.get("metadata", {})
                    title = _m.get("note_title", _m.get("file_path", ""))
                    section = _m.get("section_title", "")
                    fp = _m.get("file_path", "")
                    col_info, col_btn = st.columns([5, 1])
                    with col_info:
                        st.markdown(
                            f"**{title}**"
                            f"{'  —  ' + section if section else ''}  \n"
                            f"*{_m.get('date_modified','')[:10]}* · Score `{src.get('score',0):.2f}`"
                        )
                        st.caption(src.get("text", "")[:300] + "…")
                    with col_btn:
                        if fp:
                            st.button("📖", key=f"hist_src_{mi}_{hi}_{fp[-20:]}",
                                      help="Ouvrir la note",
                                      on_click=_open_note_cb, args=(fp,))
                    st.divider()

# Suggestions de démarrage
if not st.session_state.messages:
    st.markdown("#### Exemples de questions")
    cols = st.columns(2)
    suggestions = [
        "Quelles sont mes dernières notes ? Fais une synthèse de la semaine.",
        "Quelles sont les notes où je parle de machine learning ?",
        "Fais le point sur ce que j'ai appris ce mois-ci.",
        "Quelles connexions vois-tu entre mes notes récentes ?",
    ]
    for i, sug in enumerate(suggestions):
        with cols[i % 2]:
            if st.button(sug, use_container_width=True, key=f"sug_{i}"):
                st.session_state._pending_query = sug
                st.rerun()

pending = st.session_state.pop("_pending_query", None)

user_input = st.chat_input("Posez une question sur votre coffre…") or pending

if user_input:
    if not llm_ok:
        st.error("Ollama n'est pas disponible.")
        st.stop()

    # Mémorise dans l'historique sidebar (dédupliqué, max 20, en tête de liste)
    ph = st.session_state.prompt_history
    if user_input not in ph:
        ph.insert(0, user_input)
        st.session_state.prompt_history = ph[:20]

    svc.learner.log_user_query(user_input)

    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    history = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages[:-1]
    ]

    with st.chat_message("assistant"):
        # Zone de statut (mise à jour en temps réel)
        status = st.empty()
        response_area = st.empty()

        full_response = ""
        token_count = 0
        first_token_time: float | None = None
        sources: list = []
        gen_stats: dict = {}

        t0 = time.perf_counter()

        try:
            # Phase 1 — récupération RAG
            status.markdown("🔍 *Recherche dans le coffre…*")
            stream, sources = svc.rag.query_stream(user_input, chat_history=history)

            # Progression des notes dans le contexte
            seen: list[str] = []
            for src in sources:
                title = src.get("metadata", {}).get("note_title", "")
                if title and title not in seen:
                    seen.append(title)
            for i, note in enumerate(seen, 1):
                status.markdown(f"📄 *Note {i} sur {len(seen)} — {note}*")
                time.sleep(0.12)

            # Phase 2 — génération Ollama
            ctx_chars = sum(len(s.get("text", "")) for s in sources)
            ctx_notes = len(seen)
            status.markdown(
                f"⏳ *Ollama charge le contexte… "
                f"{ctx_notes} note{'s' if ctx_notes > 1 else ''} · "
                f"~{ctx_chars:,} caractères*"
            )

            for token in stream:
                if first_token_time is None:
                    first_token_time = time.perf_counter()
                    ttft = first_token_time - t0
                    status.markdown(f"⚡ *Génération en cours · premier token en {ttft:.1f}s*")

                full_response += token
                token_count += 1
                response_area.markdown(full_response + " ▌")

                # Mise à jour du compteur toutes les 15 tokens
                if token_count % 15 == 0:
                    elapsed = time.perf_counter() - t0
                    tps = token_count / max(0.01, time.perf_counter() - first_token_time)
                    status.markdown(
                        f"⚡ *{token_count} tokens · {elapsed:.1f}s · {tps:.0f} tok/s*"
                    )

            # Affichage final propre — Mermaid visuel + highlight NER
            response_area.empty()
            _render_chat_response(full_response)
            total = time.perf_counter() - t0
            ttft_val = (first_token_time - t0) if first_token_time else total
            tps_val = token_count / max(0.01, total - ttft_val)

            gen_stats = {
                "tokens": token_count,
                "ttft": ttft_val,
                "total": total,
                "tps": tps_val,
            }
            status.caption(
                f"✅ {token_count} tokens · "
                f"TTFT {ttft_val:.1f}s · "
                f"{total:.1f}s total · "
                f"{tps_val:.0f} tok/s"
            )

        except Exception as exc:
            full_response = f"❌ Erreur : {exc}"
            response_area.error(full_response)
            status.empty()
            sources = []

        # Sources
        if sources:
            with st.expander(f"📚 {len(sources)} source(s)", expanded=False):
                for i, src in enumerate(sources[:8]):
                    _m = src.get("metadata", {})
                    title = _m.get("note_title", _m.get("file_path", ""))
                    section = _m.get("section_title", "")
                    date = _m.get("date_modified", "")[:10]
                    score = src.get("score", 0)
                    fp = _m.get("file_path", "")

                    col_info, col_btn = st.columns([5, 1])
                    with col_info:
                        st.markdown(
                            f"**{title}**"
                            f"{'  —  ' + section if section else ''}  \n"
                            f"*{date}* · Score `{score:.2f}`"
                        )
                        st.caption(src.get("text", "")[:300] + "…")
                    with col_btn:
                        if fp:
                            st.button("📖", key=f"open_src_{i}_{fp[-20:]}",
                                      help="Ouvrir la note",
                                      on_click=_open_note_cb, args=(fp,))
                    st.divider()

    # Sauvegarde dans l'historique et les stats sidebar
    st.session_state.messages.append({
        "role": "assistant",
        "content": full_response,
        "sources": sources[:8],
        "stats": gen_stats,
    })
    if gen_stats:
        st.session_state.last_gen_stats = gen_stats

if st.session_state.messages:
    if st.button("🗑 Effacer l'historique", key="clear_history"):
        st.session_state.messages = []
        st.session_state.pop("last_gen_stats", None)
        st.rerun()
