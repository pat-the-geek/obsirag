"""
Tests unitaires + performance — RAG Pipeline (src/ai/rag.py)
Tous les appels LLM et ChromaDB sont mockés.
"""
from __future__ import annotations

import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.ai.rag import RAGPipeline, _TAG_PATTERN


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_chunk(title: str = "Note test", text: str = "Contenu de test.", fp: str = "note.md") -> dict:
    return {
        "chunk_id": f"{fp}_0",
        "text": text,
        "metadata": {
            "note_title": title,
            "file_path": fp,
            "date_modified": "2026-04-01T10:00:00",
            "tags": "test",
            "wikilinks": "",
        },
        "score": 0.9,
    }


@pytest.fixture
def rag(mock_chroma, mock_llm):
    return RAGPipeline(chroma=mock_chroma, llm=mock_llm)


# ---------------------------------------------------------------------------
# Détection d'intention — _detect_temporal
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTemporalDetection:
    @pytest.mark.parametrize("query,expected_days", [
        ("notes de cette semaine", 7),
        ("qu'ai-je fait ce mois", 30),
        ("notes d'aujourd'hui", 1),
        ("récemment j'ai noté", 14),
        ("cette année j'ai appris", 365),
        ("les 5 derniers jours", 5),
        ("les 30 derniers jours", 30),
    ])
    def test_temporal_patterns(self, query, expected_days):
        from src.ai.rag import RAGPipeline
        result = RAGPipeline._detect_temporal(query)
        assert result == expected_days, f"Query {query!r}: attendu {expected_days}, got {result}"

    def test_no_temporal_returns_none(self):
        from src.ai.rag import RAGPipeline
        assert RAGPipeline._detect_temporal("comment fonctionne Python ?") is None
        assert RAGPipeline._detect_temporal("qu'est-ce que le LLM ?") is None


# ---------------------------------------------------------------------------
# Détection d'intention — tags
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestTagDetection:
    def test_tag_pattern_extracts_tags(self):
        tags = _TAG_PATTERN.findall("Ma question sur #python et #ia")
        assert "python" in tags
        assert "ia" in tags

    def test_tag_pattern_no_match(self):
        tags = _TAG_PATTERN.findall("Aucun tag ici")
        assert tags == []

    def test_tag_pattern_with_hyphen(self):
        tags = _TAG_PATTERN.findall("Note sur #machine-learning")
        assert "machine-learning" in tags

    def test_tag_pattern_with_slash(self):
        tags = _TAG_PATTERN.findall("Vois #projets/alpha")
        assert "projets/alpha" in tags


# ---------------------------------------------------------------------------
# Détection d'intention — noms propres
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestProperNounDetection:
    def test_extracts_proper_noun(self):
        nouns = RAGPipeline._extract_proper_nouns("Notes sur Einstein et Newton")
        assert any("Einstein" in n for n in nouns)
        assert any("Newton" in n for n in nouns)

    def test_ignores_first_word_of_sentence(self):
        nouns = RAGPipeline._extract_proper_nouns("Comment fonctionne Python ?")
        # "Comment" est le premier mot → non extrait
        assert not any("Comment" in n for n in nouns)

    def test_common_acronyms_filtered(self):
        nouns = RAGPipeline._extract_proper_nouns("Comment fonctionne IA et LLM ?")
        assert "IA" not in nouns
        assert "LLM" not in nouns

    def test_empty_query(self):
        assert RAGPipeline._extract_proper_nouns("") == []


# ---------------------------------------------------------------------------
# Construction du contexte — _build_context
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBuildContext:
    def test_empty_chunks_returns_fallback(self, rag):
        ctx = rag._build_context([])
        assert "Aucune note" in ctx

    def test_context_contains_chunk_text(self, rag):
        chunks = [_make_chunk(text="Texte important du chunk.")]
        ctx = rag._build_context(chunks)
        assert "Texte important" in ctx

    def test_char_budget_truncates(self, rag):
        chunks = [_make_chunk(text="x" * 2000)]
        ctx = rag._build_context(chunks, char_budget=100)
        assert len(ctx) <= 500  # contexte tronqué + header

    def test_multiple_notes_deduplicated(self, rag):
        """Deux chunks de la même note → une seule entrée dans le contexte."""
        chunks = [
            _make_chunk(title="Note A", fp="a.md"),
            _make_chunk(title="Note A", fp="a.md"),  # même note
        ]
        ctx = rag._build_context(chunks)
        assert ctx.count("Note A") == 1

    def test_context_budget_budgets_applied(self, rag):
        budgets = RAGPipeline._context_budgets()
        assert len(budgets) == 4
        assert budgets[0] > budgets[1] > budgets[2] > budgets[3]


# ---------------------------------------------------------------------------
# Construction des messages — _build_messages
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBuildMessages:
    def test_messages_contain_system_prompt(self, rag):
        msgs = rag._build_messages("Question ?", "Contexte.", [])
        assert any(m["role"] == "system" for m in msgs)

    def test_messages_contain_user_query(self, rag):
        msgs = rag._build_messages("Ma question ici ?", "Contexte.", [])
        user_msgs = [m for m in msgs if m["role"] == "user"]
        assert any("Ma question ici" in m["content"] for m in user_msgs)

    def test_messages_include_history(self, rag):
        history = [{"role": "user", "content": "Ancienne question"}]
        msgs = rag._build_messages("Nouvelle question ?", "ctx", history)
        contents = [m["content"] for m in msgs]
        assert any("Ancienne question" in c for c in contents)

    def test_messages_context_in_user_message(self, rag):
        msgs = rag._build_messages("Q ?", "CONTEXTE_UNIQUE_TEST", [])
        user_msgs = [m for m in msgs if m["role"] == "user"]
        assert any("CONTEXTE_UNIQUE_TEST" in m["content"] for m in user_msgs)


# ---------------------------------------------------------------------------
# query() — appels LLM mockés
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRAGQuery:
    def test_query_returns_answer_and_sources(self, rag):
        answer, sources = rag.query("Qu'est-ce que Python ?")
        assert isinstance(answer, str)
        assert len(answer) > 0
        assert isinstance(sources, list)

    def test_query_uses_chroma_search(self, rag, mock_chroma):
        rag.query("Qu'est-ce que Python ?")
        mock_chroma.search.assert_called()

    def test_query_uses_llm(self, rag, mock_llm):
        rag.query("Qu'est-ce que Python ?")
        mock_llm.chat.assert_called()

    def test_query_tag_intent_uses_tag_search(self, rag, mock_chroma):
        rag.query("Montre-moi mes notes #python")
        mock_chroma.search_by_tags.assert_called()

    def test_query_temporal_intent_uses_date_search(self, rag, mock_chroma):
        rag.query("Qu'est-ce que j'ai noté cette semaine ?")
        mock_chroma.search_by_date_range.assert_called()


# ---------------------------------------------------------------------------
# query_stream() — token streaming mocké
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRAGQueryStream:
    def test_stream_returns_iterator_and_sources(self, rag):
        stream, sources = rag.query_stream("Explique Python")
        assert hasattr(stream, "__iter__") or hasattr(stream, "__next__")
        assert isinstance(sources, list)

    def test_stream_yields_tokens(self, rag):
        stream, _ = rag.query_stream("Explique Python")
        tokens = list(stream)
        assert len(tokens) > 0

    def test_stream_concatenated_is_answer(self, rag):
        stream, _ = rag.query_stream("Explique Python")
        full = "".join(tokens for tokens in stream)
        assert len(full) > 0


# ---------------------------------------------------------------------------
# Performance — RAG pipeline (LLM + Chroma mockés)
# ---------------------------------------------------------------------------

@pytest.mark.perf
class TestRAGPerformance:
    def test_retrieve_under_50ms(self, rag, mock_chroma):
        """La phase de retrieval (hors LLM) doit être inférieure à 50ms."""
        t0 = time.perf_counter()
        rag._retrieve("Qu'est-ce que Python ?")
        elapsed = time.perf_counter() - t0
        assert elapsed < 0.05, f"Retrieval trop lent : {elapsed*1000:.1f}ms"

    def test_build_context_100_chunks_under_10ms(self, rag):
        """Construction du contexte pour 100 chunks doit être < 10ms."""
        chunks = [_make_chunk(title=f"Note {i}", fp=f"note_{i}.md") for i in range(100)]
        t0 = time.perf_counter()
        rag._build_context(chunks)
        elapsed = time.perf_counter() - t0
        assert elapsed < 0.01, f"_build_context trop lent : {elapsed*1000:.1f}ms"

    def test_detect_temporal_under_1ms(self):
        """La détection d'intention temporelle doit être quasi-instantanée."""
        queries = [
            "notes de cette semaine",
            "qu'ai-je fait ce mois",
            "comment fonctionne Python",
            "les 10 derniers jours",
            "récemment j'ai découvert",
        ]
        t0 = time.perf_counter()
        for _ in range(200):
            for q in queries:
                RAGPipeline._detect_temporal(q)
        elapsed = (time.perf_counter() - t0) / (200 * len(queries))
        assert elapsed < 0.001, f"_detect_temporal trop lent : {elapsed*1000:.3f}ms/appel"

    def test_extract_proper_nouns_under_1ms(self):
        """L'extraction des noms propres doit être < 1ms par requête."""
        queries = [
            "Notes sur Einstein et Newton",
            "Rencontre avec Marie Curie",
            "Projet avec Apple et Google",
        ]
        t0 = time.perf_counter()
        for _ in range(500):
            for q in queries:
                RAGPipeline._extract_proper_nouns(q)
        elapsed = (time.perf_counter() - t0) / (500 * len(queries))
        assert elapsed < 0.001, f"_extract_proper_nouns trop lent : {elapsed*1000:.3f}ms/appel"

    def test_query_end_to_end_mock_under_200ms(self, rag):
        """Un appel complet query() avec mocks doit être < 200ms."""
        t0 = time.perf_counter()
        rag.query("Qu'est-ce que Python ?")
        elapsed = time.perf_counter() - t0
        assert elapsed < 0.2, f"query() trop lent avec mocks: {elapsed*1000:.0f}ms"

    def test_10_parallel_queries_under_1s(self, mock_chroma, mock_llm):
        """10 appels _retrieve() séquentiels doivent tenir en moins de 1s."""
        rag = RAGPipeline(chroma=mock_chroma, llm=mock_llm)
        t0 = time.perf_counter()
        for i in range(10):
            rag._retrieve(f"Question numéro {i} ?")
        elapsed = time.perf_counter() - t0
        assert elapsed < 1.0, f"10 retrievals trop lents : {elapsed:.3f}s"


# ---------------------------------------------------------------------------
# Import conditionnel de _detect_temporal (fonction statique → accessible hors classe)
# ---------------------------------------------------------------------------

def _detect_temporal_query(query: str):
    return RAGPipeline._detect_temporal(query)
