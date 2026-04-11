"""
Pipeline d'indexation incrémentale du coffre Obsidian.
- Détecte les notes nouvelles / modifiées / supprimées via un état persistant (hash MD5)
- Traite les notes en lots avec une petite pause entre chacune pour ménager le CPU
- Ignore le répertoire obsirag/data (données internes d'ObsiRAG)
"""
import json
import time
from collections.abc import Callable
from pathlib import Path

from loguru import logger

from src.config import settings
from src.indexer.chunker import Chunk, TextChunker
from src.vault.parser import NoteParser


class IndexingPipeline:
    _SLEEP_BETWEEN_NOTES = 0.1  # secondes — mode normal, doux pour le CPU
    _FAST_BATCH_SIZE = 500       # chunks par lot en mode accéléré (première indexation)

    def __init__(self, chroma_store) -> None:
        self._chroma = chroma_store
        self._parser = NoteParser()
        self._chunker = TextChunker()
        self._state: dict[str, str] = self._load_state()  # rel_path → hash

    # ---- API publique ----

    def index_vault(self, on_progress: Callable[[str, int, int], None] | None = None) -> dict:
        """Indexe (ou met à jour) l'ensemble du coffre. Retourne les stats.

        Première exécution (état vide + ChromaDB vide) : mode accéléré automatique —
        les chunks sont regroupés en lots avant envoi à ChromaDB, sans pause entre notes.
        Les exécutions suivantes utilisent le mode normal incrémental.

        on_progress(current_note, processed, total) — appelé après chaque note traitée.
        """
        vault = settings.vault
        if not vault.exists():
            logger.error(f"Coffre introuvable : {vault}")
            return {"added": 0, "updated": 0, "deleted": 0, "skipped": 0, "errors": 0}

        all_md = {
            str(p.relative_to(vault)): p
            for p in vault.rglob("*.md")
            if not self._is_internal(p)
        }

        stats = {"added": 0, "updated": 0, "deleted": 0, "skipped": 0, "errors": 0}
        total = len(all_md)
        processed = 0

        # Suppression des notes retirées du coffre
        stale = set(self._state.keys()) - set(all_md.keys())
        for rel_path in stale:
            self._delete_from_index(rel_path)
            stats["deleted"] += 1

        # ---- Mode accéléré (première indexation uniquement) ----
        if self._is_first_run():
            logger.info(
                f"Mode accéléré activé — première indexation de {total} note(s). "
                f"Lot : {self._FAST_BATCH_SIZE} chunks."
            )
            chunk_buffer: list[Chunk] = []

            for rel_path, abs_path in all_md.items():
                try:
                    chunks = self._prepare_chunks(abs_path, rel_path)
                    chunk_buffer.extend(chunks)
                    stats["added"] += 1

                    if len(chunk_buffer) >= self._FAST_BATCH_SIZE:
                        self._chroma.add_chunks(chunk_buffer)
                        chunk_buffer.clear()

                except Exception as exc:
                    logger.error(f"Erreur d'indexation pour {rel_path} : {exc}")
                    stats["errors"] += 1

                processed += 1
                if on_progress:
                    on_progress(rel_path, processed, total)

            if chunk_buffer:
                self._chroma.add_chunks(chunk_buffer)

            self._save_state()
            logger.info(f"index_vault (accéléré) → {stats}")
            return stats

        # ---- Mode normal (incrémental) ----
        for rel_path, abs_path in all_md.items():
            try:
                current_hash = self._file_hash(abs_path)
                if self._state.get(rel_path) == current_hash:
                    stats["skipped"] += 1
                else:
                    action = "updated" if rel_path in self._state else "added"
                    self._index_file(abs_path, rel_path)
                    stats[action] += 1
                    time.sleep(self._SLEEP_BETWEEN_NOTES)

            except Exception as exc:
                logger.error(f"Erreur d'indexation pour {rel_path} : {exc}")
                stats["errors"] += 1

            processed += 1
            if on_progress:
                on_progress(rel_path, processed, total)

        self._save_state()
        logger.info(f"index_vault → {stats}")
        return stats

    def index_note(self, abs_path: Path) -> None:
        """Indexe (ou re-indexe) une note individuelle."""
        if self._is_internal(abs_path):
            return
        if not abs_path.exists() or abs_path.suffix != ".md":
            return
        rel_path = str(abs_path.relative_to(settings.vault))
        try:
            self._index_file(abs_path, rel_path)
            self._save_state()
            logger.debug(f"Note indexée : {rel_path}")
        except Exception as exc:
            logger.error(f"index_note({rel_path}) : {exc}")

    def remove_note(self, abs_path: Path) -> None:
        """Supprime une note de l'index."""
        rel_path = str(abs_path.relative_to(settings.vault))
        self._delete_from_index(rel_path)
        self._save_state()

    # ---- helpers privés ----

    def _is_first_run(self) -> bool:
        """Vrai si le coffre n'a jamais été indexé (état vide et ChromaDB vide).
        Déclenche le mode accéléré dans index_vault()."""
        return len(self._state) == 0 and self._chroma.count() == 0

    def _prepare_chunks(self, abs_path: Path, rel_path: str) -> list[Chunk]:
        """Parse et découpe une note sans l'envoyer à ChromaDB.
        Utilisé en mode accéléré pour accumuler les chunks avant envoi par lots."""
        # Ignorer les notes trop volumineuses
        try:
            size = abs_path.stat().st_size
        except OSError:
            size = 0
        if size > settings.max_note_size_bytes:
            logger.warning(
                f"Note ignorée (trop grande {size // 1024} KB > "
                f"{settings.max_note_size_bytes // 1024} KB) : {rel_path}"
            )
            return []
        note = self._parser.parse(abs_path)
        if note is None:
            return []
        self._state[rel_path] = note.metadata.file_hash
        chunks = self._chunker.chunk_note(note.metadata, note.sections)
        cap = settings.max_chunks_per_note
        if len(chunks) > cap:
            logger.warning(
                f"Note tronquée à {cap} chunks (était {len(chunks)}) : {rel_path}"
            )
            chunks = chunks[:cap]
        return chunks

    def _index_file(self, abs_path: Path, rel_path: str) -> None:
        # Ignorer les notes trop volumineuses
        try:
            size = abs_path.stat().st_size
        except OSError:
            size = 0
        if size > settings.max_note_size_bytes:
            logger.warning(
                f"Note ignorée (trop grande {size // 1024} KB > "
                f"{settings.max_note_size_bytes // 1024} KB) : {rel_path}"
            )
            return

        note = self._parser.parse(abs_path)
        if note is None:
            return

        # Supprimer les anciens chunks si la note existait déjà
        if rel_path in self._state:
            self._chroma.delete_by_file(rel_path)

        chunks = self._chunker.chunk_note(note.metadata, note.sections)
        cap = settings.max_chunks_per_note
        if len(chunks) > cap:
            logger.warning(
                f"Note tronquée à {cap} chunks (était {len(chunks)}) : {rel_path}"
            )
            chunks = chunks[:cap]
        if chunks:
            self._chroma.add_chunks(chunks)

        self._state[rel_path] = note.metadata.file_hash

    def _delete_from_index(self, rel_path: str) -> None:
        self._chroma.delete_by_file(rel_path)
        self._state.pop(rel_path, None)
        logger.debug(f"Note retirée de l'index : {rel_path}")

    @staticmethod
    def _is_internal(path: Path) -> bool:
        """Les fichiers écrits par ObsiRAG sont indexés comme les autres notes."""
        return False

    @staticmethod
    def _file_hash(path: Path) -> str:
        import hashlib
        return hashlib.md5(path.read_bytes()).hexdigest()

    def _load_state(self) -> dict[str, str]:
        f = settings.index_state_file
        if f.exists():
            try:
                return json.loads(f.read_text())
            except Exception:
                return {}
        return {}

    def _save_state(self) -> None:
        f = settings.index_state_file
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(self._state, ensure_ascii=False))
