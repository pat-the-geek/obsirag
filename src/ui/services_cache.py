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
<script>
(function() {
  var ICON_URL = '/app/static/apple-touch-icon.png';
  var MANIFEST_URL = '/app/static/site.webmanifest';
  var MASK_URL = '/app/static/safari-pinned-tab.svg';
  var FAVICON_ICO = '/app/static/favicon.ico';
  var FAVICON_32 = '/app/static/favicon-32x32.png';
  var FAVICON_16 = '/app/static/favicon-16x16.png';

  function applyHeadTags() {
    var head = document.head;

    // Remove any existing icons/manifest injected by Streamlit or us
    head.querySelectorAll('link[rel*="icon"], link[rel="manifest"], link[rel="mask-icon"], meta[name="theme-color"], meta[name="apple-mobile-web-app"]').forEach(function(el) { el.remove(); });

    var links = [
      {rel:'icon', type:'image/x-icon', href:FAVICON_ICO},
      {rel:'icon', type:'image/png', sizes:'32x32', href:FAVICON_32},
      {rel:'icon', type:'image/png', sizes:'16x16', href:FAVICON_16},
      {rel:'apple-touch-icon', sizes:'180x180', href:ICON_URL},
      {rel:'mask-icon', href:MASK_URL, color:'#7C3AED'},
      {rel:'manifest', href:MANIFEST_URL}
    ];
    links.forEach(function(attrs) {
      var el = document.createElement('link');
      Object.keys(attrs).forEach(function(k) { el.setAttribute(k, attrs[k]); });
      head.appendChild(el);
    });

    var metas = [
      {name:'theme-color', content:'#7C3AED'},
      {name:'apple-mobile-web-app-capable', content:'yes'},
      {name:'apple-mobile-web-app-status-bar-style', content:'black-translucent'},
      {name:'apple-mobile-web-app-title', content:'ObsiRAG'}
    ];
    metas.forEach(function(attrs) {
      var el = document.createElement('meta');
      Object.keys(attrs).forEach(function(k) { el.setAttribute(k, attrs[k]); });
      head.appendChild(el);
    });
  }

  // Apply immediately
  applyHeadTags();

  // Watch for Streamlit overwriting our tags and re-apply
  var _applying = false;
  var observer = new MutationObserver(function(mutations) {
    if (_applying) return;
    var relevant = mutations.some(function(m) {
      return Array.from(m.addedNodes).some(function(n) {
        return n.nodeName === 'LINK' || n.nodeName === 'META';
      }) || Array.from(m.removedNodes).some(function(n) {
        return n.nodeName === 'LINK' || n.nodeName === 'META';
      });
    });
    if (relevant) {
      _applying = true;
      applyHeadTags();
      setTimeout(function() { _applying = false; }, 100);
    }
  });
  observer.observe(document.head, {childList: true});
})();
</script>
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
