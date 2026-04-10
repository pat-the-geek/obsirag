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
from src.ui.theme import inject_theme, render_theme_toggle

# ---- Configuration de la page ----
_icon = str(Path(__file__).parent / "static" / "favicon-32x32.png")
_icon_b64 = base64.b64encode((Path(__file__).parent / "static" / "android-chrome-512x512.png").read_bytes()).decode()
st.set_page_config(
    page_title="ObsiRAG",
    page_icon=_icon,
    layout="wide",
)
inject_theme()

svc = get_services()

# Pending query (depuis sidebar historique ou suggestions) — capturé dès le début
if "prompt_history" not in st.session_state:
    st.session_state.prompt_history = []
_pending = st.session_state.pop("_pending_query", None)


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


_MERMAID_SPLIT_RE = re.compile(r"```mermaid\s*\n(.*?)```", re.DOTALL)


def _open_note_cb(fp: str) -> None:
    """Callback on_click : mémorise la note à ouvrir, déclenche navigate après rerun."""
    st.session_state.viewing_note = fp
    st.session_state.note_nav_request = fp
    st.session_state._goto_note = True


def _render_user_bubble(text: str) -> None:
    """Rendu d'un message user : bulle alignée à droite, avatar cerveau violet ObsiRAG."""
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    _brain_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="64" height="64">'
        '<g fill="none" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M 200 310 C 175 310 155 295 148 272 C 138 265 130 252 130 237 C 130 222 138 210 150 203 C 150 185 160 170 175 163 C 175 148 185 136 200 132 C 210 128 220 128 230 132 C 238 120 252 114 265 116 L 265 310 Z" fill="#7c3aed" opacity="0.95"/>'
        '<path d="M 312 310 C 337 310 357 295 364 272 C 374 265 382 252 382 237 C 382 222 374 210 362 203 C 362 185 352 170 337 163 C 337 148 327 136 312 132 C 302 128 292 128 282 132 C 274 120 260 114 247 116 L 247 310 Z" fill="#6d28d9" opacity="0.95"/>'
        '<line x1="256" y1="116" x2="256" y2="310" stroke-width="4" stroke="rgba(0,0,0,0.3)"/>'
        '<path d="M 220 310 C 220 330 230 342 256 345 C 282 342 292 330 292 310" fill="#7c3aed"/>'
        '<path d="M 175 175 C 165 185 162 200 168 212" stroke="#a78bfa" stroke-width="5"/>'
        '<path d="M 155 220 C 150 235 155 250 165 258" stroke="#a78bfa" stroke-width="5"/>'
        '<path d="M 165 270 C 162 282 168 295 180 300" stroke="#a78bfa" stroke-width="5"/>'
        '<path d="M 200 148 C 192 158 190 172 196 182" stroke="#a78bfa" stroke-width="5"/>'
        '<path d="M 215 132 C 210 145 212 160 220 168" stroke="#c4b5fd" stroke-width="4"/>'
        '<path d="M 195 210 C 185 222 185 238 192 248" stroke="#a78bfa" stroke-width="5"/>'
        '<path d="M 198 268 C 190 278 190 292 198 300" stroke="#a78bfa" stroke-width="4"/>'
        '<path d="M 337 175 C 347 185 350 200 344 212" stroke="#a78bfa" stroke-width="5"/>'
        '<path d="M 357 220 C 362 235 357 250 347 258" stroke="#a78bfa" stroke-width="5"/>'
        '<path d="M 347 270 C 350 282 344 295 332 300" stroke="#a78bfa" stroke-width="5"/>'
        '<path d="M 312 148 C 320 158 322 172 316 182" stroke="#a78bfa" stroke-width="5"/>'
        '<path d="M 297 132 C 302 145 300 160 292 168" stroke="#c4b5fd" stroke-width="4"/>'
        '<path d="M 317 210 C 327 222 327 238 320 248" stroke="#a78bfa" stroke-width="5"/>'
        '<path d="M 314 268 C 322 278 322 292 314 300" stroke="#a78bfa" stroke-width="4"/>'
        '<ellipse cx="210" cy="158" rx="18" ry="10" fill="#c4b5fd" opacity="0.25" transform="rotate(-30 210 158)"/>'
        '<ellipse cx="302" cy="158" rx="18" ry="10" fill="#c4b5fd" opacity="0.15" transform="rotate(30 302 158)"/>'
        '</g>'
        '<ellipse cx="256" cy="225" rx="130" ry="110" fill="none" stroke="#7c3aed" stroke-width="1.5" opacity="0.3"/>'
        '</svg>'
    )
    st.markdown(
        f'<div style="display:flex;justify-content:flex-end;align-items:flex-start;'
        f'gap:8px;margin:6px 0;padding:0 2px;width:100%">'
        f'<div style="max-width:75%;'
        f'background:var(--user-bubble-bg,#264f78);'
        f'border:1px solid var(--user-bubble-border,#569cd6);'
        f'border-radius:14px 4px 14px 14px;'
        f'padding:10px 14px;'
        f'color:var(--text-color,#d4d4d4);'
        f'font-size:0.95rem;line-height:1.5;word-break:break-word">'
        f'{escaped}</div>'
        f'<div style="flex-shrink:0;margin-top:1px;filter:drop-shadow(0 1px 3px rgba(124,58,237,0.4))">'
        f'{_brain_svg}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _mermaid_fullscreen_html(code: str, idx: int) -> str:
    """Page HTML autonome plein-écran : zoom/pan, thème auto dark/light."""
    code_json = json.dumps(code)
    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Diagramme — ObsiRAG</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/svg-pan-zoom@3.6.1/dist/svg-pan-zoom.min.js"></script>
<style>
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  html,body{{width:100%;height:100%;overflow:hidden;background:#1e1e1e;color:#d4d4d4}}
  @media(prefers-color-scheme:light){{html,body{{background:#ffffff;color:#1a1a1a}}}}
  #toolbar{{
    position:fixed;top:0;left:0;right:0;z-index:100;
    display:flex;align-items:center;gap:8px;padding:7px 16px;
    background:rgba(37,37,38,0.95);border-bottom:1px solid #3e3e42;
    font-family:'Consolas','Menlo',monospace;font-size:12px;color:#d4d4d4;
  }}
  @media(prefers-color-scheme:light){{
    #toolbar{{background:rgba(247,247,247,0.97);border-color:#e2e2e2;color:#1a1a1a}}
  }}
  #toolbar .logo{{font-weight:700;color:#569cd6;margin-right:4px}}
  @media(prefers-color-scheme:light){{#toolbar .logo{{color:#0066b8}}}}
  #toolbar .hint{{opacity:0.45;font-size:10px;margin-left:auto}}
  #container{{position:absolute;inset:0;top:40px}}
  #container svg{{position:absolute;inset:0;width:100%;height:100%;display:block}}
  #err{{position:fixed;top:50px;left:50%;transform:translateX(-50%);
        color:#f87171;font-size:12px;z-index:30;text-align:center}}
  #loading{{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;
            background:#1e1e1e;z-index:50;font-size:13px;opacity:0.7}}
  @media(prefers-color-scheme:light){{#loading{{background:#ffffff}}}}
</style>
</head>
<body>
<div id="toolbar">
  <span class="logo">ObsiRAG</span>
  <span style="opacity:.35">—</span>
  <span>Diagramme</span>
  <span class="hint">🖱 molette = zoom &nbsp;·&nbsp; glisser = déplacer &nbsp;·&nbsp; dbl-clic = ajuster</span>
</div>
<div id="loading">Rendu en cours…</div>
<div id="container"></div>
<div id="err"></div>
<script>
(function(){{
  'use strict';
  var CODE={code_json};
  var isDark=!window.matchMedia('(prefers-color-scheme:light)').matches;
  var TV_LIGHT={{
    fontFamily:"system-ui,-apple-system,'Segoe UI',Helvetica,Arial,sans-serif",fontSize:'14px',
    background:'#ffffff',
    primaryColor:'#dbeafe',primaryTextColor:'#1a1a1a',
    primaryBorderColor:'#0066b8',lineColor:'#0066b8',
    secondaryColor:'#ffedd5',tertiaryColor:'#ede9fe',
    mainBkg:'#dbeafe',nodeBorder:'#0066b8',
    clusterBkg:'#f0f4ff',clusterBorder:'#d97706',
    titleColor:'#7c3aed',
    edgeLabelBackground:'#ffffff'
  }};
  var TV_DARK={{
    fontFamily:"system-ui,-apple-system,'Segoe UI',Helvetica,Arial,sans-serif",fontSize:'14px',
    background:'#0d1117',
    primaryColor:'#1f3a5f',primaryTextColor:'#e6edf3',
    primaryBorderColor:'#58a6ff',lineColor:'#58a6ff',
    secondaryColor:'#431407',tertiaryColor:'#2d1b52',
    mainBkg:'#1f3a5f',nodeBorder:'#58a6ff',
    clusterBkg:'#161b22',clusterBorder:'#a371f7',
    titleColor:'#a371f7',
    edgeLabelBackground:'#0d1117'
  }};

  mermaid.initialize({{
    startOnLoad:false,securityLevel:'loose',theme:'base',
    themeVariables:isDark?TV_DARK:TV_LIGHT
  }});

  mermaid.render('diag_{idx}',CODE).then(function(r){{
    var loading=document.getElementById('loading');
    if(loading)loading.remove();
    var container=document.getElementById('container');
    container.innerHTML=r.svg;
    var svgEl=container.querySelector('svg');
    if(!svgEl)return;
    if(!svgEl.getAttribute('viewBox'))
      svgEl.setAttribute('viewBox','0 0 '+(parseFloat(svgEl.getAttribute('width'))||800)+' '+(parseFloat(svgEl.getAttribute('height'))||600));
    svgEl.removeAttribute('width');svgEl.removeAttribute('height');
    svgEl.style.cssText='position:absolute;inset:0;width:100%;height:100%;display:block;';
    setTimeout(function(){{
      var pz=svgPanZoom(svgEl,{{
        zoomEnabled:true,panEnabled:true,controlIconsEnabled:true,
        fit:true,center:true,minZoom:0.02,maxZoom:80,zoomScaleSensitivity:0.3,dblClickZoomEnabled:false
      }});
      pz.resize();pz.fit();pz.center();
      window.addEventListener('resize',function(){{pz.resize();pz.fit();pz.center();}});
      document.addEventListener('dblclick',function(e){{if(!e.target.closest('#toolbar')){{pz.resize();pz.fit();pz.center();}}}})
    }},120);
  }}).catch(function(e){{
    var loading=document.getElementById('loading');
    if(loading)loading.remove();
    document.getElementById('err').textContent='\u26a0 '+e.message;
  }});
}})();
</script>
</body>
</html>"""


def _mermaid_html_chat(code: str, idx: int) -> str:
    """Preview Mermaid inline dans le chat — thème auto, clic = plein écran via postMessage."""
    code_json = json.dumps(code)
    # HTML de la page fullscreen encodé en base64 pour contourner les restrictions CSP sur blob:
    import base64
    fullscreen_b64 = base64.b64encode(
        _mermaid_fullscreen_html(code, idx).encode("utf-8")
    ).decode("ascii")
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<style>
  *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:transparent;padding:2px 0}}
  #out{{display:flex;justify-content:center;cursor:zoom-in;border-radius:6px;overflow:hidden}}
  #out svg{{max-width:100%;height:auto;border-radius:6px}}
  #err{{color:#F87171;font-family:monospace;font-size:11px;white-space:pre-wrap;padding:4px}}
  #hint{{font-size:10px;text-align:center;margin-top:4px;opacity:0.45;
         font-family:'Consolas','Courier New',monospace}}
</style>
</head><body>
<div id="out"></div>
<div id="hint">🔍 Cliquer pour plein écran</div>
<div id="err"></div>
<script>
(function(){{
  var CODE={code_json};
  var FS_B64="{fullscreen_b64}";
  var isDark=!window.matchMedia('(prefers-color-scheme:light)').matches;
  var TV_LIGHT={{
    fontFamily:"system-ui,-apple-system,'Segoe UI',Helvetica,Arial,sans-serif",fontSize:'13px',
    background:'#ffffff',
    primaryColor:'#dbeafe',primaryTextColor:'#1a1a1a',primaryBorderColor:'#0066b8',lineColor:'#0066b8',
    secondaryColor:'#ffedd5',tertiaryColor:'#ede9fe',mainBkg:'#dbeafe',
    nodeBorder:'#0066b8',clusterBkg:'#f0f4ff',clusterBorder:'#d97706',titleColor:'#7c3aed',
    edgeLabelBackground:'#ffffff'
  }};
  var TV_DARK={{
    fontFamily:"system-ui,-apple-system,'Segoe UI',Helvetica,Arial,sans-serif",fontSize:'13px',
    background:'#0d1117',
    primaryColor:'#1f3a5f',primaryTextColor:'#e6edf3',primaryBorderColor:'#58a6ff',lineColor:'#58a6ff',
    secondaryColor:'#431407',tertiaryColor:'#2d1b52',mainBkg:'#1f3a5f',
    nodeBorder:'#58a6ff',clusterBkg:'#161b22',clusterBorder:'#a371f7',titleColor:'#a371f7',
    edgeLabelBackground:'#0d1117'
  }};
  mermaid.initialize({{startOnLoad:false,securityLevel:'loose',theme:'base',
    themeVariables:isDark?TV_DARK:TV_LIGHT}});
  mermaid.render('prev_{idx}',CODE).then(function(r){{
    document.getElementById('out').innerHTML=r.svg;
  }}).catch(function(e){{
    document.getElementById('err').textContent='\u26a0 '+e.message;
  }});
  function openFullscreen(){{
    try{{
      var html=atob(FS_B64);
      var win=window.open('','_blank');
      if(!win){{alert('Autorisez les popups pour cette page.');return;}}
      win.document.open();
      win.document.write(html);
      win.document.close();
    }}catch(e){{
      console.error('Fullscreen error',e);
    }}
  }}
  document.getElementById('out').addEventListener('click',openFullscreen);
}})();
</script>
</body></html>"""
def _render_chat_response(text: str, *, placeholder=None) -> None:
    """
    Rend la réponse finale du chat.
    - Si placeholder fourni ET pas de Mermaid : met à jour en place (pas de slot vide).
    - Sinon : st.markdown dans le contexte courant.
    """
    has_mermaid = bool(_MERMAID_SPLIT_RE.search(text))

    if not has_mermaid:
        # Cas le plus fréquent : rendu simple, mise à jour en place du placeholder
        if placeholder is not None:
            placeholder.markdown(text)
        else:
            st.markdown(text)
        return

    # Cas Mermaid : vider le placeholder et rendre dans le contexte parent
    if placeholder is not None:
        placeholder.empty()

    segments = _MERMAID_SPLIT_RE.split(text)
    blocks: list[tuple[str, str]] = []
    text_accum: list[str] = []
    for i, segment in enumerate(segments):
        if i % 2 == 0:
            text_accum.append(segment)
        else:
            if text_accum:
                blocks.append(("text", "\n".join(text_accum)))
                text_accum = []
            blocks.append(("mermaid", _clean_mermaid(segment.strip())))
    if text_accum:
        blocks.append(("text", "\n".join(text_accum)))

    mermaid_idx = 0
    for btype, content in blocks:
        if btype == "text":
            if content.strip():
                st.markdown(content)
        else:
            lines = content.splitlines()
            height = max(220, min(600, 120 + len(lines) * 22))
            st.caption("📊 Diagramme Mermaid")
            components.html(_mermaid_html_chat(content, mermaid_idx),
                            height=height, scrolling=False)
            mermaid_idx += 1





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
    try:
        _processed_map = _json.loads(_pf.read_text(encoding="utf-8")) if _pf.exists() else {}
    except Exception:
        _processed_map = {}
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
                if st.button("↩", key=f"ph_{_pi}", help="Réutiliser",
                             on_click=lambda p=_ph: st.session_state.update({"_pending_query": p})):
                    pass

    render_theme_toggle()

# ---- Sauvegarde de conversation ----

def _save_conversation() -> None:
    """Génère un nom de fichier via LLM et sauvegarde la conversation en Markdown."""
    messages = st.session_state.get("messages", [])
    if not messages:
        st.warning("Aucun message à sauvegarder.")
        return

    # Résumé des échanges pour le LLM (questions utilisateur seulement)
    user_turns = [m["content"] for m in messages if m["role"] == "user"]
    summary_input = "\n".join(f"- {q[:200]}" for q in user_turns[:5])

    # Génération du titre via LLM
    title = "conversation"
    try:
        prompt = (
            "Voici les questions posées lors d'une conversation avec un assistant IA :\n\n"
            f"{summary_input}\n\n"
            "Propose UN titre court (4 à 8 mots) en français, sans ponctuation, "
            "qui résume le sujet principal de cette conversation. "
            "Réponds uniquement avec le titre, rien d'autre."
        )
        title = svc.llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=30,
            operation="save_conversation",
        ).strip().strip('"').strip("'")
    except Exception:
        pass

    # Slug du titre : même logique que les insights
    safe_title = unicodedata.normalize("NFD", title)
    safe_title = "".join(c for c in safe_title if unicodedata.category(c) != "Mn")
    safe_title = re.sub(r"[^\w\s-]", "", safe_title).strip()
    safe_title = re.sub(r"[\s_]+", "-", safe_title)[:60]

    date_str = datetime.now().strftime("%Y-%m")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"{safe_title}_{timestamp}.md"

    from src.config import settings as _settings
    conv_dir = _settings.conversations_dir / date_str
    conv_dir.mkdir(parents=True, exist_ok=True)
    out_path = conv_dir / filename

    # Construction du Markdown
    lines = [
        "---",
        "tags:",
        "  - conversation",
        "  - obsirag",
        "---",
        "",
        f"# {title}",
        "",
        f"**Date :** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
        f"**Questions :** {len(user_turns)}  ",
        "",
        "---",
        "",
    ]
    for msg in messages:
        if msg["role"] == "user":
            lines += [f"## 🧑 {msg['content'][:120]}", "", f"> {msg['content']}", ""]
        else:
            lines += ["### 🤖 Réponse", "", msg["content"], ""]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    st.success(f"✅ Conversation sauvegardée : `obsirag/conversations/{date_str}/{filename}`")


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
    st.session_state.note_nav_request = _bridge_val
    st.switch_page("pages/4_Note.py")

# Navigation différée : déclenchée par on_click des boutons 📖
if st.session_state.pop("_goto_note", False):
    st.switch_page("pages/4_Note.py")

# Affiche l'historique
for mi, msg in enumerate(st.session_state.messages):
    if msg["role"] == "user":
        _render_user_bubble(msg["content"])
        continue
    with st.chat_message("assistant"):
        _render_chat_response(msg["content"], placeholder=None)
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
                    fp = _m.get("file_path", "")
                    col_info, col_btn = st.columns([8, 1])
                    with col_info:
                        st.caption(
                            f"**{title}** · {_m.get('date_modified','')[:10]}"
                            f" · Score `{src.get('score',0):.2f}`"
                        )
                    with col_btn:
                        if fp:
                            st.button("📖", key=f"hist_src_{mi}_{hi}_{fp[-20:]}",
                                      help="Ouvrir la note",
                                      on_click=_open_note_cb, args=(fp,))

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

pending = _pending

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
    _render_user_bubble(user_input)

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
                title = (src.get("metadata") or {}).get("note_title", "")
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

            # Affichage final propre (met à jour response_area en place si pas de Mermaid)
            _render_chat_response(full_response, placeholder=response_area)
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
                    _m = src.get("metadata") or {}
                    title = _m.get("note_title", _m.get("file_path", ""))
                    fp = _m.get("file_path", "")
                    col_info, col_btn = st.columns([8, 1])
                    with col_info:
                        st.caption(
                            f"**{title}** · {_m.get('date_modified','')[:10]}"
                            f" · Score `{src.get('score',0):.2f}`"
                        )
                    with col_btn:
                        if fp:
                            st.button("📖", key=f"open_src_{i}_{fp[-20:]}",
                                      help="Ouvrir la note",
                                      on_click=_open_note_cb, args=(fp,))

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
    col_clear, col_save = st.columns([1, 1])
    with col_clear:
        if st.button("🗑 Effacer l'historique", key="clear_history", use_container_width=True):
            st.session_state.messages = []
            st.session_state.pop("last_gen_stats", None)
            st.rerun()
    with col_save:
        if st.button("💾 Sauvegarder cette conversation", key="save_conv", use_container_width=True):
            _save_conversation()
