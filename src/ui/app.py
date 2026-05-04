"""
ObsiRAG — Page principale : Chat
"""
import html
import inspect
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import streamlit as st
from loguru import logger

from src.ui.services_cache import get_services
from src.ui.chat_navigation import (
    append_loaded_conversation,
    build_chat_navigation_entries,
    build_conversation_source_entries,
    filter_chat_navigation_entries,
    filter_saved_conversations,
    load_saved_conversation,
    list_saved_conversations,
    source_identity_key,
)
from src.ui.chat_sessions import (
    create_new_thread,
    create_thread_from_messages,
    delete_thread,
    ensure_chat_state,
    get_current_thread,
    list_thread_summaries,
    resolve_active_thread_messages,
    switch_thread,
    update_current_thread,
)
from src.ui.components.note_bridge_component import note_bridge as _note_bridge
from src.ui.chat_mermaid import build_mermaid_chat_preview_html, estimate_chat_mermaid_height
from src.ui.mermaid_streamlit import MERMAID_SPLIT_RE, build_streamlit_chat_blocks
from src.ui.chat_ui_fragments import (
    build_cited_source_row_html,
    build_generation_status_caption,
    build_message_stats_caption,
    build_primary_source_html,
    build_source_entry_html,
    build_user_bubble_html,
)
from src.ui.html_embed import render_html_document
from src.ui.note_badges import render_note_badge
from src.ui.path_resolver import resolve_vault_path
from src.ui.chat_view_models import (
    build_generation_summary_caption,
    build_navigation_meta,
    build_navigation_turn_title,
    build_saved_conversation_meta,
    build_saved_conversation_title,
    build_web_sources_markdown,
)
from src.ui.runtime_state_store import load_processed_notes_map, load_processing_status
from src.ui.theme import inject_theme, render_theme_toggle
from src.ui.side_menu import render_mobile_main_menu, render_side_menu
from src.ai.web_search import (
    build_query_overview_sync,
    enrich_sync,
    is_not_in_vault,
    save_chat_enrichment_insight,
)
from src.config import settings
from src.ui.runtime_state_store import load_chat_threads_state, save_chat_threads_state

# ---- Configuration de la page ----
_icon = str(Path(__file__).parent / "static" / "favicon-32x32.png")
st.set_page_config(
    page_title="ObsiRAG",
    page_icon=_icon,
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()
render_mobile_main_menu()
# Ajout à l'historique navigation
HISTO_KEY = "obsirag_historique"
st.session_state.setdefault(HISTO_KEY, [])
if not st.session_state[HISTO_KEY] or st.session_state[HISTO_KEY][-1] != "Chat":
    st.session_state[HISTO_KEY].append("Chat")

svc = get_services()

if "chat_threads_state" not in st.session_state:
    st.session_state.chat_threads_state = load_chat_threads_state(settings.chat_threads_state_file)

# Pending query (depuis sidebar historique ou suggestions) — capturé dès le début
_pending = st.session_state.pop("_pending_query", None)
# Pending web search — déclenché par le bouton "Rechercher sur le web"
_pending_web = st.session_state.pop("_pending_web_query", None)
st.session_state.setdefault("messages", [])


def _restore_active_chat_thread(*, force: bool = False) -> None:
    chat_state = ensure_chat_state(st.session_state.get("chat_threads_state"))
    current_thread = get_current_thread(chat_state)
    st.session_state.chat_threads_state = chat_state
    thread_messages = list(current_thread.get("messages", []))
    current_messages = list(st.session_state.get("messages", []))

    # En simple rerun, conserver l'historique visible s'il est plus riche qu'un
    # snapshot de thread potentiellement en retard. Les remplacements explicites
    # passent par les callbacks de changement de fil ou de chargement.
    restored_messages = resolve_active_thread_messages(
        thread_messages=thread_messages,
        current_messages=current_messages,
        force=force,
    )
    st.session_state.messages = restored_messages
    if restored_messages != thread_messages:
        chat_state = update_current_thread(
            chat_state,
            messages=restored_messages,
            draft=str(current_thread.get("draft", "")),
            title=str(current_thread.get("title") or ""),
            last_gen_stats=dict(current_thread.get("last_gen_stats", {})),
        )
        st.session_state.chat_threads_state = chat_state
        save_chat_threads_state(settings.chat_threads_state_file, chat_state)
    st.session_state["chat_thread_draft"] = str(current_thread.get("draft", ""))
    if current_thread.get("last_gen_stats"):
        st.session_state.last_gen_stats = dict(current_thread.get("last_gen_stats", {}))
    else:
        st.session_state.pop("last_gen_stats", None)


def _persist_active_chat_thread(title: str | None = None) -> None:
    chat_state = update_current_thread(
        st.session_state.get("chat_threads_state"),
        messages=list(st.session_state.get("messages", [])),
        draft=st.session_state.get("chat_thread_draft", ""),
        title=title,
        last_gen_stats=st.session_state.get("last_gen_stats", {}),
    )
    st.session_state.chat_threads_state = chat_state
    save_chat_threads_state(settings.chat_threads_state_file, chat_state)


def _save_chat_draft() -> None:
    _persist_active_chat_thread()


def _create_chat_thread_cb() -> None:
    _persist_active_chat_thread()
    chat_state = create_new_thread(st.session_state.get("chat_threads_state"))
    st.session_state.chat_threads_state = chat_state
    _restore_active_chat_thread(force=True)
    st.session_state.pop("last_gen_stats", None)


def _switch_chat_thread_cb(thread_id: str) -> None:
    _persist_active_chat_thread()
    chat_state = switch_thread(st.session_state.get("chat_threads_state"), thread_id)
    st.session_state.chat_threads_state = chat_state
    _restore_active_chat_thread(force=True)
    st.session_state.pop("last_gen_stats", None)


def _delete_chat_thread_cb(thread_id: str) -> None:
    _persist_active_chat_thread()
    chat_state = delete_thread(st.session_state.get("chat_threads_state"), thread_id)
    st.session_state.chat_threads_state = chat_state
    _restore_active_chat_thread(force=True)
    st.session_state.pop("last_gen_stats", None)


def _queue_chat_draft() -> None:
    draft = st.session_state.get("chat_thread_draft", "").strip()
    if not draft:
        return
    _persist_active_chat_thread()
    st.session_state["_pending_query"] = draft
    st.session_state["chat_thread_draft"] = ""
    _persist_active_chat_thread()


def _clear_chat_draft() -> None:
    st.session_state["chat_thread_draft"] = ""
    _persist_active_chat_thread()


def _clear_chat_history_cb() -> None:
    st.session_state.messages = []
    st.session_state["chat_thread_draft"] = ""
    st.session_state.pop("last_gen_stats", None)
    _persist_active_chat_thread()


_restore_active_chat_thread()


# ---- Helpers rendu ----

# SVG "cerveau" — constante module-level (évite de reconstruire la chaîne à chaque message)
_BRAIN_SVG = (
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


def _open_note_cb(fp: str) -> None:
    """Callback on_click : mémorise la note à ouvrir, déclenche navigate après rerun."""
    st.session_state.viewing_note = fp
    st.session_state.note_nav_request = fp
    st.session_state._goto_note = True


def _load_saved_conversation_cb(path_str: str, mode: str = "replace") -> None:
    resolved_path = resolve_vault_path(path_str)
    messages = load_saved_conversation(resolved_path)
    if not messages:
        return
    label = resolved_path.stem
    if mode == "append":
        st.session_state.messages = append_loaded_conversation(
            st.session_state.get("messages", []),
            messages,
        )
        _persist_active_chat_thread()
    elif mode == "duplicate":
        _persist_active_chat_thread()
        chat_state = create_thread_from_messages(
            st.session_state.get("chat_threads_state"),
            messages=list(messages),
            title=label,
            last_gen_stats={},
        )
        st.session_state.chat_threads_state = chat_state
        _restore_active_chat_thread(force=True)
    else:
        st.session_state.messages = messages
        _persist_active_chat_thread(title=label)
    st.session_state.pop("last_gen_stats", None)
    st.session_state["_loaded_conversation_label"] = label
    st.session_state["_loaded_conversation_mode"] = mode


def _dedupe_sources_keep_primary(sources: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for src in sources:
        metadata = src.get("metadata") or {}
        source_key = source_identity_key(metadata)
        if not source_key:
            continue
        current = seen.get(source_key)
        if current is None:
            seen[source_key] = src
            continue
        current_primary = bool((current.get("metadata") or {}).get("is_primary"))
        src_primary = bool(metadata.get("is_primary"))
        if src_primary and not current_primary:
            seen[source_key] = src
    return list(seen.values())


def _render_sources_block(sources: list[dict], expander_label: str, key_prefix: str) -> None:
    unique_sources = _dedupe_sources_keep_primary(sources)
    if not unique_sources:
        return

    primary_src = next(
        (src for src in unique_sources if (src.get("metadata") or {}).get("is_primary")),
        None,
    )
    if primary_src:
        primary_meta = primary_src.get("metadata") or {}
        primary_title = primary_meta.get("note_title", primary_meta.get("file_path", ""))
        primary_fp = primary_meta.get("file_path", "")
        st.markdown(
            build_primary_source_html(primary_title, render_note_badge(primary_fp)),
            unsafe_allow_html=True,
        )

    with st.expander(expander_label, expanded=False):
        for i, src in enumerate(unique_sources):
            _m = src.get("metadata") or {}
            title = _m.get("note_title", _m.get("file_path", ""))
            fp = _m.get("file_path", "")
            col_info, col_btn = st.columns([7, 1.4])
            with col_info:
                st.markdown(
                    build_source_entry_html(
                        note_title=title,
                        note_badge_html=render_note_badge(fp),
                        date_modified=str(_m.get("date_modified", "")),
                        score=float(src.get("score", 0) or 0),
                        is_primary=bool(_m.get("is_primary")),
                    ),
                    unsafe_allow_html=True,
                )
            with col_btn:
                if fp:
                    st.button(
                        "📖 Ouvrir",
                        key=f"{key_prefix}_{i}_{fp[-20:]}",
                        use_container_width=True,
                        on_click=_open_note_cb,
                        args=(fp,),
                    )


def _lookup_conversation_entity_contexts(user_text: str, assistant_text: str = "") -> list[dict]:
    combined = "\n\n".join(part for part in (user_text, assistant_text) if part and part.strip())
    if not combined.strip():
        return []
    try:
        return svc.learner.lookup_wuddai_entity_contexts(combined, max_entities=10, max_notes=3)
    except Exception as exc:
        logger.debug(f"Entity context lookup échoué: {exc}")
        return []


def _lookup_query_overview(user_text: str) -> dict:
    if not user_text or len(user_text.strip()) < 3:
        return {}
    try:
        return build_query_overview_sync(user_text, svc.llm)
    except Exception as exc:
        logger.debug(f"DDG overview échoué: {exc}")
        return {}


def _render_query_overview(query_overview: dict, key_prefix: str, *, expanded: bool = False) -> None:
    if not query_overview:
        return
    summary = str(query_overview.get("summary") or "").strip()
    sources = query_overview.get("sources") or []
    search_query = str(query_overview.get("search_query") or "").strip()
    if not summary and not sources:
        return

    with st.expander("🌐 Vue d'ensemble DDG", expanded=expanded):
        if summary:
            st.markdown(summary)
        if search_query:
            st.caption(f"Requête DDG : {search_query}")
        if sources:
            st.markdown(build_web_sources_markdown(sources[:5]))


def _compact_ddg_knowledge(ddg_knowledge: dict) -> dict:
    if not ddg_knowledge:
        return {}

    compact: dict[str, object] = {}
    for key in ("heading", "entity", "abstract_text", "answer", "answer_type", "definition"):
        value = ddg_knowledge.get(key)
        if isinstance(value, str) and value.strip():
            compact[key] = value.strip()

    infobox = []
    for item in ddg_knowledge.get("infobox") or []:
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        if label and value:
            infobox.append({"label": label, "value": value})
        if len(infobox) >= 5:
            break
    if infobox:
        compact["infobox"] = infobox

    related_topics = []
    for item in ddg_knowledge.get("related_topics") or []:
        text = str(item.get("text") or "").strip()
        url = str(item.get("url") or "").strip()
        if text and url:
            related_topics.append({"text": text, "url": url})
        if len(related_topics) >= 3:
            break
    if related_topics:
        compact["related_topics"] = related_topics

    return compact


def _render_ddg_fact_tiles(items: list[tuple[str, str]], key_prefix: str) -> None:
    if not items:
        return

    columns = st.columns(2)
    for index, (label, value) in enumerate(items):
        if not label or not value:
            continue
        with columns[index % 2]:
            st.markdown(
                (
                    "<div style='padding:0.8rem 0.9rem; margin:0 0 0.6rem 0; "
                    "border:1px solid rgba(120,120,120,0.18); border-radius:12px; "
                    "background:rgba(120,120,120,0.06)'>"
                    f"<div style='font-size:0.78rem; opacity:0.75; margin-bottom:0.25rem'>{html.escape(label)}</div>"
                    f"<div style='font-size:0.96rem; line-height:1.35'>{html.escape(value)}</div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )


def _render_ddg_knowledge_panel(ddg_knowledge: dict, entity_name: str, key_prefix: str) -> None:
    compact = _compact_ddg_knowledge(ddg_knowledge)
    if not compact:
        return

    heading = str(compact.get("heading") or compact.get("entity") or entity_name).strip()
    abstract_text = str(compact.get("abstract_text") or "").strip()
    answer = str(compact.get("answer") or "").strip()
    answer_type = str(compact.get("answer_type") or "").strip()
    definition = str(compact.get("definition") or "").strip()
    infobox = compact.get("infobox") or []
    related_topics = compact.get("related_topics") or []

    with st.container(border=True):
        st.caption("DuckDuckGo Knowledge")
        st.markdown(f"**{heading}**")

        if abstract_text:
            st.markdown(abstract_text)

        summary_facts: list[tuple[str, str]] = []
        if answer:
            summary_facts.append(("Reponse rapide", answer))
        if answer_type:
            summary_facts.append(("Type de reponse", answer_type))
        if definition:
            summary_facts.append(("Definition", definition))
        _render_ddg_fact_tiles(summary_facts, f"{key_prefix}_summary")

        if infobox:
            st.markdown("**Faits cles**")
            _render_ddg_fact_tiles(
                [
                    (str(item.get("label") or "").strip(), str(item.get("value") or "").strip())
                    for item in infobox[:6]
                ],
                f"{key_prefix}_infobox",
            )

        if related_topics:
            st.markdown("**Pour aller plus loin**")
            for item in related_topics[:3]:
                text = str(item.get("text") or "").strip()
                url = str(item.get("url") or "").strip()
                if text and url:
                    st.markdown(f"- [{text}]({url})")


def _render_entity_contexts(entity_contexts: list[dict], key_prefix: str, *, expanded: bool = False) -> None:
    if not entity_contexts:
        return

    with st.expander("🧠 Entités détectées", expanded=expanded):
        for index, context in enumerate(entity_contexts):
            entity_name = context.get("value") or "Entité"
            type_label = context.get("type_label") or context.get("type") or "Entité"
            notes = context.get("notes") or []
            ddg_knowledge = context.get("ddg_knowledge") or {}
            image_url = context.get("image_url")

            st.markdown(f"### {entity_name}")
            info_col, image_col = st.columns([3, 1])
            with info_col:
                st.markdown(f"**Type :** {type_label}")
                if context.get("mentions"):
                    st.markdown(f"**Mentions WUDD.AI :** {int(context.get('mentions') or 0)}")
                if context.get("tag"):
                    st.markdown(f"**Tag Obsidian :** `{context['tag']}`")

                if notes:
                    st.markdown("**Notes liées**")
                    for note_index, note in enumerate(notes):
                        note_title = note.get("title") or note.get("file_path") or "Note"
                        note_path = note.get("file_path") or ""
                        note_col, button_col = st.columns([5, 1.4])
                        with note_col:
                            st.markdown(f"- {note_title}")
                        with button_col:
                            if note_path:
                                st.button(
                                    "📖 Ouvrir",
                                    key=f"{key_prefix}_note_{index}_{note_index}",
                                    use_container_width=True,
                                    on_click=_open_note_cb,
                                    args=(note_path,),
                                )

                if ddg_knowledge:
                    _render_ddg_knowledge_panel(ddg_knowledge, entity_name, f"{key_prefix}_ddg_{index}")

            with image_col:
                if image_url:
                    st.image(image_url, caption=entity_name, use_container_width=True)

            if index < len(entity_contexts) - 1:
                st.divider()


def _persist_chat_enrichment(
    user_text: str,
    assistant_text: str,
    *,
    entity_contexts: list[dict] | None = None,
    query_overview: dict | None = None,
    path: Path | None = None,
) -> Path | None:
    try:
        return save_chat_enrichment_insight(
            user_text,
            assistant_text,
            entity_contexts=entity_contexts or [],
            query_overview=query_overview or {},
            path=path,
        )
    except Exception as exc:
        logger.debug(f"Chat enrichment persist échoué: {exc}")
        return path


def _render_web_failure(web_status, web_results: list[dict], web_quality: bool, message_key: str) -> str:
    if not web_results:
        failure_message = "🌐 Aucun résultat web trouvé pour cette question."
        web_status.warning(failure_message)
        return failure_message

    sources_md = build_web_sources_markdown(web_results)
    if web_quality:
        failure_message = "🌐 Des sources web ont été trouvées, mais la synthèse n'a pas pu être générée."
    else:
        failure_message = "🌐 Des sources web ont été trouvées, mais elles ont été jugées trop faibles ou trop ambiguës pour produire une réponse fiable."

    web_status.warning(f"{failure_message}\n\n---\n{sources_md}")
    return failure_message


def _render_user_bubble(text: str) -> None:
    """Rendu d'un message user : bulle alignée à droite, avatar cerveau violet ObsiRAG."""
    st.markdown(build_user_bubble_html(text, _BRAIN_SVG), unsafe_allow_html=True)


def _render_chat_response(text: str, *, placeholder=None) -> None:
    """
    Rend la réponse finale du chat.
    - Si placeholder fourni ET pas de Mermaid : met à jour en place (pas de slot vide).
    - Sinon : st.markdown dans le contexte courant.
    """
    has_mermaid = bool(MERMAID_SPLIT_RE.search(text))

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

    blocks = build_streamlit_chat_blocks(text)
    mermaid_idx = 0
    for btype, content in blocks:
        if btype == "text":
            if content.strip():
                st.markdown(content)
        elif btype == "mermaid_code":
            st.caption("📊 Diagramme Mermaid")
            st.code(content, language="mermaid")
        else:
            st.caption("📊 Diagramme Mermaid")
            height = estimate_chat_mermaid_height(content)
            render_html_document(build_mermaid_chat_preview_html(content, mermaid_idx), height=height)
            mermaid_idx += 1





# ---- Statut auto-learner (fragment auto-rafraîchi toutes les 5s) ----
@st.fragment(run_every=5)
def _autolearn_live_status():
    from src.config import settings as _s

    # Compteur notes (recalculé à chaque refresh)
    _user_notes = svc.chroma.list_user_notes()
    _user_fps = {n["file_path"] for n in _user_notes}
    _total = len(_user_notes)
    _pf = _s.processed_notes_file
    _processed_map = load_processed_notes_map(_pf)
    _processed = len([fp for fp in _processed_map if fp in _user_fps])
    # Comptages via helpers Chroma (évite les scans filesystem ad hoc côté UI)
    _insights = len(svc.chroma.list_notes_by_type("insight"))
    _synapses = len(svc.chroma.list_notes_by_type("synapse"))

    if _processed < _total:
        st.progress(_processed / _total if _total else 0,
                    text=f"Insights {_processed}/{_total} notes")
        st.caption(f"💡 {_insights} insight(s) · ⚡ {_synapses} synapse(s)")
    else:
        st.caption(f"{_processed}/{_total} notes · 💡 {_insights} insights · ⚡ {_synapses} synapses")

    # Statut traitement en cours — in-memory (même process) ou fichier (après redémarrage)
    ps = svc.learner.processing_status
    if not ps.get("log") and not ps.get("active"):
        # Lire depuis le fichier persisté si la mémoire est vide
        _sf = _s.processing_status_file
        ps = load_processing_status(_sf) or ps
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
    # Menu latéral ObsiRAG (navigation, favoris, historique)
    render_side_menu()
    st.metric("Notes indexées", svc.chroma.count_notes())
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
    st.markdown(f"**MLX** : {'🟢 Modèle chargé' if llm_ok else '🔴 Non disponible'}")

    chat_state = ensure_chat_state(st.session_state.get("chat_threads_state"))
    current_thread = get_current_thread(chat_state)
    thread_summaries = list_thread_summaries(chat_state, limit=10)

    st.divider()
    with st.expander("🧵 Fils de conversation", expanded=False):
        st.caption("Chaque fil conserve son historique et son brouillon courant.")
        st.markdown(f"**Fil actif** · {current_thread.get('title', 'Nouveau fil')}")
        st.button(
            "➕ Nouveau fil",
            key="chat_new_thread",
            use_container_width=True,
            on_click=_create_chat_thread_cb,
        )
        st.text_area(
            "Brouillon courant",
            key="chat_thread_draft",
            height=110,
            placeholder="Question en cours, idée à reformuler, rappel pour plus tard…",
            on_change=_save_chat_draft,
        )
        draft_cols = st.columns(2)
        draft_cols[0].button(
            "↗ Envoyer le brouillon",
            key="chat_send_draft",
            use_container_width=True,
            on_click=_queue_chat_draft,
            disabled=not st.session_state.get("chat_thread_draft", "").strip(),
        )
        draft_cols[1].button(
            "✖ Vider",
            key="chat_clear_draft",
            use_container_width=True,
            on_click=_clear_chat_draft,
        )

        for thread in thread_summaries:
            st.markdown(f"**{thread['title']}**")
            st.caption(
                f"{thread['turn_count']} tour(s) · {thread['message_count']} message(s) · {thread['preview']}"
            )
            col_open, col_delete = st.columns(2)
            col_open.button(
                "Ouvrir",
                key=f"chat_thread_open_{thread['id']}",
                use_container_width=True,
                on_click=_switch_chat_thread_cb,
                args=(str(thread["id"]),),
                disabled=bool(thread["is_current"]),
            )
            col_delete.button(
                "Supprimer",
                key=f"chat_thread_delete_{thread['id']}",
                use_container_width=True,
                on_click=_delete_chat_thread_cb,
                args=(str(thread["id"]),),
                disabled=len(thread_summaries) <= 1,
            )

    if st.session_state.messages:
        st.divider()
        with st.expander("🧭 Conversation en cours", expanded=False):
            nav_search = st.text_input(
                "Filtrer l'historique",
                key="chat_nav_search",
                placeholder="Question ou source…",
            )
            nav_entries = filter_chat_navigation_entries(
                build_chat_navigation_entries(st.session_state.messages),
                nav_search,
            )
            if not nav_entries:
                st.caption("Aucun tour ne correspond à ce filtre.")
            for entry in nav_entries:
                st.markdown(build_navigation_turn_title(int(entry["turn"]), str(entry["preview"])))
                meta_caption = build_navigation_meta(
                    int(entry["source_count"]) if entry.get("source_count") else None,
                    str(entry["primary_source_title"]) if entry.get("primary_source_title") else None,
                )
                if meta_caption:
                    st.caption(meta_caption)
                col_reuse, col_open = st.columns(2)
                if col_reuse.button("↺ Reposer", key=f"chat_nav_reuse_{entry['turn']}", use_container_width=True):
                    st.session_state["_pending_query"] = entry["query"]
                    st.rerun()
                if entry.get("primary_source_path"):
                    col_open.button(
                        "📖 Source",
                        key=f"chat_nav_open_{entry['turn']}",
                        use_container_width=True,
                        on_click=_open_note_cb,
                        args=(entry["primary_source_path"],),
                    )
                else:
                    col_open.button(
                        "📖 Source",
                        key=f"chat_nav_open_disabled_{entry['turn']}",
                        use_container_width=True,
                        disabled=True,
                    )

        with st.expander("📚 Notes citées", expanded=False):
            cited_sources = build_conversation_source_entries(st.session_state.messages)
            if not cited_sources:
                st.caption("Aucune source citée pour l'instant.")
            for entry in cited_sources:
                st.markdown(
                    build_cited_source_row_html(entry["title"], render_note_badge(entry["file_path"])),
                    unsafe_allow_html=True,
                )
                st.caption(
                    f"{entry['mentions']} mention(s) · {entry['primary_mentions']} principale(s)"
                )
                st.button(
                    "📖 Ouvrir",
                    key=f"chat_cited_{entry['file_path']}",
                    use_container_width=True,
                    on_click=_open_note_cb,
                    args=(entry["file_path"],),
                )

    from src.config import settings as _settings
    saved_conversations = list_saved_conversations(_settings.conversations_dir, vault_root=_settings.vault)
    if saved_conversations:
        st.divider()
        with st.expander("🗂 Conversations sauvegardées", expanded=False):
            saved_search = st.text_input(
                "Filtrer les conversations",
                key="saved_conv_search",
                placeholder="Titre, mois ou chemin…",
            )
            filtered_saved = filter_saved_conversations(saved_conversations, saved_search)
            if not filtered_saved:
                st.caption("Aucune conversation ne correspond à ce filtre.")
            for entry in filtered_saved[:10]:
                st.markdown(build_saved_conversation_title(str(entry["title"])))
                st.caption(build_saved_conversation_meta(str(entry["month"]), str(entry["file_path"])))
                col_replace, col_append, col_duplicate, col_open = st.columns(4)
                col_replace.button(
                    "↺ Remplacer",
                    key=f"saved_conv_replace_{entry['file_path']}",
                    use_container_width=True,
                    on_click=_load_saved_conversation_cb,
                    args=(entry["absolute_path"], "replace"),
                )
                col_append.button(
                    "⊕ Ajouter",
                    key=f"saved_conv_append_{entry['file_path']}",
                    use_container_width=True,
                    on_click=_load_saved_conversation_cb,
                    args=(entry["absolute_path"], "append"),
                )
                col_duplicate.button(
                    "⧉ Dupliquer",
                    key=f"saved_conv_duplicate_{entry['file_path']}",
                    use_container_width=True,
                    on_click=_load_saved_conversation_cb,
                    args=(entry["absolute_path"], "duplicate"),
                )
                col_open.button(
                    "📖 Ouvrir",
                    key=f"saved_conv_open_{entry['file_path']}",
                    use_container_width=True,
                    on_click=_open_note_cb,
                    args=(entry["file_path"],),
                )

    # Dernières stats de génération
    if st.session_state.get("last_gen_stats"):
        s = st.session_state.last_gen_stats
        st.divider()
        st.caption("**Dernière génération**")
        c1, c2 = st.columns(2)
        c1.metric("Tokens", s["tokens"])
        c2.metric("Tok/s", f"{s['tps']:.0f}")
        st.caption(build_generation_summary_caption(float(s["ttft"]), float(s["total"])))

    st.divider()

    if st.button("♻️ Re-indexer le coffre", use_container_width=True):
        progress_bar = st.progress(0, text="Démarrage de l'indexation…")
        note_lbl = st.empty()

        def _on_idx(note: str, processed: int, total: int) -> None:
            pct = processed / total if total > 0 else 0
            progress_bar.progress(pct, text=f"Indexation {processed} / {total}")
            note_lbl.caption(f"📄 `{note[-50:]}`")

        idx_stats = svc.indexer.index_vault(on_progress=_on_idx)
        progress_bar.progress(1.0, text="Indexation terminée")
        note_lbl.empty()
        st.success(
            f"✅ +{idx_stats['added']} ajoutées, "
            f"~{idx_stats['updated']} mises à jour, "
            f"🗑 {idx_stats['deleted']} supprimées"
        )
        st.rerun()

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

loaded_conversation_label = st.session_state.pop("_loaded_conversation_label", None)
loaded_conversation_mode = st.session_state.pop("_loaded_conversation_mode", None)
if loaded_conversation_label:
    if loaded_conversation_mode == "append":
        st.success(f"Conversation ajoutée au fil courant : {loaded_conversation_label}")
    elif loaded_conversation_mode == "duplicate":
        st.success(f"Conversation dupliquée dans un nouveau fil : {loaded_conversation_label}")
    else:
        st.success(f"Conversation rechargée : {loaded_conversation_label}")

if not llm_ok:
    st.warning(
        "⚠️ Le modèle MLX n'est pas disponible. "
        "Vérifiez que le modèle est correctement configuré dans `.env` (MLX_CHAT_MODEL)."
    )

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
        if msg.get("query_overview"):
            _render_query_overview(msg["query_overview"], f"hist_overview_{mi}")
        if msg.get("entity_contexts"):
            _render_entity_contexts(msg["entity_contexts"], f"hist_entities_{mi}")
        if msg.get("timeline"):
            with st.expander("🧭 Timeline activité", expanded=False):
                st.markdown(msg["timeline"])
        if msg.get("stats"):
            s = msg["stats"]
            st.caption(build_message_stats_caption(
                int(s.get("tokens", 0)),
                float(s.get("ttft", 0.0)),
                float(s.get("total", 0.0)),
                float(s.get("tps", 0.0)),
            ))
        _hist_not_in_vault = msg.get("content", "").strip().lower().startswith(
            "cette information n'est pas dans ton coffre"
        )
        if msg.get("sources") and not _hist_not_in_vault:
            unique_hist = _dedupe_sources_keep_primary(msg["sources"])
            _render_sources_block(
                msg["sources"],
                f"📚 {len(unique_hist)} source(s)",
                f"hist_src_{mi}",
            )
        if msg.get("enrichment_path"):
            st.caption(f"💾 Enrichissement sauvegardé : {Path(msg['enrichment_path']).name}")

# ---- Génération des suggestions dynamiques ----

def _generate_suggestions(on_suggestion=None) -> list[str]:
    """Génère 4 questions, basées sur un extrait réel de 4 notes tirées aléatoirement parmi les 30 plus récentes."""
    import random

    fallback = [
        "Quelles sont mes dernières notes ? Fais une synthèse de la semaine.",
        "Quelles sont les notes où je parle de machine learning ?",
        "Fais le point sur ce que j'ai appris ce mois-ci.",
        "Quelles connexions vois-tu entre mes notes récentes ?",
    ]

    def _emit(question: str) -> None:
        if callable(on_suggestion):
            try:
                on_suggestion(question)
            except Exception:
                pass

    try:
        notes = svc.chroma.list_user_notes()
        if not notes:
            for question in fallback:
                _emit(question)
            return fallback

        # 4 notes distinctes tirées aléatoirement parmi les 30 plus récentes
        recent = notes[:30]
        sample = random.sample(recent, min(4, len(recent)))

        questions: list[str] = []
        for note in sample:
            # Récupérer un extrait réel depuis le store vecteurs plutôt que de n'utiliser que le titre
            snippet = ""
            try:
                docs = [
                    chunk.get("text", "")
                    for chunk in svc.chroma.get_chunks_by_file_path(note["file_path"], limit=2)
                    if chunk.get("text")
                ]
                if docs:
                    snippet = " ".join(docs[:2])[:600]
            except Exception:
                pass

            if snippet:
                context_part = (
                    f"Titre de la note : « {note['title']} »\n"
                    f"Extrait : {snippet}"
                )
            else:
                context_part = f"Titre de la note : « {note['title']} »"

            prompt = (
                f"{context_part}\n\n"
                "Génère UNE seule question courte en FRANÇAIS que l'utilisateur "
                "pourrait poser à un assistant IA sur le contenu de cette note. "
                "RÈGLES IMPORTANTES :\n"
                "- La question doit OBLIGATOIREMENT être entièrement rédigée en français, "
                "même si la note est en anglais ou dans une autre langue.\n"
                "- La question doit être directement et entièrement répondable à partir de l'extrait fourni.\n"
                "- Ne pose PAS de questions sur des données chiffrées précises (altitudes, dates, pourcentages, distances…) "
                "sauf si ces valeurs apparaissent explicitement dans l'extrait.\n"
                "- Préfère les formulations du type 'Quels sont mes apprentissages sur…', "
                "'Que retiens-je de…', 'Qu'est-ce que mes notes disent sur…', 'Quels sont les points clés de…'.\n"
                "- La question doit obligatoirement se terminer par '?'.\n"
                "Réponds uniquement avec la question en français, rien d'autre."
            )
            answer = svc.llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=60,
                operation="suggestions",
            ).strip()
            # Garder uniquement la première ligne non vide
            q = next((l.strip() for l in answer.splitlines() if l.strip()), "")
            if q:
                q = q if q.endswith("?") else re.sub(r"[.!]+$", "", q) + "?"
                # Rejeter si la question contient des mots anglais courants (pas en français)
                _EN_MARKERS = {"what", "how", "why", "when", "where", "who", "which",
                               "is", "are", "the", "of", "in", "and", "or", "do",
                               "does", "can", "could", "would", "should"}
                words_lower = set(re.sub(r"[^\w\s]", "", q.lower()).split())
                if not (words_lower & _EN_MARKERS):
                    questions.append(q)
                    _emit(q)

        if len(questions) < 4:
            for question in fallback[len(questions):]:
                questions.append(question)
                _emit(question)

        return questions
    except Exception:
        for question in fallback:
            _emit(question)
        return fallback


# Suggestions de démarrage — générées en arrière-plan (non-bloquant)
# @st.cache_resource persiste à travers tous les reruns Streamlit (process-level)
@st.cache_resource
def _get_sug_state() -> dict:
    """Retourne un état partagé persistant pour la génération des suggestions."""
    return {"lock": threading.Lock(), "items": [], "result": None, "generating": False, "done": False}


def _ensure_suggestions_bg() -> None:
    """Lance la génération des suggestions dans un thread daemon si pas déjà fait."""
    state = _get_sug_state()
    with state["lock"]:
        if state["done"] or state["generating"]:
            return
        state["items"] = []
        state["result"] = None
        state["done"] = False
        state["generating"] = True

    def _run() -> None:
        def _on_suggestion(question: str) -> None:
            s = _get_sug_state()
            with s["lock"]:
                if question not in s["items"]:
                    s["items"].append(question)

        try:
            result = _generate_suggestions(on_suggestion=_on_suggestion)
        except Exception:
            result = []
        s = _get_sug_state()
        with s["lock"]:
            s["result"] = result
            s["generating"] = False
            s["done"] = True
            if not s["items"] and result:
                s["items"] = list(result)

    threading.Thread(target=_run, daemon=True).start()


pending = _pending

# st.chat_input doit TOUJOURS être rendu avant tout st.rerun() pour éviter les erreurs de widget
user_input = st.chat_input("Posez une question sur votre coffre…") or pending

if not st.session_state.messages and not user_input:
    _ensure_suggestions_bg()
    state = _get_sug_state()
    with state["lock"]:
        _sug_result = list(state["items"])
        _sug_done = bool(state["done"])
        _sug_generating = bool(state["generating"])

    st.markdown("#### Exemples de questions")
    if _sug_result:
        cols = st.columns(2)
        for i, sug in enumerate(_sug_result):
            with cols[i % 2]:
                if st.button(sug, use_container_width=True, key=f"sug_{i}"):
                    st.session_state._pending_query = sug
                    st.rerun()
        if _sug_generating and not _sug_done:
            st.caption("⏳ Génération des suggestions…")
            time.sleep(0.25)
            st.rerun()
    else:
        st.caption("⏳ Génération des suggestions…")
        time.sleep(0.25)
        st.rerun()

# Recherche web déclenchée par le bouton (indépendamment du chat input)
if _pending_web:
    if not llm_ok:
        st.error("Le modèle MLX n'est pas disponible.")
        st.stop()
    st.session_state.messages.append({"role": "user", "content": f"🌐 Recherche web : {_pending_web}"})
    _persist_active_chat_thread()
    _render_user_bubble(f"🌐 Recherche web : {_pending_web}")
    with st.chat_message("assistant"):
        web_status = st.empty()
        web_status.markdown("🌐 *Recherche web en cours…*")
        web_answer, web_path, web_results, web_quality = enrich_sync(_pending_web, svc.llm)
        if web_answer:
            sources_md = "\n".join(
                f"- [{r.get('title', r.get('href', ''))}]({r.get('href', '')})"
                for r in web_results
            )
            web_full = (
                f"🌐 **Résultat de la recherche web :**\n\n{web_answer}"
                + (f"\n\n---\n{sources_md}" if sources_md else "")
            )
            web_status.markdown(web_full)
            _q_badge = "✅ Bonne qualité" if web_quality else "⚠️ Résultat partiel"
            web_entity_contexts = _lookup_conversation_entity_contexts(_pending_web, web_answer)
            if web_entity_contexts:
                _render_entity_contexts(web_entity_contexts, "pending_web_entities")
                web_path = _persist_chat_enrichment(
                    _pending_web,
                    web_answer,
                    entity_contexts=web_entity_contexts,
                    path=web_path,
                )
            if web_path:
                st.caption(f"{_q_badge} · 💾 Insight sauvegardé : `{web_path.name}`")
            else:
                st.caption(_q_badge)
            st.session_state.messages.append({
                "role": "assistant",
                "content": web_full,
                "sources": [],
                "stats": {},
                "timeline": "",
                "entity_contexts": web_entity_contexts,
                "query_overview": {},
                "enrichment_path": str(web_path) if web_path else "",
            })
            _persist_active_chat_thread()
        else:
            failure_message = _render_web_failure(web_status, web_results, web_quality, "pending_web")
            st.session_state.messages.append({
                "role": "assistant",
                "content": failure_message,
                "sources": [],
                "stats": {},
                "timeline": "",
                "entity_contexts": [],
                "query_overview": {},
                "enrichment_path": "",
            })
            _persist_active_chat_thread()

if user_input:
    if not llm_ok:
        st.error("Le modèle MLX n'est pas disponible.")
        st.stop()

    svc.learner.log_user_query(user_input)

    st.session_state.messages.append({"role": "user", "content": user_input})
    _persist_active_chat_thread()
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
        entity_contexts: list[dict] = []
        query_overview: dict = {}
        enrichment_path: Path | None = None
        gen_stats: dict = {}
        ttft_val = 0.0
        total = 0.0
        tps_val = 0.0
        timeline_entries: list[str] = []
        timeline_lock = threading.Lock()

        t0 = time.perf_counter()

        def _push_timeline(message: str) -> None:
            if not message:
                return
            elapsed = time.perf_counter() - t0
            entry = f"- `{elapsed:.1f}s` {message}"
            with timeline_lock:
                if timeline_entries and timeline_entries[-1].endswith(message):
                    return
                timeline_entries.append(entry)

        try:
            # Phase 1 — récupération RAG
            retrieval_started_at = time.perf_counter()
            progress_lock = threading.Lock()
            progress_state: dict[str, object] = {
                "message": "Recherche dans le coffre",
                "phase": "retrieval",
            }
            phase_order = ("resolve", "retrieval", "context", "generation")
            phase_labels = {
                "resolve": "Analyse de la requête",
                "retrieval": "Recherche dans le coffre",
                "context": "Préparation du contexte",
                "generation": "Génération MLX",
            }

            def _on_rag_progress(event: dict) -> None:
                if not isinstance(event, dict):
                    return
                message = str(event.get("message") or "").strip()
                if not message:
                    return
                phase = str(event.get("phase") or "retrieval")
                phase_label = phase_labels.get(phase, "Activité")
                _push_timeline(f"{phase_label} — {message}")
                with progress_lock:
                    progress_state.update(event)
                    progress_state["message"] = message

            def _supports_progress_callback(fn) -> bool:
                try:
                    params = inspect.signature(fn).parameters
                except (TypeError, ValueError):
                    return False
                return "progress_callback" in params

            def _run_query_stream_with_compat() -> tuple[object, list]:
                rag_query_stream = svc.rag.query_stream
                if _supports_progress_callback(rag_query_stream):
                    try:
                        return rag_query_stream(
                            user_input,
                            chat_history=history,
                            progress_callback=_on_rag_progress,
                        )
                    except TypeError as exc:
                        if "progress_callback" not in str(exc):
                            raise
                with progress_lock:
                    progress_state["message"] = "Recherche dans le coffre (mode compatibilité)"
                _push_timeline("Recherche dans le coffre — mode compatibilité")
                return rag_query_stream(user_input, chat_history=history)

            with ThreadPoolExecutor(max_workers=1) as pool:
                retrieval_future = pool.submit(_run_query_stream_with_compat)
                while not retrieval_future.done():
                    elapsed = time.perf_counter() - retrieval_started_at
                    with progress_lock:
                        snapshot = dict(progress_state)
                    status_message = str(snapshot.get("message") or "Recherche dans le coffre")
                    dots = "." * ((int(elapsed * 2) % 3) + 1)
                    status.markdown(
                        f"🔍 *{status_message}{dots}*  \n"
                        f"`{elapsed:.1f}s`"
                    )
                    time.sleep(0.2)
                stream, sources = retrieval_future.result()
            retrieval_elapsed = time.perf_counter() - retrieval_started_at
            with progress_lock:
                end_snapshot = dict(progress_state)
            retrieved_chunks = int(end_snapshot.get("chunk_count") or len(sources))
            retrieved_intent = str(end_snapshot.get("intent") or "")
            intent_suffix = f" · intent `{retrieved_intent}`" if retrieved_intent else ""
            status.markdown(
                f"✅ *Contexte récupéré en {retrieval_elapsed:.1f}s*  \n"
                f"`{retrieved_chunks} passage(s){intent_suffix}`"
            )
            _push_timeline(f"Contexte récupéré — {retrieved_chunks} passage(s){intent_suffix}")

            # Progression des notes dans le contexte
            seen: list[str] = []
            for src in sources:
                title = (src.get("metadata") or {}).get("note_title", "")
                if title and title not in seen:
                    seen.append(title)
            for i, note in enumerate(seen, 1):
                status.markdown(f"📄 *Note {i} sur {len(seen)} — {note}*")
                time.sleep(0.12)

            # Phase 2 — génération MLX
            ctx_chars = sum(len(s.get("text", "")) for s in sources)
            ctx_notes = len(seen)
            status.markdown(
                f"⏳ *MLX charge le contexte… "
                f"{ctx_notes} note{'s' if ctx_notes > 1 else ''} · "
                f"~{ctx_chars:,} caractères*"
            )
            _push_timeline("Génération MLX — chargement du contexte")

            for token in stream:
                if first_token_time is None:
                    first_token_time = time.perf_counter()
                    ttft = first_token_time - t0
                    status.markdown(f"⚡ *Génération en cours · premier token en {ttft:.1f}s*")
                    _push_timeline(f"Génération MLX — premier token en {ttft:.1f}s")

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
            _push_timeline(f"Réponse finalisée — {token_count} token(s)")
            status.caption(build_generation_status_caption(token_count, ttft_val, total, tps_val))

        except Exception as exc:
            full_response = f"❌ Erreur : {exc}"
            response_area.error(full_response)
            status.empty()
            sources = []

        # Sources — dédupliquées par note (file_path), une seule entrée par note
        # Ne pas afficher les sources seulement si la réponse est un sentinel pur.
        _NOT_IN_VAULT = "cette information n'est pas dans ton coffre"
        _SOFT_SENTINEL = "n'est pas consignée dans ton coffre"
        _low = full_response.strip().lower().rstrip(".")
        _response_is_sentinel = _low == _NOT_IN_VAULT or _low == _SOFT_SENTINEL
        if sources and not _response_is_sentinel:
            unique_sources = _dedupe_sources_keep_primary(sources)
            _render_sources_block(
                sources,
                f"📚 {len(unique_sources)} source(s)",
                "open_src",
            )

        if full_response and not full_response.startswith("❌ Erreur"):
            entity_contexts = _lookup_conversation_entity_contexts(user_input, full_response)
            query_overview = _lookup_query_overview(user_input)
            _render_query_overview(query_overview, f"live_overview_{len(st.session_state.messages)}", expanded=True)
            _render_entity_contexts(entity_contexts, f"live_entities_{len(st.session_state.messages)}", expanded=True)
            enrichment_path = _persist_chat_enrichment(
                user_input,
                full_response,
                entity_contexts=entity_contexts,
                query_overview=query_overview,
            )
            if enrichment_path:
                st.caption(f"💾 Enrichissement sauvegardé : {enrichment_path.name}")

        # Bouton "Rechercher sur le web" — disponible après chaque réponse (hors résultat web)
        _is_web_result = full_response.startswith("🌐 **Résultat")

        # Timeline activité — affichée après la réponse, expandée par défaut
        with timeline_lock:
            _timeline_now = "\n".join(timeline_entries[:16])
        if _timeline_now:
            with st.expander("🧭 Timeline activité", expanded=False):
                st.markdown(_timeline_now)

        if not _response_is_sentinel and not _is_web_result:
            def _trigger_web_search(_q=user_input):
                st.session_state["_pending_web_query"] = _q
            st.button(
                "🌐 Rechercher sur le web",
                key=f"web_btn_{len(st.session_state.messages)}",
                on_click=_trigger_web_search,
            )

    # Sauvegarde dans l'historique et les stats sidebar
    with timeline_lock:
        timeline_text = "\n".join(timeline_entries[:16])
    st.session_state.messages.append({
        "role": "assistant",
        "content": full_response,
        "sources": sources[:8],
        "stats": gen_stats,
        "timeline": timeline_text,
        "entity_contexts": entity_contexts,
        "query_overview": query_overview,
        "enrichment_path": str(enrichment_path) if enrichment_path else "",
    })
    _persist_active_chat_thread()
    if gen_stats:
        st.session_state.last_gen_stats = gen_stats
        _persist_active_chat_thread()

    # Enrichissement web : si la réponse est "pas dans ton coffre",
    # lancer une recherche DuckDuckGo synchrone et afficher la réponse dans le chat
    if is_not_in_vault(full_response):
        logger.info("UI decision: fallback web déclenché (sentinel pur détecté)")
        with st.chat_message("assistant"):
            web_status = st.empty()
            web_status.markdown("🌐 *Information absente du coffre — recherche web en cours…*")
            web_answer, web_path, web_results, web_quality = enrich_sync(user_input, svc.llm)

            if web_answer:
                sources_md = "\n".join(
                    f"- [{r.get('title', r.get('href',''))}]({r.get('href','')})"
                    for r in web_results
                )
                web_full = (
                    f"🌐 **Résultat de la recherche web :**\n\n{web_answer}"
                    + (f"\n\n---\n{sources_md}" if sources_md else "")
                )
                web_status.markdown(web_full)
                _q_badge = "✅ Bonne qualité" if web_quality else "⚠️ Résultat partiel"
                web_entity_contexts = _lookup_conversation_entity_contexts(user_input, web_answer)
                if web_entity_contexts:
                    _render_entity_contexts(web_entity_contexts, "fallback_web_entities")
                    web_path = _persist_chat_enrichment(
                        user_input,
                        web_answer,
                        entity_contexts=web_entity_contexts,
                        path=web_path,
                    )
                if web_path:
                    st.caption(f"{_q_badge} · 💾 Insight sauvegardé : `{web_path.name}`")
                else:
                    st.caption(_q_badge)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": web_full,
                    "sources": [],
                    "stats": {},
                    "timeline": "",
                    "entity_contexts": web_entity_contexts,
                    "query_overview": {},
                    "enrichment_path": str(web_path) if web_path else "",
                })
                _persist_active_chat_thread()
            else:
                failure_message = _render_web_failure(web_status, web_results, web_quality, "fallback_web")
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": failure_message,
                    "sources": [],
                    "stats": {},
                    "timeline": "",
                    "entity_contexts": [],
                    "query_overview": {},
                    "enrichment_path": "",
                })
                _persist_active_chat_thread()
    else:
        logger.info("UI decision: réponse du coffre conservée (pas de fallback web)")

if st.session_state.messages:
    col_clear, col_save = st.columns([1, 1])
    with col_clear:
        st.button(
            "🗑 Effacer l'historique",
            key="clear_history",
            use_container_width=True,
            on_click=_clear_chat_history_cb,
        )
    with col_save:
        if st.button("💾 Sauvegarder cette conversation", key="save_conv", use_container_width=True):
            _save_conversation()
