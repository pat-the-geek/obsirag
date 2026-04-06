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

_icon = (Path(__file__).parent.parent / "static" / "obsirag_icon.svg").read_bytes()
st.set_page_config(page_title="Insights — ObsiRAG", page_icon=_icon, layout="wide")
svc = get_services()

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

    total_notes = len(svc.chroma.list_notes()) if hasattr(svc, "chroma") else 0
    processed_count = len(processed_map)
    remaining = max(0, total_notes - processed_count)

    # Paramètres de vitesse (secondes par note)
    # 1 appel semantic field + 1 appel questions + 3 × (15s sleep + ~10s LLM) + 30s sleep fin
    secs_per_note = (
        5          # sleep post-semantic-field
        + 3 * 15   # sleep entre questions
        + 30       # sleep entre notes
        + 3 * 20   # estimation appels LLM (~20s chacun)
    )

    notes_per_cycle = settings.autolearn_max_notes_per_run + settings.autolearn_fullscan_per_run
    cycle_minutes = settings.autolearn_interval_minutes

    cycles_needed = math.ceil(remaining / notes_per_cycle) if notes_per_cycle > 0 else 0
    time_in_cycle_secs = notes_per_cycle * secs_per_note
    total_secs = cycles_needed * max(cycle_minutes * 60, time_in_cycle_secs)

    def _fmt_duration(secs: int) -> str:
        if secs < 60:
            return f"{secs}s"
        if secs < 3600:
            return f"{secs // 60} min"
        h = secs // 3600
        m = (secs % 3600) // 60
        return f"{h}h{m:02d}"

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Notes totales", total_notes)
    col2.metric("Notes traitées", processed_count)
    col3.metric("Notes restantes", remaining)
    col4.metric(
        "Temps estimé restant",
        _fmt_duration(total_secs) if remaining > 0 else "✅ Complet",
        help=f"{cycles_needed} cycle(s) × ~{_fmt_duration(time_in_cycle_secs)} / cycle · "
             f"intervalle cycle : {cycle_minutes} min · "
             f"{notes_per_cycle} notes/cycle"
    )

    if remaining > 0 and total_notes > 0:
        st.progress(processed_count / total_notes, text=f"{processed_count}/{total_notes} notes")

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
