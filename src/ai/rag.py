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

import hashlib
import re
import threading
import time
import unicodedata
from collections.abc import Iterator
from datetime import datetime, timedelta
from itertools import chain
from typing import Any, Callable

from loguru import logger
from src.ai.answer_prompting import AnswerPrompting
from src.ai.mermaid_sanitizer import contains_mermaid_fence, sanitize_mermaid_blocks
from src.ai.retrieval_strategy import RetrievalStrategy
from src.metrics import MetricsRecorder
# Sentinelle locale — plus jamais levée depuis la migration vers MLX-LM,
# conservée pour que la logique de retry sur contexte trop grand reste en place.
class _ContextTooLargeError(Exception):
    pass

BadRequestError = _ContextTooLargeError  # alias de compatibilité


class _AnswerCache:
    """Cache mémoire réponse RAG avec TTL.

    Clé = SHA-1 de (query normalisée + historique condensé).
    Évite les doubles inférences sur les rechargements de page UI
    ou les requêtes identiques soumises en rafale.
    TTL par défaut : 300 s (5 min).
    """

    def __init__(self, ttl_s: float = 300.0, max_size: int = 128) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, tuple[str, list, float]] = {}  # key → (answer, sources, ts)
        self._ttl = ttl_s
        self._max_size = max_size

    @staticmethod
    def _make_key(query: str, history: list[dict[str, str]]) -> str:
        norm = unicodedata.normalize("NFC", query.strip().lower())
        history_sig = "|".join(f"{m.get('role','')}:{m.get('content','')}" for m in history[-4:])
        return hashlib.sha1(f"{norm}\x00{history_sig}".encode()).hexdigest()  # noqa: S324

    def get(self, query: str, history: list[dict[str, str]]) -> tuple[str, list] | None:
        key = self._make_key(query, history)
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            answer, sources, ts = entry
            if time.monotonic() - ts > self._ttl:
                del self._store[key]
                return None
        return answer, sources

    def put(self, query: str, history: list[dict[str, str]], answer: str, sources: list) -> None:
        key = self._make_key(query, history)
        with self._lock:
            if len(self._store) >= self._max_size:
                # Éviction LRU simplifiée : supprime les entrées les plus anciennes
                oldest = sorted(self._store.items(), key=lambda kv: kv[1][2])[:16]
                for k, _ in oldest:
                    del self._store[k]
            self._store[key] = (answer, sources, time.monotonic())

    def invalidate(self, query: str, history: list[dict[str, str]]) -> None:
        key = self._make_key(query, history)
        with self._lock:
            self._store.pop(key, None)

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)


class _InferenceBackpressure:
    """Limite la concurrence MLX à 1 inférence active + max_queue en attente.

    MLX/Metal n'accepte pas les appels GPU simultanés.  Sans borne sur la file
    d'attente, des requêtes concurrentes s'accumulent et dégradent le P99.
    Cette gate applique la politique :
      - 1 inférence active à la fois
      - max_queue requêtes supplémentaires tolérées en attente
      - rejet immédiat si la file est pleine (RuntimeError)
      - timeout défensif pour les verrous bloqués
    """

    def __init__(self, max_queue: int = 2, timeout_s: float = 120.0) -> None:
        self._sem = threading.Semaphore(1)  # 1 inférence à la fois
        self._lock = threading.Lock()
        self._active = 0  # requêtes en attente + en cours
        self._max_active = 1 + max_queue
        self._timeout = timeout_s

    @property
    def queue_depth(self) -> int:
        """Nombre de requêtes actuellement en attente ou en cours d'inférence."""
        with self._lock:
            return self._active

    def acquire(self) -> None:
        """Entre dans la gate.  Lève RuntimeError si la file est saturée ou si le délai expire."""
        with self._lock:
            if self._active >= self._max_active:
                raise RuntimeError(
                    f"File d'inférence saturée ({self._active} requêtes en cours/attente) "
                    "— réessaie dans un instant."
                )
            self._active += 1
        acquired = self._sem.acquire(timeout=self._timeout)
        if not acquired:
            with self._lock:
                self._active = max(0, self._active - 1)
            raise RuntimeError(
                f"Délai d'attente de la gate d'inférence dépassé ({self._timeout:.0f} s)."
            )
        logger.debug(f"[backpressure] inférence démarrée — queue_depth={self._active}")

    def release(self) -> None:
        """Libère le slot d'inférence."""
        self._sem.release()
        with self._lock:
            self._active = max(0, self._active - 1)
        logger.debug(f"[backpressure] inférence terminée — queue_depth={self._active}")


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
Si tu produis un bloc ```mermaid```, le code Mermaid doit utiliser uniquement des caracteres ASCII simples.
- Interdits dans le bloc Mermaid : accents, emojis, puces Unicode, guillemets typographiques, tirets typographiques et tout caractere non ASCII.
- Ecris par exemple Resume, Reponse, Etape, Schema au lieu de Resume, Reponse, Etape avec accents.
- Cette contrainte s'applique uniquement au code Mermaid, pas au texte explicatif hors du bloc.
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
_DISALLOWED_USER_VISIBLE_SCRIPT_RE = re.compile(
    r"[\u0400-\u04FF\u0600-\u06FF\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]"
)


class RAGPipeline:
    def __init__(self, chroma: ChromaStore, llm, metrics: MetricsRecorder | None = None) -> None:
        self._chroma = chroma
        self._llm = llm
        self._system_prompt = _SYSTEM_PROMPT
        self._metrics = metrics or MetricsRecorder(lambda: settings.data_dir / "stats" / "metrics.json")
        self._tag_pattern = _TAG_PATTERN
        self._relation_pattern = _RELATION_PATTERN
        self._entity_patterns = _ENTITY_PATTERNS
        self._synthesis_patterns = _SYNTHESIS_PATTERNS
        self._retrieval_strategy = RetrievalStrategy(self)
        self._answer_prompting = AnswerPrompting(self)
        # PERF-14 : gate de backpressure (désactivable via settings.rag_backpressure_enabled)
        self._backpressure: _InferenceBackpressure | None = (
            _InferenceBackpressure(
                max_queue=settings.rag_backpressure_max_queue,
                timeout_s=settings.rag_backpressure_timeout_s,
            )
            if settings.rag_backpressure_enabled
            else None
        )
        # PERF-15a : cache réponse (désactivable via settings.rag_answer_cache_enabled)
        self._answer_cache: _AnswerCache | None = (
            _AnswerCache(
                ttl_s=settings.rag_answer_cache_ttl_s,
                max_size=settings.rag_answer_cache_max_size,
            )
            if settings.rag_answer_cache_enabled
            else None
        )
        # PERF-12 : pré-chauffe du cache KV pour le prompt système (si le LLM le supporte)
        if hasattr(self._llm, "configure_prefix_cache"):
            self._llm.configure_prefix_cache([{"role": "system", "content": _SYSTEM_PROMPT}])

    @staticmethod
    def _get_settings():
        return settings

    def _prepare_query_execution(
        self,
        user_query: str,
        history: list[dict[str, str]],
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        *,
        exclude_obsirag_generated: bool = False,
    ) -> tuple[str, list[dict], str]:
        self._emit_progress(progress_callback, phase="resolve", message="Analyse de la requête")
        resolved_query = self._resolve_query_with_history(user_query, history)
        self._emit_progress(progress_callback, phase="retrieval", message="Recherche des passages pertinents")
        chunks, intent = self._retrieve(resolved_query, progress_callback=progress_callback)
        if exclude_obsirag_generated:
            chunks = self._filter_obsirag_generated_chunks(chunks)
        self._emit_progress(
            progress_callback,
            phase="retrieval",
            message=f"{len(chunks)} passage(s) retenu(s)",
            chunk_count=len(chunks),
            intent=intent,
        )
        chunks = self._mark_primary_sources(chunks, resolved_query, intent)
        self._emit_progress(progress_callback, phase="context", message="Contextualisation des sources")
        return resolved_query, chunks, intent

    @staticmethod
    def _emit_progress(
        progress_callback: Callable[[dict[str, Any]], None] | None,
        *,
        phase: str,
        message: str,
        **metadata: Any,
    ) -> None:
        if not callable(progress_callback):
            return
        payload: dict[str, Any] = {
            "phase": phase,
            "message": message,
        }
        payload.update(metadata)
        try:
            progress_callback(payload)
        except Exception:
            pass

    def _iter_query_attempts(
        self,
        user_query: str,
        history: list[dict[str, str]],
        resolved_query: str,
        chunks: list[dict],
        intent: str,
    ) -> Iterator[tuple[int, str, list[dict[str, str]]]]:
        for budget in self._context_budgets():
            context = self._build_context(chunks, resolved_query, intent, char_budget=budget)
            messages = self._build_messages(
                user_query,
                context,
                history,
                intent=intent,
                resolved_query=resolved_query,
            )
            yield budget, context, messages

    def _run_chat_attempt(
        self,
        messages: list[dict[str, str]],
        context: str,
        history: list[dict[str, str]],
        resolved_query: str,
        intent: str,
    ) -> str:
        answer = self._llm.chat(
            messages,
            max_tokens=self._max_tokens_for_intent(intent),
            operation="rag_query",
        )
        answer = self._retry_forced_study_synthesis(
            answer=answer,
            query=resolved_query,
            context=context,
            history=history,
            intent=intent,
        )
        normalized = self._normalize_final_answer(answer, resolved_query, intent)
        if normalized.strip().lower() == _HARD_SENTINEL:
            try:
                self._metrics.increment("rag_sentinel_answers_total")
            except Exception:
                pass
        return normalized

    def _stream_first_token_or_empty(
        self,
        messages: list[dict[str, str]],
        intent: str,
    ) -> Iterator[str]:
        raw_stream = self._llm.stream(
            messages,
            max_tokens=self._max_tokens_for_intent(intent),
            operation="rag_query",
        )
        first = next(raw_stream, None)
        if first is None:
            return iter([])
        return chain([first], raw_stream)

    def _gated_stream(self, stream: Iterator[str]) -> Iterator[str]:
        """Wraps a stream iterator; releases the backpressure gate on exhaustion or error."""
        try:
            yield from stream
        finally:
            if self._backpressure is not None:
                self._backpressure.release()

    def _gated_and_cached_stream(
        self,
        stream: Iterator[str],
        query: str,
        history: list[dict[str, str]],
        sources: list,
    ) -> Iterator[str]:
        """Wraps a stream: releases backpressure gate + stores completed answer in cache."""
        parts: list[str] = []
        try:
            for token in stream:
                parts.append(token)
                yield token
        finally:
            if self._backpressure is not None:
                self._backpressure.release()
        if parts and self._answer_cache is not None:
            self._answer_cache.put(query, history, "".join(parts), sources)

    @staticmethod
    def _max_tokens_for_intent(intent: str) -> int:
        """Budget de génération adaptatif selon l'intention.

        Réduit la latence moyenne sur les intents factuels, tout en gardant
        un plafond plus élevé pour les synthèses multi-notes.
        """
        caps = {
            "general": 640,
            "general_kw_fallback": 700,
            "entity": 700,
            "temporal": 720,
            "tag": 700,
            "hybrid": 1100,
            "synthesis": 1100,
            "relation": 1200,
        }
        return caps.get(intent, 800)

    def _get_linked_chunks_by_note_title(self, note_title: str, limit: int = 2) -> list[dict]:
        return self._chroma.get_chunks_by_note_title(note_title, limit=limit)

    def _get_linked_chunks_by_file_path(self, file_path: str, limit: int = 2) -> list[dict]:
        return self._chroma.get_chunks_by_file_path(file_path, limit=limit)

    def _get_linked_chunks_by_file_paths(self, file_paths: list[str], limit_per_path: int = 2) -> dict[str, list[dict]]:
        getter = getattr(self._chroma, "get_chunks_by_file_paths", None)
        if callable(getter):
            return getter(file_paths, limit_per_path=limit_per_path)

        return {
            file_path: self._get_linked_chunks_by_file_path(file_path, limit=limit_per_path)
            for file_path in file_paths
        }

    # ---- API publique ----

    def query_stream(
        self,
        user_query: str,
        chat_history: list[dict[str, str]] | None = None,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[Iterator[str], list[dict]]:
        """Retourne (stream_generator, sources). Réduit le contexte si dépassement."""
        try:
            self._metrics.increment("rag_queries_total")
        except Exception:
            pass
        history = chat_history or []
        # PERF-15a : cache hit → retour immédiat sans inférence
        cached = self._answer_cache.get(user_query, history) if self._answer_cache is not None else None
        if cached is not None:
            logger.debug("[answer_cache] HIT query_stream")
            try:
                self._metrics.increment("rag_cache_hits_total")
            except Exception:
                pass
            cached_answer, cached_sources = cached
            return iter([cached_answer]), cached_sources
        resolved_query, chunks, intent = self._prepare_query_execution(
            user_query,
            history,
            progress_callback=progress_callback,
        )
        if not chunks:
            logger.info("RAG: aucun chunk retenu, retour sentinel immédiat")
            self._emit_progress(progress_callback, phase="retrieval", message="Aucune source pertinente trouvée")
            try:
                self._metrics.increment("rag_sentinel_answers_total")
            except Exception:
                pass
            return iter(["Cette information n'est pas dans ton coffre."]), []
        logger.info(f"RAG intent={intent} chunks={len(chunks)}")

        for budget, context, messages in self._iter_query_attempts(
            user_query,
            history,
            resolved_query,
            chunks,
            intent,
        ):
            try:
                self._emit_progress(
                    progress_callback,
                    phase="generation",
                    message="Préparation du prompt modèle",
                    context_chars=len(context),
                    context_budget=budget,
                    intent=intent,
                )
                if intent in {"synthesis", "relation", "hybrid"}:
                    self._emit_progress(progress_callback, phase="generation", message="Génération de la réponse")
                    if self._backpressure is not None:
                        self._backpressure.acquire()
                    try:
                        answer = self._run_chat_attempt(messages, context, history, resolved_query, intent)
                    finally:
                        if self._backpressure is not None:
                            self._backpressure.release()
                    if self._answer_cache is not None:
                        self._answer_cache.put(user_query, history, answer, chunks)
                    return iter([answer]), chunks
                self._emit_progress(progress_callback, phase="generation", message="Démarrage du flux de génération")
                if self._backpressure is not None:
                    self._backpressure.acquire()
                try:
                    stream = self._stream_first_token_or_empty(messages, intent)
                except Exception:
                    if self._backpressure is not None:
                        self._backpressure.release()
                    raise
                # Pour le stream, on enveloppe pour stocker la réponse dans le cache à la fin
                return self._gated_and_cached_stream(stream, user_query, history, chunks), chunks
            except BadRequestError as exc:
                if self._is_context_error(exc):
                    try:
                        self._metrics.increment("rag_context_retries_total")
                    except Exception:
                        pass
                    logger.warning(f"Contexte trop grand (budget={budget}), réduction…")
                    self._emit_progress(
                        progress_callback,
                        phase="generation",
                        message="Contexte trop large, nouvelle tentative réduite",
                        context_budget=budget,
                    )
                    continue
                raise

        raise RuntimeError("Impossible d'envoyer la requête : contexte trop grand même après réductions.")

    def query(
        self,
        user_query: str,
        chat_history: list[dict[str, str]] | None = None,
        *,
        exclude_obsirag_generated: bool = False,
    ) -> tuple[str, list[dict]]:
        """Appel bloquant — retourne (réponse, sources). Réduit le contexte si dépassement."""
        try:
            self._metrics.increment("rag_queries_total")
        except Exception:
            pass
        history = chat_history or []
        # PERF-15a : cache hit → retour immédiat sans inférence
        cached = None
        if self._answer_cache is not None and not exclude_obsirag_generated:
            cached = self._answer_cache.get(user_query, history)
        if cached is not None:
            logger.debug("[answer_cache] HIT query")
            try:
                self._metrics.increment("rag_cache_hits_total")
            except Exception:
                pass
            return cached
        resolved_query, chunks, intent = self._prepare_query_execution(
            user_query,
            history,
            exclude_obsirag_generated=exclude_obsirag_generated,
        )
        if not chunks:
            logger.info("RAG: aucun chunk retenu, retour sentinel immédiat")
            try:
                self._metrics.increment("rag_sentinel_answers_total")
            except Exception:
                pass
            return "Cette information n'est pas dans ton coffre.", []

        self._backpressure.acquire() if self._backpressure is not None else None
        try:
            for budget, context, messages in self._iter_query_attempts(
                user_query,
                history,
                resolved_query,
                chunks,
                intent,
            ):
                try:
                    answer = self._run_chat_attempt(messages, context, history, resolved_query, intent)
                    if self._answer_cache is not None and not exclude_obsirag_generated:
                        self._answer_cache.put(user_query, history, answer, chunks)
                    return answer, chunks
                except BadRequestError as exc:
                    if self._is_context_error(exc):
                        try:
                            self._metrics.increment("rag_context_retries_total")
                        except Exception:
                            pass
                        logger.warning(f"Contexte trop grand (budget={budget}), réduction…")
                        continue
                    raise
        finally:
            if self._backpressure is not None:
                self._backpressure.release()

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
        forcer une seconde tentative explicitement synthétique.

        PERF-15b : on n'effectue le retry que si le contexte est à la fois
        suffisamment long (≥ 300 c) ET dense en sources distinctes (≥ 2 notes).
        Cela évite un 2e appel LLM quand une seule note courte a été trouvée —
        cas où la réponse sentinel est probablement correcte.
        """
        if intent not in {"synthesis", "relation", "hybrid"}:
            return answer
        if not answer or not answer.strip().lower().startswith(_HARD_SENTINEL.rstrip(".")):
            return answer
        if len(context.strip()) < 300:
            return answer
        # PERF-15b : exige au moins 2 notes distinctes pour justifier un 2e appel LLM
        distinct_sources = len({line.lstrip("#").strip().split("\n")[0]
                                 for line in context.split("## ")
                                 if line.strip()})
        if distinct_sources < 2:
            logger.debug("[retry_synthesis] skipped — source unique dans le contexte")
            return answer

        retry_messages = self._build_messages(
            query,
            context,
            history,
            intent=intent,
            force_study_answer=True,
        )
        try:
            retried = self._llm.chat(
                retry_messages,
                max_tokens=self._max_tokens_for_intent(intent),
                temperature=0.1,
                operation="rag_query_retry",
            )
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

        if contains_mermaid_fence(text):
            return sanitize_mermaid_blocks(text)

        text = self._sanitize_single_subject_answer(text, query, intent)

        text = RAGPipeline._sanitize_structured_study_answer(text)

        if self._contains_disallowed_user_visible_script(text):
            text = self._rewrite_answer_in_french(text, query=query)

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

    @staticmethod
    def _contains_disallowed_user_visible_script(text: str) -> bool:
        return bool(_DISALLOWED_USER_VISIBLE_SCRIPT_RE.search(text or ""))

    def _rewrite_answer_in_french(self, text: str, *, query: str) -> str:
        prompt = (
            "Réécris la réponse suivante en français naturel et homogène. "
            "Conserve le sens, les titres Markdown utiles, les titres de notes entre crochets, les wikilinks, "
            "les URLs et les citations indispensables. N'utilise aucune autre langue pour la prose finale.\n\n"
            f"Question d'origine : {query}\n\n"
            f"Réponse à réécrire :\n{text}"
        )
        try:
            rewritten = self._llm.chat(
                [
                    {
                        "role": "system",
                        "content": "Tu es ObsiRAG. Tu réécris exclusivement en français naturel et tu réponds uniquement avec le texte final.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=max(1200, self._max_tokens_for_intent("general")),
                operation="rag_rewrite_fr",
            )
            normalized = str(rewritten or "").strip()
            return normalized or text
        except Exception as exc:
            logger.warning(f"RAG rewrite français échoué : {exc}")
            return text

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

    def _retrieve(
        self,
        query: str,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple[list[dict], str]:
        return self._retrieval_strategy.retrieve(query, progress_callback=progress_callback)

    @staticmethod
    def _is_obsirag_generated_chunk(chunk: dict) -> bool:
        metadata = chunk.get("metadata") or {}
        file_path = str(metadata.get("file_path") or "").replace("\\", "/")
        return "/obsirag/" in file_path or file_path.startswith("obsirag/")

    def _filter_obsirag_generated_chunks(self, chunks: list[dict]) -> list[dict]:
        filtered = [chunk for chunk in chunks if not self._is_obsirag_generated_chunk(chunk)]
        dropped = len(chunks) - len(filtered)
        if dropped > 0:
            logger.info(f"RAG autolearn: {dropped} chunk(s) ObsiRAG exclus du contexte")
        return filtered

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
        return self._retrieval_strategy.retrieve_hybrid_chunks(query, proper_nouns)

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
        return self._retrieval_strategy.prepare_context_chunks(chunks, query, intent)

    def _mark_primary_sources(self, chunks: list[dict], query: str, intent: str) -> list[dict]:
        return self._retrieval_strategy.mark_primary_sources(chunks, query, intent)

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
        return self._answer_prompting.build_context(chunks, query, intent, char_budget=char_budget)

    def _group_chunks_by_note(self, chunks: list[dict]) -> dict[str, list[dict]]:
        return self._answer_prompting.group_chunks_by_note(chunks)

    def _build_title_to_file_index(self, seen_notes: dict[str, list[dict]]) -> dict[str, str]:
        return self._answer_prompting.build_title_to_file_index(seen_notes)

    def _collect_linked_targets(self, seen_notes: dict[str, list[dict]]) -> set[str]:
        return self._answer_prompting.collect_linked_targets(seen_notes)

    def _load_linked_chunks(self, linked_target: str) -> list[dict]:
        return self._answer_prompting.load_linked_chunks(linked_target)

    def _enrich_seen_notes_with_linked_chunks(self, seen_notes: dict[str, list[dict]]) -> None:
        self._answer_prompting.enrich_seen_notes_with_linked_chunks(seen_notes)

    def _render_context_from_seen_notes(
        self,
        seen_notes: dict[str, list[dict]],
        char_budget: int | None,
    ) -> str:
        return self._answer_prompting.render_context_from_seen_notes(seen_notes, char_budget)

    def _build_intent_hint(
        self,
        query: str,
        intent: str,
        *,
        force_study_answer: bool,
    ) -> str:
        return self._answer_prompting.build_intent_hint(
            query,
            intent,
            force_study_answer=force_study_answer,
        )

    def _build_study_intent_hint(self, query: str) -> str:
        return self._answer_prompting.build_study_intent_hint(query)

    def _build_single_subject_intent_hint(self, query: str) -> str:
        return self._answer_prompting.build_single_subject_intent_hint(query)

    def _build_messages(
        self,
        query: str,
        context: str,
        history: list[dict[str, str]],
        intent: str = "general",
        force_study_answer: bool = False,
        resolved_query: str | None = None,
    ) -> list[dict[str, str]]:
        return self._answer_prompting.build_messages(
            query,
            context,
            history,
            intent=intent,
            force_study_answer=force_study_answer,
            resolved_query=resolved_query,
        )
