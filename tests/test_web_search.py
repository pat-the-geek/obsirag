from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ai import web_search


@pytest.mark.unit
class TestWebSearchHelpers:
    def test_is_not_in_vault_only_accepts_pure_sentinel(self):
        assert web_search.is_not_in_vault("Cette information n'est pas dans ton coffre.") is True
        assert web_search.is_not_in_vault("Cette information n'est pas dans ton coffre.\n\nMais voici une synthèse") is False

    def test_normalize_user_query_for_search_removes_chat_prefix(self):
        assert web_search._normalize_user_query_for_search("Parle moi de Ada Lovelace ?") == "Ada Lovelace"

    def test_extract_focus_terms_filters_stopwords_and_short_tokens(self):
        terms = web_search._extract_focus_terms("Que sais-tu de la mission Artemis II ?")
        assert "mission" in terms
        assert "artemis" in terms
        assert "ii" not in terms

    def test_build_snippets_concatenates_sources(self):
        snippets = web_search._build_snippets([
            {"title": "Titre 1", "href": "https://a", "body": "Texte A"},
            {"title": "Titre 2", "href": "https://b", "body": "Texte B"},
        ])
        assert "Titre 1" in snippets
        assert "https://b" in snippets

    def test_safe_filename_truncates_and_sanitizes(self):
        name = web_search._safe_filename("Question complexe: Python/IA & données !!!")
        assert "/" not in name
        assert len(name) <= 60

    def test_is_generic_subject_request_detects_subject_overview_prompt(self):
        assert web_search._is_generic_subject_request("Présente-moi Dune") is True
        assert web_search._is_generic_subject_request("Quel est le PIB de la France ?") is False

    def test_is_latin_text_rejects_mostly_non_latin_text(self):
        assert web_search._is_latin_text("Ada Lovelace") is True
        assert web_search._is_latin_text("纯中文内容纯中文内容") is False


@pytest.mark.unit
class TestWebSearchQueryBuilding:
    def test_build_disambiguation_query_returns_none_for_non_generic_or_multi_term_subject(self):
        llm = MagicMock()
        assert web_search._build_disambiguation_query("Quel est le PIB de la France ?", llm) is None
        assert web_search._build_disambiguation_query("Parle moi de mission Artemis", llm) is None
        llm.chat.assert_not_called()

    def test_build_disambiguation_query_returns_cleaned_llm_output(self):
        llm = MagicMock()
        llm.chat.return_value = ' "Dune science fiction overview" '

        with (
            patch("src.ai.web_search._is_generic_subject_request", return_value=True),
            patch("src.ai.web_search._extract_focus_terms", return_value=["dune"]),
        ):
            query = web_search._build_disambiguation_query("Présente-moi Dune", llm)

        assert query == "Dune science fiction overview"

    def test_build_search_query_uses_disambiguation_when_available(self):
        llm = MagicMock()
        with patch("src.ai.web_search._build_disambiguation_query", return_value="Dune science fiction overview"):
            query = web_search._build_search_query("Parle moi de Dune", llm)
        assert query == "Dune science fiction overview"
        llm.chat.assert_not_called()

    def test_build_search_query_falls_back_to_normalized_question_on_meta_output(self):
        llm = MagicMock()
        llm.chat.return_value = "comment chercher"
        with patch("src.ai.web_search._build_disambiguation_query", return_value=None):
            query = web_search._build_search_query("Parle moi de Ada Lovelace", llm)
        assert query == "Ada Lovelace"

    def test_build_search_query_returns_normalized_question_on_exception(self):
        llm = MagicMock()
        llm.chat.side_effect = RuntimeError("boom")
        with patch("src.ai.web_search._build_disambiguation_query", return_value=None):
            query = web_search._build_search_query("Parle moi de Grace Hopper", llm)
        assert query == "Grace Hopper"

    def test_build_search_query_keeps_short_valid_focus_query(self):
        llm = MagicMock()
        llm.chat.return_value = "Ada Lovelace"
        with patch("src.ai.web_search._build_disambiguation_query", return_value=None):
            query = web_search._build_search_query("Parle moi de Ada Lovelace", llm)
        assert query == "Ada Lovelace"

    def test_build_search_query_keeps_single_short_subject_without_llm_rewrite(self):
        llm = MagicMock()

        query = web_search._build_search_query("lune", llm)

        assert query == "lune"
        llm.chat.assert_not_called()


@pytest.mark.unit
class TestWebSearchDuckDuckGo:
    def test_ddg_search_tries_fallback_candidate_query_when_first_is_empty(self):
        fake_module = types.ModuleType("duckduckgo_search")
        seen_queries = []

        class _FakeDDGS:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def text(self, query, region=None, safesearch=None, max_results=None):
                seen_queries.append(query)
                if query == "Dune":
                    return []
                return [{"title": "Wikipedia", "href": "https://wikipedia.org", "body": "Dune overview"}]

        fake_module.DDGS = _FakeDDGS

        with patch.dict(sys.modules, {"duckduckgo_search": fake_module}):
            results = web_search._ddg_search("Dune", max_results=5)

        assert results[0]["href"] == "https://wikipedia.org"
        assert seen_queries == ["Dune", "Dune -知乎", "Dune wikipedia"]

    def test_ddg_search_prefers_more_relevant_later_candidate_results(self):
        fake_module = types.ModuleType("duckduckgo_search")

        class _FakeDDGS:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def text(self, query, region=None, safesearch=None, max_results=None):
                if query == "lune":
                    return [
                        {"title": "River Lune 2025", "href": "https://example.com/river-lune", "body": "Fishing report"},
                    ]
                if query == "lune -知乎":
                    return [
                        {"title": "River Lune forum", "href": "https://example.com/forum", "body": "Fishing on the Lune"},
                    ]
                return [
                    {"title": "Lune — Wikipédia", "href": "https://fr.wikipedia.org/wiki/Lune", "body": "La Lune est le satellite naturel de la Terre."},
                ]

        fake_module.DDGS = _FakeDDGS

        with patch.dict(sys.modules, {"duckduckgo_search": fake_module}):
            results = web_search._ddg_search("lune", max_results=5)

        assert results == [
            {"title": "Lune — Wikipédia", "href": "https://fr.wikipedia.org/wiki/Lune", "body": "La Lune est le satellite naturel de la Terre."},
        ]

    def test_ddg_search_filters_non_latin_and_returns_results(self):
        fake_module = types.ModuleType("duckduckgo_search")

        class _FakeDDGS:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def text(self, query, region=None, safesearch=None, max_results=None):
                return [
                    {"title": "Titre latin", "href": "https://a", "body": "Contenu latin utile"},
                    {"title": "纯中文", "href": "https://b", "body": "中文内容"},
                ]

        fake_module.DDGS = _FakeDDGS

        with patch.dict(sys.modules, {"duckduckgo_search": fake_module}):
            results = web_search._ddg_search("Ada Lovelace", max_results=5)

        assert len(results) == 1
        assert results[0]["href"] == "https://a"

    def test_ddg_search_returns_empty_on_exception(self):
        fake_module = types.ModuleType("duckduckgo_search")

        class _FakeDDGS:
            def __enter__(self):
                raise RuntimeError("network")

            def __exit__(self, exc_type, exc, tb):
                return False

        fake_module.DDGS = _FakeDDGS

        with patch.dict(sys.modules, {"duckduckgo_search": fake_module}):
            results = web_search._ddg_search("Ada Lovelace", max_results=5)

        assert results == []


@pytest.mark.unit
class TestWebSearchPublicApi:
    def test_synthesize_returns_none_on_llm_error(self):
        llm = MagicMock()
        llm.chat.side_effect = RuntimeError("boom")
        answer = web_search._synthesize("query", [{"title": "T", "href": "https://a", "body": "B"}], llm)
        assert answer is None

    def test_synthesize_returns_none_without_results(self):
        llm = MagicMock()
        assert web_search._synthesize("query", [], llm) is None

    def test_check_quality_rejects_zero_lexical_overlap(self):
        llm = MagicMock()
        ok = web_search._check_quality(
            "satellite gravite",
            "Réponse",
            [{"title": "recette", "body": "cuisine dessert", "href": "https://a"}],
            llm,
        )
        assert ok is False
        llm.chat.assert_not_called()

    def test_check_quality_uses_llm_verdict_when_overlap_exists(self):
        llm = MagicMock()
        llm.chat.return_value = "GOOD"

        ok = web_search._check_quality(
            "Ada Lovelace",
            "Réponse",
            [{"title": "Ada Lovelace", "body": "Ada Lovelace pionnière", "href": "https://a"}],
            llm,
        )

        assert ok is True
        llm.chat.assert_called_once()

    def test_check_quality_accepts_authoritative_exact_match_without_llm(self):
        llm = MagicMock()

        ok = web_search._check_quality(
            "lune",
            "La Lune est le satellite naturel de la Terre.",
            [
                {
                    "title": "Lune — Wikipédia",
                    "body": "La Lune est le seul satellite naturel permanent de la Terre.",
                    "href": "https://fr.wikipedia.org/wiki/Lune",
                }
            ],
            llm,
        )

        assert ok is True
        llm.chat.assert_not_called()

    def test_check_quality_returns_true_when_llm_check_fails(self):
        llm = MagicMock()
        llm.chat.side_effect = RuntimeError("boom")

        ok = web_search._check_quality(
            "Ada Lovelace",
            "Réponse",
            [{"title": "Ada Lovelace", "body": "Ada Lovelace pionnière", "href": "https://a"}],
            llm,
        )

        assert ok is True

    def test_save_insight_writes_markdown_file(self, tmp_settings):
        with patch("src.ai.web_search.settings", tmp_settings):
            path = web_search._save_insight(
                "Qui est Ada Lovelace ?",
                "Mathématicienne pionnière.",
                [{"title": "Wikipedia", "href": "https://wikipedia.org"}],
            )

        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "web_insight" in content
        assert "Ada Lovelace" in content

    def test_enrich_sync_happy_path_returns_answer_and_path(self, tmp_settings):
        llm = MagicMock()
        with (
            patch("src.ai.web_search.settings", tmp_settings),
            patch("src.ai.web_search._build_search_query", return_value="ada lovelace"),
            patch("src.ai.web_search._ddg_search", return_value=[{"title": "Wiki", "href": "https://wikipedia.org", "body": "Ada Lovelace body"}]),
            patch("src.ai.web_search._synthesize", return_value="Réponse web utile"),
            patch("src.ai.web_search._check_quality", return_value=True),
        ):
            answer, path, results, quality = web_search.enrich_sync("Qui est Ada Lovelace ?", llm)

        assert answer == "Réponse web utile"
        assert path is not None and path.exists()
        assert len(results) == 1
        assert quality is True

    def test_enrich_sync_returns_none_when_search_has_no_results(self):
        llm = MagicMock()
        with (
            patch("src.ai.web_search._build_search_query", return_value="ada lovelace"),
            patch("src.ai.web_search._ddg_search", return_value=[]),
        ):
            answer, path, results, quality = web_search.enrich_sync("Qui est Ada Lovelace ?", llm)

        assert answer is None
        assert path is None
        assert results == []
        assert quality is False

    def test_enrich_sync_returns_none_when_synthesis_fails(self):
        llm = MagicMock()
        with (
            patch("src.ai.web_search._build_search_query", return_value="ada lovelace"),
            patch("src.ai.web_search._ddg_search", return_value=[{"title": "Wiki", "href": "https://wikipedia.org", "body": "Ada Lovelace body"}]),
            patch("src.ai.web_search._synthesize", return_value=None),
        ):
            answer, path, results, quality = web_search.enrich_sync("Qui est Ada Lovelace ?", llm)

        assert answer is None
        assert path is None
        assert len(results) == 1
        assert quality is False

    def test_enrich_sync_returns_none_when_quality_fails(self):
        llm = MagicMock()
        with (
            patch("src.ai.web_search._build_search_query", return_value="ada lovelace"),
            patch("src.ai.web_search._ddg_search", return_value=[{"title": "Wiki", "href": "https://wikipedia.org", "body": "Ada Lovelace body"}]),
            patch("src.ai.web_search._synthesize", return_value="Réponse web utile"),
            patch("src.ai.web_search._check_quality", return_value=False),
        ):
            answer, path, results, quality = web_search.enrich_sync("Qui est Ada Lovelace ?", llm)

        assert answer is None
        assert path is None
        assert len(results) == 1
        assert quality is False

    def test_enrich_async_calls_callback(self):
        callback = MagicMock()

        class _ImmediateThread:
            def __init__(self, target=None, daemon=None, name=None):
                self.target = target

            def start(self):
                self.target()

        with (
            patch("src.ai.web_search.enrich_sync", return_value=("answer", Path("/tmp/x.md"), [{"href": "https://a"}], True)),
            patch("src.ai.web_search.threading.Thread", side_effect=lambda **kwargs: _ImmediateThread(**kwargs)),
        ):
            web_search.enrich_async("query", MagicMock(), on_done=callback)

        callback.assert_called_once_with("answer", Path("/tmp/x.md"), [{"href": "https://a"}], True)
