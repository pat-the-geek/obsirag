"""
Singleton des services ObsiRAG.

Stratégie :
- _services_instance : variable module-level (singleton process), initialisée une seule fois
- st.session_state["_svc_ready"] : évite de réafficher le panneau de démarrage
  lors des reruns et navigations dans la même session Streamlit
"""
import threading

import streamlit as st

from src.services import ServiceManager

_lock = threading.Lock()
_services_instance: ServiceManager | None = None


_COMPACT_CSS = """
<style>
/* Header transparent (conserve la hauteur pour le bouton sidebar) */
header[data-testid="stHeader"] {
    background: transparent !important;
    box-shadow: none !important;
}
/* Barre décorative colorée supprimée */
div[data-testid="stDecoration"] { display: none !important; }
/* Masque le conteneur du composant bridge (iframe hauteur 0) */
iframe[title="obsirag_note_bridge"] { display: none !important; }
div[data-testid="stCustomComponentV1"]:has(iframe[title="obsirag_note_bridge"]) {
    display: none !important;
}
/* Réduit le padding du contenu principal (tous sélecteurs Streamlit) */
section[data-testid="stMain"] .block-container,
div[data-testid="stMainBlockContainer"] {
    padding-top: 0.75rem !important;
    padding-bottom: 1rem !important;
}
</style>
"""


def get_services() -> ServiceManager:
    global _services_instance

    # Injecte le CSS compact sur chaque page (idempotent)
    st.markdown(_COMPACT_CSS, unsafe_allow_html=True)

    # Chemin rapide : services déjà prêts ET session déjà vue
    if st.session_state.get("_svc_ready") and _services_instance is not None:
        return _services_instance

    # Services déjà créés par une autre session → marquer et retourner
    if _services_instance is not None:
        st.session_state["_svc_ready"] = True
        return _services_instance

    # Première initialisation : afficher la progression
    with st.status("⏳ Démarrage d'ObsiRAG…", expanded=True) as status:
        def on_step(msg: str) -> None:
            status.write(msg)

        with _lock:
            if _services_instance is None:
                _services_instance = ServiceManager(on_step=on_step)

        status.update(label="✅ ObsiRAG prêt", state="complete", expanded=False)

    st.session_state["_svc_ready"] = True
    return _services_instance
