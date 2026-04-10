"""
Page Insights — Artefacts générés par l'auto-learner + historique des requêtes.
"""
import json
import math
from datetime import datetime

from pathlib import Path

import streamlit as st

from src.config import settings
from src.ui.services_cache import get_services
from src.ui.theme import inject_theme, render_theme_toggle

_icon = str(Path(__file__).parent.parent / "static" / "favicon-32x32.png")
st.set_page_config(page_title="Insights — ObsiRAG", page_icon=_icon, layout="wide")
inject_theme()
svc = get_services()

render_theme_toggle()
st.title("💡 Insights")
st.caption("Connaissances générées automatiquement et historique de vos questions")

# ---- Estimation du temps de traitement ----
with st.expander("⏱️ Progression & estimation du temps restant", expanded=True):
    # Données de traitement
    processed_map: dict = {}
    if settings.processed_notes_file.exists():
        try:
            processed_map = json.loads(settings.processed_notes_file.read_text(encoding="utf-8"))
        except Exception:
            processed_map = {}

    total_notes_raw = svc.chroma.list_notes() if hasattr(svc, "chroma") else []
    # Exclure les notes générées par ObsiRAG (insights, synthesis, synapses)
    user_notes = [
        n for n in total_notes_raw
        if "/obsirag/" not in n["file_path"].replace("\\", "/")
        and not n["file_path"].replace("\\", "/").startswith("obsirag/")
    ]
    user_fps = {n["file_path"] for n in user_notes}
    processed_count = len([fp for fp in processed_map if fp in user_fps])

    # Pendant un bulk initial, utiliser les compteurs exposés par l'auto-learner
    # (bulk_pending_total / bulk_new_done) plutôt que le total ChromaDB.
    bulk_pending = 0
    bulk_done = 0
    if hasattr(svc, "learner") and svc.learner is not None:
        bulk_pending = svc.learner.processing_status.get("bulk_pending_total", 0)
        bulk_done = svc.learner.processing_status.get("bulk_new_done", 0)

    if bulk_pending > 0:
        # Mode bulk : "à traiter" = lot initial, "traitées" = avancement dans ce lot
        total_notes = bulk_pending
        processed_in_view = bulk_done
        remaining = max(0, bulk_pending - bulk_done)
    else:
        # Mode normal : base sur processed_map vs ChromaDB
        total_notes = len(user_notes)
        processed_in_view = processed_count
        remaining = max(0, total_notes - processed_count)

    # Durée réelle moyenne par note (historique glissant)
    _FALLBACK_SECS_PER_NOTE = 125  # valeur par défaut avant les premières mesures
    secs_per_note = _FALLBACK_SECS_PER_NOTE
    avg_source = "estimation par défaut"
    if settings.processing_times_file.exists():
        try:
            _times: list[float] = json.loads(
                settings.processing_times_file.read_text(encoding="utf-8")
            )
            if _times:
                _recent = _times[-20:]  # moyenne glissante sur les 20 dernières notes
                secs_per_note = sum(_recent) / len(_recent)
                avg_source = f"moyenne réelle ({len(_recent)} notes)"
        except Exception:
            pass

    notes_per_cycle = settings.autolearn_max_notes_per_run + settings.autolearn_fullscan_per_run
    cycle_minutes = settings.autolearn_interval_minutes

    cycles_needed = math.ceil(remaining / notes_per_cycle) if notes_per_cycle > 0 else 0
    time_in_cycle_secs = notes_per_cycle * secs_per_note
    total_secs = cycles_needed * max(cycle_minutes * 60, time_in_cycle_secs)

    def _fmt_duration(secs: float) -> str:
        secs = int(secs)
        if secs < 60:
            return f"{secs}s"
        if secs < 3600:
            return f"{secs // 60} min"
        h = secs // 3600
        m = (secs % 3600) // 60
        return f"{h}h{m:02d}"

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Notes à traiter", total_notes)
    col2.metric("Notes traitées", processed_in_view)
    col3.metric("Notes restantes", remaining)
    col4.metric(
        "Temps estimé restant",
        _fmt_duration(total_secs) if remaining > 0 else "✅ Complet",
        help=f"{cycles_needed} cycle(s) × ~{_fmt_duration(time_in_cycle_secs)} / cycle · "
             f"intervalle cycle : {cycle_minutes} min · "
             f"{notes_per_cycle} notes/cycle · "
             f"~{_fmt_duration(int(secs_per_note))}/note ({avg_source})"
    )

    if remaining > 0 and total_notes > 0:
        st.progress(processed_in_view / total_notes, text=f"{processed_in_view}/{total_notes} notes")

    # Prochaine exécution du cycle
    if hasattr(svc, "learner") and svc.learner is not None:
        try:
            import os
            from zoneinfo import ZoneInfo
            job = svc.learner._scheduler.get_job("autolearn_cycle")
            if job and job.next_run_time:
                tz = ZoneInfo(os.environ.get("TZ", "UTC"))
                next_run = job.next_run_time.astimezone(tz).strftime("%H:%M:%S")
                tz_label = os.environ.get("TZ", "UTC")
                st.caption(f"Prochain cycle auto-learner : **{next_run}** ({tz_label})")
        except Exception:
            pass

tab_knowledge, tab_synapses, tab_synthesis, tab_queries = st.tabs(
    ["🧩 Artefacts de connaissance", "⚡ Synapses", "📋 Synthèses hebdomadaires", "🔍 Historique requêtes"]
)

# ---- Artefacts de connaissance (vault/obsirag/insights/) ----
with tab_knowledge:
    insights_dir = settings.insights_dir
    artifacts = sorted(insights_dir.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True) \
        if insights_dir.exists() else []

    if not artifacts:
        st.info(
            "Aucun artefact généré pour l'instant. "
            "L'auto-learner s'activera dans quelques minutes et créera des notes "
            f"dans `{settings.vault_obsirag_dir.relative_to(settings.vault)}/insights/`."
        )
    else:
        st.caption(
            f"{len(artifacts)} artefact(s) · "
            f"Visibles dans Obsidian sous `obsirag/insights/`"
        )
        for art_path in artifacts[:30]:
            date_str = datetime.fromtimestamp(art_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            with st.expander(f"📄 {art_path.stem} — {date_str}", expanded=False):
                st.markdown(art_path.read_text(encoding="utf-8"))

# ---- Synapses (vault/obsirag/synapses/) ----
with tab_synapses:
    synapses_dir = settings.synapses_dir
    synapses = sorted(synapses_dir.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True) \
        if synapses_dir.exists() else []

    if not synapses:
        st.info(
            "Aucune synapse générée pour l'instant. "
            "L'auto-learner découvre des connexions implicites entre notes à chaque cycle. "
            f"Elles apparaîtront dans Obsidian sous `obsirag/synapses/`."
        )
    else:
        st.caption(
            f"{len(synapses)} synapse(s) découverte(s) · "
            f"Visibles dans Obsidian sous `obsirag/synapses/`"
        )
        for syn_path in synapses[:50]:
            date_str = datetime.fromtimestamp(syn_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            with st.expander(f"⚡ {syn_path.stem} — {date_str}", expanded=False):
                st.markdown(syn_path.read_text(encoding="utf-8"))

# ---- Synthèses hebdomadaires (vault/obsirag/synthesis/) ----
with tab_synthesis:
    synth_dir = settings.synthesis_dir
    syntheses = sorted(synth_dir.glob("*.md"), reverse=True) if synth_dir.exists() else []

    if not syntheses:
        st.info(
            "Aucune synthèse générée. La première sera créée dimanche soir. "
            f"Elle apparaîtra dans Obsidian sous `obsirag/synthesis/`."
        )
    else:
        st.caption(f"Visibles dans Obsidian sous `obsirag/synthesis/`")
        for s_path in syntheses[:10]:
            with st.expander(f"📊 {s_path.stem}", expanded=(s_path == syntheses[0])):
                st.markdown(s_path.read_text(encoding="utf-8"))

# ---- Historique des requêtes (volume Docker) ----
with tab_queries:
    q_file = settings.queries_file
    if not q_file.exists():
        st.info("Aucune requête enregistrée.")
    else:
        lines = q_file.read_text(encoding="utf-8").strip().splitlines()
        queries = []
        for line in lines:
            try:
                queries.append(json.loads(line))
            except Exception:
                pass

        queries.sort(key=lambda x: x.get("ts", ""), reverse=True)
        st.caption(f"{len(queries)} requête(s) enregistrée(s)")

        if queries:
            col1, col2 = st.columns(2)
            col1.metric("Total requêtes", len(queries))
            today = datetime.utcnow().strftime("%Y-%m-%d")
            today_count = sum(1 for q in queries if q.get("ts", "").startswith(today))
            col2.metric("Aujourd'hui", today_count)

            st.markdown("#### Dernières requêtes")
            for q in queries[:20]:
                ts = q.get("ts", "")[:16].replace("T", " ")
                st.markdown(f"- `{ts}` — {q.get('query', '')}")
