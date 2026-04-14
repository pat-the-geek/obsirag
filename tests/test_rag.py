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
        ctx = rag._build_context([], "Question ?", "general")
        assert "Aucune note" in ctx

    def test_context_contains_chunk_text(self, rag):
        chunks = [_make_chunk(text="Texte important du chunk.")]
        ctx = rag._build_context(chunks, "Question ?", "general")
        assert "Texte important" in ctx

    def test_char_budget_truncates(self, rag):
        chunks = [_make_chunk(text="x" * 2000)]
        ctx = rag._build_context(chunks, "Question ?", "general", char_budget=100)
        assert len(ctx) <= 500  # contexte tronqué + header

    def test_multiple_notes_deduplicated(self, rag):
        """Deux chunks de la même note → une seule entrée dans le contexte."""
        chunks = [
            _make_chunk(title="Note A", fp="a.md"),
            _make_chunk(title="Note A", fp="a.md"),  # même note
        ]
        ctx = rag._build_context(chunks, "Question ?", "general")
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

    def test_messages_include_resolved_query_and_study_prompt(self, rag):
        msgs = rag._build_messages(
            "Et la durée ?",
            "Contexte.",
            [],
            intent="relation",
            resolved_query="Et la durée ? concernant Artemis II",
        )

        user_content = [m for m in msgs if m["role"] == "user"][0]["content"]
        assert "Question résolue dans le fil" in user_content
        assert "### Ce que disent mes notes" in user_content

    def test_messages_include_single_subject_prompt(self, rag):
        msgs = rag._build_messages("Parle moi de Python", "Contexte.", [], intent="hybrid")
        user_content = [m for m in msgs if m["role"] == "user"][0]["content"]
        assert "### Aperçu de Python" in user_content
        assert "### Détails utiles" in user_content


# ---------------------------------------------------------------------------
# Conversation / normalisation / sources primaires
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRAGConversationBehavior:
    def test_normalize_query_converts_roman_numerals_except_single_letter(self):
        assert RAGPipeline._normalize_query("Artemis II") == "Artemis 2"
        assert RAGPipeline._normalize_query("Mission X") == "Mission X"

    def test_resolve_query_with_history_expands_follow_up(self):
        history = [
            {"role": "user", "content": "Parle moi de Artemis II"},
            {"role": "assistant", "content": "### Aperçu de Artemis II\nMission lunaire habitée."},
        ]

        resolved = RAGPipeline._resolve_query_with_history("et la durée de la mission ?", history)

        assert "concernant Artemis II" in resolved

    def test_resolve_query_with_history_keeps_query_when_no_subject(self):
        history = [{"role": "assistant", "content": "Merci."}]

        resolved = RAGPipeline._resolve_query_with_history("et la durée ?", history)

        assert resolved == "et la durée ?"

    def test_normalize_final_answer_removes_leading_sentinel_when_body_exists(self, rag):
        answer = (
            "Cette information n'est pas dans ton coffre.\n\n"
            "### Aperçu de Python\nPython est bien documenté dans tes notes."
        )

        normalized = rag._normalize_final_answer(answer, "Parle moi de Python", "hybrid")

        assert not normalized.lower().startswith("cette information n'est pas dans ton coffre")
        assert "Python est bien documenté" in normalized

    def test_normalize_final_answer_replaces_embedded_sentinel_in_study_answer(self, rag):
        answer = (
            "### Ce que disent mes notes sur le sujet\n"
            "Cette information n'est pas dans ton coffre.\n\n"
            "### Ce que je peux conclure\nLes notes permettent une synthèse partielle."
        )

        normalized = rag._normalize_final_answer(answer, "relation entre A et B", "relation")

        assert "Le lien direct n'est pas documenté dans ton coffre." in normalized
        assert "Les notes permettent une synthèse partielle." in normalized

    def test_mark_primary_sources_flags_dominant_note(self, rag):
        chunks = [
            _make_chunk(title="Python pour data science", text="Python et pandas.", fp="python.md"),
            _make_chunk(title="Note annexe", text="Sujet voisin.", fp="other.md"),
        ]

        marked = rag._mark_primary_sources(chunks, "Parle moi de Python", "hybrid")

        primary = [c for c in marked if c["metadata"].get("is_primary")]
        assert len(primary) == 1
        assert primary[0]["metadata"]["file_path"] == "python.md"

    def test_verify_response_handles_verified_corrected_and_unexpected_formats(self, rag, mock_llm):
        mock_llm.chat.return_value = "VERIFIED\nRéponse fidèle"
        verified, changed = rag.verify_response(
            "Réponse fidèle avec suffisamment de détails pour être vérifiée.",
            [_make_chunk()],
        )
        assert verified == "Réponse fidèle"
        assert changed is False

        mock_llm.chat.return_value = "CORRECTED\nRéponse corrigée"
        corrected, changed = rag.verify_response(
            "Réponse brute avec suffisamment de détails pour déclencher la vérification.",
            [_make_chunk()],
        )
        assert corrected == "Réponse corrigée"
        assert changed is True

        mock_llm.chat.return_value = "UNKNOWN\nRéponse"
        original = "Réponse brute avec suffisamment de détails pour déclencher la vérification."
        fallback, changed = rag.verify_response(original, [_make_chunk()])
        assert fallback == original
        assert changed is False

    def test_verify_response_returns_original_on_llm_failure(self, rag, mock_llm):
        mock_llm.chat.side_effect = RuntimeError("boom")
        text, changed = rag.verify_response("Réponse brute", [_make_chunk()])
        assert text == "Réponse brute"
        assert changed is False

    def test_run_chat_attempt_counts_sentinel_and_ignores_metric_failure(self, rag, mock_llm):
        mock_llm.chat.return_value = "Cette information n'est pas dans ton coffre."
        rag._metrics = MagicMock()
        rag._metrics.increment.side_effect = RuntimeError("metrics down")

        answer = rag._run_chat_attempt([], "ctx", [], "Question", "general")

        assert answer == "Cette information n'est pas dans ton coffre."

    def test_stream_first_token_or_empty_returns_empty_iterator(self, rag, mock_llm):
        mock_llm.stream.return_value = iter([])

        stream = rag._stream_first_token_or_empty([{"role": "user", "content": "Q"}], "general")

        assert list(stream) == []

    def test_linked_chunk_helpers_delegate_to_chroma_store(self, rag, mock_chroma):
        mock_chroma.get_chunks_by_note_title.return_value = [_make_chunk(title="Note B", fp="b.md")]
        mock_chroma.get_chunks_by_file_path.return_value = [_make_chunk(title="Note C", fp="c.md")]

        by_title = rag._get_linked_chunks_by_note_title("Note B")
        by_path = rag._get_linked_chunks_by_file_path("c.md")

        mock_chroma.get_chunks_by_note_title.assert_called_once_with("Note B", limit=2)
        mock_chroma.get_chunks_by_file_path.assert_called_once_with("c.md", limit=2)
        assert by_title[0]["metadata"]["note_title"] == "Note B"
        assert by_path[0]["metadata"]["file_path"] == "c.md"

    def test_retry_forced_study_synthesis_returns_original_when_context_is_short(self, rag, mock_llm):
        answer = rag._retry_forced_study_synthesis(
            answer="Cette information n'est pas dans ton coffre.",
            query="relation entre A et B",
            context="court",
            history=[],
            intent="relation",
        )
        assert answer == "Cette information n'est pas dans ton coffre."
        mock_llm.chat.assert_not_called()

    def test_retry_forced_study_synthesis_returns_retry_when_successful(self, rag, mock_llm):
        mock_llm.chat.return_value = "Synthèse forcée utile"

        # PERF-15b : le retry exige >= 2 notes distinctes dans le contexte
        context = (
            "## Note A\n" + "x" * 200 + "\n"
            "## Note B\n" + "y" * 200 + "\n"
        )
        answer = rag._retry_forced_study_synthesis(
            answer="Cette information n'est pas dans ton coffre.",
            query="relation entre A et B",
            context=context,
            history=[],
            intent="relation",
        )

        assert answer == "Synthèse forcée utile"
        mock_llm.chat.assert_called_once()

    def test_sanitize_structured_study_answer_removes_unsupported_inferences(self):
        text = (
            "### Ce que disent mes notes sur A\nFait A.\n\n"
            "### Ce que je peux conclure\n"
            "On peut inférer une relation forte. Ada a probablement joué un rôle."
        )

        sanitized = RAGPipeline._sanitize_structured_study_answer(text)

        assert "probablement" not in sanitized.lower()
        assert "documenté dans ton coffre" in sanitized

    def test_normalize_final_answer_wraps_single_subject_plain_remainder(self, rag):
        answer = (
            "Cette information n'est pas dans ton coffre.\n"
            "Python est un langage polyvalent. Il sert au scripting. Il est souvent utilisé pour la data."
        )

        normalized = rag._normalize_final_answer(answer, "Parle moi de Python", "hybrid")

        assert normalized.startswith("### Aperçu de Python")
        assert "### Détails utiles" in normalized

    def test_sanitize_structured_study_answer_adds_period_and_notice(self):
        text = (
            "### Ce que disent mes notes sur A\nFaits.\n\n"
            "### Ce que je peux conclure\nConclusion partielle"
        )

        sanitized = RAGPipeline._sanitize_structured_study_answer(text)

        assert "Conclusion partielle." in sanitized
        assert sanitized.rstrip().endswith("Le lien direct n'est pas documenté dans ton coffre.")

    def test_entity_target_rejects_blocked_fragments_and_long_values(self):
        assert RAGPipeline._is_entity_target("la contribution de Claude qui a permis un retour") is False
        assert RAGPipeline._is_entity_target("un deux trois quatre cinq six sept") is False

    def test_looks_like_follow_up_query_distinguishes_short_generic_vs_subject_query(self):
        assert RAGPipeline._looks_like_follow_up_query("et ensuite ?") is True
        assert RAGPipeline._looks_like_follow_up_query("Parle moi de Python") is False

    def test_extract_subject_from_message_falls_back_to_proper_noun(self):
        subject = RAGPipeline._extract_subject_from_message("Discussion sur Ada Lovelace et son travail")
        assert subject == "Ada Lovelace"

    def test_retry_forced_study_synthesis_keeps_original_on_retry_failure(self, rag, mock_llm):
        mock_llm.chat.side_effect = RuntimeError("boom")

        answer = rag._retry_forced_study_synthesis(
            answer="Cette information n'est pas dans ton coffre.",
            query="relation entre A et B",
            context="x" * 400,
            history=[],
            intent="relation",
        )

        assert answer == "Cette information n'est pas dans ton coffre."

    def test_normalize_final_answer_keeps_pure_sentinel_without_remainder(self, rag):
        answer = rag._normalize_final_answer(
            "Cette information n'est pas dans ton coffre.",
            "Parle moi de Python",
            "hybrid",
        )
        assert answer == "Cette information n'est pas dans ton coffre."

    def test_sanitize_single_subject_answer_returns_original_when_cleaning_empties_text(self, rag):
        original = "Cette information n'est pas dans ton coffre."
        cleaned = rag._sanitize_single_subject_answer(original, "Parle moi de Python", "hybrid")
        assert cleaned == original

    def test_is_generic_subject_reference_detects_all_generic_tokens(self):
        assert RAGPipeline._is_generic_subject_reference("les objectifs") is True
        assert RAGPipeline._is_generic_subject_reference("Ada Lovelace") is False

    def test_extract_single_subject_candidate_returns_none_for_multi_subject_reference(self):
        candidate = RAGPipeline._extract_single_subject_candidate("Parle moi de Ada et Alan")
        assert candidate is None

    def test_normalize_theme_label_preserves_special_cases(self):
        normalized = RAGPipeline._normalize_theme_label("garry tans claude artemis ii iii iv")
        assert normalized == "Garry Tan Claude Artemis II III IV"

    def test_extract_theme_labels_handles_special_multi_theme_queries(self):
        labels = RAGPipeline._extract_theme_labels("Quels liens entre Garry Tan et Claude dans la mission Artemis II ?")
        assert labels[0] == "Garry Tan et Claude Code"
        assert "Artemis II" in labels

    def test_derive_study_themes_falls_back_when_missing_labels(self):
        assert RAGPipeline._derive_study_themes("question générique") == ("le premier thème", "le second thème")

    def test_derive_primary_theme_falls_back_to_default(self):
        assert RAGPipeline._derive_primary_theme("question sans sujet explicite") == "le sujet demandé"

    def test_extract_subject_from_message_returns_none_without_signal(self):
        assert RAGPipeline._extract_subject_from_message("merci beaucoup pour la réponse") is None

    def test_should_use_single_subject_prompt_excludes_study_prompt(self):
        assert RAGPipeline._should_use_single_subject_prompt("relation", "lien entre A et B") is False


# ---------------------------------------------------------------------------
# Retrieval avancé
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRAGAdvancedRetrieval:
    def test_retrieve_temporal_falls_back_to_semantic_when_window_is_empty(self, rag, mock_chroma):
        mock_chroma.search_by_date_range.return_value = []
        fallback_chunk = _make_chunk(title="Fallback")
        mock_chroma.search.return_value = [fallback_chunk]

        chunks, intent = rag._retrieve("notes de cette semaine sur Python")

        assert intent == "temporal"
        assert chunks == [fallback_chunk]

    def test_retrieve_entity_uses_search_by_entity_for_real_entity_targets(self, rag, mock_chroma):
        entity_chunk = _make_chunk(title="Ada")
        entity_chunk["metadata"]["ner_persons"] = "Ada Lovelace"
        mock_chroma.search_by_entity.return_value = [entity_chunk]

        chunks, intent = rag._retrieve("notes qui parlent de Ada Lovelace ?")

        assert intent == "entity"
        assert chunks == [entity_chunk]
        mock_chroma.search_by_entity.assert_called_once()

    def test_retrieve_synthesis_with_proper_noun_uses_hybrid_retrieval(self, rag):
        with patch.object(rag, "_retrieve_hybrid_chunks", return_value=[_make_chunk(title="Python")]) as hybrid:
            chunks, intent = rag._retrieve("fais une synthèse de Python")

        assert intent == "synthesis"
        assert chunks[0]["metadata"]["note_title"] == "Python"
        hybrid.assert_called_once()

    def test_retrieve_relation_merges_searches_without_duplicates(self, rag, mock_chroma):
        a = _make_chunk(title="Alpha", fp="a.md")
        b = _make_chunk(title="Beta", fp="b.md")
        bridge = _make_chunk(title="Pont", fp="bridge.md")
        bridge["chunk_id"] = "bridge_1"
        a["chunk_id"] = "a_1"
        b["chunk_id"] = "b_1"
        mock_chroma.search.side_effect = [
            [a],
            [b],
            [bridge, a],
        ]

        chunks, intent = rag._retrieve("relation entre Alpha et Beta ?")

        assert intent == "relation"
        assert [c["chunk_id"] for c in chunks] == ["bridge_1", "a_1", "b_1"]

    def test_retrieve_general_uses_keyword_fallback_when_semantic_scores_are_low(self, rag, mock_chroma):
        low_chunk = _make_chunk(title="Note vague", text="contenu peu utile", fp="vague.md")
        low_chunk["score"] = 0.2
        keyword_chunk = _make_chunk(title="Mesure thermique", text="Température et mesure précise.", fp="measure.md")
        keyword_chunk["chunk_id"] = "kw_1"
        keyword_chunk["score"] = 0.95

        mock_chroma.search.return_value = [low_chunk]
        mock_chroma.search_by_keyword.return_value = [keyword_chunk]

        chunks, intent = rag._retrieve("Quelles mesures thermiques ?")

        assert intent == "general_kw_fallback"
        assert chunks[0]["chunk_id"] == "kw_1"
        assert mock_chroma.search_by_keyword.called

    def test_filter_supported_chunks_can_empty_context_when_no_lexical_support(self, rag):
        chunks = [_make_chunk(title="Mythologie grecque", text="Zeus et Héra.", fp="mytho.md")]

        filtered = rag._filter_supported_chunks("Parle moi de Artemis II", chunks, "entity")

        assert filtered == []

    def test_retrieve_hybrid_chunks_prefers_bridges_and_unique_notes(self, rag, mock_chroma):
        bridge = _make_chunk(title="Bridge", text="Garry Tan et Claude Code ensemble.", fp="bridge.md")
        bridge["chunk_id"] = "bridge"
        garry = _make_chunk(title="Garry Tan", text="Garry Tan investit.", fp="garry.md")
        garry["chunk_id"] = "garry"
        claude = _make_chunk(title="Claude Code", text="Claude Code assiste le dev.", fp="claude.md")
        claude["chunk_id"] = "claude"

        mock_chroma.search.return_value = [bridge, garry, claude]
        mock_chroma.search_by_note_title.side_effect = lambda noun, top_k=3: {
            "Garry Tan": [bridge],
            "Claude Code": [claude],
        }.get(noun, [])
        mock_chroma.search_by_keyword.side_effect = lambda noun, top_k=3: {
            "Garry Tan": [garry],
            "Claude Code": [claude],
        }.get(noun, [])

        chunks = rag._retrieve_hybrid_chunks("relation entre Garry Tan et Claude Code", ["Garry Tan", "Claude Code"])

        assert chunks[0]["chunk_id"] == "bridge"
        assert {chunk["metadata"]["file_path"] for chunk in chunks[:3]} == {"bridge.md", "garry.md", "claude.md"}

    def test_prepare_context_chunks_prefers_dominant_note_context(self, rag):
        dominant = _make_chunk(title="Python", fp="python.md")
        support = _make_chunk(title="Autre", fp="other.md")
        dominant_fetch = [
            _make_chunk(title="Python", text="Chunk principal 1", fp="python.md"),
            _make_chunk(title="Python", text="Chunk principal 2", fp="python.md"),
        ]

        with (
            patch.object(rag, "_select_dominant_note_key", return_value="python.md"),
            patch.object(rag, "_fetch_note_context_chunks", return_value=dominant_fetch),
        ):
            prepared = rag._prepare_context_chunks([dominant, support], "Parle moi de Python", "hybrid")

        assert prepared[0]["text"] == "Chunk principal 1"
        assert prepared[1]["text"] == "Chunk principal 2"
        assert any(chunk["metadata"]["file_path"] == "other.md" for chunk in prepared)

    def test_select_dominant_note_key_returns_none_when_signal_is_too_weak(self, rag):
        weak = _make_chunk(title="Note vague", text="un mot", fp="weak.md")
        weak["score"] = 0.3

        dominant = rag._select_dominant_note_key("Parle moi de Python", [weak])

        assert dominant is None

    def test_fetch_note_context_chunks_returns_empty_on_search_error(self, rag, mock_chroma):
        mock_chroma.search.side_effect = RuntimeError("boom")

        chunks = rag._fetch_note_context_chunks("Python", "python.md", 3)

        assert chunks == []

    def test_prepare_context_chunks_returns_original_when_no_dominant_context_found(self, rag):
        chunks = [_make_chunk(title="Python", fp="python.md"), _make_chunk(title="Autre", fp="other.md")]

        with (
            patch.object(rag, "_select_dominant_note_key", return_value="python.md"),
            patch.object(rag, "_fetch_note_context_chunks", return_value=[]),
        ):
            prepared = rag._prepare_context_chunks(chunks, "Parle moi de Python", "hybrid")

        assert prepared == chunks

    def test_retrieve_hybrid_chunks_falls_back_to_semantic_when_no_symbolic_hits_and_low_scores(self, rag, mock_chroma):
        low = _make_chunk(title="Low", fp="low.md")
        low["score"] = 0.2
        fallback = _make_chunk(title="Fallback", fp="fallback.md")
        fallback["chunk_id"] = "fallback"

        mock_chroma.search.side_effect = [[low], [fallback]]
        mock_chroma.search_by_note_title.return_value = []
        mock_chroma.search_by_keyword.return_value = []

        chunks = rag._retrieve_hybrid_chunks("Sujet X", ["Sujet X"])

        assert chunks == [fallback]

    def test_mark_primary_sources_marks_none_when_no_dominant_note(self, rag):
        chunks = [_make_chunk(title="A", fp="a.md"), _make_chunk(title="B", fp="b.md")]

        with patch.object(rag, "_select_dominant_note_key", return_value=None):
            marked = rag._mark_primary_sources(chunks, "Question", "general")

        assert all(chunk["metadata"]["is_primary"] is False for chunk in marked)


# ---------------------------------------------------------------------------
# query_stream() — branches supplémentaires
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRAGQueryStreamAdvanced:
    def test_query_retries_on_context_too_large(self, rag, mock_llm):
        from src.ai.rag import BadRequestError

        chunks = [_make_chunk(title="Python")]
        mock_llm.chat.side_effect = [BadRequestError("context length exceeded"), "Réponse finale"]

        with patch.object(rag, "_retrieve", return_value=(chunks, "general")):
            answer, sources = rag.query("Parle moi de Python")

        assert "Réponse finale" in answer
        assert "### Aperçu de Python" in answer
        assert sources
        assert mock_llm.chat.call_count == 2

    def test_query_stream_retries_on_context_too_large_before_streaming(self, rag, mock_llm):
        from src.ai.rag import BadRequestError

        chunks = [_make_chunk(title="Python")]

        def _stream_side_effect(*args, **kwargs):
            if _stream_side_effect.calls == 0:
                _stream_side_effect.calls += 1
                raise BadRequestError("context size exceeded")
            return iter(["Réponse ", "streamée"])

        _stream_side_effect.calls = 0
        mock_llm.stream.side_effect = _stream_side_effect

        with patch.object(rag, "_retrieve", return_value=(chunks, "general")):
            stream, sources = rag.query_stream("Explique Python")

        assert "Réponse streamée" == "".join(stream)
        assert sources

    def test_stream_returns_sentinel_when_no_chunks_are_retained(self, rag):
        with patch.object(rag, "_retrieve", return_value=([], "general")):
            stream, sources = rag.query_stream("Sujet absent")

        assert list(stream) == ["Cette information n'est pas dans ton coffre."]
        assert sources == []

    def test_query_stream_emits_progress_events(self, rag):
        chunks = [_make_chunk(title="Python")]
        events: list[dict] = []

        with patch.object(rag, "_retrieve", return_value=(chunks, "general")):
            stream, _ = rag.query_stream("Explique Python", progress_callback=events.append)

        assert "".join(stream)
        assert any(event.get("phase") == "resolve" for event in events)
        assert any(event.get("phase") == "retrieval" and event.get("chunk_count") == 1 for event in events)
        assert any(event.get("phase") == "generation" for event in events)

    def test_stream_returns_normalized_answer_for_synthesis_intent(self, rag, mock_llm):
        chunks = [_make_chunk(title="Python pour data science", text="Python et pandas.", fp="python.md")]
        mock_llm.chat.return_value = (
            "Cette information n'est pas dans ton coffre.\n\n"
            "### Aperçu de Python\nPython est décrit dans tes notes."
        )

        with patch.object(rag, "_retrieve", return_value=(chunks, "synthesis")):
            stream, sources = rag.query_stream("Fais une synthèse sur Python")

        answer = "".join(stream)
        assert "Python est décrit dans tes notes." in answer
        assert not answer.lower().startswith("cette information n'est pas dans ton coffre")
        assert sources

    def test_build_context_enriches_linked_notes_via_store_api(self, rag, mock_chroma):
        base_chunk = _make_chunk(title="Note A", text="Contenu A.", fp="a.md")
        base_chunk["metadata"]["wikilinks"] = "Note B"
        mock_chroma.get_chunks_by_note_title.return_value = [
            _make_chunk(title="Note B", text="Contenu B.", fp="b.md")
        ]

        context = rag._build_context([base_chunk], "Question ?", "general")

        mock_chroma.get_chunks_by_note_title.assert_called_once_with("Note B", limit=2)
        assert "Note A" in context
        assert "Note B" in context

    def test_query_raises_runtime_error_when_all_context_retries_fail(self, rag):
        from src.ai.rag import BadRequestError

        chunks = [_make_chunk(title="Python")]
        rag._metrics = MagicMock()

        with (
            patch.object(rag, "_prepare_query_execution", return_value=("Question", chunks, "general")),
            patch.object(rag, "_iter_query_attempts", return_value=iter([(100, "ctx", [])])),
            patch.object(rag, "_run_chat_attempt", side_effect=BadRequestError("context length exceeded")),
        ):
            with pytest.raises(RuntimeError):
                rag.query("Parle moi de Python")

        rag._metrics.increment.assert_any_call("rag_context_retries_total")

    def test_query_stream_reraises_non_context_bad_request(self, rag):
        from src.ai.rag import BadRequestError

        chunks = [_make_chunk(title="Python")]
        with (
            patch.object(rag, "_prepare_query_execution", return_value=("Question", chunks, "general")),
            patch.object(rag, "_iter_query_attempts", return_value=iter([(100, "ctx", [])])),
            patch.object(rag, "_stream_first_token_or_empty", side_effect=BadRequestError("other bad request")),
            patch.object(rag, "_is_context_error", return_value=False),
        ):
            with pytest.raises(BadRequestError):
                rag.query_stream("Parle moi de Python")


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
        rag._build_context(chunks, "Question ?", "general")
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
# PERF-14 — Backpressure gate (_InferenceBackpressure)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestInferenceBackpressure:
    """Tests de la gate de backpressure sans LLM réel."""

    def _make_gate(self, max_queue=2, timeout_s=0.1):
        from src.ai.rag import _InferenceBackpressure
        return _InferenceBackpressure(max_queue=max_queue, timeout_s=timeout_s)

    def test_acquire_release_cycle(self):
        gate = self._make_gate()
        assert gate.queue_depth == 0
        gate.acquire()
        assert gate.queue_depth == 1
        gate.release()
        assert gate.queue_depth == 0

    def test_rejects_when_queue_full(self):
        """La gate doit rejeter dès que active >= 1 + max_queue."""
        gate = self._make_gate(max_queue=0)
        gate.acquire()  # slot unique occupé
        # le second thread ne peut pas entrer — rejection immédiate car max_active=1
        # (max_queue=0 → max_active=1, déjà atteint)
        with pytest.raises(RuntimeError, match="satur"):
            gate.acquire()
        gate.release()

    def test_timeout_raises_runtime_error(self):
        """Quand le semaphore est occupé et le timeout expire, RuntimeError est levée."""
        gate = self._make_gate(max_queue=1, timeout_s=0.05)
        gate.acquire()  # slot occupé par ce thread lui-même
        # Avec max_queue=1, on peut en avoir 2 en _active ; on tente un 2e acquire.
        # Le semaphore ne sera jamais libéré → timeout s'écoule.
        import threading
        error_caught = []
        def _try_acquire():
            try:
                gate.acquire()
            except RuntimeError as e:
                error_caught.append(str(e))

        t = threading.Thread(target=_try_acquire)
        t.start()
        t.join(timeout=1.0)
        assert not t.is_alive(), "Le thread ne s'est pas terminé dans les temps"
        assert error_caught, "Aucune RuntimeError capturée"
        assert "D\u00e9lai" in error_caught[0]
        gate.release()

    def test_query_acquires_and_releases_gate(self, rag, mock_llm):
        """Après query(), la gate doit être revenue à 0."""
        assert rag._backpressure.queue_depth == 0
        rag.query("Qu'est-ce que Python ?")
        assert rag._backpressure.queue_depth == 0

    def test_query_stream_acquires_and_releases_gate(self, rag, mock_llm):
        """Après consommation complète du stream, la gate doit être revenue à 0."""
        stream, _ = rag.query_stream("Qu'est-ce que Python ?")
        list(stream)  # consomme entièrement
        assert rag._backpressure.queue_depth == 0

    def test_query_stream_synthesis_acquires_and_releases_gate(self, rag, mock_llm):
        """Pour les intents synthesis, la gate est libérée dès le retour de query_stream."""
        from unittest.mock import patch
        chunks = [_make_chunk(title="Python")]
        mock_llm.chat.return_value = "Synthèse Python."
        with patch.object(rag, "_retrieve", return_value=(chunks, "synthesis")):
            stream, _ = rag.query_stream("Fais une synthèse sur Python")
        list(stream)
        assert rag._backpressure.queue_depth == 0

    def test_no_chunks_bypasses_gate(self, rag):
        """Le chemin 'aucun résultat' ne doit pas acquérir la gate."""
        from unittest.mock import patch
        with patch.object(rag, "_retrieve", return_value=([], "general")):
            stream, _ = rag.query_stream("Sujet absent")
        list(stream)
        assert rag._backpressure.queue_depth == 0


# ---------------------------------------------------------------------------
# PERF-15a — Cache réponse (_AnswerCache)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAnswerCache:
    def _make_cache(self, ttl_s=60.0):
        from src.ai.rag import _AnswerCache
        return _AnswerCache(ttl_s=ttl_s, max_size=16)

    def test_miss_returns_none(self):
        cache = self._make_cache()
        assert cache.get("Qu'est-ce que Python ?", []) is None

    def test_put_then_get(self):
        cache = self._make_cache()
        cache.put("Question", [], "Réponse", [{"source": "a"}])
        result = cache.get("Question", [])
        assert result is not None
        answer, sources = result
        assert answer == "Réponse"
        assert sources == [{"source": "a"}]

    def test_normalization_ignores_case_and_whitespace(self):
        cache = self._make_cache()
        cache.put("Python", [], "Réponse", [])
        assert cache.get("python", []) is not None
        assert cache.get("  Python  ", []) is not None

    def test_ttl_expiry(self):
        import time as _time
        cache = self._make_cache(ttl_s=0.05)
        cache.put("Q", [], "R", [])
        _time.sleep(0.1)
        assert cache.get("Q", []) is None

    def test_different_history_is_different_key(self):
        cache = self._make_cache()
        h1 = [{"role": "user", "content": "contexte A"}]
        h2 = [{"role": "user", "content": "contexte B"}]
        cache.put("Q", h1, "Réponse A", [])
        assert cache.get("Q", h2) is None

    def test_invalidate_removes_entry(self):
        cache = self._make_cache()
        cache.put("Q", [], "R", [])
        cache.invalidate("Q", [])
        assert cache.get("Q", []) is None

    def test_max_size_evicts_oldest(self):
        cache = self._make_cache()
        for i in range(20):
            cache.put(f"Q{i}", [], f"R{i}", [])
        assert cache.size <= 16

    def test_query_uses_cache_on_second_call(self, rag, mock_llm):
        rag.query("Qu'est-ce que Python ?")
        mock_llm.chat.reset_mock()
        rag.query("Qu'est-ce que Python ?")
        mock_llm.chat.assert_not_called()

    def test_query_stream_uses_cache_on_second_call(self, rag, mock_llm):
        stream1, _ = rag.query_stream("Qu'est-ce que Python ?")
        list(stream1)  # consomme pour déclencher le stockage
        mock_llm.stream.reset_mock()
        stream2, _ = rag.query_stream("Qu'est-ce que Python ?")
        list(stream2)
        mock_llm.stream.assert_not_called()


# ---------------------------------------------------------------------------
# PERF-15b — Retry synthesis conditionnel
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRetrySynthesisConditional:
    def test_skip_retry_when_single_source_in_context(self, rag, mock_llm):
        """Avec une seule note dans le contexte, pas de 2e appel LLM."""
        context = "## Note unique\nQuelques lignes sur Python.\n" * 5  # > 300 chars
        answer_sentinel = "Cette information n'est pas dans ton coffre."
        result = rag._retry_forced_study_synthesis(
            answer=answer_sentinel,
            query="Synthèse sur Python",
            context=context,
            history=[],
            intent="synthesis",
        )
        mock_llm.chat.assert_not_called()
        assert result == answer_sentinel

    def test_retry_triggered_with_multiple_sources(self, rag, mock_llm):
        """Avec 2+ notes distinctes, le retry est tenté."""
        context = (
            "## Note A\n" + "Python est un langage. " * 20 + "\n"
            "## Note B\n" + "Data science et Python. " * 20 + "\n"
        )
        answer_sentinel = "Cette information n'est pas dans ton coffre."
        mock_llm.chat.return_value = "Voici une synthèse utile."
        result = rag._retry_forced_study_synthesis(
            answer=answer_sentinel,
            query="Synthèse sur Python",
            context=context,
            history=[],
            intent="synthesis",
        )
        mock_llm.chat.assert_called_once()
        assert result == "Voici une synthèse utile."

    def test_no_retry_for_non_synthesis_intent(self, rag, mock_llm):
        context = "## Note A\n" + "x" * 400 + "\n## Note B\n" + "y" * 400
        result = rag._retry_forced_study_synthesis(
            answer="Cette information n'est pas dans ton coffre.",
            query="Qu'est-ce que Python ?",
            context=context,
            history=[],
            intent="general",
        )
        mock_llm.chat.assert_not_called()
        assert "coffre" in result


# ---------------------------------------------------------------------------
# Import conditionnel de _detect_temporal (fonction statique → accessible hors classe)
# ---------------------------------------------------------------------------

def _detect_temporal_query(query: str):
    return RAGPipeline._detect_temporal(query)
