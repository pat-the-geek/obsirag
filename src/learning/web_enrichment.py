from __future__ import annotations

import re
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from src.learning.autolearn import AutoLearner


class AutoLearnWebEnrichment:
    def __init__(self, owner: "AutoLearner") -> None:
        self._owner = owner

    @staticmethod
    def build_search_query(query: str) -> str:
        query = str(query or "").strip()
        if not query:
            return ""
        return f"{query} explication analyse histoire contexte"

    @staticmethod
    def fetch_url_content(url: str, max_chars: int = 3000) -> str:
        if url.lower().endswith(".pdf") or "/pdf" in url.lower():
            logger.debug(f"URL PDF ignorée : {url[:60]}")
            return ""
        try:
            import urllib.request

            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                content_type = resp.headers.get("Content-Type", "")
                if "pdf" in content_type.lower():
                    return ""
                raw = resp.read(50_000).decode("utf-8", errors="ignore")
            text = re.sub(r"<style[^>]*>.*?</style>", " ", raw, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"([a-zàéèêëîïôùûüç])([A-ZÀÉÈÊËÎÏÔÙÛÜÇ])", r"\1 \2", text)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 100 and text.count(" ") / len(text) < 0.05:
                return ""
            words = text.split()
            if words:
                long_words = sum(1 for word in words if len(word) > 15 and word.isalpha())
                if long_words / len(words) > 0.15:
                    return ""
            return text[:max_chars]
        except Exception:
            return ""

    def synthesize_web_sources(self, note_title: str, qa_pairs: list[dict]) -> str:
        all_refs: list[dict] = []
        seen_urls: set[str] = set()
        for qa in qa_pairs:
            for ref in qa.get("web_refs", []):
                url = ref.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    all_refs.append(ref)

        if not all_refs:
            return ""

        fetched: list[str] = []
        for ref in all_refs[:4]:
            content = self._owner._fetch_url_content(ref["url"])
            if content:
                fetched.append(f"### {ref.get('title', ref['url'])}\n{content}")
                logger.debug(f"Fetché : {ref['url'][:60]}")

        if not fetched:
            return ""

        _, combined_fitted = self._owner._fit_context("", "\n\n".join(fetched), overhead=300)
        prompt = (
            f"Sujet : {note_title}\n\n"
            f"Voici le contenu de {len(fetched)} source(s) web citées dans les insights :\n\n"
            f"{combined_fitted}\n\n"
            f"Rédige une synthèse structurée en français (max 400 mots) qui extrait "
            f"les informations clés, faits importants et apports de connaissance de ces sources. "
            f"Format : paragraphes courts avec sous-titres Markdown si pertinent."
        )
        try:
            return self._owner._chat_user_visible_french(
                prompt,
                temperature=0.3,
                max_tokens=self._owner._MAX_TOKENS_RESPONSE,
                operation="autolearn_web_synthesis",
            )
        except Exception as exc:
            logger.debug(f"Synthèse sources web échouée : {exc}")
            return ""

    def web_search(self, query: str) -> list[dict]:
        try:
            from ddgs import DDGS

            enriched_query = self.build_search_query(query)
            with DDGS() as ddgs:
                results = list(ddgs.text(enriched_query, max_results=15))
            trusted = [
                result for result in results
                if any(domain in result.get("href", "") for domain in self._owner._TRUSTED_DOMAINS)
            ]
            if results and not trusted:
                try:
                    self._owner._metrics.increment("autolearn_web_search_fallback_total")
                except Exception:
                    pass
            selected = trusted[:3] if trusted else results[:3]
            enriched_results: list[dict] = []
            for result in selected:
                body = result.get("body", "")
                full_text = self.fetch_url_content(result.get("href", "")) if result.get("href") else ""
                if not body and not full_text:
                    continue
                enriched = dict(result)
                if full_text:
                    enriched["full_text"] = full_text
                enriched_results.append(enriched)
            return enriched_results
        except Exception as exc:
            try:
                self._owner._metrics.increment("autolearn_web_search_error_total")
            except Exception:
                pass
            logger.debug(f"Web search échouée : {exc}")
            return []

    @staticmethod
    def snippets_relevant(question: str, snippets: list[str]) -> bool:
        words = [word.lower() for word in re.findall(r"\b\w{5,}\b", question)]
        if not words or not snippets:
            return bool(snippets)
        combined = " ".join(snippets).lower()
        return any(word in combined for word in words)

    def enrich_with_web(self, question: str, rag_answer: str, web_snippets: list[str]) -> str:
        if not self._owner._snippets_relevant(question, web_snippets):
            logger.debug(f"Sources web hors sujet pour : {question[:60]}")
            return rag_answer

        _, context_fitted = self._owner._fit_context("", "\n\n".join(web_snippets[:3]), overhead=300)
        prompt = (
            f"Question : {question}\n\n"
            f"Sources web :\n{context_fitted}\n\n"
            f"Rédige une réponse structurée et informative en français, en t'appuyant principalement "
            f"sur les sources web ci-dessus. Apporte des faits concrets, des chiffres, des exemples "
            f"et du contexte qui enrichissent la compréhension du sujet. Sois précis et complet."
        )
        try:
            return self._owner._chat_user_visible_french(
                prompt,
                temperature=0.3,
                max_tokens=self._owner._MAX_TOKENS_RESPONSE,
                operation="autolearn_enrich",
            )
        except Exception as exc:
            logger.debug(f"Enrichissement web échoué : {exc}")
            return rag_answer

    def generate_questions(self, content: str, already_asked: list[str] | None = None) -> list[str]:
        try:
            if already_asked:
                lines = "\n".join(f"- {question}" for question in already_asked)
                already_asked_section = (
                    "\n<deja_posees>\nCes questions ont déjà été posées et ont obtenu une réponse insuffisante. "
                    f"Génère une question DIFFÉRENTE :\n{lines}\n</deja_posees>\n"
                )
            else:
                already_asked_section = ""
            prompt = self._owner._question_prompt.format(
                content=content[:3000],
                already_asked_section=already_asked_section,
            )
            answer = self._owner._chat_user_visible_french(
                prompt,
                temperature=0.7,
                max_tokens=150,
                operation="autolearn_questions",
            )
            question = self._extract_question(answer)
            if question:
                return [question]
            return []
        except Exception as exc:
            logger.debug(f"Génération de question échouée : {exc}")
            return []

    @staticmethod
    def _extract_question(answer: str) -> str | None:
        prefix = re.compile(r"^[•\*\-]?\s*(?:Q\d+[.:）]|Question\s*\d*[.:]|\d+[.)]\s*)?\s*", re.I)
        for line in answer.strip().splitlines():
            cleaned = prefix.sub("", line.strip()).strip()
            if len(cleaned) > 10 and cleaned.endswith("?"):
                return cleaned

        inline_match = re.search(r"((?:Quel(?:le|s)?|Quoi|Comment|Pourquoi|Quand|O[uù]|Combien|En quoi|Dans quelle mesure)[^?]{8,}\?)", answer.strip(), re.I)
        if inline_match:
            return inline_match.group(1).strip()

        return None