"""
Couche d'accès LanceDB — remplacement drop-in de ChromaStore.

Interface publique identique à ChromaStore ; aucun fichier consommateur
n'a besoin d'être modifié.  Avantages par rapport à ChromaDB :
  - Multi-process safe (format Lance, pas d'index HNSW partageable)
  - Filtres metadata via SQL (colonnaire Arrow)
  - FTS intégré sans contournement SQLite
  - Pas de SIGSEGV lors des accès concurrents tests/service
"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa
import requests
from loguru import logger

from src.config import settings
from src.indexer.chunker import Chunk

# ── Schéma PyArrow ──────────────────────────────────────────────────────────
# Doit couvrir TOUS les champs de Chunk.as_metadata() + le vecteur.
# Les champs numériques optionnels utilisent float64/int64 nullable.

_DIMS = 768  # nomic-embed-text & all-MiniLM-L6-v2 ; mis à jour au 1er embed

def _build_schema(dims: int) -> pa.Schema:
    return pa.schema([
        pa.field("chunk_id",        pa.string()),
        pa.field("text",            pa.string()),
        pa.field("file_path",       pa.string()),
        pa.field("note_title",      pa.string()),
        pa.field("section_title",   pa.string()),
        pa.field("section_level",   pa.int64()),
        pa.field("chunk_index",     pa.int64()),
        pa.field("date_modified",   pa.string()),
        pa.field("date_created",    pa.string()),
        pa.field("date_modified_ts", pa.float64()),
        pa.field("date_created_ts",  pa.float64()),
        pa.field("tags",            pa.string()),
        pa.field("wikilinks",       pa.string()),
        pa.field("ner_persons",     pa.string()),
        pa.field("ner_orgs",        pa.string()),
        pa.field("ner_locations",   pa.string()),
        pa.field("ner_misc",        pa.string()),
        pa.field("file_hash",       pa.string()),
        pa.field("vector",          pa.list_(pa.float32(), dims)),
    ])


# ── Embedding ────────────────────────────────────────────────────────────────

def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Calcule les embeddings pour une liste de textes (batch)."""
    if settings.ollama_embed_model:
        return _embed_ollama(texts)
    return _embed_sentence_transformers(texts)


def _embed_ollama(texts: list[str]) -> list[list[float]]:
    base = settings.ollama_base_url.rstrip("/v1").rstrip("/")
    results: list[list[float]] = []
    for text in texts:
        r = requests.post(
            f"{base}/api/embeddings",
            json={"model": settings.ollama_embed_model, "prompt": text},
            timeout=120,
        )
        r.raise_for_status()
        results.append(r.json()["embedding"])
    return results


def _embed_sentence_transformers(texts: list[str]) -> list[list[float]]:
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(settings.embedding_model)
    return model.encode(texts, convert_to_numpy=True).tolist()


# ── Helpers ───────────────────────────────────────────────────────────────────

_LIST_NOTES_TTL = 30


def _is_retrieval_artifact_path(file_path: str) -> bool:
    normalized = str(file_path or "").replace("\\", "/").lower()
    if not normalized:
        return False
    if "/obsirag/" not in normalized and not normalized.startswith("obsirag/"):
        return False
    name = Path(normalized).name
    return name.startswith("chat_") or name.startswith("web_")


def _is_obsirag_generated_path(file_path: str) -> bool:
    normalized = file_path.replace("\\", "/")
    return "/obsirag/" in normalized or normalized.startswith("obsirag/")


def _note_type_for_path(file_path: str) -> str:
    normalized = file_path.replace("\\", "/").lower()
    if "/obsirag/insights/" in normalized or normalized.startswith("obsirag/insights/"):
        return "insight"
    if "/obsirag/synapses/" in normalized or normalized.startswith("obsirag/synapses/"):
        return "synapse"
    if "/obsirag/synthesis/" in normalized or normalized.startswith("obsirag/synthesis/"):
        return "report"
    return "user"


def _row_to_chunk(row: dict, score: float = 0.0) -> dict:
    """Convertit une ligne LanceDB au format chunk ObsiRAG."""
    meta = {
        k: v for k, v in row.items()
        if k not in ("vector", "_distance", "chunk_id", "text")
    }
    return {
        "chunk_id": row.get("chunk_id", ""),
        "text": row.get("text", ""),
        "metadata": meta,
        "score": score,
    }


def _safe_int(v: Any) -> int:
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


def _safe_float(v: Any) -> float:
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _safe_str(v: Any) -> str:
    return str(v) if v is not None else ""


class LanceStore:
    """Couche vecteurs LanceDB — interface identique à ChromaStore."""

    # ── Init ──────────────────────────────────────────────────────────────────

    def __init__(self, persist_dir: str | None = None) -> None:
        self._persist_dir = persist_dir or str(
            Path(settings.data_dir) / "lance"
        )
        logger.info(f"Initialisation LanceDB → {self._persist_dir}")

        # Découverte de la dimension du modèle d'embedding
        self._dims = self._probe_dims()
        logger.info(f"Embedding dims détectés : {self._dims}")

        Path(self._persist_dir).mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(self._persist_dir)
        self._table = self._open_or_create_table()

        self._lock = threading.RLock()
        self._list_notes_cache: list[dict] | None = None
        self._list_notes_ts: float = 0.0
        self._note_views_cache: dict[str, Any] | None = None
        self._note_views_ts: float = 0.0
        self._count_cache: int | None = None
        self._count_ts: float = 0.0

        logger.info(f"Table LanceDB '{settings.chroma_collection}' prête — {self.count()} chunks")

    def _probe_dims(self) -> int:
        """Obtient la dimension réelle du modèle d'embedding courant."""
        try:
            vecs = _embed_texts(["probe"])
            return len(vecs[0])
        except Exception as exc:
            logger.warning(f"Probe embedding dims échoué ({exc}) — fallback 768")
            return _DIMS

    def _open_or_create_table(self) -> Any:
        name = settings.chroma_collection
        schema = _build_schema(self._dims)
        existing = self._db.list_tables()
        if name in existing:
            tbl = self._db.open_table(name)
            # FTS index si absent
            try:
                tbl.create_fts_index("text", replace=False)
            except Exception:
                pass
            return tbl
        tbl = self._db.create_table(name, schema=schema, mode="create")
        logger.info(f"Table LanceDB '{name}' créée (schéma {self._dims}d)")
        return tbl

    # ── Utilitaires statiques (compatibilité ChromaStore) ─────────────────────

    @staticmethod
    def _is_retrieval_artifact_path(file_path: str) -> bool:
        return _is_retrieval_artifact_path(file_path)

    @staticmethod
    def _is_obsirag_generated_path(file_path: str) -> bool:
        return _is_obsirag_generated_path(file_path)

    @staticmethod
    def _note_type_for_path(file_path: str) -> str:
        return _note_type_for_path(file_path)

    @staticmethod
    def _filter_retrieval_chunks(chunks: list[dict], *, top_k: int | None = None) -> list[dict]:
        filtered = [c for c in chunks if not _is_retrieval_artifact_path(
            (c.get("metadata") or {}).get("file_path", "")
        )]
        return filtered[:top_k] if top_k is not None and top_k > 0 else filtered

    # ── Écriture ──────────────────────────────────────────────────────────────

    def add_chunks(self, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        t0 = time.perf_counter()
        texts = [c.text for c in chunks]
        try:
            vectors = _embed_texts(texts)
        except Exception as exc:
            logger.error(f"Embedding failed for batch of {len(chunks)} chunks: {exc}")
            return

        rows = []
        for c, vec in zip(chunks, vectors):
            meta = c.as_metadata()
            rows.append({
                "chunk_id":         _safe_str(c.chunk_id),
                "text":             _safe_str(c.text),
                "file_path":        _safe_str(meta.get("file_path")),
                "note_title":       _safe_str(meta.get("note_title")),
                "section_title":    _safe_str(meta.get("section_title")),
                "section_level":    _safe_int(meta.get("section_level")),
                "chunk_index":      _safe_int(meta.get("chunk_index")),
                "date_modified":    _safe_str(meta.get("date_modified")),
                "date_created":     _safe_str(meta.get("date_created")),
                "date_modified_ts": _safe_float(meta.get("date_modified_ts")),
                "date_created_ts":  _safe_float(meta.get("date_created_ts")),
                "tags":             _safe_str(meta.get("tags")),
                "wikilinks":        _safe_str(meta.get("wikilinks")),
                "ner_persons":      _safe_str(meta.get("ner_persons")),
                "ner_orgs":         _safe_str(meta.get("ner_orgs")),
                "ner_locations":    _safe_str(meta.get("ner_locations")),
                "ner_misc":         _safe_str(meta.get("ner_misc")),
                "file_hash":        _safe_str(meta.get("file_hash")),
                "vector":           [float(x) for x in vec],
            })

        with self._lock:
            (
                self._table.merge_insert("chunk_id")
                .when_matched_update_all()
                .when_not_matched_insert_all()
                .execute(rows)
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
            safe = rel_path.replace("'", "''")
            with self._lock:
                self._table.delete(f"file_path = '{safe}'")
            logger.debug(f"Suppression chunks pour {rel_path}")
            self.invalidate_list_notes_cache()
        except Exception as exc:
            logger.error(f"delete_by_file({rel_path}) : {exc}")

    # ── Recherche sémantique ──────────────────────────────────────────────────

    def search(
        self,
        query: str,
        top_k: int = settings.search_top_k,
        where: dict | None = None,
    ) -> list[dict]:
        try:
            vecs = _embed_texts([query])
        except Exception as exc:
            logger.error(f"embed query failed: {exc}")
            return []

        t0 = time.perf_counter()
        q = self._table.search(vecs[0], vector_column_name="vector").metric("cosine").limit(top_k * 4)

        if where:
            # Convertit le format ChromaDB where-dict en SQL LanceDB
            sql = _where_dict_to_sql(where)
            if sql:
                q = q.where(sql, prefilter=True)

        try:
            rows = q.to_list()
        except Exception as exc:
            logger.error(f"LanceDB search failed: {exc}")
            return []

        elapsed = time.perf_counter() - t0
        backend = settings.ollama_embed_model or settings.embedding_model
        logger.debug(f"embed:search {elapsed:.3f}s backend={backend} top_k={top_k}")

        chunks = [_row_to_chunk(r, score=round(1 - r.get("_distance", 1), 4)) for r in rows]
        return LanceStore._filter_retrieval_chunks(chunks, top_k=top_k)

    def search_by_date_range(
        self,
        query: str,
        since: datetime,
        until: datetime | None = None,
        top_k: int = settings.search_top_k,
    ) -> list[dict]:
        since_ts = since.timestamp()
        until_ts = (until or datetime.now()).timestamp()
        try:
            where = {"$and": [
                {"date_modified_ts": {"$gte": since_ts}},
                {"date_modified_ts": {"$lte": until_ts}},
            ]}
            results = self.search(query, top_k=top_k, where=where)
            if results:
                return results
        except Exception:
            pass
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
        fields = {
            "persons":   ["ner_persons"],
            "orgs":      ["ner_orgs"],
            "locations": ["ner_locations"],
            "misc":      ["ner_misc"],
            "all":       ["ner_persons", "ner_orgs", "ner_locations", "ner_misc"],
        }.get(entity_type, ["ner_persons", "ner_orgs", "ner_locations", "ner_misc"])
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

    def search_by_keyword(self, keyword: str, top_k: int = 10) -> list[dict]:
        """FTS nativement via l'index Lance (sans contournement ChromaDB $contains)."""
        try:
            rows = (
                self._table.search(keyword, query_type="fts")
                .limit(top_k * 4)
                .to_list()
            )
        except Exception:
            # Fallback : recherche sémantique si FTS indisponible
            return self.search(keyword, top_k=top_k)

        chunks: list[dict] = []
        seen: set[str] = set()
        for r in rows:
            cid = r.get("chunk_id", "")
            if cid in seen:
                continue
            seen.add(cid)
            chunk = _row_to_chunk(r, score=0.95)
            if not _is_retrieval_artifact_path((chunk.get("metadata") or {}).get("file_path", "")):
                chunks.append(chunk)
        return chunks[:top_k]

    def search_by_note_title(self, title: str, top_k: int = 10) -> list[dict]:
        """Récupère les chunks d'une note par titre exact ou partiel."""
        results: list[dict] = []
        seen: set[str] = set()
        safe = title.replace("'", "''")
        try:
            rows = (
                self._table.search(query=None)
                .where(f"note_title = '{safe}'")
                .limit(top_k * 4)
                .to_list()
            )
            for r in rows:
                cid = r.get("chunk_id", "")
                if cid in seen or _is_retrieval_artifact_path(r.get("file_path", "")):
                    continue
                seen.add(cid)
                results.append(_row_to_chunk(r, score=0.98))
        except Exception:
            pass

        if not results:
            results = self.search_by_keyword(title, top_k=top_k)
        return results[:top_k]

    # ── Récupération par chemin ───────────────────────────────────────────────

    def get_chunks_by_note_title(self, note_title: str, limit: int = 2) -> list[dict]:
        safe = note_title.replace("'", "''")
        try:
            rows = (
                self._table.search(query=None)
                .where(f"note_title = '{safe}'")
                .limit(limit)
                .to_list()
            )
            return [_row_to_chunk(r, score=0.0) for r in rows
                    if not _is_retrieval_artifact_path(r.get("file_path", ""))][:limit]
        except Exception:
            return []

    def get_chunks_by_file_path(self, file_path: str, limit: int = 2) -> list[dict]:
        safe = file_path.replace("'", "''")
        try:
            rows = (
                self._table.search(query=None)
                .where(f"file_path = '{safe}'")
                .limit(limit)
                .to_list()
            )
            return [_row_to_chunk(r, score=0.0) for r in rows][:limit]
        except Exception:
            return []

    def get_chunks_by_file_paths(
        self, file_paths: list[str], limit_per_path: int = 2
    ) -> dict[str, list[dict]]:
        if not file_paths:
            return {}
        grouped: dict[str, list[dict]] = {fp: [] for fp in file_paths}
        escaped = [f"'{fp.replace(chr(39), chr(39)+chr(39))}'" for fp in file_paths]
        where_sql = f"file_path IN ({', '.join(escaped)})"
        try:
            rows = (
                self._table.search(query=None)
                .where(where_sql)
                .limit(len(file_paths) * limit_per_path * 4)
                .to_list()
            )
            for r in rows:
                fp = r.get("file_path", "")
                if fp not in grouped or len(grouped[fp]) >= limit_per_path:
                    continue
                grouped[fp].append(_row_to_chunk(r, score=0.0))
        except Exception:
            for fp in file_paths:
                grouped[fp] = self.get_chunks_by_file_path(fp, limit=limit_per_path)
        return grouped

    def get_notes_by_file_paths(self, file_paths: list[str]) -> list[dict]:
        if not file_paths:
            return []
        views = self._get_note_views()
        by_fp = views.get("by_file_path", {})
        selected = [by_fp[fp] for fp in file_paths if fp in by_fp]
        if not selected:
            wanted = set(file_paths)
            selected = [n for n in self.list_notes() if n["file_path"] in wanted]
        order = {fp: i for i, fp in enumerate(file_paths)}
        return sorted(selected, key=lambda n: order.get(n["file_path"], len(order)))

    def get_note_by_file_path(self, file_path: str) -> dict | None:
        views = self._get_note_views()
        result = views.get("by_file_path", {}).get(file_path)
        if result:
            return result
        notes = self.get_notes_by_file_paths([file_path])
        return notes[0] if notes else None

    # ── Comptage & listing ────────────────────────────────────────────────────

    def count(self) -> int:
        now = time.monotonic()
        if self._count_cache is not None and (now - self._count_ts) < _LIST_NOTES_TTL:
            return self._count_cache
        try:
            result = len(self._table)
        except Exception:
            result = self._count_cache or 0
        self._count_cache = result
        self._count_ts = now
        return result

    def invalidate_list_notes_cache(self) -> None:
        self._list_notes_ts = 0.0
        self._note_views_ts = 0.0
        self._count_ts = 0.0

    def list_notes(self) -> list[dict]:
        now = time.monotonic()
        if self._list_notes_cache is not None and (now - self._list_notes_ts) < _LIST_NOTES_TTL:
            return self._list_notes_cache

        try:
            rows = (
                self._table.search(query=None)
                .select(["file_path", "note_title", "date_modified", "date_created", "tags", "wikilinks"])
                .limit(100_000)
                .to_list()
            )
        except Exception as exc:
            logger.warning(f"list_notes LanceDB failed ({exc})")
            self._list_notes_cache = []
            self._list_notes_ts = now
            return []

        seen: dict[str, dict] = {}
        for r in rows:
            fp = r.get("file_path") or ""
            if not fp or fp in seen:
                continue
            seen[fp] = {
                "file_path":     fp,
                "title":         r.get("note_title") or fp,
                "date_modified": r.get("date_modified") or "",
                "date_created":  r.get("date_created") or "",
                "tags":          [t for t in (r.get("tags") or "").split(",") if t],
                "wikilinks":     [w for w in (r.get("wikilinks") or "").split(",") if w],
            }

        self._list_notes_cache = sorted(
            seen.values(), key=lambda x: x["date_modified"], reverse=True
        )
        self._list_notes_ts = now
        return self._list_notes_cache

    def get_recently_modified(self, since: datetime) -> list[dict]:
        notes = self.list_notes()
        since_iso = since.isoformat()
        return [n for n in notes if (n.get("date_modified") or "") >= since_iso]

    # ── Vues notes (même logique que ChromaStore._build_note_views) ───────────

    def _build_note_views(self) -> dict[str, Any]:
        notes = self.list_notes()
        sorted_by_title = sorted(
            notes,
            key=lambda n: str(n.get("title") or Path(n["file_path"]).stem).lower(),
        )
        recent_notes = sorted(notes, key=lambda n: str(n.get("date_modified") or ""), reverse=True)
        recent_notes = sorted(recent_notes, key=lambda n: not bool(n.get("date_modified")))

        folders: set[str] = set()
        tags: set[str] = set()
        notes_by_type: dict[str, list[dict]] = {"insight": [], "synapse": [], "report": [], "user": []}
        by_file_path: dict[str, dict] = {}
        generated_notes: list[dict] = []
        user_notes: list[dict] = []
        backlinks_by_target: dict[str, list[dict]] = {}

        for note in notes:
            fp = note["file_path"]
            by_file_path[fp] = note
            folders.add(str(Path(fp).parent))
            tags.update(t for t in note.get("tags", []) if t)

            note_type = _note_type_for_path(fp)
            notes_by_type.setdefault(note_type, []).append(note)

            if _is_obsirag_generated_path(fp):
                generated_notes.append(note)
            else:
                user_notes.append(note)

            for wikilink in note.get("wikilinks", []):
                target = str(wikilink).strip().lower()
                if target:
                    backlinks_by_target.setdefault(target, []).append(note)

        return {
            "notes":               notes,
            "sorted_by_title":     sorted_by_title,
            "recent_notes":        recent_notes,
            "count_notes":         len(notes),
            "folders":             sorted(folders),
            "tags":                sorted(tags),
            "notes_by_type":       notes_by_type,
            "by_file_path":        by_file_path,
            "user_notes":          user_notes,
            "generated_notes":     generated_notes,
            "backlinks_by_target": backlinks_by_target,
        }

    def _get_note_views(self) -> dict[str, Any]:
        now = time.monotonic()
        if self._note_views_cache is not None and (now - self._note_views_ts) < _LIST_NOTES_TTL:
            return self._note_views_cache
        self._note_views_cache = self._build_note_views()
        self._note_views_ts = now
        return self._note_views_cache

    def list_notes_sorted_by_title(self) -> list[dict]:
        return list(self._get_note_views()["sorted_by_title"])

    def list_recent_notes(self, limit: int = 20) -> list[dict]:
        notes = list(self._get_note_views()["recent_notes"])
        return notes[:limit] if limit > 0 else notes

    def count_notes(self) -> int:
        return int(self._get_note_views()["count_notes"])

    def list_note_folders(self) -> list[str]:
        return list(self._get_note_views()["folders"])

    def list_note_tags(self) -> list[str]:
        return list(self._get_note_views()["tags"])

    def list_notes_by_type(self, note_type: str) -> list[dict]:
        wanted = str(note_type or "").strip().lower()
        if not wanted:
            return []
        return list(self._get_note_views()["notes_by_type"].get(wanted, []))

    def list_insight_notes(self) -> list[dict]:
        return self.list_notes_by_type("insight")

    def list_synapse_notes(self) -> list[dict]:
        return self.list_notes_by_type("synapse")

    def list_report_notes(self) -> list[dict]:
        return self.list_notes_by_type("report")

    def list_user_notes(self) -> list[dict]:
        return list(self._get_note_views()["user_notes"])

    def list_generated_notes(self) -> list[dict]:
        return list(self._get_note_views()["generated_notes"])

    def get_backlinks(self, file_path: str) -> list[dict]:
        target_name = Path(file_path).stem.lower()
        backlinks = self._get_note_views()["backlinks_by_target"].get(target_name, [])
        return [n for n in backlinks if n["file_path"] != file_path]

    def find_similar_notes(
        self,
        source_fp: str,
        existing_links: set[str],
        top_k: int = 10,
        threshold: float = 0.65,
    ) -> list[dict]:
        safe = source_fp.replace("'", "''")
        try:
            rows = (
                self._table.search(query=None)
                .where(f"file_path = '{safe}'")
                .select(["text"])
                .limit(3)
                .to_list()
            )
        except Exception:
            return []
        docs = [r.get("text", "") for r in rows]
        if not docs:
            return []
        query_text = " ".join(docs[:2])
        candidates = self.search(query_text, top_k=top_k + 5)
        seen_fps: set[str] = {source_fp}
        results: list[dict] = []
        for c in candidates:
            fp = c["metadata"].get("file_path", "")
            if not fp or fp in seen_fps:
                continue
            seen_fps.add(fp)
            note_title = c["metadata"].get("note_title", fp)
            if fp in existing_links or note_title.lower() in existing_links:
                continue
            if c["score"] < threshold:
                continue
            results.append({
                "file_path": fp,
                "title":     note_title,
                "score":     c["score"],
                "excerpt":   c["text"][:300],
            })
            if len(results) >= top_k:
                break
        return results

    # ── Compatibilité ChromaStore (méthode native_api_available) ─────────────

    def native_api_available(self) -> bool:
        """Toujours True avec LanceDB — pas de mode dégradé."""
        return True


# ── Traduction where-dict ChromaDB → SQL LanceDB ─────────────────────────────

def _where_dict_to_sql(where: dict) -> str:
    """Convertit un filtre ChromaDB (dict) en clause SQL LanceDB.

    Supporte : $eq, $gte, $lte, $gt, $lt, $in, $and, $or.
    """
    if not where:
        return ""
    parts: list[str] = []
    for key, value in where.items():
        if key == "$and":
            clauses = [_where_dict_to_sql(c) for c in value if c]
            parts.append("(" + " AND ".join(c for c in clauses if c) + ")")
        elif key == "$or":
            clauses = [_where_dict_to_sql(c) for c in value if c]
            parts.append("(" + " OR ".join(c for c in clauses if c) + ")")
        elif isinstance(value, dict):
            for op, operand in value.items():
                sql_op = {"$eq": "=", "$gte": ">=", "$lte": "<=", "$gt": ">", "$lt": "<"}.get(op)
                if sql_op:
                    if isinstance(operand, str):
                        safe = operand.replace("'", "''")
                        parts.append(f"{key} {sql_op} '{safe}'")
                    else:
                        parts.append(f"{key} {sql_op} {operand}")
                elif op == "$in":
                    items = []
                    for v in operand:
                        if isinstance(v, str):
                            items.append(f"'{v.replace(chr(39), chr(39)+chr(39))}'")
                        else:
                            items.append(str(v))
                    parts.append(f"{key} IN ({', '.join(items)})")
        else:
            if isinstance(value, str):
                safe = value.replace("'", "''")
                parts.append(f"{key} = '{safe}'")
            else:
                parts.append(f"{key} = {value}")
    return " AND ".join(parts)
