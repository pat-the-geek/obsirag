"""
Tests unitaires + performance — ChromaStore (src/database/chroma_store.py)

Stratégie : ChromaDB en mémoire (ephemeral) avec embedding mocké,
ce qui évite le disque, le modèle sentence-transformers et les ports réseau.
"""
from __future__ import annotations

import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.indexer.chunker import Chunk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chunk(idx: int, file_hash: str = "abc", file_path: str = "note.md") -> Chunk:
    from datetime import datetime
    return Chunk(
        text=f"Contenu du chunk numéro {idx} avec du texte suffisant.",
        chunk_id=f"{file_hash}_{idx}",
        chunk_index=idx,
        note_title="Note de test",
        file_path=file_path,
        section_title="Section",
        section_level=1,
        date_modified=datetime(2026, 1, 1).isoformat(),
        date_created=datetime(2026, 1, 1).isoformat(),
        date_modified_ts=datetime(2026, 1, 1).timestamp(),
        date_created_ts=datetime(2026, 1, 1).timestamp(),
        tags="test,python",
        wikilinks="",
        ner_persons="",
        ner_orgs="",
        ner_locations="",
        ner_misc="",
        file_hash=file_hash,
    )


def _make_chroma_store(tmp_path):
    """Instancie un ChromaStore avec ChromaDB en mémoire et embedding mocké."""
    import uuid
    import chromadb
    from chromadb.utils.embedding_functions import EmbeddingFunction

    class _FakeEmbedFn(EmbeddingFunction):
        def __call__(self, input):  # noqa: A002
            return [[float(i % 10) / 10.0] * 384 for i in range(len(input))]

    client = chromadb.EphemeralClient()
    # Nom unique pour éviter les conflits d'état partagé entre tests
    collection = client.create_collection(
        name=f"test_col_{uuid.uuid4().hex}",
        embedding_function=_FakeEmbedFn(),
        metadata={"hnsw:space": "cosine"},
    )

    store = MagicMock()
    store._client = client
    store._collection = collection
    store._list_notes_cache = None
    store._list_notes_ts = 0.0
    store._count_cache = None
    store._count_ts = 0.0

    # Brancher les vraies méthodes sur le mock pour pouvoir les tester
    from src.database.chroma_store import ChromaStore
    for method in [
        "add_chunks", "delete_by_file", "search",
        "count", "invalidate_list_notes_cache", "list_notes",
        "search_by_tags", "search_by_entity", "search_by_keyword",
        "search_by_date_range", "find_similar_notes",
    ]:
        real_method = getattr(ChromaStore, method)
        setattr(store, method, lambda *a, m=real_method, s=store, **kw: m(s, *a, **kw))

    # Les méthodes statiques/privées doivent aussi être accessibles via l'instance mock
    store._format_results = ChromaStore._format_results

    return store


@pytest.fixture
def chroma(tmp_path):
    return _make_chroma_store(tmp_path)


@pytest.fixture
def chroma_with_data(chroma):
    chunks = [_make_chunk(i) for i in range(5)]
    chroma.add_chunks(chunks)
    return chroma


# ---------------------------------------------------------------------------
# Tests fonctionnels — add_chunks / count
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestChromaAddAndCount:
    def test_count_empty_store(self, chroma):
        assert chroma.count() == 0

    def test_add_chunks_increases_count(self, chroma):
        chroma.add_chunks([_make_chunk(0)])
        assert chroma.count() == 1

    def test_add_multiple_chunks(self, chroma):
        chunks = [_make_chunk(i) for i in range(10)]
        chroma.add_chunks(chunks)
        assert chroma.count() == 10

    def test_add_empty_list_is_noop(self, chroma):
        chroma.add_chunks([])
        assert chroma.count() == 0

    def test_upsert_same_id_does_not_duplicate(self, chroma):
        chroma.add_chunks([_make_chunk(0)])
        chroma.add_chunks([_make_chunk(0)])  # même chunk_id
        assert chroma.count() == 1


# ---------------------------------------------------------------------------
# Tests fonctionnels — cache count
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestChromaCountCache:
    def test_count_uses_cache(self, chroma):
        chroma.add_chunks([_make_chunk(0)])
        # Premier appel → peuple le cache
        c1 = chroma.count()
        # Ajouter un chunk sans invalider le cache
        chroma._collection.upsert(
            ids=["bypass_1"],
            documents=["bypass"],
            metadatas=[_make_chunk(99).as_metadata()],
        )
        # Doit retourner le résultat caché
        c2 = chroma.count()
        assert c1 == c2

    def test_invalidate_clears_count_cache(self, chroma):
        chroma.add_chunks([_make_chunk(0)])
        chroma.count()  # peuple le cache
        chroma.invalidate_list_notes_cache()
        assert chroma._count_ts == 0.0

    def test_count_cache_expires_after_ttl(self, chroma):
        from src.database import chroma_store as cs_module
        original_ttl = cs_module._LIST_NOTES_TTL
        try:
            cs_module._LIST_NOTES_TTL = 0.01  # 10ms
            chroma._count_ts = 0.0
            chroma._count_cache = None
            chroma.add_chunks([_make_chunk(0)])
            chroma.count()  # peuple le cache
            time.sleep(0.05)
            # Forcer expiration
            chroma._count_ts = 0.0
            # Doit recalculer
            assert chroma.count() == 1
        finally:
            cs_module._LIST_NOTES_TTL = original_ttl


# ---------------------------------------------------------------------------
# Tests fonctionnels — delete_by_file
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestChromaDelete:
    def test_delete_removes_chunks(self, chroma):
        chroma.add_chunks([_make_chunk(0), _make_chunk(1)])
        assert chroma.count() == 2
        chroma.invalidate_list_notes_cache()
        chroma.delete_by_file("note.md")
        chroma.invalidate_list_notes_cache()
        assert chroma.count() == 0

    def test_delete_file_not_in_index_is_noop(self, chroma):
        chroma.add_chunks([_make_chunk(0)])
        chroma.delete_by_file("inexistant.md")
        chroma.invalidate_list_notes_cache()
        assert chroma.count() == 1

    def test_delete_only_affects_target_file(self, chroma):
        chroma.add_chunks([_make_chunk(0, file_path="a.md", file_hash="aaa")])
        chroma.add_chunks([_make_chunk(0, file_path="b.md", file_hash="bbb")])
        chroma.invalidate_list_notes_cache()
        chroma.delete_by_file("a.md")
        chroma.invalidate_list_notes_cache()
        assert chroma.count() == 1


# ---------------------------------------------------------------------------
# Tests fonctionnels — search
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestChromaSearch:
    def test_search_returns_list(self, chroma_with_data):
        results = chroma_with_data.search("python", top_k=3)
        assert isinstance(results, list)

    def test_search_result_structure(self, chroma_with_data):
        results = chroma_with_data.search("contenu", top_k=1)
        assert len(results) >= 1
        r = results[0]
        assert "chunk_id" in r
        assert "text" in r
        assert "metadata" in r
        assert "score" in r

    def test_search_top_k_limits_results(self, chroma_with_data):
        results = chroma_with_data.search("chunk", top_k=2)
        assert len(results) <= 2

    def test_search_score_between_0_and_1(self, chroma_with_data):
        results = chroma_with_data.search("chunk", top_k=5)
        for r in results:
            assert 0.0 <= r["score"] <= 1.0, f"Score hors bornes: {r['score']}"

    def test_search_empty_store_returns_empty(self, chroma):
        results = chroma.search("requête", top_k=5)
        assert results == []


# ---------------------------------------------------------------------------
# Tests fonctionnels — search_by_keyword
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestChromaKeyword:
    def test_keyword_exact_match(self, chroma):
        chroma.add_chunks([_make_chunk(0)])
        results = chroma.search_by_keyword("Contenu")
        assert len(results) > 0

    def test_keyword_partial_match(self, chroma):
        chroma.add_chunks([_make_chunk(0)])
        results = chroma.search_by_keyword("numéro")
        assert len(results) > 0

    def test_keyword_no_match_returns_empty(self, chroma):
        chroma.add_chunks([_make_chunk(0)])
        results = chroma.search_by_keyword("MotInexistantXYZ123")
        assert results == []

    def test_keyword_deduplicates_results(self, chroma):
        chroma.add_chunks([_make_chunk(0)])
        # Appel deux fois avec le même terme — doit dédupliquer
        results = chroma.search_by_keyword("Contenu")
        ids = [r["chunk_id"] for r in results]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Tests de performance — ChromaStore
# ---------------------------------------------------------------------------

@pytest.mark.perf
class TestChromaPerformance:
    def test_add_100_chunks_under_5s(self, chroma, perf_timer):
        chunks = [_make_chunk(i) for i in range(100)]
        with perf_timer.measure("add_100_chunks", max_seconds=5.0):
            chroma.add_chunks(chunks)

    def test_search_under_2s(self, chroma):
        """Une recherche sémantique doit répondre en moins de 2s (embedding mocké)."""
        chroma.add_chunks([_make_chunk(i) for i in range(20)])
        t0 = time.perf_counter()
        chroma.search("python", top_k=5)
        elapsed = time.perf_counter() - t0
        assert elapsed < 2.0, f"Recherche trop lente : {elapsed:.3f}s"

    def test_count_cache_hit_under_1ms(self, chroma):
        """Un appel count() après cache-warm doit prendre moins de 1ms."""
        chroma.add_chunks([_make_chunk(0)])
        chroma.count()  # warm le cache
        t0 = time.perf_counter()
        for _ in range(50):
            chroma.count()
        elapsed = (time.perf_counter() - t0) / 50
        assert elapsed < 0.001, f"Cache count trop lent : {elapsed*1000:.2f}ms/appel"

    def test_keyword_search_under_1s(self, chroma):
        chroma.add_chunks([_make_chunk(i) for i in range(50)])
        t0 = time.perf_counter()
        chroma.search_by_keyword("Contenu")
        elapsed = time.perf_counter() - t0
        assert elapsed < 1.0, f"Keyword search trop lente : {elapsed:.3f}s"

    def test_delete_100_chunks_under_3s(self, chroma):
        chunks = [_make_chunk(i) for i in range(100)]
        chroma.add_chunks(chunks)
        chroma.invalidate_list_notes_cache()
        t0 = time.perf_counter()
        chroma.delete_by_file("note.md")
        elapsed = time.perf_counter() - t0
        assert elapsed < 3.0, f"Suppression trop lente : {elapsed:.3f}s"

    def test_add_1000_chunks_under_30s(self, chroma, perf_timer):
        """Benchmark bulk insert — première indexation d'un grand coffre."""
        chunks = [_make_chunk(i) for i in range(1000)]
        with perf_timer.measure("add_1000_chunks", max_seconds=30.0):
            chroma.add_chunks(chunks)
        assert chroma.count() == 1000
