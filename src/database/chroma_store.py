"""
Couche d'accès ChromaDB.
- Persistance sur disque dans obsirag/data/chroma
- Embedding via sentence-transformers (local, multilingue)
- Recherche sémantique, par date, par entité NER, par tags
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from loguru import logger

from src.config import settings
from src.indexer.chunker import Chunk


class ChromaStore:
    def __init__(self) -> None:
        persist_dir = settings.chroma_persist_dir
        logger.info(f"Initialisation ChromaDB → {persist_dir}")

        self._client = chromadb.PersistentClient(path=persist_dir)

        embed_fn = SentenceTransformerEmbeddingFunction(
            model_name=settings.embedding_model,
            device="cpu",
        )
        logger.info(f"Modèle d'embedding chargé : {settings.embedding_model}")

        self._collection = self._client.get_or_create_collection(
            name=settings.chroma_collection,
            embedding_function=embed_fn,
            metadata={"hnsw:space": "cosine"},
        )

        logger.info(
            f"Collection '{settings.chroma_collection}' — "
            f"{self._collection.count()} chunks existants"
        )

    # ---- Écriture ----

    def add_chunks(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        self._collection.upsert(
            ids=[c.chunk_id for c in chunks],
            documents=[c.text for c in chunks],
            metadatas=[c.as_metadata() for c in chunks],
        )
        logger.debug(f"Upsert de {len(chunks)} chunk(s)")

    def delete_by_file(self, rel_path: str) -> None:
        try:
            results = self._collection.get(where={"file_path": rel_path}, limit=10_000)
            ids = results.get("ids", [])
            if ids:
                self._collection.delete(ids=ids)
                logger.debug(f"Suppression de {len(ids)} chunk(s) pour {rel_path}")
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

        results = self._collection.query(**kwargs)
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

    # ---- Méta-informations ----

    def count(self) -> int:
        return self._collection.count()

    def list_notes(self) -> list[dict]:
        """Retourne la liste dédupliquée des notes indexées avec leurs métadonnées."""
        if self._collection.count() == 0:
            return []
        results = self._collection.get(
            include=["metadatas"],
            limit=100_000,
        )
        seen: dict[str, dict] = {}
        for meta in results.get("metadatas", []):
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
        return sorted(seen.values(), key=lambda x: x["date_modified"], reverse=True)

    def get_recently_modified(self, since: datetime) -> list[dict]:
        notes = self.list_notes()
        since_iso = since.isoformat()
        return [n for n in notes if (n.get("date_modified") or "") >= since_iso]

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
                "metadata": meta,
                "score": round(1 - dist, 4),  # cosine distance → similarity
            })
        return out
