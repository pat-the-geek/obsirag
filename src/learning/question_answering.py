from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from src.learning.autolearn import AutoLearner


class AutoLearnQuestionAnswering:
    _HARD_CLAIM_RE = re.compile(r"\b(?:\d{1,4}(?:[.,]\d+)?%?|20\d{2}|19\d{2})\b")

    def __init__(self, owner: "AutoLearner") -> None:
        self._owner = owner

    def generate_valid_qa_pair(
        self,
        title: str,
        content_preview: str,
        *,
        sleep_between_questions: int,
        max_retries: int,
    ) -> dict | None:
        asked_questions: list[str] = []

        for attempt in range(1, max_retries + 1):
            self._owner._set_status(
                note=title,
                step=f"Génération de la question (tentative {attempt}/{max_retries})…",
            )
            questions = self._owner._generate_questions(
                content_preview,
                already_asked=asked_questions or None,
            )
            if not questions:
                logger.warning(
                    f"Auto-learner : aucune question générée pour '{title}' (tentative {attempt})"
                )
                if sleep_between_questions > 0 and attempt < max_retries:
                    time.sleep(sleep_between_questions)
                continue

            question = questions[0]
            asked_questions.append(question)
            logger.info(
                f"Auto-learner : question générée (tentative {attempt}) : '{question[:80]}'"
            )

            if sleep_between_questions > 0 and attempt > 1:
                time.sleep(sleep_between_questions)

            outcome, qa_pair = self.attempt_question_answer(title, question, attempt)
            if outcome == "accepted":
                return qa_pair
            if outcome == "abort":
                return None

        return None

    def attempt_question_answer(
        self,
        title: str,
        question: str,
        attempt: int,
    ) -> tuple[str, dict | None]:
        try:
            self._owner._set_status(
                note=title,
                step=f"Tentative {attempt} — Recherche web : {question[:60]}…",
            )
            web_results = self._owner._web_search(question)
            web_snippets = [
                result.get("full_text") or result.get("body", "")
                for result in web_results
                if result.get("full_text") or result.get("body")
            ]
            if web_snippets and self._owner._snippets_relevant(question, web_snippets):
                rag_context, sources = self._build_rag_context(question)
                answer, sources, web_results, provenance = self._compose_web_answer(
                    question,
                    rag_context,
                    sources,
                    web_snippets,
                    web_results,
                )
                if provenance != "Coffre" and not self._is_grounded_web_answer(answer, web_snippets):
                    logger.info(
                        f"Auto-learner : réponse web jugée insuffisamment ancrée, repli coffre pour '{question[:60]}'"
                    )
                    answer, sources = self._owner._rag.query(question, exclude_obsirag_generated=True)
                    web_results = []
                    provenance = "Coffre"
            else:
                answer, sources = self._owner._rag.query(question, exclude_obsirag_generated=True)
                web_results = []
                provenance = "Coffre"

            if self._owner._is_weak_answer(answer):
                self._owner._set_status(
                    note=title,
                    step=f"Tentative {attempt} — Réponse insuffisante, nouvelle question…",
                )
                logger.debug(
                    f"Réponse faible (tentative {attempt}), nouvelle question demandée pour '{title}'"
                )
                return "retry", None

            return "accepted", {
                "question": question,
                "answer": answer,
                "sources": [source["metadata"].get("file_path", "") for source in sources[:3]],
                "web_refs": [
                    {"title": result.get("title", result.get("href", "")), "url": result.get("href", "")}
                    for result in web_results
                ],
                "provenance": provenance,
            }
        except Exception as exc:
            logger.warning(
                f"Auto-learner QA failed pour '{title}' (tentative {attempt}) : {exc}"
            )
            return "abort", None

    def _build_rag_context(self, question: str) -> tuple[str, list[dict]]:
        _, sources = self._owner._rag.query(question, exclude_obsirag_generated=True)
        rag_context = (
            "\n\n".join(source.get("text", "")[:400] for source in sources[:2])
            if sources
            else "Aucune note personnelle sur ce sujet."
        )
        return rag_context, sources

    def _compose_web_answer(
        self,
        question: str,
        rag_context: str,
        sources: list[dict],
        web_snippets: list[str],
        web_results: list[dict],
    ) -> tuple[str, list[dict], list[dict], str]:
        fitted_rag, fitted_web = self._owner._fit_context(
            rag_context,
            "\n\n".join(web_snippets[:3]),
        )
        prompt = self._owner._web_answer_prompt.format(
            question=question,
            rag_context=fitted_rag,
            web_context=fitted_web,
        )
        try:
            answer = self._owner._chat_user_visible_french(
                prompt,
                temperature=0.3,
                max_tokens=self._owner._MAX_TOKENS_RESPONSE,
                operation="autolearn_enrich",
            )
            provenance = "Web + Coffre" if sources else "Web"
            logger.info(f"Auto-learner : réponse web pour '{question[:60]}'")
            return answer, sources, web_results, provenance
        except Exception:
            answer, rag_sources = self._owner._rag.query(question, exclude_obsirag_generated=True)
            return answer, rag_sources, [], "Coffre"

    @classmethod
    def _is_grounded_web_answer(cls, answer: str, web_snippets: list[str]) -> bool:
        normalized_answer = (answer or "").strip().lower()
        if not normalized_answer:
            return False

        claims = {
            match.group(0).replace(",", ".")
            for match in cls._HARD_CLAIM_RE.finditer(normalized_answer)
        }
        if not claims:
            return True

        normalized_context = "\n".join(snippet.lower().replace(",", ".") for snippet in web_snippets if snippet)
        if not normalized_context:
            return False

        unsupported_claims = [claim for claim in claims if claim not in normalized_context]
        return len(unsupported_claims) < len(claims)