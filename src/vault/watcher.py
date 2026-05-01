"""
Surveillance du coffre Obsidian avec watchdog.
Déclenche l'indexation incrémentale à chaque modification de fichier .md,
avec debounce de 3 secondes pour éviter les rafales.
Les fichiers dans obsirag/data sont ignorés (écrits par ObsiRAG lui-même).
"""
import threading
import time
import hashlib
from pathlib import Path

from loguru import logger
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from src.config import settings


class _DebouncedHandler(FileSystemEventHandler):
    """Handler qui accumule les événements et les traite après un délai."""

    DEBOUNCE_SECONDS = 3.0

    def __init__(self, indexer) -> None:
        super().__init__()
        self._indexer = indexer
        self._pending: dict[str, str] = {}  # path → event_type
        self._last_indexed_hash: dict[str, str] = {}
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def on_created(self, event: FileSystemEvent) -> None:
        self._queue(event.src_path, "created")

    def on_modified(self, event: FileSystemEvent) -> None:
        self._queue(event.src_path, "modified")

    def on_deleted(self, event: FileSystemEvent) -> None:
        self._queue(event.src_path, "deleted")

    def on_moved(self, event: FileSystemEvent) -> None:
        self._queue(event.src_path, "deleted")
        self._queue(event.dest_path, "created")

    def _queue(self, path: str, event_type: str) -> None:
        if not path.endswith(".md"):
            return

        with self._lock:
            self._pending[path] = event_type
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self.DEBOUNCE_SECONDS, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            pending = dict(self._pending)
            self._pending.clear()

        if not pending:
            return

        logger.info(f"Watcher : {len(pending)} fichier(s) à retraiter")
        for path, evt_type in pending.items():
            try:
                p = Path(path)
                if evt_type == "deleted":
                    self._last_indexed_hash.pop(path, None)
                    self._indexer.remove_note(p)
                else:
                    current_hash = self._content_hash(p)
                    if current_hash and self._last_indexed_hash.get(path) == current_hash:
                        logger.debug(f"Watcher : aucun changement de contenu pour {p.name}, indexation ignorée")
                        continue
                    self._indexer.index_note(p)
                    if current_hash:
                        self._last_indexed_hash[path] = current_hash
            except Exception as exc:
                logger.error(f"Erreur lors du traitement de {path} : {exc}")

    @staticmethod
    def _content_hash(path: Path) -> str | None:
        try:
            if not path.exists() or not path.is_file():
                return None
            return hashlib.md5(path.read_bytes()).hexdigest()
        except Exception:
            return None


class VaultWatcher:
    def __init__(self, indexer) -> None:
        self._indexer = indexer
        self._observer: Observer | None = None

    def start(self) -> None:
        vault = settings.vault
        if not vault.exists():
            logger.warning(f"Coffre introuvable : {vault}. Watcher non démarré.")
            return

        handler = _DebouncedHandler(self._indexer)
        self._observer = Observer()
        self._observer.schedule(handler, str(vault), recursive=True)
        self._observer.start()
        logger.info(f"Surveillance du coffre activée : {vault}")

    def stop(self) -> None:
        if self._observer and self._observer.is_alive():
            self._observer.stop()
            self._observer.join(timeout=5)
            logger.info("Vault watcher arrêté")
