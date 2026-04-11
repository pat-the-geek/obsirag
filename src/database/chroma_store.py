"""
Couche d'accès ChromaDB.
- Persistance sur disque dans obsirag/data/chroma
- Embedding via Ollama (Metal/ANE) si OLLAMA_EMBED_MODEL est défini,
  sinon via sentence-transformers en local (CPU, fallback)
- Recherche sémantique, par date, par entité NER, par tags
"""
from __future__ import annotations

import shutil
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import chromadb
from chromadb.errors import InternalError
from chromadb.utils.embedding_functions import EmbeddingFunction
from loguru import logger

from src.config import settings
from src.indexer.chunker import Chunk


def _build_embedding_function() -> EmbeddingFunction:
    """
    Choisit la fonction d'embedding selon la configuration :
    - OLLAMA_EMBED_MODEL défini  → OpenAI-compatible via Ollama (Metal/ANE)
    - sinon                      → SentenceTransformers local (CPU, fallback)

    IMPORTANT : changer de backend change la dimension des vecteurs.
    Si vous basculez d'un mode à l'autre sur une collection existante,
    supprimez le dossier data/chroma et relancez une indexation complète.
    """
    if settings.ollama_embed_model:
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
        logger.info(
            f"Embedding via Ollama ({settings.ollama_base_url}) : "
            f"{settings.ollama_embed_model}"
        )
        return OpenAIEmbeddingFunction(
            api_key="ollama",
            api_base=settings.ollama_base_url,
            model_name=settings.ollama_embed_model,
        )

    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    logger.info(f"Embedding local CPU : {settings.embedding_model}")
    return SentenceTransformerEmbeddingFunction(
        model_name=settings.embedding_model,
        device="cpu",
    )


# Durée de validité du cache list_notes() (secondes)
_LIST_NOTES_TTL = 30


class ChromaStore:
    def __init__(self) -> None:
        persist_dir = settings.chroma_persist_dir
        logger.info(f"Initialisation ChromaDB → {persist_dir}")

        embed_fn = _build_embedding_function()
        self._client, self._collection = self._init_with_recovery(
            persist_dir, embed_fn
        )
        # Verrou global : sérialise TOUTES les opérations ChromaDB
        # (l'index HNSW natif n'est pas thread-safe en écriture simultanée)
        self._lock = threading.RLock()
        self._list_notes_cache: list[dict] | None = None
        self._list_notes_ts: float = 0.0
        self._count_cache: int | None = None
        self._count_ts: float = 0.0

        logger.info(
            f"Collection '{settings.chroma_collection}' — "
            f"{self._collection.count()} chunks existants"
        )

    def _init_with_recovery(self, persist_dir: str, embed_fn: EmbeddingFunction):
        """Ouvre ChromaDB. En cas de corruption HNSW, efface et repart à zéro."""
        for attempt in range(2):
            try:
                client = chromadb.PersistentClient(path=persist_dir)
                collection = client.get_or_create_collection(
                    name=settings.chroma_collection,
                    embedding_function=embed_fn,
                    metadata={"hnsw:space": "cosine"},
                )
                # Force un count() pour détecter la corruption dès maintenant
                collection.count()
                return client, collection
            except InternalError as e:
                if attempt == 0:
                    logger.warning(
                        f"ChromaDB corrompu ({e}) — suppression et recréation de la base"
                    )
                    chroma_path = Path(persist_dir)
                    if chroma_path.exists():
                        shutil.rmtree(chroma_path)
                    # Réinitialiser aussi le fichier d'état d'indexation
                    try:
                        idx_state = settings.index_state_file
                        if idx_state.exists():
                            idx_state.write_text("{}", encoding="utf-8")
                    except Exception:
                        pass
                    logger.info("Base ChromaDB réinitialisée — une réindexation est nécessaire")
                else:
                    raise

    def _collection_get(self, **kwargs) -> dict:
        lock = getattr(self, "_lock", None)
        if lock is None:
            return self._collection.get(**kwargs)
        with lock:
            return self._collection.get(**kwargs)

    @staticmethod
    def _metadata_to_chunk(doc: str, meta: dict | None, *, fallback_value: str, score: float = 0.0) -> dict:
        metadata = dict(meta or {})
        chunk_ref = metadata.get("file_path") or metadata.get("note_title") or fallback_value
        return {
            "chunk_id": f"linked_{chunk_ref}",
            "text": doc,
            "metadata": metadata,
            "score": score,
        }

    def _get_chunks_by_metadata(self, metadata_key: str, value: str, limit: int = 2) -> list[dict]:
        try:
            raw = ChromaStore._collection_get(
                self,
                where={metadata_key: value},
                limit=limit,
                include=["documents", "metadatas"],
            )
        except Exception:
            return []

        return [
            ChromaStore._metadata_to_chunk(doc, meta, fallback_value=value)
            for doc, meta in zip(raw.get("documents") or [], raw.get("metadatas") or [])
        ]

    @staticmethod
    def _is_obsirag_generated_path(file_path: str) -> bool:
        normalized = file_path.replace("\\", "/")
        return "/obsirag/" in normalized or normalized.startswith("obsirag/")

    # ---- Écriture ----

    def add_chunks(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        t0 = time.perf_counter()
        with self._lock:
            self._collection.upsert(
                ids=[c.chunk_id for c in chunks],
                documents=[c.text for c in chunks],
                metadatas=[c.as_metadata() for c in chunks],
            )
        elapsed = time.perf_counter() - t0
        backend = settings.ollama_embed_model or settings.embedding_model
        logger.info(
            f"embed:add {len(chunks)} chunk(s) — {elapsed:.2f}s "
            f"({elapsed / len(chunks):.3f}s/chunk) backend={backend}"
        )
        self.invalidate_list_notes_cache()

    def delete_by_file(self, rel_path: str) -> None:
        try:
            total_deleted = 0
            with self._lock:
                while True:
                    results = self._collection.get(
                        where={"file_path": rel_path}, limit=500
                    )
                    ids = results.get("ids", [])
                    if not ids:
                        break
                    self._collection.delete(ids=ids)
                    total_deleted += len(ids)
            if total_deleted:
                logger.debug(f"Suppression de {total_deleted} chunk(s) pour {rel_path}")
                self.invalidate_list_notes_cache()
        except Exception as exc:
            logger.error(f"delete_by_file({rel_path}) : {exc}")

    # ---- Recherche sémantique ----

    def search(
        self,
        query: str,
        top_k: int = settings.search_top_k,
        where: dict | None = None,
    ) -> list[dict]:
        kwargs: dict[str, Any] = {
            "query_texts": [query],
            "n_results": min(top_k, max(1, self._collection.count())),
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        t0 = time.perf_counter()
        with self._lock:
            results = self._collection.query(**kwargs)
        elapsed = time.perf_counter() - t0
        backend = settings.ollama_embed_model or settings.embedding_model
        logger.debug(
            f"embed:search {elapsed:.3f}s backend={backend} top_k={top_k}"
        )
        return self._format_results(results)

    def search_by_date_range(
        self,
        query: str,
        since: datetime,
        until: datetime | None = None,
        top_k: int = settings.search_top_k,
    ) -> list[dict]:
        """Recherche sémantique filtrée sur date_modified_ts (Unix float — requis par ChromaDB)."""
        since_ts = since.timestamp()
        until_ts = (until or datetime.now()).timestamp()

        # Essai avec le filtre ChromaDB (nécessite que les chunks aient date_modified_ts)
        # Fallback sur filtrage Python post-hoc pour les chunks anciennement indexés
        try:
            where: dict = {
                "$and": [
                    {"date_modified_ts": {"$gte": since_ts}},
                    {"date_modified_ts": {"$lte": until_ts}},
                ]
            }
            results = self.search(query, top_k=top_k, where=where)
            if results:
                return results
        except Exception:
            pass

        # Fallback : recherche générale puis filtrage Python par date ISO
        candidates = self.search(query, top_k=top_k * 3)
        since_iso = since.isoformat()
        until_iso = (until or datetime.now()).isoformat()
        filtered = [
            c for c in candidates
            if since_iso <= (c["metadata"].get("date_modified") or "") <= until_iso
        ]
        return filtered[:top_k] if filtered else candidates[:top_k]

    def search_by_entity(
        self,
        entity: str,
        entity_type: str = "all",
        top_k: int = settings.search_top_k,
    ) -> list[dict]:
        """Récupère les chunks mentionnant une entité NER donnée."""
        fields = {
            "persons": ["ner_persons"],
            "orgs": ["ner_orgs"],
            "locations": ["ner_locations"],
            "misc": ["ner_misc"],
            "all": ["ner_persons", "ner_orgs", "ner_locations", "ner_misc"],
        }.get(entity_type, ["ner_persons", "ner_orgs", "ner_locations", "ner_misc"])

        # Recherche sémantique combinée à un filtre post-hoc (ChromaDB ne supporte pas
        # de recherche full-text sur les métadonnées — on filtre côté Python)
        candidates = self.search(entity, top_k=top_k * 3)
        entity_lower = entity.lower()
        filtered = [
            c for c in candidates
            if any(entity_lower in (c["metadata"].get(f) or "").lower() for f in fields)
        ]
        return filtered[:top_k] if filtered else candidates[:top_k]

    def search_by_tags(self, tags: list[str], top_k: int = settings.search_top_k) -> list[dict]:
        query = " ".join(tags)
        candidates = self.search(query, top_k=top_k * 2)
        tag_set = {t.lower() for t in tags}
        scored = [
            c for c in candidates
            if tag_set & {t.lower() for t in (c["metadata"].get("tags") or "").split(",") if t}
        ]
        return scored[:top_k] if scored else candidates[:top_k]

    def get_chunks_by_note_title(self, note_title: str, limit: int = 2) -> list[dict]:
        return self._get_chunks_by_metadata("note_title", note_title, limit=limit)

    def get_chunks_by_file_path(self, file_path: str, limit: int = 2) -> list[dict]:
        return self._get_chunks_by_metadata("file_path", file_path, limit=limit)

    def get_notes_by_file_paths(self, file_paths: list[str]) -> list[dict]:
        if not file_paths:
            return []
        wanted = set(file_paths)
        selected = [note for note in self.list_notes() if note["file_path"] in wanted]
        order = {file_path: index for index, file_path in enumerate(file_paths)}
        return sorted(selected, key=lambda note: order.get(note["file_path"], len(order)))

    def get_note_by_file_path(self, file_path: str) -> dict | None:
        notes = self.get_notes_by_file_paths([file_path])
        return notes[0] if notes else None

    def list_user_notes(self) -> list[dict]:
        return [
            note for note in self.list_notes()
            if not ChromaStore._is_obsirag_generated_path(note["file_path"])
        ]

    def list_generated_notes(self) -> list[dict]:
        return [
            note for note in self.list_notes()
            if ChromaStore._is_obsirag_generated_path(note["file_path"])
        ]

    # ---- Méta-informations ----

    def search_by_keyword(self, keyword: str, top_k: int = 10) -> list[dict]:
        """Recherche exacte par mot-clé dans le contenu des chunks (case-insensitive via double requête)."""
        results = []
        for term in [keyword, keyword.lower(), keyword.title()]:
            try:
                raw = ChromaStore._collection_get(
                    self,
                    where_document={"$contains": term},
                    include=["documents", "metadatas"],
                    limit=top_k * 2,
                )
                ids = raw.get("ids", [])
                docs = raw.get("documents", [])
                metas = raw.get("metadatas", [])
                seen_ids: set[str] = {r["chunk_id"] for r in results}
                for chunk_id, doc, meta in zip(ids, docs, metas):
                    if chunk_id not in seen_ids:
                        seen_ids.add(chunk_id)
                        results.append({
                            "chunk_id": chunk_id,
                            "text": doc,
                            "metadata": meta,
                            "score": 0.95,  # score fixe élevé : correspondance exacte
                        })
            except Exception:
                pass
        return results[:top_k]

    def search_by_note_title(self, title: str, top_k: int = 10) -> list[dict]:
        """Récupère les chunks d'une note dont le titre (métadonnée note_title)
        contient la chaîne donnée (insensible à la casse, correspondance partielle)."""
        results = []
        seen_ids: set[str] = set()
        for variant in {title, title.lower(), title.title(), title.upper()}:
            try:
                raw = ChromaStore._collection_get(
                    self,
                    where={"note_title": {"$eq": variant}},
                    include=["documents", "metadatas"],
                    limit=top_k * 2,
                )
                for chunk_id, doc, meta in zip(
                    raw.get("ids", []),
                    raw.get("documents", []),
                    raw.get("metadatas", []),
                ):
                    if chunk_id not in seen_ids:
                        seen_ids.add(chunk_id)
                        results.append({
                            "chunk_id": chunk_id,
                            "text": doc,
                            "metadata": meta,
                            "score": 0.98,  # correspondance exacte de titre
                        })
            except Exception:
                pass
        # Fallback : recherche partielle par contenu du titre via keyword
        if not results:
            results = self.search_by_keyword(title, top_k=top_k)
        return results[:top_k]


    def count(self) -> int:
        now = time.monotonic()
        if self._count_cache is not None and (now - self._count_ts) < _LIST_NOTES_TTL:
            return self._count_cache
        with self._lock:
            result = self._collection.count()
        self._count_cache = result
        self._count_ts = now
        return result

    def invalidate_list_notes_cache(self) -> None:
        """Invalide le cache list_notes et count (à appeler après indexation/suppression)."""
        self._list_notes_ts = 0.0
        self._count_ts = 0.0

    def list_notes(self) -> list[dict]:
        """Retourne la liste dédupliquée des notes indexées avec leurs métadonnées.

        Interroge directement le SQLite de ChromaDB pour éviter la limite
        "too many SQL variables" de l'API Rust. Résultat mis en cache 30 s.
        """
        now = time.monotonic()
        if self._list_notes_cache is not None and (now - self._list_notes_ts) < _LIST_NOTES_TTL:
            return self._list_notes_cache

        db_path = Path(settings.chroma_persist_dir) / "chroma.sqlite3"
        seen: dict[str, dict] = {}
        try:
            con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            try:
                rows = con.execute("""
                    SELECT
                        MAX(CASE WHEN m.key = 'file_path'    THEN m.string_value END),
                        MAX(CASE WHEN m.key = 'note_title'   THEN m.string_value END),
                        MAX(CASE WHEN m.key = 'date_modified' THEN m.string_value END),
                        MAX(CASE WHEN m.key = 'date_created'  THEN m.string_value END),
                        MAX(CASE WHEN m.key = 'tags'          THEN m.string_value END),
                        MAX(CASE WHEN m.key = 'wikilinks'     THEN m.string_value END)
                    FROM embedding_metadata m
                    INNER JOIN embeddings e ON e.id = m.id
                    INNER JOIN segments s   ON s.id = e.segment_id
                    INNER JOIN collections c ON c.id = s.collection
                    WHERE c.name = ? AND m.key IN (
                        'file_path','note_title','date_modified','date_created','tags','wikilinks'
                    )
                    GROUP BY m.id
                """, (settings.chroma_collection,)).fetchall()
            finally:
                con.close()
        except Exception as exc:
            logger.warning(f"list_notes SQLite direct failed ({exc}), fallback ChromaDB API")
            rows = []
            # Fallback : pagination via API ChromaDB
            batch_size = 500
            offset = 0
            while True:
                results = ChromaStore._collection_get(
                    self,
                    include=["metadatas"],
                    limit=batch_size,
                    offset=offset,
                )
                metadatas = results.get("metadatas") or []
                if not metadatas:
                    break
                for meta in metadatas:
                    fp = meta.get("file_path", "")
                    if fp and fp not in seen:
                        seen[fp] = {
                            "file_path": fp,
                            "title": meta.get("note_title", fp),
                            "date_modified": meta.get("date_modified", ""),
                            "date_created": meta.get("date_created", ""),
                            "tags": [t for t in (meta.get("tags") or "").split(",") if t],
                            "wikilinks": [w for w in (meta.get("wikilinks") or "").split(",") if w],
                        }
                if len(metadatas) < batch_size:
                    break
                offset += batch_size
        else:
            for fp, title, date_mod, date_cre, tags, wikilinks in rows:
                if fp and fp not in seen:
                    seen[fp] = {
                        "file_path": fp,
                        "title": title or fp,
                        "date_modified": date_mod or "",
                        "date_created": date_cre or "",
                        "tags": [t for t in (tags or "").split(",") if t],
                        "wikilinks": [w for w in (wikilinks or "").split(",") if w],
                    }

        self._list_notes_cache = sorted(seen.values(), key=lambda x: x["date_modified"], reverse=True)
        self._list_notes_ts = now
        return self._list_notes_cache

    def get_recently_modified(self, since: datetime) -> list[dict]:
        notes = self.list_notes()
        since_iso = since.isoformat()
        return [n for n in notes if (n.get("date_modified") or "") >= since_iso]

    def find_similar_notes(
        self,
        source_fp: str,
        existing_links: set[str],
        top_k: int = 10,
        threshold: float = 0.65,
    ) -> list[dict]:
        """Retourne les notes sémantiquement proches de source_fp sans lien existant.

        Chaque résultat : {"file_path", "title", "score", "excerpt"}.
        """
        # Récupère les chunks de la note source
        try:
            raw = ChromaStore._collection_get(
                self,
                where={"file_path": source_fp},
                include=["documents"],
                limit=3,
            )
        except Exception:
            return []

        docs = raw.get("documents", [])
        if not docs:
            return []

        query_text = " ".join(docs[:2])  # on utilise les 2 premiers chunks comme requête

        candidates = self.search(query_text, top_k=top_k + 5)

        seen_fps: set[str] = {source_fp}
        results: list[dict] = []
        for c in candidates:
            fp = c["metadata"].get("file_path", "")
            if not fp or fp in seen_fps:
                continue
            seen_fps.add(fp)
            # Exclure les notes déjà liées
            note_title = c["metadata"].get("note_title", fp)
            if fp in existing_links or note_title.lower() in existing_links:
                continue
            if c["score"] < threshold:
                continue
            results.append({
                "file_path": fp,
                "title": note_title,
                "score": c["score"],
                "excerpt": c["text"][:300],
            })
            if len(results) >= top_k:
                break

        return results

    # ---- helpers ----

    @staticmethod
    def _format_results(raw: dict) -> list[dict]:
        out: list[dict] = []
        ids = raw.get("ids", [[]])[0]
        docs = raw.get("documents", [[]])[0]
        metas = raw.get("metadatas", [[]])[0]
        dists = raw.get("distances", [[]])[0]

        for chunk_id, doc, meta, dist in zip(ids, docs, metas, dists):
            out.append({
                "chunk_id": chunk_id,
                "text": doc,
                "metadata": meta or {},
                "score": round(1 - dist, 4),  # cosine distance → similarity
            })
        return out
