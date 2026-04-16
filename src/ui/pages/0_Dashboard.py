"""
Page Tableau de bord — Vue synthétique : statistiques, alertes, état système, accès rapide.
"""
import streamlit as st
from pathlib import Path
from src.ui.theme import inject_theme, render_theme_toggle
from src.ui.side_menu import render_mobile_main_menu, render_side_menu
from src.ui.services_cache import get_services
from src.ui.runtime_state_store import load_processing_status
from src.ui.telemetry_store import load_runtime_metrics_payload, load_latest_json
from src.config import settings

# Icône et config page
_icon = str(Path(__file__).parent.parent / "static" / "favicon-32x32.png")
st.set_page_config(page_title="Tableau de bord — ObsiRAG", page_icon=_icon, layout="wide", initial_sidebar_state="expanded")
inject_theme()
render_mobile_main_menu()

# Bouton d'ouverture de la sidebar en haut à droite du contenu principal
st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
# Ajout à l'historique navigation
HISTO_KEY = "obsirag_historique"
st.session_state.setdefault(HISTO_KEY, [])
if not st.session_state[HISTO_KEY] or st.session_state[HISTO_KEY][-1] != "Tableau de bord":
    st.session_state[HISTO_KEY].append("Tableau de bord")
render_side_menu()
render_theme_toggle()
svc = get_services()

st.title("\U0001F4CA Tableau de bord ObsiRAG")

# Statistiques clés
col1, col2, col3 = st.columns(3)
with col1:
    n_notes = svc.chroma.count_notes() if hasattr(svc.chroma, "count_notes") else "?"
    st.metric("Notes indexées", n_notes)
with col2:
    n_insights = len(svc.chroma.list_notes_by_type("insight"))
    st.metric("Insights générés", n_insights)
with col3:
    n_synapses = len(svc.chroma.list_notes_by_type("synapse"))
    st.metric("Synapses détectées", n_synapses)

# Alertes système
st.subheader("\U0001F6A8 Alertes système")
metrics = load_runtime_metrics_payload(settings.runtime_metrics_file)
counters = metrics.get("counters", {}) if metrics else {}
alerts = []
if counters.get("rag_context_retries_total", 0) > 10:
    alerts.append("Contexte trop grand : trop de retries.")
if counters.get("rag_sentinel_answers_total", 0) > 5:
    alerts.append("Réponses sentinelle fréquentes (infos manquantes).")
if not alerts:
    st.success("Aucune alerte critique détectée.")
else:
    for alert in alerts:
        st.warning(alert)

# État du système
st.subheader("\U0001F527 État du système")
status = load_processing_status(settings.processing_status_file)
if status:
    st.json(status, expanded=False)
else:
    st.info("Aucun statut de traitement en cours.")

# Accès rapide
st.subheader("\U0001F680 Accès rapide")
col1, col2 = st.columns(2)
with col1:
    if st.button("Cerveau (graphe)"):
        st.switch_page("pages/1_Brain.py")
    if st.button("Insights"):
        st.switch_page("pages/2_Insights.py")
with col2:
    if st.button("Paramètres & Statistiques"):
        st.switch_page("pages/3_Settings.py")
    if st.button("Dernière note consultée") and hasattr(st.session_state, "viewing_note"):
        st.switch_page("pages/4_Note.py")
