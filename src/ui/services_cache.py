"""
Singleton des services ObsiRAG.

Stratégie :
- L'initialisation de ServiceManager démarre dans un thread dédié dès le premier
  appel à get_services(), sans bloquer le thread principal Streamlit.
- L'UI affiche un écran de chargement et se rerun toutes les 500 ms jusqu'à
  ce que l'init soit terminée.
- _services_instance : singleton process, écrit une seule fois par le thread init.
"""
import base64
import json
import queue
import time
import threading
import inspect
from pathlib import Path

import streamlit as st

from src.services import ServiceManager
from src.ui.html_embed import run_inline_script

_lock = threading.Lock()
_services_instance: ServiceManager | None = None
_init_thread: threading.Thread | None = None
_init_done = threading.Event()
_init_error: Exception | None = None
_step_queue: "queue.Queue[str]" = queue.Queue()

_STATIC_DIR = Path(__file__).parent / "static"


def _build_data_url(file_name: str, mime_type: str) -> str:
  payload = base64.b64encode((_STATIC_DIR / file_name).read_bytes()).decode("ascii")
  return f"data:{mime_type};base64,{payload}"


_APPLE_TOUCH_ICON_URL = _build_data_url("apple-touch-icon.png", "image/png")
_FAVICON_32_URL = _build_data_url("favicon-32x32.png", "image/png")
_FAVICON_16_URL = _build_data_url("favicon-16x16.png", "image/png")
_FAVICON_ICO_URL = _build_data_url("favicon.ico", "image/x-icon")
_MASK_ICON_URL = _build_data_url("safari-pinned-tab.svg", "image/svg+xml")
_MANIFEST_URL = "data:application/manifest+json," + json.dumps(
  {
    "name": "ObsiRAG",
    "short_name": "ObsiRAG",
    "description": "Votre coffre Obsidian, augmente par l'IA locale",
    "start_url": "/",
    "scope": "/",
    "display": "standalone",
    "background_color": "#0d1117",
    "theme_color": "#7C3AED",
    "icons": [
      {"src": _FAVICON_16_URL, "sizes": "16x16", "type": "image/png"},
      {"src": _FAVICON_32_URL, "sizes": "32x32", "type": "image/png"},
      {"src": _APPLE_TOUCH_ICON_URL, "sizes": "180x180", "type": "image/png"},
    ],
  },
  separators=(",", ":"),
)


def _is_services_instance_compatible(instance: ServiceManager) -> bool:
  chroma = getattr(instance, "chroma", None)
  rag = getattr(instance, "rag", None)
  required_chroma_methods = (
    "list_notes_sorted_by_title",
    "list_note_folders",
    "list_note_tags",
    "list_notes_by_type",
    "list_recent_notes",
    "list_user_notes",
    "list_generated_notes",
    "count_notes",
    "get_backlinks",
  )
  chroma_compatible = chroma is not None and all(callable(getattr(chroma, name, None)) for name in required_chroma_methods)

  query_stream = getattr(rag, "query_stream", None)
  if not callable(query_stream):
    return False
  try:
    params = inspect.signature(query_stream).parameters
  except (TypeError, ValueError):
    return False
  rag_compatible = "progress_callback" in params

  return chroma_compatible and rag_compatible


def _reset_cached_services() -> None:
  global _services_instance, _init_thread, _init_error
  with _lock:
    _services_instance = None
    _init_thread = None
    _init_error = None
    _init_done.clear()


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

_HEAD_TAGS_SCRIPT = """
(function() {
  var ICON_URL = __APPLE_TOUCH_ICON_URL__;
  var MANIFEST_URL = __MANIFEST_URL__;
  var MASK_URL = __MASK_ICON_URL__;
  var FAVICON_ICO = __FAVICON_ICO_URL__;
  var FAVICON_32 = __FAVICON_32_URL__;
  var FAVICON_16 = __FAVICON_16_URL__;

  function applyHeadTags() {
    var head = document.head;
    head.querySelectorAll(
      'link[rel*="icon"], link[rel="manifest"], link[rel="mask-icon"], ' +
      'meta[name="theme-color"], meta[name^="apple-mobile-web-app"]'
    ).forEach(function(el) { el.remove(); });

    [
      {rel:'shortcut icon', type:'image/x-icon', href:FAVICON_ICO},
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
""".replace("__APPLE_TOUCH_ICON_URL__", json.dumps(_APPLE_TOUCH_ICON_URL)) \
  .replace("__MANIFEST_URL__", json.dumps(_MANIFEST_URL)) \
  .replace("__MASK_ICON_URL__", json.dumps(_MASK_ICON_URL)) \
  .replace("__FAVICON_ICO_URL__", json.dumps(_FAVICON_ICO_URL)) \
  .replace("__FAVICON_32_URL__", json.dumps(_FAVICON_32_URL)) \
  .replace("__FAVICON_16_URL__", json.dumps(_FAVICON_16_URL))


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
    run_inline_script(_HEAD_TAGS_SCRIPT)

    # Lance le thread d'init si ce n'est pas encore fait
    _ensure_init_started()

    # Chemin rapide : init terminée avec succès
    if _services_instance is not None:
      if not _is_services_instance_compatible(_services_instance):
        _reset_cached_services()
        st.session_state["_startup_steps"] = [
          "Compatibilite runtime detectee — reconstruction des services…"
        ]
        _ensure_init_started()
      else:
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
