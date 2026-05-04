from __future__ import annotations

import os
import signal
import threading
import time
from datetime import UTC, datetime

from loguru import logger

from src.ai.ollama_client import OllamaClient
from src.ai.rag import RAGPipeline
from src.config import settings
from src.database import make_vector_store
from src.indexer.pipeline import IndexingPipeline
from src.learning.autolearn import AutoLearner
from src.learning.runtime_state import save_autolearn_runtime_state
from src.logger import configure_logging
from src.metrics import MetricsRecorder


class AutolearnWorker:
    def __init__(self) -> None:
        configure_logging(settings.log_level, settings.log_dir)
        self._stop_event = threading.Event()
        self._metrics = MetricsRecorder(lambda: settings.data_dir / "stats" / "metrics.json")
        self._chroma = make_vector_store()
        self._llm = OllamaClient()
        self._rag = RAGPipeline(self._chroma, self._llm, metrics=self._metrics)
        self._indexer = IndexingPipeline(self._chroma)
        self._learner = AutoLearner(
            self._chroma,
            self._rag,
            self._indexer,
            ui_active_fn=lambda: False,
            metrics=self._metrics,
        )
        self._started_at = datetime.now(UTC).isoformat()

    def _persist_runtime(self) -> None:
        next_run = None
        try:
            job = self._learner._scheduler.get_job("autolearn_cycle")
            if job and job.next_run_time:
                next_run = job.next_run_time.isoformat()
        except Exception:
            next_run = None

        save_autolearn_runtime_state(
            {
                "managedBy": "worker",
                "running": not self._stop_event.is_set(),
                "pid": os.getpid(),
                "startedAt": self._started_at,
                "nextRunAt": next_run,
            }
        )

    def _handle_signal(self, signum: int, _frame) -> None:
        logger.info(f"Auto-learner worker: arrêt demandé (signal {signum})")
        self._stop_event.set()

    def run(self) -> None:
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        logger.info("=== Démarrage worker auto-learner séparé ===")
        self._persist_runtime()

        try:
            self._learner.start()
            self._persist_runtime()

            while not self._stop_event.wait(10):
                self._persist_runtime()
        finally:
            try:
                self._learner.stop()
            except Exception as exc:
                logger.warning(f"Auto-learner worker: erreur arrêt scheduler : {exc}")
            try:
                self._llm.unload()
            except Exception as exc:
                logger.warning(f"Auto-learner worker: erreur fermeture client LLM : {exc}")

            save_autolearn_runtime_state(
                {
                    "managedBy": "worker",
                    "running": False,
                    "pid": os.getpid(),
                    "startedAt": self._started_at,
                    "nextRunAt": None,
                }
            )
            logger.info("=== Arrêt worker auto-learner séparé ===")


def main() -> None:
    worker = AutolearnWorker()
    worker.run()


if __name__ == "__main__":
    main()