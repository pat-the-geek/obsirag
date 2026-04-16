"""
ServiceManager — point d'entrée unique pour tous les composants ObsiRAG.
Instancié une seule fois via @st.cache_resource dans l'UI.
"""
import time
import threading
from loguru import logger

from src.config import settings
from src.logger import configure_logging
from src.metrics import MetricsRecorder
from src.storage.json_state import JsonStateStore

# Durée d'inactivité UI (en secondes) avant déchargement automatique du modèle.
# Le watchdog vérifie toutes les 30 s — mettre > 30 pour un déclenchement fiable.
_UI_IDLE_TIMEOUT = 120


class ServiceManager:
    indexing_status: dict  # {"running": bool, "processed": int, "total": int, "current": str}

    def __init__(self, on_step=None) -> None:
        """
        on_step : callable(message: str) optionnel, appelé à chaque étape
                  pour permettre à l'UI d'afficher la progression.
        """
        _step = on_step or (lambda msg: None)
        self.indexing_status = {"running": False, "processed": 0, "total": 0, "current": ""}
        self._last_ui_activity: float = 0.0
        self.metrics = MetricsRecorder(lambda: settings.data_dir / "stats" / "metrics.json")
        self._persist_indexing_status()

        configure_logging(settings.log_level, settings.log_dir)
        logger.info("=== Démarrage ObsiRAG ===")

        _step("📁 Initialisation des répertoires de données…")
        self._init_data_dirs()

        _step("🗄️ Chargement de ChromaDB et du modèle d'embedding (peut prendre 30 s)…")
        from src.database.chroma_store import ChromaStore
        self.chroma = ChromaStore()

        _step("🤖 Chargement du modèle MLX (peut prendre 30-60 s)…")
        from src.ai.mlx_client import MlxClient
        self.llm = MlxClient()
        self.llm.load()

        _step("🔗 Initialisation du pipeline RAG…")
        from src.ai.rag import RAGPipeline
        self.rag = RAGPipeline(self.chroma, self.llm, metrics=self.metrics)

        _step("🗂️ Initialisation du pipeline d'indexation…")
        from src.indexer.pipeline import IndexingPipeline
        self.indexer = IndexingPipeline(self.chroma)

        _step("🧠 Initialisation du graphe de connaissances…")
        from src.graph.builder import GraphBuilder
        self.graph = GraphBuilder()

        _step("📚 Initialisation de l'auto-learner…")
        from src.learning.autolearn import AutoLearner
        self.learner = AutoLearner(self.chroma, self.rag, self.indexer, ui_active_fn=self.is_ui_active, metrics=self.metrics)

        _step("👁️ Démarrage du watcher de coffre…")
        from src.vault.watcher import VaultWatcher
        self.watcher = VaultWatcher(self.indexer)

        _step("🚀 Lancement des services en arrière-plan…")
        self._start_background_services()
        logger.info("Tous les services sont opérationnels")
        _step("✅ Tous les services sont opérationnels")

    def _init_data_dirs(self) -> None:
        # Données système (volume Docker)
        for d in [
            settings.data_dir,
            settings.data_dir / "stats",
            settings.data_dir / "queries",
            settings.graph_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

        # Markdown dans le coffre (visibles dans Obsidian)
        for d in [
            settings.insights_dir,
            settings.synthesis_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def _start_background_services(self) -> None:
        self.watcher.start()
        logger.info("Vault watcher démarré")

        if settings.autolearn_enabled:
            self.learner.start()
            logger.info("Auto-learner démarré")

        thread = threading.Thread(
            target=self._initial_index,
            daemon=True,
            name="initial-indexer",
        )
        thread.start()

        self._start_model_watchdog()

    # ---- Gestion du cycle de vie du modèle LLM ----

    def signal_ui_active(self) -> None:
        """Marque l'UI comme active et charge le modèle si nécessaire."""
        self._last_ui_activity = time.monotonic()
        if not self.llm.is_loaded():
            logger.info("Activité UI détectée — chargement du modèle MLX…")
            threading.Thread(target=self.llm.load, daemon=True, name="llm-autoload").start()

    def is_ui_active(self) -> bool:
        """Retourne True si une session UI a été active dans la fenêtre d'inactivité."""
        return (time.monotonic() - self._last_ui_activity) < _UI_IDLE_TIMEOUT

    def is_scheduler_active(self) -> bool:
        """Retourne True si l'auto-learner est en cours d'exécution."""
        return (
            settings.autolearn_enabled
            and hasattr(self, "learner")
            and self.learner.processing_status.get("active", False)
        )

    def _start_model_watchdog(self) -> None:
        """Lance un thread de surveillance qui décharge le modèle quand personne ne l'utilise."""
        def _watch() -> None:
            while True:
                time.sleep(30)
                try:
                    if (
                        self.llm.is_loaded()
                        and not self.is_ui_active()
                        and not self.is_scheduler_active()
                    ):
                        logger.info(
                            "Watchdog : UI inactif + aucun scheduler actif — déchargement du modèle MLX"
                        )
                        self.llm.unload()
                except Exception as exc:
                    logger.warning(f"Watchdog modèle erreur : {exc}")

        t = threading.Thread(target=_watch, daemon=True, name="model-watchdog")
        t.start()
        logger.info("Watchdog modèle démarré")

    def _status_store(self) -> JsonStateStore:
        return JsonStateStore(settings.data_dir / "stats" / "service_manager_status.json")

    def _persist_indexing_status(self) -> None:
        try:
            self._status_store().save(self.indexing_status, ensure_ascii=False)
        except Exception:
            pass

    def _initial_index(self) -> None:
        def _on_progress(current: str, processed: int, total: int) -> None:
            self.indexing_status.update({"running": True, "processed": processed, "total": total, "current": current})
            self._persist_indexing_status()

        try:
            logger.info("Indexation initiale du coffre…")
            self.indexing_status = {"running": True, "processed": 0, "total": 0, "current": ""}
            self._persist_indexing_status()
            stats = self.indexer.index_vault(on_progress=_on_progress)
            logger.info(
                f"Indexation terminée — "
                f"{stats['added']} ajoutées, {stats['updated']} mises à jour, "
                f"{stats['deleted']} supprimées, {stats['skipped']} inchangées"
            )
        except Exception as exc:
            logger.error(f"Erreur lors de l'indexation initiale : {exc}")
        finally:
            self.indexing_status["running"] = False
            self._persist_indexing_status()
