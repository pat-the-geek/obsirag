"""
ObsiRAG — Page principale : Chat
"""
import base64
import re
import time
import unicodedata
from datetime import datetime

from pathlib import Path

import streamlit as st

from src.ui.services_cache import get_services

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
    return "\n".join(lines)


_NER_COLORS = {
    "persons":   ("#d4e8ff", "#1a4a7a"),   # bleu
    "orgs":      ("#d4f5e8", "#1a5c3a"),   # vert
    "locations": ("#fff3d4", "#7a5200"),   # orange
    "misc":      ("#f0d4ff", "#5a1a7a"),   # violet
}


def _highlight_ner(text: str, sources: list[dict]) -> str:
    """Entoure les entités NER trouvées dans les sources avec du HTML coloré."""
    # Collecter toutes les entités
    entities: dict[str, str] = {}  # nom -> catégorie
    for src in sources:
        m = src.get("metadata", {})
        for cat in ("persons", "orgs", "locations", "misc"):
            raw = m.get(f"ner_{cat}", "")
            if not raw:
                continue
            for ent in raw.split(","):
                ent = ent.strip()
                if len(ent) >= 3:
                    entities[ent] = cat
    if not entities:
        return text

    # Trier par longueur décroissante pour éviter les chevauchements
    sorted_ents = sorted(entities.keys(), key=len, reverse=True)

    # Séparer les blocs code/mermaid pour ne pas les modifier
    parts = re.split(r"(```.*?```)", text, flags=re.DOTALL)
    result_parts = []
    for part in parts:
        if part.startswith("```"):
            result_parts.append(part)
            continue
        for ent in sorted_ents:
            cat = entities[ent]
            bg, fg = _NER_COLORS.get(cat, ("#eeeeee", "#333333"))
            label = {"persons": "👤", "orgs": "🏢", "locations": "📍", "misc": "🔖"}.get(cat, "")
            span = (
                f'<span style="background:{bg};color:{fg};border-radius:3px;'
                f'padding:1px 4px;font-weight:600" '
                f'title="{cat}">{ent}</span>'
            )
            part = re.sub(rf"\b{re.escape(ent)}\b", span, part)
        result_parts.append(part)
    return "".join(result_parts)


def _render_response(text: str, sources: list[dict]) -> str:
    """Post-traite la réponse : cleanup Mermaid + highlight NER."""
    # Cleanup blocs Mermaid
    def _clean_block(m: re.Match) -> str:
        lang = m.group(1)
        code = m.group(2)
        if "mermaid" in lang.lower():
            code = _clean_mermaid(code)
        return f"```{lang}\n{code}\n```"

    text = re.sub(r"```([^\n]*)\n(.*?)```", _clean_block, text, flags=re.DOTALL)
    # Highlight NER
    text = _highlight_ner(text, sources)
    return text


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

# ---- Zone de chat ----
st.title("💬 Chat avec votre coffre")

if not llm_ok:
    st.warning(
        "⚠️ Ollama n'est pas accessible. "
        "Vérifiez qu'Ollama est démarré et que l'URL est correcte dans `.env`."
    )

if "messages" not in st.session_state:
    st.session_state.messages = []

# Affiche l'historique
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            rendered_hist = _render_response(msg["content"], msg.get("sources", []))
            st.markdown(rendered_hist, unsafe_allow_html=True)
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
                        if fp and st.button("📖", key=f"hist_src_{id(msg)}_{hi}", help="Ouvrir la note"):
                            st.session_state.viewing_note = fp
                            st.switch_page("pages/4_Note.py")
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

            # Affichage final propre — cleanup Mermaid + highlight NER
            rendered = _render_response(full_response, sources)
            response_area.markdown(rendered, unsafe_allow_html=True)
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
                        if fp and st.button("📖", key=f"open_src_{i}_{fp[:20]}", help="Ouvrir la note"):
                            st.session_state.viewing_note = fp
                            st.switch_page("pages/4_Note.py")
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
