from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Callable, cast
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from src.ai.rag import RAGPipeline


class RetrievalStrategy:
    def __init__(self, owner: "RAGPipeline") -> None:
        self._owner = owner

    @staticmethod
    def _emit_progress(
        progress_callback: Callable[[dict[str, Any]], None] | None,
        message: str,
        **metadata: Any,
    ) -> None:
        if not callable(progress_callback):
            return
        payload: dict[str, Any] = {
            "phase": "retrieval",
            "message": message,
        }
        payload.update(metadata)
        try:
            progress_callback(payload)
        except Exception:
            pass

    def retrieve(
        self,
        query: str,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[list[dict], str]:
        cfg = self._owner._get_settings()
        query = self._owner._normalize_query(query)
        self._emit_progress(progress_callback, "Détection de l'intention", query=query)
        tags = self._owner._tag_pattern.findall(query)
        if tags:
            self._emit_progress(progress_callback, "Filtrage par tags", retrieval_mode="tags", tags=len(tags))
            chunks = self._owner._chroma.search_by_tags(tags, top_k=cfg.search_top_k)
            self._emit_progress(progress_callback, f"Recherche tags terminée ({len(chunks)} résultat(s))", chunk_count=len(chunks), retrieval_mode="tags")
            return chunks, "tags"

        relation_match = self._owner._relation_pattern.search(query)
        if relation_match:
            entity_a = relation_match.group(1).strip().strip('"\'«»')
            entity_b = relation_match.group(2).strip().strip('"\'«»')
            logger.info(f"RAG intent=relation entités: {entity_a!r} ↔ {entity_b!r}")
            self._emit_progress(
                progress_callback,
                f"Recherche relationnelle entre {entity_a} et {entity_b}",
                retrieval_mode="relation",
            )
            chunks_a = self._owner._chroma.search(entity_a, top_k=cfg.search_top_k)
            chunks_b = self._owner._chroma.search(entity_b, top_k=cfg.search_top_k)
            chunks_ab = self._owner._chroma.search(f"{entity_a} {entity_b}", top_k=cfg.search_top_k)
            seen_ids: set[str] = set()
            merged: list[dict] = []
            for chunk in chunks_ab + chunks_a + chunks_b:
                if chunk["chunk_id"] not in seen_ids:
                    seen_ids.add(chunk["chunk_id"])
                    merged.append(chunk)
            chunks = merged[: cfg.search_top_k * 2]
            self._emit_progress(progress_callback, f"Recherche relationnelle terminée ({len(chunks)} résultat(s))", chunk_count=len(chunks), retrieval_mode="relation")
            return chunks, "relation"

        days = self._owner._detect_temporal(query)
        if days is not None:
            self._emit_progress(progress_callback, f"Filtrage temporel sur {days} jour(s)", retrieval_mode="temporal", days=days)
            since = datetime.now() - timedelta(days=days)
            chunks = self._owner._chroma.search_by_date_range(query, since=since, top_k=cfg.search_top_k)
            if not chunks:
                self._emit_progress(progress_callback, "Aucun résultat temporel, fallback sémantique", retrieval_mode="temporal")
                chunks = self._owner._chroma.search(query, top_k=cfg.search_top_k)
            self._emit_progress(progress_callback, f"Recherche temporelle terminée ({len(chunks)} résultat(s))", chunk_count=len(chunks), retrieval_mode="temporal")
            return chunks, "temporal"

        entity_match = self._owner._entity_patterns.search(query)
        if entity_match:
            entity = entity_match.group(1).strip()
            if self._owner._is_entity_target(entity):
                self._emit_progress(progress_callback, f"Recherche par entité: {entity}", retrieval_mode="entity")
                chunks = self._owner._chroma.search_by_entity(entity, top_k=cfg.search_top_k)
                filtered = self._owner._filter_supported_chunks(query, chunks, "entity")
                self._emit_progress(progress_callback, f"Recherche entité terminée ({len(filtered)} résultat(s))", chunk_count=len(filtered), retrieval_mode="entity")
                return filtered, "entity"

        proper_nouns = self._owner._extract_proper_nouns(query)
        if self._owner._synthesis_patterns.search(query):
            if proper_nouns:
                self._emit_progress(progress_callback, "Recherche hybride de synthèse", retrieval_mode="synthesis")
                chunks = self._owner._retrieve_hybrid_chunks(query, proper_nouns)
                self._emit_progress(progress_callback, f"Recherche hybride terminée ({len(chunks[: cfg.search_top_k])} résultat(s))", chunk_count=len(chunks[: cfg.search_top_k]), retrieval_mode="synthesis")
                return chunks[: cfg.search_top_k], "synthesis"
            self._emit_progress(progress_callback, "Recherche sémantique de synthèse", retrieval_mode="synthesis")
            chunks = self._owner._chroma.search(query, top_k=cfg.search_top_k)
            self._emit_progress(progress_callback, f"Recherche synthèse terminée ({len(chunks)} résultat(s))", chunk_count=len(chunks), retrieval_mode="synthesis")
            return chunks, "synthesis"

        if proper_nouns:
            self._emit_progress(progress_callback, "Recherche hybride multi-termes", retrieval_mode="hybrid")
            chunks = self._owner._retrieve_hybrid_chunks(query, proper_nouns)
            filtered = self._owner._filter_supported_chunks(
                query, chunks[: cfg.search_top_k], "hybrid"
            )
            self._emit_progress(
                progress_callback,
                f"Recherche hybride terminée ({len(filtered)} résultat(s))",
                chunk_count=len(filtered),
                retrieval_mode="hybrid",
            )
            return filtered, "hybrid"

        self._emit_progress(progress_callback, "Recherche sémantique générale", retrieval_mode="general")
        chunks = self._owner._chroma.search(query, top_k=cfg.search_top_k)
        stop_words = {
            "quelles", "quelle", "quel", "quels", "comment", "pourquoi",
            "mesures", "prend", "prend-elle", "assurer", "pour", "dans",
            "avec", "sont", "cette", "avoir", "faire", "être", "les", "des",
            "une", "que", "qui", "sur", "par", "elle", "ils",
        }
        if all(chunk["score"] < 0.55 for chunk in chunks):
            keyword_extra: list[dict] = []
            for word in query.split():
                cleaned = re.sub(r"[^\w]", "", word).lower()
                if len(cleaned) >= 4 and cleaned not in stop_words:
                    keyword_extra.extend(self._owner._chroma.search_by_keyword(cleaned, top_k=3))
            if keyword_extra:
                self._emit_progress(progress_callback, "Fallback mots-clés activé", retrieval_mode="general_kw_fallback")
                seen_ids: set[str] = set()
                merged: list[dict] = []
                for chunk in keyword_extra + chunks:
                    if chunk["chunk_id"] not in seen_ids:
                        seen_ids.add(chunk["chunk_id"])
                        merged.append(chunk)
                logger.info(f"RAG fallback keyword: {len(keyword_extra)} chunks supplémentaires")
                filtered = self._owner._filter_supported_chunks(
                    query,
                    merged[: cfg.search_top_k],
                    "general_kw_fallback",
                )
                self._emit_progress(progress_callback, f"Recherche fallback terminée ({len(filtered)} résultat(s))", chunk_count=len(filtered), retrieval_mode="general_kw_fallback")
                return filtered, "general_kw_fallback"
        filtered = self._owner._filter_supported_chunks(query, chunks, "general")
        self._emit_progress(progress_callback, f"Recherche générale terminée ({len(filtered)} résultat(s))", chunk_count=len(filtered), retrieval_mode="general")
        return filtered, "general"

    def retrieve_hybrid_chunks(
        self,
        query: str,
        proper_nouns: list[str],
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[dict]:
        cfg = self._owner._get_settings()
        self._emit_progress(progress_callback, "Hybrid retrieval: recherche sémantique")
        semantic = self._owner._prefer_informative_chunks(
            self._owner._chroma.search(query, top_k=cfg.search_top_k)
        )
        per_term_chunks: list[list[dict]] = []
        retrieval_terms = self._owner._expand_retrieval_terms(query, proper_nouns)
        focus_terms = self._owner._select_focus_terms(retrieval_terms)
        logger.info(f"RAG hybrid termes={retrieval_terms}")
        self._emit_progress(progress_callback, f"Hybrid retrieval: {len(retrieval_terms)} terme(s) analysé(s)")
        for noun in retrieval_terms:
            title_hits = self._owner._chroma.search_by_note_title(noun, top_k=3)
            keyword_hits = self._owner._chroma.search_by_keyword(noun, top_k=3)
            per_term_chunks.append(self._owner._prefer_informative_chunks(title_hits + keyword_hits))

        seen_ids: set[str] = set()
        seen_notes: set[str] = set()
        merged: list[dict] = []
        focus_buckets: list[list[dict]] = []
        bridge_chunks: list[dict] = []
        if focus_terms:
            symbolic_hits: list[dict] = []
            symbolic_ids: set[str] = set()
            for bucket in per_term_chunks:
                for chunk in bucket:
                    if chunk["chunk_id"] not in symbolic_ids:
                        symbolic_ids.add(chunk["chunk_id"])
                        symbolic_hits.append(chunk)

            focus_token_sets: list[tuple[str, set[str]]] = []
            for term in focus_terms:
                tokens = {
                    token.lower()
                    for token in re.findall(r"\w+", term)
                    if len(token) >= 4 and token.lower() not in {"mission", "terre", "lune", "code"}
                }
                if tokens:
                    focus_token_sets.append((term, tokens))

            focus_bucket_map: dict[str, list[dict]] = {term: [] for term, _ in focus_token_sets}
            bridge_ids: set[str] = set()
            for chunk in symbolic_hits + semantic:
                matched_terms = [
                    term for term, tokens in focus_token_sets
                    if self._owner._chunk_match_count(chunk, [(term, tokens)])
                ]
                if len(matched_terms) >= 2:
                    if chunk["chunk_id"] not in bridge_ids:
                        bridge_ids.add(chunk["chunk_id"])
                        bridge_chunks.append(chunk)
                elif len(matched_terms) == 1:
                    bucket = focus_bucket_map[matched_terms[0]]
                    if chunk["chunk_id"] not in {candidate["chunk_id"] for candidate in bucket}:
                        bucket.append(chunk)

            for term, tokens in focus_token_sets:
                focus_bucket_map[term].sort(
                    key=lambda chunk: self._owner._chunk_term_rank(chunk, tokens),
                    reverse=True,
                )
            focus_buckets = [bucket for bucket in focus_bucket_map.values() if bucket]

        for chunk in bridge_chunks:
            note_key = self._owner._chunk_note_key(chunk)
            if chunk["chunk_id"] not in seen_ids and note_key not in seen_notes:
                seen_ids.add(chunk["chunk_id"])
                seen_notes.add(note_key)
                merged.append(chunk)

        max_focus_depth = max((len(bucket) for bucket in focus_buckets), default=0)
        for depth in range(max_focus_depth):
            for bucket in focus_buckets:
                if depth < len(bucket):
                    chunk = bucket[depth]
                    note_key = self._owner._chunk_note_key(chunk)
                    if chunk["chunk_id"] not in seen_ids and note_key not in seen_notes:
                        seen_ids.add(chunk["chunk_id"])
                        seen_notes.add(note_key)
                        merged.append(chunk)

        max_bucket_depth = max((len(bucket) for bucket in per_term_chunks), default=0)
        focus_token_sets = [
            (
                term,
                {
                    token.lower() for token in re.findall(r"\w+", term)
                    if len(token) >= 4 and token.lower() not in {"mission", "terre", "lune", "code"}
                },
            )
            for term in focus_terms
        ]
        for depth in range(max_bucket_depth):
            for bucket in per_term_chunks:
                if depth < len(bucket):
                    chunk = bucket[depth]
                    if focus_terms and self._owner._chunk_match_count(chunk, focus_token_sets) == 0:
                        continue
                    note_key = self._owner._chunk_note_key(chunk)
                    if chunk["chunk_id"] not in seen_ids and note_key not in seen_notes:
                        seen_ids.add(chunk["chunk_id"])
                        seen_notes.add(note_key)
                        merged.append(chunk)
        for chunk in semantic:
            if focus_terms and self._owner._chunk_match_count(chunk, focus_token_sets) == 0:
                continue
            note_key = self._owner._chunk_note_key(chunk)
            if chunk["chunk_id"] not in seen_ids and note_key not in seen_notes:
                seen_ids.add(chunk["chunk_id"])
                seen_notes.add(note_key)
                merged.append(chunk)

        chunks = merged[: cfg.search_top_k * 2]
        has_symbolic_hits = any(per_term_chunks)
        if not has_symbolic_hits and all(chunk["score"] < 0.55 for chunk in chunks):
            self._emit_progress(progress_callback, "Hybrid retrieval: fallback sémantique global")
            chunks = self._owner._chroma.search(query, top_k=cfg.search_top_k * 2)
        self._emit_progress(progress_callback, f"Hybrid retrieval terminé ({len(cast(list[dict], chunks))} résultat(s))")
        return chunks

    def prepare_context_chunks(self, chunks: list[dict], query: str, intent: str) -> list[dict]:
        cfg = self._owner._get_settings()
        if not self._owner._should_focus_dominant_note(intent, query):
            return chunks

        dominant_note_key = self._extract_primary_note_hint(chunks)
        if not dominant_note_key:
            dominant_note_key = self._owner._select_dominant_note_key(query, chunks)
        if not dominant_note_key:
            return chunks

        dominant_limit = min(cfg.max_context_chunks - 1, max(2, cfg.max_context_chunks // 2 + 1))
        dominant_chunks = self._owner._fetch_note_context_chunks(query, dominant_note_key, dominant_limit)
        if not dominant_chunks:
            return chunks

        supporting_chunks = self._owner._prefer_informative_chunks(
            [chunk for chunk in chunks if self._owner._chunk_note_key(chunk) != dominant_note_key]
        )
        remaining = max(0, cfg.max_context_chunks - len(dominant_chunks))
        prepared = dominant_chunks + supporting_chunks[:remaining]
        return prepared[: cfg.max_context_chunks]

    @staticmethod
    def _extract_primary_note_hint(chunks: list[dict]) -> str | None:
        for chunk in chunks:
            metadata = chunk.get("metadata") or {}
            hint = str(metadata.get("primary_note_key_hint") or "").strip()
            if hint:
                return hint
        return None

    def mark_primary_sources(self, chunks: list[dict], query: str, intent: str) -> list[dict]:
        if not chunks:
            return chunks

        dominant_note_key = self._owner._select_dominant_note_key(query, chunks)
        marked: list[dict] = []
        for chunk in chunks:
            clone = dict(chunk)
            metadata = dict(chunk.get("metadata") or {})
            metadata["is_primary"] = bool(dominant_note_key and self._owner._chunk_note_key(chunk) == dominant_note_key)
            if dominant_note_key:
                metadata["primary_note_key_hint"] = dominant_note_key
            clone["metadata"] = metadata
            marked.append(clone)
        return marked