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
from chromadb.errors import InternalError

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
        def __init__(self) -> None:
            pass

        @staticmethod
        def build_from_config(config: dict):
            return _FakeEmbedFn()

        @staticmethod
        def name() -> str:
            return "fake-embed"

        @staticmethod
        def get_config() -> dict:
            return {"name": "fake-embed", "dimensions": 384}

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
        "get_notes_by_file_paths", "get_note_by_file_path", "list_user_notes",
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


@pytest.mark.unit
class TestChromaNoteHelpers:
    def test_get_notes_by_file_paths_preserves_requested_order(self, chroma):
        from src.database.chroma_store import ChromaStore

        chroma.list_notes = MagicMock(return_value=[
            {"file_path": "b.md", "title": "B"},
            {"file_path": "a.md", "title": "A"},
            {"file_path": "c.md", "title": "C"},
        ])

        notes = ChromaStore.get_notes_by_file_paths(chroma, ["a.md", "c.md"])

        assert [note["file_path"] for note in notes] == ["a.md", "c.md"]

    def test_get_note_by_file_path_returns_first_exact_match(self, chroma):
        from src.database.chroma_store import ChromaStore

        chroma.get_notes_by_file_paths = MagicMock(return_value=[{"file_path": "a.md", "title": "A"}])

        note = ChromaStore.get_note_by_file_path(chroma, "a.md")

        assert note == {"file_path": "a.md", "title": "A"}

    def test_list_user_notes_filters_obsirag_generated_paths(self, chroma):
        from src.database.chroma_store import ChromaStore

        chroma.list_notes = MagicMock(return_value=[
            {"file_path": "notes/a.md", "title": "A"},
            {"file_path": "obsirag/insights/generated.md", "title": "Generated"},
            {"file_path": "folder/obsirag/synapses/test.md", "title": "Generated 2"},
        ])

        notes = ChromaStore.list_user_notes(chroma)

        assert notes == [{"file_path": "notes/a.md", "title": "A"}]

    def test_list_generated_notes_keeps_only_obsirag_artifacts(self, chroma):
        from src.database.chroma_store import ChromaStore

        chroma.list_notes = MagicMock(return_value=[
            {"file_path": "notes/a.md", "title": "A"},
            {"file_path": "obsirag/insights/generated.md", "title": "Insight"},
            {"file_path": "folder/obsirag/synthesis/report.md", "title": "Report"},
        ])

        notes = ChromaStore.list_generated_notes(chroma)

        assert notes == [
            {"file_path": "obsirag/insights/generated.md", "title": "Insight"},
            {"file_path": "folder/obsirag/synthesis/report.md", "title": "Report"},
        ]

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
# Tests fonctionnels — branches avancées
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestChromaAdvancedBranches:
    def test_init_sets_lock_caches_and_collection_from_recovery(self):
        from src.database.chroma_store import ChromaStore

        collection = MagicMock()
        collection.count.return_value = 7

        with (
            patch("src.database.chroma_store.settings") as settings_mock,
            patch("src.database.chroma_store._build_embedding_function", return_value="embed") as build_embed,
            patch.object(ChromaStore, "_init_with_recovery", return_value=("client", collection)) as init_recovery,
        ):
            settings_mock.chroma_persist_dir = "/tmp/chroma"
            settings_mock.chroma_collection = "vault_chunks"
            store = ChromaStore()

        build_embed.assert_called_once_with()
        init_recovery.assert_called_once_with("/tmp/chroma", "embed")
        assert store._client == "client"
        assert store._collection is collection
        assert store._list_notes_cache is None
        assert store._count_cache is None

    def test_build_embedding_function_uses_openai_compatible_backend_when_ollama_embed_is_configured(self):
        from src.database.chroma_store import _build_embedding_function

        fake_openai_fn = MagicMock(name="OpenAIEmbeddingFunction")

        with (
            patch("src.database.chroma_store.settings") as settings_mock,
            patch("chromadb.utils.embedding_functions.OpenAIEmbeddingFunction", fake_openai_fn),
        ):
            settings_mock.ollama_embed_model = "nomic-embed-text"
            settings_mock.ollama_base_url = "http://localhost:11434/v1"
            settings_mock.embedding_model = "unused"
            result = _build_embedding_function()

        fake_openai_fn.assert_called_once_with(
            api_key="ollama",
            api_base="http://localhost:11434/v1",
            model_name="nomic-embed-text",
        )
        assert result is fake_openai_fn.return_value

    def test_build_embedding_function_uses_sentence_transformer_backend_by_default(self):
        from src.database.chroma_store import _build_embedding_function

        fake_sentence_fn = MagicMock(name="SentenceTransformerEmbeddingFunction")

        with (
            patch("src.database.chroma_store.settings") as settings_mock,
            patch("chromadb.utils.embedding_functions.SentenceTransformerEmbeddingFunction", fake_sentence_fn),
        ):
            settings_mock.ollama_embed_model = None
            settings_mock.embedding_model = "paraphrase-test"
            result = _build_embedding_function()

        fake_sentence_fn.assert_called_once_with(model_name="paraphrase-test", device="cpu")
        assert result is fake_sentence_fn.return_value

    def test_init_with_recovery_recreates_collection_after_corruption(self, tmp_path):
        from src.database.chroma_store import ChromaStore

        persist_dir = tmp_path / "chroma"
        persist_dir.mkdir()
        index_state = tmp_path / "data" / "index_state.json"
        index_state.parent.mkdir(parents=True)
        index_state.write_text('{"note.md": "hash"}', encoding="utf-8")

        good_collection = MagicMock()
        good_collection.count.return_value = 0
        good_client = MagicMock()
        good_client.get_or_create_collection.return_value = good_collection

        with (
            patch("src.database.chroma_store.chromadb.PersistentClient", side_effect=[InternalError("corrupt"), good_client]),
            patch("src.database.chroma_store.settings") as settings_mock,
            patch("src.database.chroma_store.shutil.rmtree") as rmtree,
        ):
            settings_mock.chroma_collection = "test_collection"
            settings_mock.index_state_file = index_state
            store = ChromaStore.__new__(ChromaStore)
            client, collection = store._init_with_recovery(str(persist_dir), MagicMock())

        assert client is good_client
        assert collection is good_collection
        rmtree.assert_called_once_with(persist_dir)
        assert index_state.read_text(encoding="utf-8") == "{}"

    def test_list_notes_uses_sqlite_rows_and_caches_result(self, chroma, tmp_path):
        from src.database.chroma_store import ChromaStore

        fake_rows = [
            ("b.md", "B", "2026-04-02T10:00:00", "2026-04-01T10:00:00", "tag2", "wiki2"),
            ("a.md", "A", "2026-04-03T10:00:00", "2026-04-01T09:00:00", "tag1,tag3", "wiki1,wiki3"),
        ]
        fake_conn = MagicMock()
        fake_conn.execute.return_value.fetchall.return_value = fake_rows
        fake_sqlite_connect = MagicMock(return_value=fake_conn)

        with (
            patch("src.database.chroma_store.settings") as settings_mock,
            patch("src.database.chroma_store.sqlite3.connect", fake_sqlite_connect),
        ):
            settings_mock.chroma_persist_dir = str(tmp_path / "chroma")
            settings_mock.chroma_collection = "test_collection"
            notes_first = ChromaStore.list_notes(chroma)
            notes_second = ChromaStore.list_notes(chroma)

        assert [n["file_path"] for n in notes_first] == ["a.md", "b.md"]
        assert notes_first[0]["tags"] == ["tag1", "tag3"]
        assert notes_first[0]["wikilinks"] == ["wiki1", "wiki3"]
        assert notes_second == notes_first
        fake_sqlite_connect.assert_called_once()
        fake_conn.close.assert_called_once()

    def test_list_notes_falls_back_to_collection_api(self, chroma, tmp_path):
        from src.database.chroma_store import ChromaStore

        chroma._collection.get = MagicMock(side_effect=[
            {
                "metadatas": [
                    {
                        "file_path": "a.md",
                        "note_title": "A",
                        "date_modified": "2026-04-03T10:00:00",
                        "date_created": "2026-04-01T09:00:00",
                        "tags": "tag1,tag2",
                        "wikilinks": "wiki1",
                    },
                    {
                        "file_path": "a.md",
                        "note_title": "A",
                        "date_modified": "2026-04-03T10:00:00",
                        "date_created": "2026-04-01T09:00:00",
                        "tags": "tag1,tag2",
                        "wikilinks": "wiki1",
                    },
                ]
            },
            {"metadatas": []},
        ])

        with (
            patch("src.database.chroma_store.settings") as settings_mock,
            patch("src.database.chroma_store.sqlite3.connect", side_effect=sqlite3.OperationalError("boom")),
        ):
            settings_mock.chroma_persist_dir = str(tmp_path / "chroma")
            settings_mock.chroma_collection = "test_collection"
            notes = ChromaStore.list_notes(chroma)

        assert notes == [{
            "file_path": "a.md",
            "title": "A",
            "date_modified": "2026-04-03T10:00:00",
            "date_created": "2026-04-01T09:00:00",
            "tags": ["tag1", "tag2"],
            "wikilinks": ["wiki1"],
        }]

    def test_search_by_note_title_falls_back_to_keyword_search(self, chroma):
        from src.database.chroma_store import ChromaStore

        chroma._collection.get = MagicMock(return_value={"ids": [], "documents": [], "metadatas": []})
        chroma.search_by_keyword = MagicMock(return_value=[{"chunk_id": "k1", "text": "x", "metadata": {}, "score": 0.95}])

        results = ChromaStore.search_by_note_title(chroma, "Titre absent", top_k=3)

        chroma.search_by_keyword.assert_called_once_with("Titre absent", top_k=3)
        assert results[0]["chunk_id"] == "k1"

    def test_get_recently_modified_filters_by_iso_date(self, chroma):
        from datetime import datetime
        from src.database.chroma_store import ChromaStore

        chroma.list_notes = MagicMock(return_value=[
            {"file_path": "old.md", "date_modified": "2026-04-01T10:00:00"},
            {"file_path": "new.md", "date_modified": "2026-04-03T10:00:00"},
        ])

        results = ChromaStore.get_recently_modified(chroma, datetime(2026, 4, 2, 0, 0, 0))

        assert [n["file_path"] for n in results] == ["new.md"]

    def test_search_by_date_range_falls_back_to_python_filter_then_candidates(self, chroma):
        from datetime import datetime
        from src.database.chroma_store import ChromaStore

        filtered_chunk = {
            "chunk_id": "ok",
            "text": "ok",
            "metadata": {"date_modified": "2026-04-03T10:00:00"},
            "score": 0.9,
        }
        old_chunk = {
            "chunk_id": "old",
            "text": "old",
            "metadata": {"date_modified": "2026-04-01T10:00:00"},
            "score": 0.8,
        }

        chroma.search = MagicMock(side_effect=[[], [filtered_chunk, old_chunk]])

        results = ChromaStore.search_by_date_range(
            chroma,
            "requête",
            since=datetime(2026, 4, 2),
            until=datetime(2026, 4, 4),
            top_k=2,
        )

        assert results == [filtered_chunk]
        assert chroma.search.call_count == 2

    def test_search_by_date_range_returns_direct_filtered_results_when_available(self, chroma):
        from datetime import datetime
        from src.database.chroma_store import ChromaStore

        direct = [{"chunk_id": "direct", "text": "x", "metadata": {"date_modified": "2026-04-03T10:00:00"}, "score": 0.9}]
        chroma.search = MagicMock(return_value=direct)

        results = ChromaStore.search_by_date_range(
            chroma,
            "requête",
            since=datetime(2026, 4, 2),
            until=datetime(2026, 4, 4),
            top_k=2,
        )

        assert results == direct
        chroma.search.assert_called_once()

    def test_search_by_date_range_swallow_search_exception_and_fallback(self, chroma):
        from datetime import datetime
        from src.database.chroma_store import ChromaStore

        fallback = [{"chunk_id": "fallback", "text": "x", "metadata": {"date_modified": "2026-04-03T10:00:00"}, "score": 0.9}]
        chroma.search = MagicMock(side_effect=[RuntimeError("boom"), fallback])

        results = ChromaStore.search_by_date_range(
            chroma,
            "requête",
            since=datetime(2026, 4, 2),
            until=datetime(2026, 4, 4),
            top_k=2,
        )

        assert results == fallback

    def test_search_by_entity_filters_matching_metadata_and_falls_back_when_no_match(self, chroma):
        from src.database.chroma_store import ChromaStore

        matching = {
            "chunk_id": "match",
            "text": "Ada mentionnée",
            "metadata": {"ner_persons": "Ada Lovelace"},
            "score": 0.9,
        }
        unrelated = {
            "chunk_id": "other",
            "text": "Alan mentionné",
            "metadata": {"ner_persons": "Alan Turing"},
            "score": 0.7,
        }

        chroma.search = MagicMock(return_value=[matching, unrelated])
        results = ChromaStore.search_by_entity(chroma, "Ada", entity_type="persons", top_k=3)
        assert results == [matching]

        chroma.search = MagicMock(return_value=[unrelated])
        fallback_results = ChromaStore.search_by_entity(chroma, "Ada", entity_type="persons", top_k=3)
        assert fallback_results == [unrelated]

    def test_search_by_tags_falls_back_to_semantic_candidates_when_no_overlap(self, chroma):
        from src.database.chroma_store import ChromaStore

        chunk = {
            "chunk_id": "chunk",
            "text": "science",
            "metadata": {"tags": "science,space"},
            "score": 0.8,
        }
        chroma.search = MagicMock(return_value=[chunk])

        results = ChromaStore.search_by_tags(chroma, ["python"], top_k=2)

        assert results == [chunk]

    def test_search_by_keyword_ignores_failed_variant_and_uses_next_one(self, chroma):
        from src.database.chroma_store import ChromaStore

        chroma._collection.get = MagicMock(side_effect=[RuntimeError("boom"), {
            "ids": ["k1"],
            "documents": ["Doc"],
            "metadatas": [{"note_title": "Note"}],
        }, {
            "ids": [],
            "documents": [],
            "metadatas": [],
        }])

        results = ChromaStore.search_by_keyword(chroma, "Keyword", top_k=2)

        assert results == [{"chunk_id": "k1", "text": "Doc", "metadata": {"note_title": "Note"}, "score": 0.95}]

    def test_list_notes_fallback_paginates_multiple_batches(self, chroma, tmp_path):
        from src.database.chroma_store import ChromaStore

        first_page = [
            {"file_path": f"fill_{i}.md", "note_title": f"Fill {i}", "date_modified": "2026-04-01T10:00:00", "date_created": "", "tags": "", "wikilinks": ""}
            for i in range(499)
        ]
        first_page.insert(0, {"file_path": "a.md", "note_title": "A", "date_modified": "2026-04-03T10:00:00", "date_created": "", "tags": "tag1", "wikilinks": ""})

        chroma._collection.get = MagicMock(side_effect=[
            {"metadatas": first_page},
            {"metadatas": [{"file_path": "b.md", "note_title": "B", "date_modified": "2026-04-02T10:00:00", "date_created": "", "tags": "tag2", "wikilinks": ""}]},
            {"metadatas": []},
        ])

        with (
            patch("src.database.chroma_store.settings") as settings_mock,
            patch("src.database.chroma_store.sqlite3.connect", side_effect=sqlite3.OperationalError("boom")),
        ):
            settings_mock.chroma_persist_dir = str(tmp_path / "chroma")
            settings_mock.chroma_collection = "test_collection"
            notes = ChromaStore.list_notes(chroma)

        assert notes[0]["file_path"] == "a.md"
        assert any(note["file_path"] == "b.md" for note in notes)
        assert chroma._collection.get.call_count == 2

    def test_find_similar_notes_returns_empty_when_source_lookup_fails_or_has_no_docs(self, chroma):
        from src.database.chroma_store import ChromaStore

        chroma._collection.get = MagicMock(side_effect=RuntimeError("boom"))
        assert ChromaStore.find_similar_notes(chroma, "source.md", existing_links=set()) == []

        chroma._collection.get = MagicMock(return_value={"documents": []})
        assert ChromaStore.find_similar_notes(chroma, "source.md", existing_links=set()) == []

    def test_find_similar_notes_respects_top_k_limit(self, chroma):
        from src.database.chroma_store import ChromaStore

        chroma._collection.get = MagicMock(return_value={"documents": ["source one", "source two"]})
        chroma.search = MagicMock(return_value=[
            {"chunk_id": "1", "text": "a", "metadata": {"file_path": "a.md", "note_title": "A"}, "score": 0.9},
            {"chunk_id": "2", "text": "b", "metadata": {"file_path": "b.md", "note_title": "B"}, "score": 0.89},
            {"chunk_id": "3", "text": "c", "metadata": {"file_path": "c.md", "note_title": "C"}, "score": 0.88},
        ])

        results = ChromaStore.find_similar_notes(chroma, "source.md", existing_links=set(), top_k=2, threshold=0.5)

        assert [result["file_path"] for result in results] == ["a.md", "b.md"]

    def test_search_by_note_title_returns_exact_matches_without_keyword_fallback(self, chroma):
        from src.database.chroma_store import ChromaStore

        chroma._collection.get = MagicMock(side_effect=[
            {"ids": ["a_1"], "documents": ["Doc A"], "metadatas": [{"note_title": "My Note", "file_path": "a.md"}]},
            {"ids": ["a_1"], "documents": ["Doc A"], "metadatas": [{"note_title": "My Note", "file_path": "a.md"}]},
            {"ids": [], "documents": [], "metadatas": []},
            {"ids": [], "documents": [], "metadatas": []},
        ])
        chroma.search_by_keyword = MagicMock()

        results = ChromaStore.search_by_note_title(chroma, "My Note", top_k=2)

        assert results == [{"chunk_id": "a_1", "text": "Doc A", "metadata": {"note_title": "My Note", "file_path": "a.md"}, "score": 0.98}]
        chroma.search_by_keyword.assert_not_called()

    def test_find_similar_notes_excludes_existing_links_and_low_scores(self, chroma):
        from src.database.chroma_store import ChromaStore

        chroma._collection.get = MagicMock(return_value={"documents": ["source one", "source two"]})
        chroma.search = MagicMock(return_value=[
            {"chunk_id": "self", "text": "source one", "metadata": {"file_path": "source.md", "note_title": "Source"}, "score": 0.99},
            {"chunk_id": "linked", "text": "linked text", "metadata": {"file_path": "linked.md", "note_title": "AlreadyLinked"}, "score": 0.91},
            {"chunk_id": "low", "text": "low text", "metadata": {"file_path": "low.md", "note_title": "Low"}, "score": 0.4},
            {"chunk_id": "good", "text": "good text" * 50, "metadata": {"file_path": "good.md", "note_title": "Good"}, "score": 0.88},
        ])

        results = ChromaStore.find_similar_notes(
            chroma,
            "source.md",
            existing_links={"linked.md", "alreadylinked"},
            top_k=3,
            threshold=0.65,
        )

        assert results == [{"file_path": "good.md", "title": "Good", "score": 0.88, "excerpt": ("good text" * 50)[:300]}]

    def test_format_results_handles_empty_metadata(self):
        from src.database.chroma_store import ChromaStore

        formatted = ChromaStore._format_results({
            "ids": [["a"]],
            "documents": [["doc"]],
            "metadatas": [[None]],
            "distances": [[0.2]],
        })

        assert formatted == [{"chunk_id": "a", "text": "doc", "metadata": {}, "score": 0.8}]



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
