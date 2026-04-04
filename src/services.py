"""
ServiceManager — point d'entrée unique pour tous les composants ObsiRAG.
Instancié une seule fois via @st.cache_resource dans l'UI.
"""
import threading
from loguru import logger

from src.config import settings
from src.logger import configure_logging


class ServiceManager:
    def __init__(self) -> None:
        configure_logging(settings.log_level, settings.log_dir)
        logger.info("=== Démarrage ObsiRAG ===")

        self._init_data_dirs()

        from src.database.chroma_store import ChromaStore
        from src.ai.lmstudio import LMStudioClient
        from src.ai.rag import RAGPipeline
        from src.indexer.pipeline import IndexingPipeline
        from src.graph.builder import GraphBuilder
        from src.learning.autolearn import AutoLearner
        from src.vault.watcher import VaultWatcher

        self.chroma = ChromaStore()
        self.llm = LMStudioClient()
        self.rag = RAGPipeline(self.chroma, self.llm)
        self.indexer = IndexingPipeline(self.chroma)
        self.graph = GraphBuilder()
        self.learner = AutoLearner(self.chroma, self.rag, self.indexer)
        self.watcher = VaultWatcher(self.indexer)

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
        try:
            logger.info("Indexation initiale du coffre…")
            stats = self.indexer.index_vault()
            logger.info(
                f"Indexation terminée — "
                f"{stats['added']} ajoutées, {stats['updated']} mises à jour, "
                f"{stats['deleted']} supprimées, {stats['skipped']} inchangées"
            )
        except Exception as exc:
            logger.error(f"Erreur lors de l'indexation initiale : {exc}")
