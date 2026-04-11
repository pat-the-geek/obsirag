"""
Singleton des services ObsiRAG.

Stratégie :
- L'initialisation de ServiceManager démarre dans un thread dédié dès le premier
  appel à get_services(), sans bloquer le thread principal Streamlit.
- L'UI affiche un écran de chargement et se rerun toutes les 500 ms jusqu'à
  ce que l'init soit terminée.
- _services_instance : singleton process, écrit une seule fois par le thread init.
"""
import queue
import time
import threading

import streamlit as st

from src.services import ServiceManager

_lock = threading.Lock()
_services_instance: ServiceManager | None = None
_init_thread: threading.Thread | None = None
_init_done = threading.Event()
_init_error: Exception | None = None
_step_queue: "queue.Queue[str]" = queue.Queue()


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
    head.querySelectorAll(
      'link[rel*="icon"], link[rel="manifest"], link[rel="mask-icon"], ' +
      'meta[name="theme-color"], meta[name^="apple-mobile-web-app"]'
    ).forEach(function(el) { el.remove(); });

    [
      {rel:'icon', type:'image/x-icon', href:FAVICON_ICO},
      {rel:'icon', type:'image/png', sizes:'32x32', href:FAVICON_32},
      {rel:'icon', type:'image/png', sizes:'16x16', href:FAVICON_16},
      {rel:'apple-touch-icon', sizes:'180x180', href:ICON_URL},
      {rel:'mask-icon', href:MASK_URL, color:'#7C3AED'},
      {rel:'manifest', href:MANIFEST_URL}
    ].forEach(function(attrs) {
      var el = document.createElement('link');
      Object.keys(attrs).forEach(function(k) { el.setAttribute(k, attrs[k]); });
      head.appendChild(el);
    });

    [
      {name:'theme-color', content:'#7C3AED'},
      {name:'apple-mobile-web-app-capable', content:'yes'},
      {name:'apple-mobile-web-app-status-bar-style', content:'black-translucent'},
      {name:'apple-mobile-web-app-title', content:'ObsiRAG'}
    ].forEach(function(attrs) {
      var el = document.createElement('meta');
      Object.keys(attrs).forEach(function(k) { el.setAttribute(k, attrs[k]); });
      head.appendChild(el);
    });
  }

  // Apply immediately
  applyHeadTags();

  // MutationObserver: re-apply whenever Streamlit modifies <head>
  var _applying = false;
  var observer = new MutationObserver(function(mutations) {
    if (_applying) return;
    var relevant = mutations.some(function(m) {
      return Array.from(m.addedNodes).concat(Array.from(m.removedNodes)).some(function(n) {
        return n.nodeName === 'LINK' || n.nodeName === 'META';
      });
    });
    if (relevant) {
      _applying = true;
      applyHeadTags();
      setTimeout(function() { _applying = false; }, 200);
    }
  });
  observer.observe(document.head, {childList: true});

  // Interval fallback: re-apply a few times after page load to catch React hydration
  // Use a longer interval (2s) with fewer iterations (4) to reduce DOM churn
  var _elapsed = 0;
  var interval = setInterval(function() {
    _elapsed += 2000;
    applyHeadTags();
    if (_elapsed >= 8000) clearInterval(interval);
  }, 2000);
})();
</script>
"""


def _run_init() -> None:
    """Exécuté dans un thread daemon : construit ServiceManager et signale la fin."""
    global _services_instance, _init_error

    def on_step(msg: str) -> None:
        _step_queue.put(msg)

    try:
        instance = ServiceManager(on_step=on_step)
        with _lock:
            _services_instance = instance
    except Exception as exc:  # noqa: BLE001
        _init_error = exc
    finally:
        _init_done.set()


def _ensure_init_started() -> None:
    """Lance le thread d'initialisation une seule fois, quels que soient les reruns."""
    global _init_thread
    with _lock:
        if _init_thread is None:
            _init_thread = threading.Thread(
                target=_run_init, daemon=True, name="service-init"
            )
            _init_thread.start()


def get_services() -> ServiceManager:
    # Injecte le CSS compact sur chaque page (idempotent)
    st.markdown(_COMPACT_CSS, unsafe_allow_html=True)

    # Lance le thread d'init si ce n'est pas encore fait
    _ensure_init_started()

    # Chemin rapide : init terminée avec succès
    if _services_instance is not None:
        _services_instance.signal_ui_active()
        st.session_state["_svc_ready"] = True
        return _services_instance

    # Init terminée mais en erreur
    if _init_done.is_set():
        st.error(f"❌ Erreur au démarrage d'ObsiRAG : {_init_error}")
        st.stop()

    # Init encore en cours — collecter les étapes et afficher l'écran de chargement
    if "_startup_steps" not in st.session_state:
        st.session_state["_startup_steps"] = []

    # Drainer la queue des messages de progression
    while True:
        try:
            st.session_state["_startup_steps"].append(_step_queue.get_nowait())
        except queue.Empty:
            break

    steps: list[str] = st.session_state["_startup_steps"]

    # Centrer l'écran de chargement dans la colonne du milieu
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("### ⏳ Démarrage d'ObsiRAG…")
        if steps:
            for step in steps:
                st.write(step)
        else:
            st.write("Initialisation en cours…")

    # Rerun dans 500 ms pour rafraîchir la progression
    time.sleep(0.5)
    st.rerun()
