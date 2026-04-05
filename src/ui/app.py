"""
ObsiRAG — Page principale : Chat
"""
import time
from datetime import datetime

import streamlit as st

from src.ui.services_cache import get_services

# ---- Configuration de la page ----
st.set_page_config(
    page_title="ObsiRAG",
    page_icon="🧠",
    layout="wide",
)

svc = get_services()

# ---- Sidebar ----
with st.sidebar:
    st.markdown("## 🧠 ObsiRAG")
    st.caption("Votre coffre Obsidian, augmenté par l'IA locale")
    st.divider()

    notes = svc.chroma.list_notes()
    st.metric("Notes indexées", len(notes))
    st.metric("Chunks vectorisés", svc.chroma.count())

    # Progression de l'indexation initiale (thread background)
    idx = svc.indexing_status
    if idx.get("running"):
        total = idx.get("total", 0)
        processed = idx.get("processed", 0)
        current = idx.get("current", "")
        st.progress(processed / total if total else 0, text=f"⏳ Indexation {processed}/{total}")
        if current:
            st.caption(f"…{current[-40:]}" if len(current) > 40 else current)
        time.sleep(1)
        st.rerun()

    llm_ok = svc.llm.is_available()
    st.markdown(f"**LM Studio** : {'🟢 Connecté' if llm_ok else '🔴 Non disponible'}")

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

    st.divider()
    st.page_link("app.py", label="💬 Chat", icon="💬")
    st.page_link("pages/1_Brain.py", label="Cerveau", icon="🧠")
    st.page_link("pages/2_Insights.py", label="Insights", icon="💡")
    st.page_link("pages/3_Settings.py", label="Paramètres", icon="⚙️")

# ---- Zone de chat ----
st.title("💬 Chat avec votre coffre")

if not llm_ok:
    st.warning(
        "⚠️ LM Studio n'est pas accessible. "
        "Vérifiez que le serveur est démarré et que l'URL est correcte dans `.env`."
    )

if "messages" not in st.session_state:
    st.session_state.messages = []

# Affiche l'historique
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
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
        st.error("LM Studio n'est pas disponible.")
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

            # Phase 2 — génération LM Studio
            ctx_chars = sum(len(s.get("text", "")) for s in sources)
            ctx_notes = len(seen)
            status.markdown(
                f"⏳ *LM Studio charge le contexte… "
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

            # Affichage final propre
            response_area.markdown(full_response)
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
