from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.learning.question_answering import AutoLearnQuestionAnswering


@pytest.mark.unit
class TestAutoLearnQuestionAnswering:
    def test_generate_valid_qa_pair_accepts_first_strong_answer(self):
        owner = MagicMock()
        owner._generate_questions.return_value = ["Quelle progression recente ?"]
        owner._web_search.return_value = [{"title": "Ref", "href": "https://example.com", "body": "Contexte web utile"}]
        owner._snippets_relevant.return_value = True
        owner._fit_context.return_value = ("ctx rag", "ctx web")
        owner._rag.query.return_value = ("Réponse RAG", [{"text": "Source", "metadata": {"file_path": "note.md"}}])
        owner._rag._llm.chat.return_value = "Réponse enrichie suffisamment longue pour être conservée comme réponse solide dans ce test."
        owner._is_weak_answer.return_value = False
        qa = AutoLearnQuestionAnswering(owner)

        result = qa.generate_valid_qa_pair(
            "Note test",
            "Contenu",
            sleep_between_questions=0,
            max_retries=3,
        )

        assert result == {
            "question": "Quelle progression recente ?",
            "answer": "Réponse enrichie suffisamment longue pour être conservée comme réponse solide dans ce test.",
            "sources": ["note.md"],
            "web_refs": [{"title": "Ref", "url": "https://example.com"}],
            "provenance": "Web + Coffre",
        }

    def test_generate_valid_qa_pair_retries_after_weak_answer(self):
        owner = MagicMock()
        owner._generate_questions.side_effect = [["Question 1 ?"], ["Question 2 ?"]]
        owner._web_search.return_value = []
        owner._rag.query.side_effect = [
            ("réponse trop courte", []),
            ("Réponse suffisamment longue pour être retenue après une seconde tentative.", []),
        ]
        owner._is_weak_answer.side_effect = [True, False]
        qa = AutoLearnQuestionAnswering(owner)

        result = qa.generate_valid_qa_pair(
            "Note test",
            "Contenu",
            sleep_between_questions=0,
            max_retries=2,
        )

        assert result is not None
        assert result["question"] == "Question 2 ?"
        assert result["provenance"] == "Coffre"

    def test_generate_valid_qa_pair_aborts_on_processing_error(self):
        owner = MagicMock()
        owner._generate_questions.return_value = ["Question ?"]
        owner._web_search.side_effect = RuntimeError("boom")
        qa = AutoLearnQuestionAnswering(owner)

        with patch("src.learning.question_answering.logger.warning") as warning:
            result = qa.generate_valid_qa_pair(
                "Note test",
                "Contenu",
                sleep_between_questions=0,
                max_retries=2,
            )

        assert result is None
        warning.assert_called_once()