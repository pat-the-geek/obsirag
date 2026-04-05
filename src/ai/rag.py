"""
Pipeline RAG (Retrieval-Augmented Generation).
Détecte l'intention de la requête et adapte la stratégie de récupération :
  - temporelle  : "cette semaine", "dernières notes", "ce mois"
  - entité NER  : "notes qui parlent de [X]", "où j'ai rencontré [Y]"
  - tags        : "#projet", "#idée"
  - synthèse    : "fais une synthèse", "résume", "que sais-je sur"
  - générale    : tout autre cas
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

from loguru import logger

from src.config import settings
from src.database.chroma_store import ChromaStore


# ---------------------------------------------------------------------------
# Détection d'intention
# ---------------------------------------------------------------------------

_TEMPORAL_PATTERNS = [
    (re.compile(r"\bce(?:tte)?\s+semaine\b", re.I), 7),
    (re.compile(r"\bcette\s+semaine\b", re.I), 7),
    (re.compile(r"\bce\s+mois\b", re.I), 30),
    (re.compile(r"\baujourd'hui\b", re.I), 1),
    (re.compile(r"\bderni[eè]r(?:es?)?\s+(?:notes?|jours?)\b", re.I), 7),
    (re.compile(r"\brécemment\b", re.I), 14),
    (re.compile(r"\bcette\s+ann[ée]e\b", re.I), 365),
    (re.compile(r"\bles?\s+(\d+)\s+derniers?\s+jours?\b", re.I), None),  # dynamique
]

_SYNTHESIS_PATTERNS = re.compile(
    r"\b(synth[eè]se|r[eé]sum[eé]|que\s+sais-je|ce\s+que\s+j.ai\s+appris|fais\s+le\s+point)\b",
    re.I,
)

_ENTITY_PATTERNS = re.compile(
    r"\b(?:notes?\s+(?:qui\s+)?(?:parlent?|mentionnent?)\s+de|o[uù]\s+j.ai|concernant|sur)\s+(.+?)(?:\s*\?|$)",
    re.I,
)

_TAG_PATTERN = re.compile(r"#([A-Za-z0-9_\-/]+)")

_SYSTEM_PROMPT = """Tu es ObsiRAG, un assistant personnel connecté au coffre Obsidian de l'utilisateur.
Tu réponds en français, de façon précise et structurée.
Tu t'appuies UNIQUEMENT sur les extraits de notes fournis dans le contexte.
Si l'information n'est pas dans le contexte, dis-le clairement plutôt que d'inventer.
Cite les titres de notes sources entre [crochets] quand tu les utilises."""


class RAGPipeline:
    def __init__(self, chroma: ChromaStore, llm) -> None:
        self._chroma = chroma
        self._llm = llm

    # ---- API publique ----

    def query_stream(
        self,
        user_query: str,
        chat_history: list[dict[str, str]] | None = None,
    ) -> tuple[Iterator[str], list[dict]]:
        """Retourne (stream_generator, sources)."""
        chunks, intent = self._retrieve(user_query)
        logger.info(f"RAG intent={intent} chunks={len(chunks)}")

        context = self._build_context(chunks)
        messages = self._build_messages(user_query, context, chat_history or [])

        stream = self._llm.stream(messages, operation="rag_query")
        return stream, chunks

    def query(
        self,
        user_query: str,
        chat_history: list[dict[str, str]] | None = None,
    ) -> tuple[str, list[dict]]:
        """Appel bloquant — retourne (réponse, sources)."""
        chunks, intent = self._retrieve(user_query)
        context = self._build_context(chunks)
        messages = self._build_messages(user_query, context, chat_history or [])

        answer = self._llm.chat(messages, operation="rag_query")
        return answer, chunks

    # ---- Détection d'intention et récupération ----

    def _retrieve(self, query: str) -> tuple[list[dict], str]:
        # 1. Tags explicites
        tags = _TAG_PATTERN.findall(query)
        if tags:
            return self._chroma.search_by_tags(tags, top_k=settings.search_top_k), "tags"

        # 2. Temporel
        days = self._detect_temporal(query)
        if days is not None:
            since = datetime.now() - timedelta(days=days)
            chunks = self._chroma.search_by_date_range(
                query, since=since, top_k=settings.search_top_k
            )
            if not chunks:
                # Fallback sémantique si aucun résultat dans la fenêtre
                chunks = self._chroma.search(query, top_k=settings.search_top_k)
            return chunks, "temporal"

        # 3. Entité NER
        entity_match = _ENTITY_PATTERNS.search(query)
        if entity_match:
            entity = entity_match.group(1).strip()
            return self._chroma.search_by_entity(entity, top_k=settings.search_top_k), "entity"

        # 4. Synthèse — même top_k que la recherche générale, le budget de chars fait le tri
        if _SYNTHESIS_PATTERNS.search(query):
            chunks = self._chroma.search(query, top_k=settings.search_top_k)
            return chunks, "synthesis"

        # 5. Détection de noms propres → recherche hybride (sémantique + keyword)
        proper_nouns = self._extract_proper_nouns(query)
        if proper_nouns:
            semantic = self._chroma.search(query, top_k=settings.search_top_k)
            keyword_chunks: list[dict] = []
            for noun in proper_nouns:
                keyword_chunks.extend(self._chroma.search_by_keyword(noun, top_k=4))
            # Fusion : keyword en priorité, sémantique en complément
            seen_ids: set[str] = set()
            merged: list[dict] = []
            for c in keyword_chunks + semantic:
                if c["chunk_id"] not in seen_ids:
                    seen_ids.add(c["chunk_id"])
                    merged.append(c)
            return merged[: settings.search_top_k], "hybrid"

        # 6. Recherche générale
        return self._chroma.search(query, top_k=settings.search_top_k), "general"

    @staticmethod
    def _extract_proper_nouns(query: str) -> list[str]:
        """Extrait les séquences de mots capitalisés (noms propres, entités)."""
        # Cherche les groupes de 1 à 4 mots commençant par une majuscule (hors début de phrase)
        words = query.split()
        proper: list[str] = []
        current: list[str] = []
        for i, w in enumerate(words):
            clean = re.sub(r"[^\w]", "", w)
            if clean and clean[0].isupper() and i > 0:
                current.append(clean)
            else:
                if len(current) >= 1:
                    proper.append(" ".join(current))
                current = []
        if current:
            proper.append(" ".join(current))
        # Filtre : au moins 3 caractères et pas un mot courant
        _STOP = {"IA", "AI", "GPT", "LLM", "URL"}
        return [p for p in proper if len(p) >= 3 and p not in _STOP]

    @staticmethod
    def _detect_temporal(query: str) -> int | None:
        for pattern, days in _TEMPORAL_PATTERNS:
            m = pattern.search(query)
            if m:
                if days is None:
                    # Groupe dynamique ex: "les 5 derniers jours"
                    try:
                        return int(m.group(1))
                    except (IndexError, ValueError):
                        return 7
                return days
        return None

    # ---- Construction du prompt ----

    def _build_context(self, chunks: list[dict]) -> str:
        if not chunks:
            return "Aucune note trouvée dans le coffre pour cette requête."

        # Déduplique par note, limite au nombre max de chunks
        seen_notes: dict[str, list[dict]] = {}
        for c in chunks[: settings.max_context_chunks]:
            fp = c["metadata"].get("file_path", "")
            seen_notes.setdefault(fp, []).append(c)

        parts: list[str] = []
        budget = settings.max_context_chars

        for fp, note_chunks in seen_notes.items():
            if budget <= 0:
                break
            title = note_chunks[0]["metadata"].get("note_title", fp)
            date_mod = note_chunks[0]["metadata"].get("date_modified", "")[:10]
            header = f"### [{title}] ({date_mod})"
            parts.append(header)
            budget -= len(header)

            for c in note_chunks:
                if budget <= 0:
                    break
                section = c["metadata"].get("section_title", "")
                # Tronque le texte du chunk si trop long
                text = c["text"][: settings.max_chunk_chars]
                if len(c["text"]) > settings.max_chunk_chars:
                    text += "…"
                line = (f"**{section}** — {text}") if section else text
                if len(line) <= budget:
                    parts.append(line)
                    budget -= len(line)
                else:
                    parts.append(line[:budget] + "…")
                    budget = 0
            parts.append("")

        return "\n".join(parts)

    def _build_messages(
        self,
        query: str,
        context: str,
        history: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [{"role": "system", "content": _SYSTEM_PROMPT}]

        # Historique : limité aux 4 derniers échanges (8 messages) pour ménager le contexte
        messages.extend(history[-8:])

        user_content = (
            f"**Extraits du coffre Obsidian :**\n\n{context}\n\n"
            f"---\n**Question :** {query}"
        )
        messages.append({"role": "user", "content": user_content})
        return messages
