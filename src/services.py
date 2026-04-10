"""
ServiceManager — point d'entrée unique pour tous les composants ObsiRAG.
Instancié une seule fois via @st.cache_resource dans l'UI.
"""
import threading
from loguru import logger

from src.config import settings
from src.logger import configure_logging


class ServiceManager:
    indexing_status: dict  # {"running": bool, "processed": int, "total": int, "current": str}

    def __init__(self, on_step=None) -> None:
        """
        on_step : callable(message: str) optionnel, appelé à chaque étape
                  pour permettre à l'UI d'afficher la progression.
        """
        _step = on_step or (lambda msg: None)
        self.indexing_status = {"running": False, "processed": 0, "total": 0, "current": ""}

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

        _step("🔗 Initialisation du pipeline RAG…")
        from src.ai.rag import RAGPipeline
        self.rag = RAGPipeline(self.chroma, self.llm)

        _step("🗂️ Initialisation du pipeline d'indexation…")
        from src.indexer.pipeline import IndexingPipeline
        self.indexer = IndexingPipeline(self.chroma)

        _step("🧠 Initialisation du graphe de connaissances…")
        from src.graph.builder import GraphBuilder
        self.graph = GraphBuilder()

        _step("📚 Initialisation de l'auto-learner…")
        from src.learning.autolearn import AutoLearner
        self.learner = AutoLearner(self.chroma, self.rag, self.indexer)

        _step("👁️ Démarrage du watcher de coffre…")
        from src.vault.watcher import VaultWatcher
        self.watcher = VaultWatcher(self.indexer)

        _step("🚀 Lancement des services en arrière-plan…")
        self._start_background_services()
        logger.info("Tous les services sont opérationnels")

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

    def _initial_index(self) -> None:
        def _on_progress(current: str, processed: int, total: int) -> None:
            self.indexing_status.update({"running": True, "processed": processed, "total": total, "current": current})

        try:
            logger.info("Indexation initiale du coffre…")
            self.indexing_status = {"running": True, "processed": 0, "total": 0, "current": ""}
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
