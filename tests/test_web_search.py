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

    def test_is_not_in_vault_accepts_common_negative_variants(self):
        assert web_search.is_not_in_vault("Cette information n'est pas consignée dans ton coffre.") is True
        assert web_search.is_not_in_vault("Je n'ai pas trouvé d'information dans ton coffre.") is True
        assert web_search.is_not_in_vault("Aucune information pertinente n'est disponible dans ton coffre.") is True

    def test_normalize_user_query_for_search_removes_chat_prefix(self):
        assert web_search._normalize_user_query_for_search("Parle moi de Ada Lovelace ?") == "Ada Lovelace"

    def test_extract_focus_terms_filters_stopwords_and_short_tokens(self):
        terms = web_search._extract_focus_terms("Que sais-tu de la mission Artemis II ?")
        assert "mission" in terms
        assert "artemis" in terms
        assert "ii" not in terms

    def test_keywordize_query_removes_question_framing_and_keeps_subject_terms(self):
        query = web_search._keywordize_query(
            "j'aimerais savoir quelles sont les nouveautés pour l'iphone de Apple en 2026"
        )
        assert query == "iphone Apple nouveautés 2026"

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

    def test_extract_subject_phrase_and_flatten_related_topics_cover_edge_cases(self):
        assert web_search._extract_subject_phrase("Ada Lovelace") == "Ada Lovelace"
        assert web_search._extract_subject_phrase("mot") is None
        assert web_search._flatten_related_topics([
            {"Topics": [{"FirstURL": "https://a", "Text": "Ada - mathematician"}]},
            {"FirstURL": "https://b", "Text": "Charles Babbage - polymath"},
        ]) == [
            {"FirstURL": "https://a", "Text": "Ada - mathematician"},
            {"FirstURL": "https://b", "Text": "Charles Babbage - polymath"},
        ]

    def test_build_instant_answer_results_deduplicates_heading_and_related_topics(self):
        results = web_search._build_instant_answer_results(
            {
                "Heading": "Ada Lovelace",
                "AbstractText": "English mathematician.",
                "AbstractURL": "https://en.wikipedia.org/wiki/Ada_Lovelace",
                "AbstractSource": "Wikipedia",
                "RelatedTopics": [
                    {"Text": "Ada Lovelace - English mathematician", "FirstURL": "https://en.wikipedia.org/wiki/Ada_Lovelace"},
                    {"Topics": [{"Text": "Charles Babbage - English polymath", "FirstURL": "https://duckduckgo.com/Charles_Babbage"}]},
                ],
            },
            max_results=3,
        )

        assert results == [
            {
                "title": "Ada Lovelace - Wikipedia",
                "href": "https://en.wikipedia.org/wiki/Ada_Lovelace",
                "body": "English mathematician.",
            },
            {
                "title": "Charles Babbage",
                "href": "https://duckduckgo.com/Charles_Babbage",
                "body": "Charles Babbage - English polymath",
            },
        ]

    def test_merge_search_results_deduplicates_urls_and_caps_length(self):
        merged = web_search._merge_search_results(
            [{"href": "https://a", "title": "A"}, {"href": "https://b", "title": "B"}],
            [{"href": "https://b", "title": "B2"}, {"href": "https://c", "title": "C"}],
            max_results=2,
        )

        assert merged == [
            {"href": "https://a", "title": "A"},
            {"href": "https://b", "title": "B"},
        ]

    def test_count_exact_term_matches_and_short_entity_query_helpers(self):
        assert web_search._count_exact_term_matches(["ada", "lovelace"], "Ada Lovelace invents") == 2
        assert web_search._count_exact_term_matches([], "Ada") == 0
        assert web_search._is_short_entity_query("Ada Lovelace") is True
        assert web_search._is_short_entity_query("mission Artemis II calendrier 2026") is False
        assert web_search._is_short_entity_query("lune 2026") is False

    def test_keywordize_query_and_tokenize_match_text_cover_fallback_cases(self):
        assert web_search._tokenize_match_text("Ada-Lovelace 2026") == ["ada-lovelace", "2026"]
        assert web_search._keywordize_query("de de de") == "de de de"
        assert web_search._keywordize_query("Apple Apple iPhone iPhone") == "Apple iPhone"


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

    def test_build_search_query_falls_back_to_keywords_on_meta_output(self):
        llm = MagicMock()
        llm.chat.return_value = "comment chercher"
        with patch("src.ai.web_search._build_disambiguation_query", return_value=None):
            query = web_search._build_search_query("Parle moi de Ada Lovelace", llm)
        assert query == "Ada Lovelace"

    def test_build_search_query_returns_keywords_on_exception(self):
        llm = MagicMock()
        llm.chat.side_effect = RuntimeError("boom")
        with patch("src.ai.web_search._build_disambiguation_query", return_value=None):
            query = web_search._build_search_query(
                "j'aimerais savoir quelles sont les nouveautés pour l'iphone de Apple en 2026",
                llm,
            )
        assert query == "iphone Apple nouveautés 2026"

    def test_build_search_query_rejects_placeholder_llm_output(self):
        llm = MagicMock()
        llm.chat.return_value = "unused"

        with patch("src.ai.web_search._build_disambiguation_query", return_value=None):
            query = web_search._build_search_query("Qui est Ada Lovelace ?", llm)

        assert query == "Ada Lovelace"

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
        fake_module = types.ModuleType("ddgs")
        seen_queries = []

        class _FakeDDGS:
            def __init__(self, *args, **kwargs):
                pass

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

        with patch.dict(sys.modules, {"ddgs": fake_module}):
            results = web_search._ddg_search("Dune", max_results=5)

        assert results[0]["href"] == "https://wikipedia.org"
        assert seen_queries == ["Dune", "Dune -知乎", "Dune wikipedia"]

    def test_ddg_search_prefers_more_relevant_later_candidate_results(self):
        fake_module = types.ModuleType("ddgs")

        class _FakeDDGS:
            def __init__(self, *args, **kwargs):
                pass

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

        with patch.dict(sys.modules, {"ddgs": fake_module}):
            results = web_search._ddg_search("lune", max_results=5)

        assert results == [
            {"title": "Lune — Wikipédia", "href": "https://fr.wikipedia.org/wiki/Lune", "body": "La Lune est le satellite naturel de la Terre."},
        ]

    def test_ddg_search_prefers_exact_phrase_candidate_for_person_name(self):
        fake_module = types.ModuleType("ddgs")
        seen_queries = []

        class _FakeDDGS:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def text(self, query, region=None, safesearch=None, max_results=None):
                seen_queries.append(query)
                if query == "Ada Lovelace":
                    return [
                        {"title": "ADA - Australian Dental Association", "href": "https://ada.org.au/", "body": "Dental resources"},
                    ]
                if query == '"Ada Lovelace"':
                    return [
                        {"title": "Ada Lovelace - Wikipedia", "href": "https://en.wikipedia.org/wiki/Ada_Lovelace", "body": "English mathematician and writer"},
                    ]
                return []

        fake_module.DDGS = _FakeDDGS

        with patch.dict(sys.modules, {"ddgs": fake_module}):
            results = web_search._ddg_search("Ada Lovelace", max_results=5)

        assert results == [
            {"title": "Ada Lovelace - Wikipedia", "href": "https://en.wikipedia.org/wiki/Ada_Lovelace", "body": "English mathematician and writer"},
        ]
        assert seen_queries[:2] == ["Ada Lovelace", '"Ada Lovelace"']

    def test_ddg_search_filters_non_latin_and_returns_results(self):
        fake_module = types.ModuleType("ddgs")

        class _FakeDDGS:
            def __init__(self, *args, **kwargs):
                pass

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

        with patch.dict(sys.modules, {"ddgs": fake_module}):
            results = web_search._ddg_search("Ada Lovelace", max_results=5)

        assert len(results) == 1
        assert results[0]["href"] == "https://a"

    def test_ddg_search_returns_empty_on_exception(self):
        fake_module = types.ModuleType("ddgs")

        class _FakeDDGS:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                raise RuntimeError("network")

            def __exit__(self, exc_type, exc, tb):
                return False

        fake_module.DDGS = _FakeDDGS

        with patch.dict(sys.modules, {"ddgs": fake_module}):
            results = web_search._ddg_search("Ada Lovelace", max_results=5)

        assert results == []

    def test_ddg_instant_answer_search_returns_entity_card_results(self):
        payload = {
            "Heading": "Ada Lovelace",
            "AbstractText": "English mathematician and writer.",
            "AbstractURL": "https://en.wikipedia.org/wiki/Ada_Lovelace",
            "AbstractSource": "Wikipedia",
            "RelatedTopics": [],
        }

        response = MagicMock()
        response.read.return_value = __import__("json").dumps(payload).encode("utf-8")
        response.__enter__.return_value = response
        response.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=response):
            results = web_search._ddg_instant_answer_search("Ada Lovelace", max_results=3)

        assert results == [
            {
                "title": "Ada Lovelace - Wikipedia",
                "href": "https://en.wikipedia.org/wiki/Ada_Lovelace",
                "body": "English mathematician and writer.",
            }
        ]

    def test_ddg_instant_answer_search_skips_non_entity_query(self):
        with patch("urllib.request.urlopen") as urlopen:
            results = web_search._ddg_instant_answer_search("iphone Apple nouveautés 2026", max_results=3)

        assert results == []
        urlopen.assert_not_called()

    def test_score_search_results_penalizes_partial_name_match(self):
        irrelevant = [
            {"title": "ADA - Australian Dental Association", "href": "https://ada.org.au/", "body": "Dental resources"},
        ]
        relevant = [
            {"title": "Ada Lovelace - Wikipedia", "href": "https://en.wikipedia.org/wiki/Ada_Lovelace", "body": "English mathematician and writer"},
        ]

        assert web_search._score_search_results("Ada Lovelace", "Ada Lovelace", relevant) > web_search._score_search_results(
            "Ada Lovelace", "Ada Lovelace wikipedia", irrelevant
        )


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

    def test_build_query_overview_sync_returns_summary_and_sources(self):
        llm = MagicMock()
        with (
            patch("src.ai.web_search._build_search_query", return_value="Ada Lovelace biography overview"),
            patch(
                "src.ai.web_search._ddg_instant_answer_search",
                return_value=[{"title": "Ada Lovelace - Wikipedia", "href": "https://en.wikipedia.org/wiki/Ada_Lovelace", "body": "English mathematician."}],
            ),
            patch(
                "src.ai.web_search._ddg_search",
                return_value=[{"title": "Britannica", "href": "https://www.britannica.com/biography/Ada-Lovelace", "body": "British mathematician."}],
            ),
            patch("src.ai.web_search._synthesize_ai_overview", return_value="Vue d'ensemble utile"),
        ):
            overview = web_search.build_query_overview_sync("Qui est Ada Lovelace ?", llm)

        assert overview["search_query"] == "Ada Lovelace biography overview"
        assert overview["summary"] == "Vue d'ensemble utile"
        assert len(overview["sources"]) == 2

    def test_build_query_overview_from_results_sync_prefers_full_text_when_available(self):
        llm = MagicMock()
        with patch("src.ai.web_search._synthesize_ai_overview", return_value="Vue detaillee") as synthesize_mock:
            overview = web_search.build_query_overview_from_results_sync(
                "Qui est Ada Lovelace ?",
                "Ada Lovelace explication analyse histoire contexte",
                [
                    {
                        "title": "Wikipedia",
                        "href": "https://example.com/ada",
                        "body": "Court resume",
                        "full_text": "Texte complet Ada Lovelace avec davantage de contexte.",
                    }
                ],
                llm,
            )

        assert overview["summary"] == "Vue detaillee"
        synthesize_args = synthesize_mock.call_args[0]
        assert synthesize_args[0] == "Qui est Ada Lovelace ?"
        assert synthesize_args[1] == "Ada Lovelace explication analyse histoire contexte"
        assert synthesize_args[2][0]["full_text"] == "Texte complet Ada Lovelace avec davantage de contexte."

    def test_save_chat_enrichment_insight_creates_markdown_file(self, tmp_settings):
        with patch("src.ai.web_search.settings", tmp_settings):
            path = web_search.save_chat_enrichment_insight(
                "Qui est Ada Lovelace ?",
                "Ada Lovelace est une pionnière.",
                query_overview={
                    "search_query": "Ada Lovelace biography overview",
                    "summary": "Vue d'ensemble utile",
                    "sources": [{"title": "Wikipedia", "href": "https://wikipedia.org"}],
                },
                entity_contexts=[
                    {
                        "value": "Ada Lovelace",
                        "type_label": "Personne",
                        "mentions": 12,
                        "tag": "personne/ada-lovelace",
                        "image_url": "https://img/ada.png",
                        "notes": [{"title": "Ada", "file_path": "People/Ada.md"}],
                        "ddg_knowledge": {"abstract_text": "Mathématicienne anglaise."},
                    }
                ],
            )

        assert path is not None and path.exists()
        content = path.read_text(encoding="utf-8")
        assert "chat_enrichment" in content
        assert "# Vue d'ensemble DDG" in content
        assert "# Entités détectées" in content
        assert "personne/ada-lovelace" in content

    def test_save_chat_enrichment_insight_updates_existing_sections_and_frontmatter(self, tmp_settings):
        target = tmp_settings.insights_dir / "chat_existing.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "---\n"
            "tags:\n"
            "  - insight\n"
            "---\n\n"
            "# Question\n\nAda\n\n"
            "# Vue d'ensemble DDG\n\nAncienne vue\n\n"
            "# Entités détectées\n\nAncienne entité\n",
            encoding="utf-8",
        )

        with patch("src.ai.web_search.settings", tmp_settings):
            path = web_search.save_chat_enrichment_insight(
                "Qui est Ada Lovelace ?",
                "Réponse",
                path=target,
                query_overview={
                    "search_query": "Ada Lovelace biography overview",
                    "summary": "Nouvelle vue.",
                    "sources": [{"title": "Wikipedia", "href": "https://wikipedia.org"}],
                },
                entity_contexts=[
                    {
                        "value": "Ada Lovelace",
                        "type_label": "Personne",
                        "tag": "personne/ada-lovelace",
                        "notes": [{"title": "Ada", "file_path": "People/Ada.md"}],
                        "ddg_knowledge": {"abstract_text": "Mathématicienne anglaise."},
                    }
                ],
            )

        content = path.read_text(encoding="utf-8")
        assert "Nouvelle vue." in content
        assert "Ancienne vue" not in content
        assert "Ancienne entité" not in content
        assert "chat_enrichment" in content

    def test_formatting_and_frontmatter_helpers_cover_empty_and_insert_paths(self):
        assert web_search._format_query_overview_markdown({}) == ""
        assert web_search._format_entity_contexts_markdown([]) == ""

        inserted = web_search._upsert_markdown_section("# Question\n\nAda\n", "# Vue d'ensemble DDG", "# Vue d'ensemble DDG\n\nTexte")
        assert "Texte" in inserted

        replaced = web_search._upsert_markdown_section(
            "# Vue d'ensemble DDG\n\nAncien\n\n# Entités détectées\n\nBloc\n",
            "# Vue d'ensemble DDG",
            "# Vue d'ensemble DDG\n\nNouveau",
        )
        assert "Nouveau" in replaced
        assert "Ancien" not in replaced

        merged = web_search._merge_frontmatter_tags("---\ntags:\n  - insight\n---\n\nBody\n", ["insight", "obsirag"])
        assert "  - obsirag" in merged

        created = web_search._merge_frontmatter_tags("Body\n", ["insight"])
        assert created.startswith("---\n")

    def test_synthesize_ai_overview_success_and_error_paths(self):
        llm = MagicMock()
        llm.chat.return_value = "Vue d'ensemble"

        summary = web_search._synthesize_ai_overview(
            "Qui est Ada Lovelace ?",
            "Ada Lovelace biography overview",
            [{"title": "Wikipedia", "href": "https://wikipedia.org", "body": "Ada"}],
            llm,
        )
        assert summary == "Vue d'ensemble"

        llm.chat.side_effect = RuntimeError("boom")
        assert web_search._synthesize_ai_overview(
            "Qui est Ada Lovelace ?",
            "Ada Lovelace biography overview",
            [{"title": "Wikipedia", "href": "https://wikipedia.org", "body": "Ada"}],
            llm,
        ) is None
        assert web_search._synthesize_ai_overview("q", "s", [], MagicMock()) is None

    def test_save_chat_enrichment_insight_returns_existing_path_when_no_payload(self, tmp_settings):
        target = tmp_settings.insights_dir / "noop.md"
        with patch("src.ai.web_search.settings", tmp_settings):
            assert web_search.save_chat_enrichment_insight(
                "Qui est Ada Lovelace ?",
                "Réponse",
                path=target,
                entity_contexts=[],
                query_overview={},
            ) == target

    def test_format_entity_contexts_markdown_renders_related_topics_and_plain_note_titles(self):
        markdown = web_search._format_entity_contexts_markdown([
            {
                "value": "Ada Lovelace",
                "type": "PERSON",
                "notes": [{"title": "Ada note"}],
                "ddg_knowledge": {
                    "answer": "Mathématicienne.",
                    "definition": "Pionnière du calcul.",
                    "infobox": [{"label": "Born", "value": "1815"}, {"label": "", "value": "skip"}],
                    "related_topics": [{"text": "Charles Babbage", "url": "https://duckduckgo.com/Charles_Babbage"}],
                },
            }
        ])

        assert "Ada note" in markdown
        assert "Born : 1815" in markdown
        assert "[Charles Babbage](https://duckduckgo.com/Charles_Babbage)" in markdown

    def test_merge_frontmatter_tags_keeps_original_content_when_no_tags_block_exists(self):
        merged = web_search._merge_frontmatter_tags("---\ntitle: Ada\n---\n\nBody\n", ["obsirag"])
        assert merged.startswith("---\n")
        assert "title: Ada" in merged
        assert "obsirag" in merged

    def test_format_entity_contexts_markdown_excludes_obsirag_generated_notes(self):
        markdown = web_search._format_entity_contexts_markdown([
            {
                "value": "Ada Lovelace",
                "type": "PERSON",
                "notes": [
                    {"title": "Generated", "file_path": "obsirag/insights/generated.md"},
                    {"title": "Ada note", "file_path": "People/Ada.md"},
                ],
            }
        ])

        assert "People/Ada" in markdown
        assert "obsirag/insights/generated" not in markdown

    def test_build_query_overview_sync_returns_empty_when_search_or_summary_fails(self):
        llm = MagicMock()

        with (
            patch("src.ai.web_search._build_search_query", return_value="Ada Lovelace"),
            patch("src.ai.web_search._ddg_instant_answer_search", return_value=[]),
            patch("src.ai.web_search._ddg_search", return_value=[]),
        ):
            assert web_search.build_query_overview_sync("Qui est Ada Lovelace ?", llm) == {}

        with (
            patch("src.ai.web_search._build_search_query", return_value="Ada Lovelace"),
            patch("src.ai.web_search._ddg_instant_answer_search", return_value=[]),
            patch("src.ai.web_search._ddg_search", return_value=[{"title": "Wiki", "href": "https://wikipedia.org", "body": "Ada"}]),
            patch("src.ai.web_search._synthesize_ai_overview", return_value=None),
        ):
            assert web_search.build_query_overview_sync("Qui est Ada Lovelace ?", llm) == {}

    def test_has_authoritative_exact_match_requires_single_focus_term(self):
        assert web_search._has_authoritative_exact_match(
            "lune",
            [{"title": "Lune - Wikipédia", "href": "https://fr.wikipedia.org/wiki/Lune"}],
        ) is True
        assert web_search._has_authoritative_exact_match(
            "Ada Lovelace",
            [{"title": "Ada Lovelace - Wikipedia", "href": "https://en.wikipedia.org/wiki/Ada_Lovelace"}],
        ) is False

    def test_enrich_async_swallows_callback_errors(self):
        class _ImmediateThread:
            def __init__(self, target=None, daemon=None, name=None):
                self.target = target

            def start(self):
                self.target()

        callback = MagicMock(side_effect=RuntimeError("boom"))
        with (
            patch("src.ai.web_search.enrich_sync", return_value=("answer", None, [], True)),
            patch("src.ai.web_search.threading.Thread", side_effect=lambda **kwargs: _ImmediateThread(**kwargs)),
        ):
            web_search.enrich_async("query", MagicMock(), on_done=callback)

        callback.assert_called_once_with("answer", None, [], True)

    def test_enrich_sync_happy_path_returns_answer_and_path(self, tmp_settings):
        llm = MagicMock()
        with (
            patch("src.ai.web_search.settings", tmp_settings),
            patch("src.ai.web_search._build_search_query", return_value="ada lovelace"),
            patch("src.ai.web_search._ddg_search", return_value=[{"title": "Wiki", "href": "https://wikipedia.org", "body": "Ada Lovelace body"}]),
            patch("src.ai.web_search._ddg_instant_answer_search", return_value=[]),
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
            patch("src.ai.web_search._ddg_instant_answer_search", return_value=[]),
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
            patch("src.ai.web_search._ddg_instant_answer_search", return_value=[]),
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
            patch("src.ai.web_search._ddg_instant_answer_search", return_value=[]),
            patch("src.ai.web_search._synthesize", return_value="Réponse web utile"),
            patch("src.ai.web_search._check_quality", return_value=False),
        ):
            answer, path, results, quality = web_search.enrich_sync("Qui est Ada Lovelace ?", llm)

        assert answer is None
        assert path is None
        assert len(results) == 1
        assert quality is False

    def test_enrich_sync_merges_instant_answer_and_ddg_results(self, tmp_settings):
        llm = MagicMock()
        with (
            patch("src.ai.web_search.settings", tmp_settings),
            patch("src.ai.web_search._build_search_query", return_value="Ada Lovelace"),
            patch(
                "src.ai.web_search._ddg_instant_answer_search",
                return_value=[{"title": "Ada Lovelace - Wikipedia", "href": "https://en.wikipedia.org/wiki/Ada_Lovelace", "body": "English mathematician."}],
            ),
            patch(
                "src.ai.web_search._ddg_search",
                return_value=[{"title": "Britannica", "href": "https://www.britannica.com/biography/Ada-Lovelace", "body": "British mathematician."}],
            ),
            patch("src.ai.web_search._synthesize", return_value="Réponse web utile"),
            patch("src.ai.web_search._check_quality", return_value=True),
        ):
            answer, path, results, quality = web_search.enrich_sync("Qui est Ada Lovelace ?", llm)

        assert answer == "Réponse web utile"
        assert path is not None and path.exists()
        assert [item["href"] for item in results] == [
            "https://en.wikipedia.org/wiki/Ada_Lovelace",
            "https://www.britannica.com/biography/Ada-Lovelace",
        ]
        assert quality is True

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
