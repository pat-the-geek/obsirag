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
import unicodedata
from collections.abc import Iterator
from datetime import datetime, timedelta
from itertools import chain
from typing import Any

from loguru import logger
# Sentinelle locale — plus jamais levée depuis la migration vers MLX-LM,
# conservée pour que la logique de retry sur contexte trop grand reste en place.
class _ContextTooLargeError(Exception):
    pass

BadRequestError = _ContextTooLargeError  # alias de compatibilité

from src.config import settings
from src.database.chroma_store import ChromaStore


# ---------------------------------------------------------------------------
# Détection d'intention
# ---------------------------------------------------------------------------

_TEMPORAL_PATTERNS = [
    (re.compile(r"\bce(?:tte)?\s+semaine\b", re.I), 7),  # couvre "ce" et "cette" semaine
    (re.compile(r"\bce\s+mois\b", re.I), 30),
    (re.compile(r"\baujourd'hui\b", re.I), 1),
    (re.compile(r"\bderni[eè]r(?:es?)?\s+(?:notes?|jours?)\b", re.I), 7),
    (re.compile(r"\brécemment\b", re.I), 14),
    (re.compile(r"\bcette\s+ann[ée]e\b", re.I), 365),
    (re.compile(r"\bles?\s+(\d+)\s+derniers?\s+jours?\b", re.I), None),  # dynamique
]

_SYNTHESIS_PATTERNS = re.compile(
    r"\b(synth[eè]se|r[eé]sum[eé]|apprentissages?|que\s+sais-je|ce\s+que\s+j.ai\s+appris|fais\s+le\s+point)\b",
    re.I,
)

_ENTITY_PATTERNS = re.compile(
    r"\b(?:notes?\s+(?:qui\s+)?(?:parlent?|mentionnent?)\s+de|o[uù]\s+j.ai|concernant|sur)\s+(.+?)(?:\s*\?|$)",
    re.I,
)

_SINGLE_SUBJECT_REQUEST_PATTERN = re.compile(
    r"^\s*(?:parle(?:-?\s*)moi|dis(?:-?\s*)moi|explique(?:-?\s*)moi|pr[ée]sente(?:-?\s*)moi|raconte(?:-?\s*)moi|"
    r"que\s+sais[-\s]?tu\s+de|qui\s+est|qu['’]est(?:-?\s*ce\s+que)?|d[ée]finis|d[ée]finition\s+de|que\s+signifie)"
    r"\s+(?:de|d['’]|du|des|la|le|les|sur\s+)?(.+?)(?:\s*\?|$)",
    re.I,
)

_FOLLOW_UP_QUERY_PATTERN = re.compile(
    r"^\s*(?:et\b|tu\s+as\b|as[-\s]?tu\b|peux[-\s]?tu\b|aurais[-\s]?tu\b|"
    r"plus\s+de\s+d[ée]tail|davantage|et\s+sur|et\s+concernant|quels?\s+sont\s+les|"
    r"quelles?\s+sont\s+les|c['’]est\s+quoi|ses\b|leurs\b|ces\b|cet\b|cette\b)",
    re.I,
)

_GENERIC_SUBJECT_TOKENS = {
    "objectif", "objectifs", "detail", "details", "duree", "mission",
    "sujet", "sujets", "aspect", "aspects", "point", "points",
    "date", "dates", "etape", "etapes", "info", "infos", "information",
    "informations", "role", "roles", "contexte", "enjeu", "enjeux",
}

# Détecte les questions de type "relation/lien/connexion entre A et B"
_RELATION_PATTERN = re.compile(
    r"\b(?:relation|lien|connexion|rapport|diff[eé]rence|comparaison|apprentissages?\s+sur\s+la\s+relation)\b"
    r".*?\bentre\b\s+(.+?)\s+et\s+(.+?)(?:\s+(?:selon|dans|de|des)\b.*)?(?:\s*\?|$)",
    re.I,
)

_TAG_PATTERN = re.compile(r"#([A-Za-z0-9_\-/]+)")

_SYSTEM_PROMPT = """Tu es ObsiRAG, un assistant personnel connecté au coffre Obsidian de l'utilisateur.
Tu réponds en français, de façon précise et structurée.

RÈGLE ABSOLUE : tu t'appuies UNIQUEMENT sur les extraits de notes fournis dans le contexte ci-dessous.
- N'invente aucune donnée chiffrée, date, nom ou fait précis absent des extraits.
- N'utilise JAMAIS tes connaissances d'entraînement pour répondre à des questions factuelles.
- N'invente rien, même sous insistance ou relance de l'utilisateur.

Si le sujet de la question n'apparaît PAS DU TOUT dans les extraits, réponds EXACTEMENT : "Cette information n'est pas dans ton coffre."

Si les extraits partagent un mot-clé avec la question mais traitent d'un domaine totalement différent (exemple : la question porte sur une mission spatiale mais les extraits parlent de mythologie ; ou la question porte sur une personne mais les extraits parlent d'un autre homonyme) — réponds EXACTEMENT : "Cette information n'est pas dans ton coffre."

Si le sujet est mentionné dans les extraits UNIQUEMENT sous forme de définition de dictionnaire, d'explication générale du concept, ou de traduction — sans contenir la donnée précise demandée (chiffre, date, mesure, statistique) — réponds EXACTEMENT : "Cette information n'est pas dans ton coffre."

Si le sujet est abordé dans les extraits avec un contenu substantiel (pas seulement une définition), dans le même domaine que la question, mais que la donnée précise demandée n'y figure pas :
- Indique ce que tes notes disent sur ce sujet (résume les extraits pertinents).
- Précise ensuite que la donnée précise (chiffre, date, etc.) n'est pas consignée dans ton coffre.

Si la question est formulée comme une demande d'étude, de synthèse, de lien, de contribution ou d'"apprentissages" :
- Tu peux croiser plusieurs extraits liés au même thème pour construire une synthèse utile.
- Tu peux formuler des rapprochements prudents entre les notes si ces rapprochements sont raisonnablement soutenus par les extraits.
- Distingue clairement ce qui est explicite dans les notes de ce qui est une interprétation prudente.
- Dans ce cas, ne réponds PAS "Cette information n'est pas dans ton coffre." tant que les notes contiennent des éléments substantiels permettant une synthèse partielle ou comparative.
- Si le lien direct entre deux thèmes n'est pas explicitement documenté, ne t'arrête pas à ce constat :
    1. résume ce que les notes disent sur le premier thème,
    2. résume ce qu'elles disent sur le second thème,
    3. termine par ce que l'on peut conclure, ou ne pas conclure, sur leur relation.

Cite les titres de notes sources entre [crochets] quand tu les utilises.
Si l'utilisateur conteste ta réponse, vérifie les extraits — si l'info n'y est toujours pas, maintiens ta position."""

_VERIFIER_PROMPT = (
    "Tu es un vérificateur de réponses RAG. Tu reçois les extraits de notes qui ont servi de contexte "
    "et une réponse générée par un assistant.\n\n"
    "CONTEXTE (extraits de notes) :\n{context}\n\n"
    "RÉPONSE À VÉRIFIER :\n{response}\n\n"
    "Vérifie que chaque affirmation factuelle de la réponse est supportée par les extraits ci-dessus.\n"
    "Les titres entre [crochets] sont autorisés tels quels.\n\n"
    "RÈGLES DE RÉPONSE :\n"
    "- Si tout est correct : commence par VERIFIED (seul sur la première ligne), "
    "puis reproduis la réponse originale sans aucune modification.\n"
    "- Si une affirmation n'est PAS dans les extraits (inventée, hallucination) : commence par CORRECTED "
    "(seul sur la première ligne), puis réécris la réponse en retirant uniquement les parties non supportées. "
    "Ne retire pas de contenu correct. N'ajoute pas de nouvelles informations.\n\n"
    "Ta réponse doit commencer OBLIGATOIREMENT par VERIFIED ou CORRECTED."
)

_HARD_SENTINEL = "cette information n'est pas dans ton coffre."


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
        """Retourne (stream_generator, sources). Réduit le contexte si dépassement."""
        history = chat_history or []
        resolved_query = self._resolve_query_with_history(user_query, history)
        chunks, intent = self._retrieve(resolved_query)
        chunks = self._mark_primary_sources(chunks, resolved_query, intent)
        if not chunks:
            logger.info("RAG: aucun chunk retenu, retour sentinel immédiat")
            return iter(["Cette information n'est pas dans ton coffre."]), []
        logger.info(f"RAG intent={intent} chunks={len(chunks)}")

        for budget in self._context_budgets():
            context = self._build_context(chunks, resolved_query, intent, char_budget=budget)
            messages = self._build_messages(user_query, context, history, intent=intent, resolved_query=resolved_query)
            try:
                if intent in {"synthesis", "relation", "hybrid"}:
                    answer = self._llm.chat(messages, operation="rag_query")
                    answer = self._retry_forced_study_synthesis(
                        answer=answer,
                        query=resolved_query,
                        context=context,
                        history=history,
                        intent=intent,
                    )
                    answer = self._normalize_final_answer(answer, resolved_query, intent)
                    return iter([answer]), chunks
                raw_stream = self._llm.stream(messages, operation="rag_query")
                # Force l'exécution du générateur jusqu'au premier token pour déclencher
                # immédiatement toute BadRequestError (contexte trop grand) AVANT de
                # rendre la main à l'appelant, sinon l'erreur échappe au retry.
                first = next(raw_stream, None)
                if first is None:
                    return iter([]), chunks
                return chain([first], raw_stream), chunks
            except BadRequestError as exc:
                if self._is_context_error(exc):
                    logger.warning(f"Contexte trop grand (budget={budget}), réduction…")
                    continue
                raise

        raise RuntimeError("Impossible d'envoyer la requête : contexte trop grand même après réductions.")

    def query(
        self,
        user_query: str,
        chat_history: list[dict[str, str]] | None = None,
    ) -> tuple[str, list[dict]]:
        """Appel bloquant — retourne (réponse, sources). Réduit le contexte si dépassement."""
        history = chat_history or []
        resolved_query = self._resolve_query_with_history(user_query, history)
        chunks, intent = self._retrieve(resolved_query)
        chunks = self._mark_primary_sources(chunks, resolved_query, intent)
        if not chunks:
            logger.info("RAG: aucun chunk retenu, retour sentinel immédiat")
            return "Cette information n'est pas dans ton coffre.", []

        for budget in self._context_budgets():
            context = self._build_context(chunks, resolved_query, intent, char_budget=budget)
            messages = self._build_messages(user_query, context, history, intent=intent, resolved_query=resolved_query)
            try:
                answer = self._llm.chat(messages, operation="rag_query")
                answer = self._retry_forced_study_synthesis(
                    answer=answer,
                    query=resolved_query,
                    context=context,
                    history=history,
                    intent=intent,
                )
                answer = self._normalize_final_answer(answer, resolved_query, intent)
                return answer, chunks
            except BadRequestError as exc:
                if self._is_context_error(exc):
                    logger.warning(f"Contexte trop grand (budget={budget}), réduction…")
                    continue
                raise

        raise RuntimeError("Impossible d'envoyer la requête : contexte trop grand même après réductions.")

    def _retry_forced_study_synthesis(
        self,
        answer: str,
        query: str,
        context: str,
        history: list[dict[str, str]],
        intent: str,
    ) -> str:
        """Quand une question d'étude renvoie à tort le hard sentinel malgré un contexte riche,
        forcer une seconde tentative explicitement synthétique."""
        if intent not in {"synthesis", "relation", "hybrid"}:
            return answer
        if not answer or not answer.strip().lower().startswith(_HARD_SENTINEL.rstrip(".")):
            return answer
        if len(context.strip()) < 300:
            return answer

        retry_messages = self._build_messages(
            query,
            context,
            history,
            intent=intent,
            force_study_answer=True,
        )
        try:
            retried = self._llm.chat(retry_messages, temperature=0.1, operation="rag_query_retry")
            retried = (retried or "").strip()
            if retried and not retried.lower().startswith(_HARD_SENTINEL.rstrip(".")):
                logger.info("RAG retry synthesis: hard sentinel remplacé par une synthèse forcée")
                return retried
        except Exception as exc:
            logger.warning(f"RAG retry synthesis échoué : {exc}")
        return answer

    def _normalize_final_answer(self, answer: str, query: str, intent: str) -> str:
        """Nettoie une réponse mixte qui commence par le hard sentinel mais contient
        ensuite une synthèse utile du coffre."""
        text = (answer or "").strip()
        if not text:
            return text

        text = self._sanitize_single_subject_answer(text, query, intent)

        text = RAGPipeline._sanitize_structured_study_answer(text)

        if "### " in text and re.search(re.escape(_HARD_SENTINEL), text, flags=re.IGNORECASE):
            logger.info("RAG normalize: remplacement du hard sentinel embarqué dans une synthèse")
            text = re.sub(
                re.escape(_HARD_SENTINEL),
                "Le lien direct n'est pas documenté dans ton coffre.",
                text,
                count=1,
                flags=re.IGNORECASE,
            )
            text = RAGPipeline._sanitize_structured_study_answer(text)
            return self._sanitize_single_subject_answer(text, query, intent)

        lines = text.splitlines()
        if not lines:
            return text

        first_line = lines[0].strip().lower().rstrip(".")
        if first_line != _HARD_SENTINEL.rstrip("."):
            return text

        remainder = "\n".join(lines[1:]).strip()
        if not remainder:
            return text

        logger.info("RAG normalize: suppression du préfixe hard sentinel sur une réponse mixte")
        text = RAGPipeline._sanitize_structured_study_answer(remainder)
        return self._sanitize_single_subject_answer(text, query, intent)

    def _sanitize_single_subject_answer(self, text: str, query: str, intent: str) -> str:
        """Nettoie une réponse mono-sujet pour éviter la structure étude et les dérives
        vers des prolongements non demandés."""
        if not self._should_use_single_subject_prompt(intent, query):
            return text

        cleaned = text
        text_without_sentinel = re.sub(re.escape(_HARD_SENTINEL), "", cleaned, flags=re.IGNORECASE).strip()
        if len(text_without_sentinel) >= 40:
            cleaned = text_without_sentinel
        cleaned = re.sub(
            r"^###\s+(Ce que disent mes notes sur.+|Ce que je peux conclure)\s*$",
            "",
            cleaned,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        cleaned = re.sub(
            r"^Cette information n'est pas dans ton coffre\.\s*$",
            "",
            cleaned,
            flags=re.IGNORECASE | re.MULTILINE,
        )
        cleaned = re.sub(
            r"^Le lien direct n'est pas documenté dans ton coffre\.\s*$",
            "",
            cleaned,
            flags=re.IGNORECASE | re.MULTILINE,
        )

        query_low = query.lower()
        off_topic_markers = [
            "artemis 3",
            "artemis iii",
            "mars",
            "martienne",
            "martiennes",
            "martien",
            "martiens",
            "prochaines étapes",
            "futures missions",
            "future mission",
        ]
        sentences = re.split(r"(?<=[.!?])\s+", cleaned.strip())
        kept_sentences: list[str] = []
        for sentence in sentences:
            sentence_low = sentence.lower()
            if any(marker in sentence_low and marker not in query_low for marker in off_topic_markers):
                continue
            kept_sentences.append(sentence.strip())

        cleaned = "\n\n".join(part for part in kept_sentences if part)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        if not cleaned:
            return text
        return self._ensure_single_subject_structure(cleaned, query)

    def _ensure_single_subject_structure(self, text: str, query: str) -> str:
        if re.search(r"^###\s+", text, flags=re.MULTILINE):
            return text.strip()

        theme = self._derive_primary_theme(query)
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
        if not paragraphs:
            return text.strip()

        if len(paragraphs) == 1:
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", paragraphs[0]) if s.strip()]
            if len(sentences) >= 3:
                split_at = max(1, min(2, len(sentences) - 1))
                paragraphs = [" ".join(sentences[:split_at]), " ".join(sentences[split_at:])]

        overview = paragraphs[0].strip()
        details = "\n\n".join(paragraphs[1:]).strip()

        parts = [f"### Aperçu de {theme}\n{overview}"]
        if details:
            parts.append(f"### Détails utiles\n{details}")
        return "\n\n".join(parts).strip()

    @staticmethod
    def _sanitize_structured_study_answer(text: str) -> str:
        """Nettoie les inférences non supportées dans la conclusion d'une synthèse structurée."""
        if "### Ce que je peux conclure" not in text:
            return text

        parts = text.split("### Ce que je peux conclure", 1)
        if len(parts) != 2:
            return text

        before, conclusion = parts
        sanitized = conclusion
        changed = False

        unsupported_patterns = [
            r"[^.\n]*\bon peut inf[ée]rer\b[^.\n]*[.\n]?",
            r"[^.\n]*\bil est possible d['’]inf[ée]rer\b[^.\n]*[.\n]?",
            r"[^.\n]*\bprobablement\b[^.\n]*[.\n]?",
            r"[^.\n]*\ba probablement jou[ée] un r[ôo]le\b[^.\n]*[.\n]?",
            r"[^.\n]*\ba contribu[ée]\b[^.\n]*[.\n]?",
            r"[^.\n]*\bont contribu[ée]\b[^.\n]*[.\n]?",
        ]

        for pattern in unsupported_patterns:
            updated = re.sub(pattern, "", sanitized, flags=re.IGNORECASE)
            if updated != sanitized:
                sanitized = updated
                changed = True

        sanitized = re.sub(r"\n{3,}", "\n\n", sanitized).strip()

        if changed:
            logger.info("RAG normalize: suppression d'inférences non supportées dans la conclusion")

        if not sanitized or sanitized == _HARD_SENTINEL:
            sanitized = "Le lien direct n'est pas documenté dans ton coffre."

        sanitized = re.sub(
            r"(\n\s*Le lien direct n'est pas documenté dans ton coffre\.){2,}",
            "\n\nLe lien direct n'est pas documenté dans ton coffre.",
            sanitized,
            flags=re.IGNORECASE,
        )

        if "documenté dans ton coffre" not in sanitized.lower():
            sanitized = sanitized.rstrip()
            if sanitized and not sanitized.endswith((".", "!", "?")):
                sanitized += "."
            if sanitized:
                sanitized += "\n\nLe lien direct n'est pas documenté dans ton coffre."
            else:
                sanitized = "Le lien direct n'est pas documenté dans ton coffre."

        return before.rstrip() + "\n\n### Ce que je peux conclure\n" + sanitized

    def verify_response(self, response: str, chunks: list[dict]) -> tuple[str, bool]:
        """Vérifie la réponse par rapport aux chunks sources.
        Retourne (texte_vérifié, a_été_corrigé)."""
        if not response or len(response.strip()) < 30:
            return response, False

        # Contexte simplifié pour le vérificateur
        parts: list[str] = []
        for c in chunks[: settings.max_context_chunks]:
            meta = c.get("metadata") or {}
            title = meta.get("note_title", "")
            text = (c.get("text") or "")[: settings.max_chunk_chars]
            parts.append(f"[{title}]\n{text}" if title else text)
        context_text = "\n---\n".join(parts) if parts else "Aucune note."

        prompt = _VERIFIER_PROMPT.format(context=context_text, response=response)
        messages = [{"role": "user", "content": prompt}]

        try:
            raw = self._llm.chat(messages, max_tokens=1200, temperature=0.0, operation="verify")
        except Exception as exc:
            logger.warning(f"Vérification échouée : {exc}")
            return response, False

        raw = (raw or "").strip()
        if raw.startswith("VERIFIED"):
            text = raw[len("VERIFIED"):].lstrip("\n").strip()
            return (text or response), False
        elif raw.startswith("CORRECTED"):
            text = raw[len("CORRECTED"):].lstrip("\n").strip()
            return (text or response), True
        else:
            logger.warning(f"Vérification : format inattendu — {raw[:100]}")
            return response, False

    # ---- Détection d'intention et récupération ----

    # Chiffres romains courants (I→1 … XX→20) — normalisation pour l'embedding
    _ROMAN_RE = re.compile(
        r"\b(X{0,2}(?:IX|IV|V?I{0,3}))\b",
        re.IGNORECASE,
    )
    _ROMAN_MAP = {
        "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5,
        "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
        "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15,
        "xvi": 16, "xvii": 17, "xviii": 18, "xix": 19, "xx": 20,
    }

    @classmethod
    def _normalize_query(cls, query: str) -> str:
        """Remplace les chiffres romains isolés par leur équivalent arabe.
        Ex : 'Artemis II' → 'Artemis 2', 'Apollo XI' → 'Apollo 11'.
        Les chiffres romains d'une seule lettre (I, V, X) sont ignorés (trop ambigus)."""
        def _replace(m: re.Match) -> str:
            token = m.group(1).lower()
            # Ignorer les tokens d'un seul caractère : "I", "V", "X" sont trop ambigus
            if len(token) == 1:
                return m.group(1)
            if token in cls._ROMAN_MAP:
                return str(cls._ROMAN_MAP[token])
            return m.group(1)

        normalized = cls._ROMAN_RE.sub(_replace, query)
        return normalized

    @staticmethod
    def _is_entity_target(candidate: str) -> bool:
        """Retourne True si le segment capturé ressemble à une vraie entité.

        Évite les faux positifs du type "sur la contribution de ... qui a permis ...",
        qui sont des formulations d'étude multi-concepts et non une entité NER."""
        text = candidate.strip().strip('"\'«»')
        if not text:
            return False

        words = [w for w in re.split(r"\s+", text) if w]
        if len(words) > 6:
            return False

        lowered = text.lower()
        blocked_fragments = {
            " qui ", " pour ", " avec ", " afin ", " parce ", " permis ",
            " retour ", " contribution ", " apprentissages ", " relation ",
            " impact ", " différence ", " comparaison ",
        }
        if any(fragment in f" {lowered} " for fragment in blocked_fragments):
            return False

        return True

    def _retrieve(self, query: str) -> tuple[list[dict], str]:
        query = self._normalize_query(query)
        # 1. Tags explicites
        tags = _TAG_PATTERN.findall(query)
        if tags:
            return self._chroma.search_by_tags(tags, top_k=settings.search_top_k), "tags"

        # 2. Relation entre deux entités — recherche parallèle sur chaque entité
        relation_match = _RELATION_PATTERN.search(query)
        if relation_match:
            entity_a = relation_match.group(1).strip().strip('"\'«»')
            entity_b = relation_match.group(2).strip().strip('"\'«»')
            logger.info(f"RAG intent=relation entités: {entity_a!r} ↔ {entity_b!r}")
            chunks_a = self._chroma.search(entity_a, top_k=settings.search_top_k)
            chunks_b = self._chroma.search(entity_b, top_k=settings.search_top_k)
            # Bonus : recherche sur les deux entités ensemble pour les notes-ponts
            chunks_ab = self._chroma.search(f"{entity_a} {entity_b}", top_k=settings.search_top_k)
            # Fusion dédupliquée : ponts d'abord, puis A, puis B
            seen_ids: set[str] = set()
            merged: list[dict] = []
            for c in chunks_ab + chunks_a + chunks_b:
                if c["chunk_id"] not in seen_ids:
                    seen_ids.add(c["chunk_id"])
                    merged.append(c)
            return merged[: settings.search_top_k * 2], "relation"

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
            if self._is_entity_target(entity):
                chunks = self._chroma.search_by_entity(entity, top_k=settings.search_top_k)
                return self._filter_supported_chunks(query, chunks, "entity"), "entity"

        proper_nouns = self._extract_proper_nouns(query)

        # 4. Synthèse — même top_k que la recherche générale, le budget de chars fait le tri
        if _SYNTHESIS_PATTERNS.search(query):
            if proper_nouns:
                chunks = self._retrieve_hybrid_chunks(query, proper_nouns)
                return chunks[: settings.search_top_k], "synthesis"
            chunks = self._chroma.search(query, top_k=settings.search_top_k)
            return chunks, "synthesis"

        # 5. Détection de noms propres → recherche hybride (sémantique + keyword + titre)
        if proper_nouns:
            chunks = self._retrieve_hybrid_chunks(query, proper_nouns)
            return chunks[: settings.search_top_k], "hybrid"

        # 6. Recherche générale
        chunks = self._chroma.search(query, top_k=settings.search_top_k)
        # Fallback : si les scores sont tous faibles, élargir avec keyword sur les
        # termes significatifs de la requête (mots ≥ 4 lettres, hors stop-words)
        _STOP_FR = {"quelles", "quelle", "quel", "quels", "comment", "pourquoi",
                    "mesures", "prend", "prend-elle", "assurer", "pour", "dans",
                    "avec", "sont", "cette", "avoir", "faire", "être", "les", "des",
                    "une", "que", "qui", "sur", "par", "elle", "ils"}
        if all(c["score"] < 0.55 for c in chunks):
            kw_extra: list[dict] = []
            for word in query.split():
                w = re.sub(r"[^\w]", "", word).lower()
                if len(w) >= 4 and w not in _STOP_FR:
                    kw_extra.extend(self._chroma.search_by_keyword(w, top_k=3))
            if kw_extra:
                seen_ids2: set[str] = set()
                merged2: list[dict] = []
                for c in kw_extra + chunks:
                    if c["chunk_id"] not in seen_ids2:
                        seen_ids2.add(c["chunk_id"])
                        merged2.append(c)
                logger.info(f"RAG fallback keyword: {len(kw_extra)} chunks supplémentaires")
                filtered = self._filter_supported_chunks(
                    query,
                    merged2[: settings.search_top_k],
                    "general_kw_fallback",
                )
                return filtered, "general_kw_fallback"
        return self._filter_supported_chunks(query, chunks, "general"), "general"

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
    def _normalize_match_text(text: str) -> str:
        normalized = unicodedata.normalize("NFD", text or "")
        stripped = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
        return stripped.lower()

    @staticmethod
    def _expand_retrieval_terms(query: str, proper_nouns: list[str]) -> list[str]:
        """Élargit les termes de retrieval à partir des noms propres capturés.

        Exemples :
        - "Garry Tans Claude" -> "Garry Tan", "Claude", "Claude Code"
        - "Artemis II" -> "Artemis II", "Artemis", "mission artemis ii"
        """
        expanded: list[str] = []
        query_low = query.lower()
        generic_singletons = {"Terre", "Lune"}

        def _add(term: str) -> None:
            term = term.strip().strip('"\'«»')
            if len(term) < 3:
                return
            if term not in expanded:
                expanded.append(term)

        for phrase in proper_nouns:
            words = [w for w in phrase.split() if w]
            if not words:
                continue

            _add(phrase)

            singular_words = [
                w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith(("is", "ss", "us")) else w
                for w in words
            ]
            singular_phrase = " ".join(singular_words)
            _add(singular_phrase)

            for idx, word in enumerate(words):
                if word not in generic_singletons:
                    _add(word)
                if idx + 1 < len(words):
                    _add(f"{word} {words[idx + 1]}")

            if any(w.lower() == "claude" for w in words) and "code" in query_low:
                _add("Claude Code")

            if any(w.lower().startswith("garry") for w in words):
                _add("Garry Tan")

            if any(w.lower() == "artemis" for w in words):
                _add("mission artemis ii")

        return expanded

    @staticmethod
    def _select_focus_terms(retrieval_terms: list[str]) -> list[str]:
        """Retient quelques axes distincts pour équilibrer le contexte multi-thèmes.

        On privilégie des termes assez spécifiques, en évitant d'empiler plusieurs
        variantes quasi identiques d'un même axe."""
        ignored_tokens = {"mission", "terre", "lune", "code"}
        selected: list[str] = []
        selected_tokens: list[set[str]] = []

        ranked_terms = sorted(
            retrieval_terms,
            key=lambda term: (-len(term.split()), -len(term)),
        )

        for term in ranked_terms:
            tokens = {
                token.lower()
                for token in re.findall(r"\w+", term)
                if len(token) >= 4 and token.lower() not in ignored_tokens
            }
            if not tokens:
                continue
            if any(tokens & existing for existing in selected_tokens):
                continue
            selected.append(term)
            selected_tokens.append(tokens)
            if len(selected) >= 3:
                break

        return selected

    @staticmethod
    def _normalize_theme_label(label: str) -> str:
        words = [w for w in re.split(r"\s+", label.strip()) if w]
        normalized_words: list[str] = []
        for word in words:
            cleaned = re.sub(r"[^\w-]", "", word)
            if not cleaned:
                continue
            lower = cleaned.lower()
            if lower == "tans":
                cleaned = "Tan"
            elif lower == "ii":
                cleaned = "II"
            elif lower == "iii":
                cleaned = "III"
            elif lower == "iv":
                cleaned = "IV"
            elif lower == "claude":
                cleaned = "Claude"
            elif lower == "garry":
                cleaned = "Garry"
            elif lower == "artemis":
                cleaned = "Artemis"
            elif lower not in {"de", "du", "des", "la", "le", "les", "et", "pour"}:
                cleaned = cleaned[0].upper() + cleaned[1:]
            normalized_words.append(cleaned)
        return " ".join(normalized_words)

    @classmethod
    def _extract_theme_labels(cls, query: str) -> list[str]:
        relation_match = _RELATION_PATTERN.search(query)
        if relation_match:
            left = cls._normalize_theme_label(relation_match.group(1))
            right = cls._normalize_theme_label(relation_match.group(2))
            labels = [label for label in (left, right) if label]
            return labels

        query_low = query.lower()
        labels: list[str] = []
        proper_nouns = cls._extract_proper_nouns(query)
        focus_terms = cls._select_focus_terms(cls._expand_retrieval_terms(query, proper_nouns))

        if "garry" in query_low and "claude" in query_low:
            labels.append("Garry Tan et Claude Code")

        if "artemis ii" in query_low or "mission artemis ii" in query_low:
            labels.append("Artemis II")
        elif "artemis" in query_low:
            labels.append("Artemis")

        for term in focus_terms:
            normalized = cls._normalize_theme_label(term)
            if not normalized:
                continue
            if normalized.lower() in {"terre", "lune", "mission artemis ii"}:
                if normalized.lower() == "mission artemis ii":
                    normalized = "Artemis II"
                else:
                    continue
            if normalized not in labels:
                labels.append(normalized)
            if len(labels) >= 2:
                break

        return labels

    @classmethod
    def _derive_study_themes(cls, query: str) -> tuple[str, str]:
        labels = cls._extract_theme_labels(query)

        while len(labels) < 2:
            labels.append("le second thème" if labels else "le premier thème")

        return labels[0], labels[1]

    @classmethod
    def _derive_primary_theme(cls, query: str) -> str:
        candidate = cls._extract_single_subject_candidate(query)
        if candidate:
            normalized = cls._normalize_theme_label(candidate)
            if normalized:
                return normalized

        labels = cls._extract_theme_labels(query)
        if labels:
            return labels[0]

        proper_nouns = cls._extract_proper_nouns(query)
        if proper_nouns:
            return cls._normalize_theme_label(proper_nouns[0]) or "le sujet demandé"

        return "le sujet demandé"

    @classmethod
    def _should_use_study_prompt(cls, intent: str, query: str) -> bool:
        if intent in {"synthesis", "relation"}:
            return True
        if intent != "hybrid":
            return False
        return len(cls._extract_theme_labels(query)) >= 2

    @classmethod
    def _extract_single_subject_candidate(cls, query: str) -> str | None:
        entity_match = _ENTITY_PATTERNS.search(query)
        if entity_match:
            candidate = entity_match.group(1).strip().strip('"\'«»')
            if (
                cls._is_entity_target(candidate)
                and not cls._is_generic_subject_reference(candidate)
                and not re.search(r"\bet\b|,", candidate, flags=re.IGNORECASE)
            ):
                return candidate

        request_match = _SINGLE_SUBJECT_REQUEST_PATTERN.search(query)
        if request_match:
            candidate = request_match.group(1).strip().strip('"\'«»')
            if (
                candidate
                and not cls._is_generic_subject_reference(candidate)
                and not re.search(r"\bet\b|,", candidate, flags=re.IGNORECASE)
            ):
                return candidate

        return None

    @classmethod
    def _is_generic_subject_reference(cls, candidate: str) -> bool:
        normalized = cls._normalize_match_text(candidate)
        tokens = [
            token for token in re.findall(r"\w+", normalized)
            if token not in {"le", "la", "les", "de", "des", "du", "un", "une", "sur", "ses", "ces"}
        ]
        if not tokens:
            return True
        return all(token in _GENERIC_SUBJECT_TOKENS for token in tokens)

    @classmethod
    def _looks_like_follow_up_query(cls, query: str) -> bool:
        text = query.strip()
        if not text:
            return False
        if cls._extract_proper_nouns(text) or cls._extract_single_subject_candidate(text):
            return False
        if _FOLLOW_UP_QUERY_PATTERN.search(text):
            return True
        return len(text.split()) <= 7

    @classmethod
    def _extract_subject_from_message(cls, content: str) -> str | None:
        candidate = cls._extract_single_subject_candidate(content)
        if candidate:
            normalized = cls._normalize_theme_label(candidate)
            if normalized:
                return normalized

        labels = cls._extract_theme_labels(content)
        if labels:
            return labels[0]

        proper_nouns = cls._extract_proper_nouns(content)
        if proper_nouns:
            normalized = cls._normalize_theme_label(proper_nouns[0])
            if normalized:
                return normalized

        return None

    @classmethod
    def _resolve_query_with_history(cls, query: str, history: list[dict[str, str]]) -> str:
        if not history or not cls._looks_like_follow_up_query(query):
            return query

        subject: str | None = None
        for message in reversed(history):
            role = message.get("role")
            if role not in {"user", "assistant"}:
                continue
            content = (message.get("content") or "").strip()
            if not content:
                continue
            subject = cls._extract_subject_from_message(content)
            if subject:
                break

        if not subject:
            return query

        resolved = f"{query.strip()} concernant {subject}"
        logger.info(f"RAG follow-up resolved: {query!r} -> {resolved!r}")
        return resolved

    @classmethod
    def _should_use_single_subject_prompt(cls, intent: str, query: str) -> bool:
        if cls._should_use_study_prompt(intent, query):
            return False
        if intent in {"hybrid", "entity"}:
            return True
        if intent in {"general", "general_kw_fallback"}:
            return cls._extract_single_subject_candidate(query) is not None
        return False

    @staticmethod
    def _chunk_match_count(chunk: dict, focus_token_sets: list[tuple[str, set[str]]]) -> int:
        haystack = " ".join(
            filter(
                None,
                [
                    (chunk.get("metadata") or {}).get("note_title", ""),
                    chunk.get("text", "")[:400],
                ],
            )
        )
        haystack = RAGPipeline._normalize_match_text(haystack)
        haystack_tokens = set(re.findall(r"\w+", haystack))
        return sum(1 for _, tokens in focus_token_sets if haystack_tokens & tokens)

    @staticmethod
    def _chunk_term_rank(chunk: dict, tokens: set[str]) -> tuple[int, int, float]:
        metadata = chunk.get("metadata") or {}
        title = RAGPipeline._normalize_match_text(metadata.get("note_title") or "")
        entity_blob = " ".join(
            filter(
                None,
                [
                    metadata.get("ner_persons", ""),
                    metadata.get("ner_orgs", ""),
                    metadata.get("ner_locations", ""),
                    metadata.get("ner_misc", ""),
                ],
            )
        )
        entity_blob = RAGPipeline._normalize_match_text(entity_blob)
        text = RAGPipeline._normalize_match_text((chunk.get("text") or "")[:400])
        title_hits = sum(1 for token in tokens if token in title)
        entity_hits = sum(1 for token in tokens if token in entity_blob)
        text_hits = sum(1 for token in tokens if token in text)
        score = float(chunk.get("score") or 0.0)
        return (title_hits + entity_hits, text_hits, score)

    def _filter_supported_chunks(self, query: str, chunks: list[dict], intent: str) -> list[dict]:
        if not chunks:
            return chunks
        if intent not in {"general", "general_kw_fallback", "entity"}:
            return chunks
        if not self._should_use_single_subject_prompt(intent, query):
            return chunks

        focus_tokens = self._note_focus_tokens(query)
        if not focus_tokens:
            return chunks

        filtered: list[dict] = []
        for chunk in chunks:
            title_hits, text_hits, score = self._chunk_term_rank(chunk, focus_tokens)
            if title_hits > 0 or text_hits >= 2 or (text_hits >= 1 and score >= 0.72):
                filtered.append(chunk)

        if filtered:
            return filtered

        logger.info("RAG lexical filter: aucun chunk fiable, contexte vidé")
        return []

    @staticmethod
    def _chunk_information_rank(chunk: dict) -> tuple[int, int, float]:
        text = (chunk.get("text") or "").strip()
        compact = re.sub(r"\s+", " ", text)
        is_image_only = compact.startswith("![") or compact.startswith("<img")
        alpha_chars = len(re.findall(r"[A-Za-zÀ-ÿ0-9]", compact))
        score = float(chunk.get("score") or 0.0)
        return (0 if is_image_only else 1, alpha_chars, score)

    def _prefer_informative_chunks(self, chunks: list[dict]) -> list[dict]:
        """Déduplique par note en conservant le chunk le plus informatif."""
        best_by_note: dict[str, dict] = {}
        order: list[str] = []
        for chunk in chunks:
            note_key = self._chunk_note_key(chunk)
            if note_key not in best_by_note:
                best_by_note[note_key] = chunk
                order.append(note_key)
                continue
            current = best_by_note[note_key]
            if self._chunk_information_rank(chunk) > self._chunk_information_rank(current):
                best_by_note[note_key] = chunk
        return [best_by_note[note_key] for note_key in order]

    @staticmethod
    def _chunk_note_key(chunk: dict) -> str:
        metadata = chunk.get("metadata") or {}
        return (
            metadata.get("file_path")
            or metadata.get("note_title")
            or chunk.get("chunk_id")
            or ""
        )

    def _retrieve_hybrid_chunks(self, query: str, proper_nouns: list[str]) -> list[dict]:
        """Recherche hybride équilibrée : titre exact + keyword + sémantique globale."""
        semantic = self._prefer_informative_chunks(
            self._chroma.search(query, top_k=settings.search_top_k)
        )
        per_term_chunks: list[list[dict]] = []
        retrieval_terms = self._expand_retrieval_terms(query, proper_nouns)
        focus_terms = self._select_focus_terms(retrieval_terms)
        logger.info(f"RAG hybrid termes={retrieval_terms}")
        for noun in retrieval_terms:
            title_hits = self._chroma.search_by_note_title(noun, top_k=3)
            keyword_hits = self._chroma.search_by_keyword(noun, top_k=3)
            per_term_chunks.append(self._prefer_informative_chunks(title_hits + keyword_hits))

        seen_ids: set[str] = set()
        seen_notes: set[str] = set()
        merged: list[dict] = []

        focus_buckets: list[list[dict]] = []
        bridge_chunks: list[dict] = []
        if focus_terms:
            symbolic_hits: list[dict] = []
            symbolic_ids: set[str] = set()
            for bucket in per_term_chunks:
                for chunk in bucket:
                    if chunk["chunk_id"] not in symbolic_ids:
                        symbolic_ids.add(chunk["chunk_id"])
                        symbolic_hits.append(chunk)

            focus_token_sets: list[tuple[str, set[str]]] = []
            for term in focus_terms:
                tokens = {
                    token.lower()
                    for token in re.findall(r"\w+", term)
                    if len(token) >= 4 and token.lower() not in {"mission", "terre", "lune", "code"}
                }
                if tokens:
                    focus_token_sets.append((term, tokens))

            focus_bucket_map: dict[str, list[dict]] = {term: [] for term, _ in focus_token_sets}
            bridge_ids: set[str] = set()
            for chunk in symbolic_hits + semantic:
                match_count = self._chunk_match_count(chunk, focus_token_sets)
                matched_terms = [
                    term for term, tokens in focus_token_sets
                    if self._chunk_match_count(chunk, [(term, tokens)])
                ]
                if len(matched_terms) >= 2:
                    if chunk["chunk_id"] not in bridge_ids:
                        bridge_ids.add(chunk["chunk_id"])
                        bridge_chunks.append(chunk)
                elif len(matched_terms) == 1:
                    bucket = focus_bucket_map[matched_terms[0]]
                    if chunk["chunk_id"] not in {c["chunk_id"] for c in bucket}:
                        bucket.append(chunk)

            for term, tokens in focus_token_sets:
                focus_bucket_map[term].sort(
                    key=lambda chunk: self._chunk_term_rank(chunk, tokens),
                    reverse=True,
                )
            focus_buckets = [bucket for bucket in focus_bucket_map.values() if bucket]

        for chunk in bridge_chunks:
            note_key = self._chunk_note_key(chunk)
            if chunk["chunk_id"] not in seen_ids and note_key not in seen_notes:
                seen_ids.add(chunk["chunk_id"])
                seen_notes.add(note_key)
                merged.append(chunk)

        max_focus_depth = max((len(bucket) for bucket in focus_buckets), default=0)
        for depth in range(max_focus_depth):
            for bucket in focus_buckets:
                if depth < len(bucket):
                    chunk = bucket[depth]
                    note_key = self._chunk_note_key(chunk)
                    if chunk["chunk_id"] not in seen_ids and note_key not in seen_notes:
                        seen_ids.add(chunk["chunk_id"])
                        seen_notes.add(note_key)
                        merged.append(chunk)

        max_bucket_depth = max((len(bucket) for bucket in per_term_chunks), default=0)
        for depth in range(max_bucket_depth):
            for bucket in per_term_chunks:
                if depth < len(bucket):
                    c = bucket[depth]
                    if focus_terms and self._chunk_match_count(c, focus_token_sets) == 0:
                        continue
                    note_key = self._chunk_note_key(c)
                    if c["chunk_id"] not in seen_ids and note_key not in seen_notes:
                        seen_ids.add(c["chunk_id"])
                        seen_notes.add(note_key)
                        merged.append(c)
        for c in semantic:
            if focus_terms and self._chunk_match_count(c, focus_token_sets) == 0:
                continue
            note_key = self._chunk_note_key(c)
            if c["chunk_id"] not in seen_ids and note_key not in seen_notes:
                seen_ids.add(c["chunk_id"])
                seen_notes.add(note_key)
                merged.append(c)

        chunks = merged[: settings.search_top_k * 2]
        has_symbolic_hits = any(per_term_chunks)
        if not has_symbolic_hits and all(c["score"] < 0.55 for c in chunks):
            chunks = self._chroma.search(query, top_k=settings.search_top_k * 2)
        return chunks

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

    @staticmethod
    def _context_budgets() -> list[int]:
        """Retourne les budgets de chars à tenter : 100%, 50%, 25%, 12%."""
        base = settings.max_context_chars
        return [base, base // 2, base // 4, base // 8]

    @classmethod
    def _should_focus_dominant_note(cls, intent: str, query: str) -> bool:
        return cls._should_use_single_subject_prompt(intent, query)

    @classmethod
    def _note_focus_tokens(cls, query: str) -> set[str]:
        proper_nouns = cls._extract_proper_nouns(query)
        retrieval_terms = cls._expand_retrieval_terms(query, proper_nouns)
        if not retrieval_terms:
            candidate = cls._extract_single_subject_candidate(query)
            primary_theme = cls._derive_primary_theme(query)
            retrieval_terms = [term for term in (candidate, primary_theme, query) if term]

        ignored_tokens = {
            "comment", "pourquoi", "parle", "moi", "sujet", "notes", "avec",
            "dans", "pour", "quoi", "quel", "quelle", "quels", "quelles",
            "mission", "projet", "code", "cela", "cette", "sur", "des", "les",
        }

        return {
            token.lower()
            for term in retrieval_terms
            for token in re.findall(r"\w+", term)
            if len(token) >= 4 and token.lower() not in ignored_tokens
        }

    @classmethod
    def _note_rank(
        cls,
        note_chunks: list[dict],
        focus_tokens: set[str],
    ) -> tuple[int, int, float, int]:
        title_or_entity_hits = 0
        text_hits = 0
        best_score = 0.0
        alpha_chars = 0

        for chunk in note_chunks:
            title_hits, chunk_text_hits, score = cls._chunk_term_rank(chunk, focus_tokens)
            title_or_entity_hits = max(title_or_entity_hits, title_hits)
            text_hits = max(text_hits, chunk_text_hits)
            best_score = max(best_score, score)
            alpha_chars += cls._chunk_information_rank(chunk)[1]

        return (title_or_entity_hits, text_hits, best_score, alpha_chars)

    def _select_dominant_note_key(self, query: str, chunks: list[dict]) -> str | None:
        if not chunks:
            return None

        focus_tokens = self._note_focus_tokens(query)
        grouped: dict[str, list[dict]] = {}
        for chunk in chunks:
            note_key = self._chunk_note_key(chunk)
            if not note_key:
                continue
            grouped.setdefault(note_key, []).append(chunk)

        if not grouped:
            return None

        ranked = sorted(
            grouped.items(),
            key=lambda item: self._note_rank(item[1], focus_tokens),
            reverse=True,
        )
        note_key, note_chunks = ranked[0]
        title_hits, text_hits, best_score, _ = self._note_rank(note_chunks, focus_tokens)
        if focus_tokens and title_hits == 0 and text_hits == 0:
            logger.info("RAG dominant note ignorée: aucun recouvrement lexical fiable")
            return None
        if focus_tokens and title_hits == 0 and text_hits <= 1 and best_score < 0.55:
            logger.info("RAG dominant note ignorée: signal trop faible pour une focalisation")
            return None
        note_title = (note_chunks[0].get("metadata") or {}).get("note_title") or note_key
        logger.info(f"RAG dominant note: {note_title} ({note_key})")
        return note_key

    def _fetch_note_context_chunks(self, query: str, note_key: str, limit: int) -> list[dict]:
        if not note_key or limit <= 0:
            return []

        field = "file_path" if "/" in note_key or note_key.endswith(".md") else "note_title"
        try:
            chunks = self._chroma.search(
                query,
                top_k=limit,
                where={field: note_key},
            )
        except Exception as exc:
            logger.warning(f"RAG dominant note fetch échoué pour {note_key}: {exc}")
            return []

        return sorted(
            chunks,
            key=lambda chunk: (
                self._chunk_information_rank(chunk),
                float(chunk.get("score") or 0.0),
            ),
            reverse=True,
        )[:limit]

    def _prepare_context_chunks(self, chunks: list[dict], query: str, intent: str) -> list[dict]:
        if not self._should_focus_dominant_note(intent, query):
            return chunks

        dominant_note_key = self._select_dominant_note_key(query, chunks)
        if not dominant_note_key:
            return chunks

        dominant_limit = min(settings.max_context_chunks - 1, max(2, settings.max_context_chunks // 2 + 1))
        dominant_chunks = self._fetch_note_context_chunks(query, dominant_note_key, dominant_limit)
        if not dominant_chunks:
            return chunks

        supporting_chunks = self._prefer_informative_chunks(
            [chunk for chunk in chunks if self._chunk_note_key(chunk) != dominant_note_key]
        )
        remaining = max(0, settings.max_context_chunks - len(dominant_chunks))
        prepared = dominant_chunks + supporting_chunks[:remaining]
        return prepared[: settings.max_context_chunks]

    def _mark_primary_sources(self, chunks: list[dict], query: str, intent: str) -> list[dict]:
        if not chunks:
            return chunks

        dominant_note_key = self._select_dominant_note_key(query, chunks)
        marked: list[dict] = []
        for chunk in chunks:
            clone = dict(chunk)
            metadata = dict(chunk.get("metadata") or {})
            metadata["is_primary"] = bool(
                dominant_note_key and self._chunk_note_key(chunk) == dominant_note_key
            )
            clone["metadata"] = metadata
            marked.append(clone)
        return marked

    @staticmethod
    def _is_context_error(exc: BadRequestError) -> bool:
        msg = str(exc).lower()
        return "context" in msg and any(w in msg for w in ("size", "length", "exceeded", "too long"))

    def _build_context(
        self,
        chunks: list[dict],
        query: str,
        intent: str,
        char_budget: int | None = None,
    ) -> str:
        if not chunks:
            return "Aucune note trouvée dans le coffre pour cette requête."

        chunks = self._prepare_context_chunks(chunks, query, intent)

        # Déduplique par note, limite au nombre max de chunks
        seen_notes: dict[str, list[dict]] = {}
        for c in chunks[: settings.max_context_chunks]:
            fp = c["metadata"].get("file_path", "")
            seen_notes.setdefault(fp, []).append(c)

        # Enrichissement : ajouter les notes liées (wikilinks) des notes trouvées
        # Les wikilinks sont des titres — construire un index titre→file_path
        title_to_fp: dict[str, str] = {}
        for fp, note_chunks in seen_notes.items():
            title = note_chunks[0]["metadata"].get("note_title", "")
            if title:
                title_to_fp[title.lower()] = fp
                # préfixe 30 chars comme fallback
                title_to_fp[title.lower()[:30]] = fp

        linked_fps: set[str] = set()
        for fp, note_chunks in seen_notes.items():
            wikilinks_raw = note_chunks[0]["metadata"].get("wikilinks", "")
            for wl in (wikilinks_raw or "").split(","):
                wl = wl.strip()
                if not wl:
                    continue
                wl_lower = wl.lower()
                resolved = title_to_fp.get(wl_lower) or title_to_fp.get(wl_lower[:30])
                if resolved and resolved not in seen_notes:
                    linked_fps.add(resolved)
                elif not resolved:
                    # Stocker le titre brut pour une recherche ChromaDB par note_title
                    linked_fps.add(f"__title__:{wl}")

        if linked_fps:
            # Chercher les chunks des notes liées (2 chunks max par note liée)
            linked_budget = max(1, settings.max_context_chunks // 2)
            for linked_fp in list(linked_fps)[:linked_budget]:
                try:
                    if linked_fp.startswith("__title__:"):
                        # Résolution par titre via ChromaDB
                        title_query = linked_fp[len("__title__:"):]
                        raw = self._chroma._collection.get(
                            where={"note_title": title_query},
                            limit=2,
                            include=["documents", "metadatas"],
                        )
                    else:
                        raw = self._chroma._collection.get(
                            where={"file_path": linked_fp},
                            limit=2,
                            include=["documents", "metadatas"],
                        )
                    for doc, meta in zip(
                        raw.get("documents") or [],
                        raw.get("metadatas") or [],
                    ):
                        fp2 = meta.get("file_path", linked_fp)
                        if fp2 not in seen_notes:
                            seen_notes[fp2] = [{
                                "chunk_id": f"linked_{fp2}",
                                "text": doc,
                                "metadata": meta,
                                "score": 0.0,
                            }]
                except Exception:
                    pass

        parts: list[str] = []
        budget = char_budget if char_budget is not None else settings.max_context_chars

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
        intent: str = "general",
        force_study_answer: bool = False,
        resolved_query: str | None = None,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [{"role": "system", "content": _SYSTEM_PROMPT}]

        # Historique : limité aux 4 derniers échanges (8 messages) pour ménager le contexte
        messages.extend(history[-8:])

        intent_hint = ""
        use_study_prompt = self._should_use_study_prompt(intent, query)
        if use_study_prompt:
            theme_a, theme_b = self._derive_study_themes(query)
            intent_hint = (
                "\n\n**Consigne de travail :**\n"
                "- La question demande une synthèse d'étude à partir de plusieurs notes liées.\n"
                "- Si les extraits contiennent des éléments substantiels sur les thèmes demandés, produis une synthèse utile depuis le coffre.\n"
                "- Tu peux rapprocher prudemment plusieurs notes pour dégager des apprentissages, à condition de signaler ce qui est explicite et ce qui relève d'une interprétation prudente.\n"
                "- N'utilise la réponse exacte \"Cette information n'est pas dans ton coffre.\" que s'il n'y a vraiment aucun matériau substantiel pour construire une synthèse partielle.\n"
                "- La réponse doit être structurée avec EXACTEMENT ces trois intertitres Markdown de niveau 3 :\n"
                f"  ### Ce que disent mes notes sur {theme_a}\n"
                f"  ### Ce que disent mes notes sur {theme_b}\n"
                "  ### Ce que je peux conclure\n"
                "- Sous chaque intertitre, fais des phrases courtes et factuelles, en citant les titres de notes utiles entre [crochets].\n"
                "- Si le lien direct n'est pas explicite, remplis quand même les deux premières sections avec les apprentissages disponibles, puis explicite la limite dans la troisième.\n"
            )
        elif self._should_use_single_subject_prompt(intent, query):
            primary_theme = self._derive_primary_theme(query)
            intent_hint = (
                "\n\n**Consigne de travail :**\n"
                f"- La question porte sur un seul sujet principal : {primary_theme}.\n"
                f"- Réponds d'abord et surtout sur {primary_theme}.\n"
                "- Donne un aperçu descriptif utile à partir des notes: nature du sujet, rôle, dates, étapes ou faits saillants, uniquement si ces éléments figurent dans les extraits.\n"
                "- La réponse doit être structurée avec EXACTEMENT ces deux intertitres Markdown de niveau 3 :\n"
                f"  ### Aperçu de {primary_theme}\n"
                "  ### Détails utiles\n"
                "- Sous chaque intertitre, écris un ou deux courts paragraphes clairs.\n"
                "- N'élargis pas la réponse à des thèmes voisins, à des suites possibles, ou à des conséquences futures, sauf si la question le demande explicitement.\n"
                "- Si les notes mentionnent des sujets proches, tu peux les citer brièvement uniquement pour situer le sujet demandé, sans en faire un second axe de réponse.\n"
                "- N'invente aucun prolongement non écrit dans les extraits.\n"
                "- N'utilise la phrase exacte \"Cette information n'est pas dans ton coffre.\" que s'il n'y a vraiment aucune matière sur le sujet demandé.\n"
                "- Cite les titres de notes utiles entre [crochets].\n"
            )
        if force_study_answer and use_study_prompt:
            intent_hint += (
                "- Deuxième tentative obligatoire : les extraits ci-dessus contiennent déjà assez de matière pour répondre partiellement.\n"
                "- Tu dois produire une synthèse depuis le coffre, même si le lien causal complet n'est pas formulé mot pour mot.\n"
                "- Mentionne les limites ou incertitudes, mais ne réponds pas par le hard sentinel.\n"
                "- Si le lien direct n'est pas prouvé, fournis quand même les apprentissages disponibles sur chaque thème avant d'énoncer cette limite.\n"
                "- Conserve impérativement les trois intertitres demandés.\n"
            )

        question_block = f"**Question :** {query}"
        if resolved_query and resolved_query != query:
            question_block += f"\n**Question résolue dans le fil :** {resolved_query}"

        user_content = (
            f"**Extraits du coffre Obsidian :**\n\n{context}{intent_hint}\n\n"
            f"---\n{question_block}"
        )
        messages.append({"role": "user", "content": user_content})
        return messages
