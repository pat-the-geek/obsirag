"""
Enrichissement web — recherche DuckDuckGo + synthèse LLM + sauvegarde insight.

Déclenché automatiquement quand le RAG répond "Cette information n'est pas dans
ton coffre." : une recherche web est lancée en arrière-plan, le LLM synthétise
les résultats, et un insight Markdown est écrit dans obsirag/insights/.
"""
from __future__ import annotations

import concurrent.futures
import json
import re
import threading
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from loguru import logger

from src.config import settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SENTINEL = "cette information n'est pas dans ton coffre"
_CHAT_PREFIX_RE = re.compile(
    r"^\s*(?:parle(?:[-\s]?moi)?\s+de|dis(?:[-\s]?moi)?\s+.+?\s+sur|dis(?:[-\s]?moi)?\s+.+?\s+de|"
    r"que\s+sais[- ]?tu\s+de|qu['’]est[- ]?ce\s+que|c['’]est\s+quoi|qui\s+est|"
    r"que\s+peux[- ]?tu\s+me\s+dire\s+de)\s+",
    re.I,
)
_QUERY_STOPWORDS = {
    "parle", "moi", "de", "du", "des", "la", "le", "les", "un", "une", "sur",
    "dis", "dire", "peux", "tu", "que", "quoi", "est", "qui", "au", "aux",
    "please", "s'il", "te", "plait", "propos", "je", "j", "aimerais", "voudrais",
    "savoir", "quelle", "quelles", "quel", "quels", "sont", "pour", "en", "quoi",
    "comment", "pourquoi", "avec", "sans", "dans", "vers", "chez", "cela", "ca",
    "ces", "ses", "cette", "cet", "sur", "fait", "font", "avoir", "etre", "être",
}
_GENERIC_REQUEST_RE = re.compile(
    r"^\s*(?:parle(?:-?moi)?\s+de|dis(?:-?moi)?\s+.+?\s+sur|dis(?:-?moi)?\s+.+?\s+de|"
    r"que\s+sais[- ]?tu\s+de|que\s+peux[- ]?tu\s+me\s+dire\s+de|présente(?:-?moi)?|"
    r"raconte(?:-?moi)?|explique(?:-?moi)?)\b",
    re.I,
)
_QUERY_ASPECT_TERMS = {
    "actualité", "actualite", "actualités", "actualites", "nouveauté", "nouveautes", "nouveautés",
    "prix", "date", "sortie", "rumeur", "rumeurs", "review", "avis", "comparatif", "test",
    "specs", "spécifications", "specifications", "version", "versions",
}
_DDG_TIMEOUT_SECONDS = 3
_DDG_USER_AGENT = "Mozilla/5.0 (ObsiRAG/1.0; +https://github.com/pat-the-geek/obsirag)"
_NOT_IN_VAULT_PATTERNS = [
    re.compile(
        r"^cette information n['’]est pas (?:dans|consignee? dans|consignée dans|presente dans|présente dans) ton coffre$"
    ),
    re.compile(
        r"^cette information n['’]est pas (?:consignee?|consignée) dans ton coffre$"
    ),
    re.compile(
        r"^je n['’]ai pas trouv(?:e|é)(?:e|es)?(?: d['’]information)? dans ton coffre$"
    ),
    re.compile(
        r"^je ne trouve pas (?:d['’]information|de trace)? dans ton coffre$"
    ),
    re.compile(
        r"^aucune information (?:pertinente )?(?:n['’]est )?(?:disponible|presente|présente) dans ton coffre$"
    ),
]


def is_not_in_vault(response: str) -> bool:
    """Retourne True si la réponse est une négation pure du contenu du coffre.

    Une réponse mixte qui commence par une formule négative mais ajoute ensuite
    une synthèse utile du coffre ne doit pas déclencher la recherche web."""
    low = response.strip().lower()
    normalized = re.sub(r"\s+", " ", low).strip(" .!?:;\n\t")
    if normalized in {
        _SENTINEL,
        "cette information n'est pas consignée dans ton coffre",
    }:
        return True
    return any(pattern.fullmatch(normalized) for pattern in _NOT_IN_VAULT_PATTERNS)


def _insights_artifacts_dir() -> Path:
    d = settings.insights_dir / datetime.now().strftime("%Y-%m")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _entity_context_tags(entity_contexts: list[dict] | None) -> list[str]:
    tags: list[str] = []
    for context in entity_contexts or []:
        tag = str(context.get("tag") or "").strip()
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def _safe_filename(query: str) -> str:
    """Convertit un prompt en nom de fichier sûr (max 60 chars)."""
    slug = re.sub(r"[^\w\s-]", "", query.lower())
    slug = re.sub(r"[\s_]+", "_", slug).strip("-_")
    return slug[:60]


def _normalize_user_query_for_search(user_question: str) -> str:
    """Nettoie les formulations conversationnelles pour obtenir le vrai sujet."""
    text = user_question.strip().strip('"\'«»').strip()
    text = re.sub(r"\s+", " ", text)
    text = _CHAT_PREFIX_RE.sub("", text).strip()
    text = text.strip(" ?!.,;:")
    return text or user_question.strip()


def _extract_focus_terms(text: str) -> list[str]:
    """Extrait les termes saillants de la question pour valider la pertinence web."""
    normalized = _normalize_user_query_for_search(text)
    terms: list[str] = []
    for token in re.findall(r"[A-Za-zÀ-ÿ0-9-]+", normalized):
        low = token.lower()
        if len(low) < 3 or low in _QUERY_STOPWORDS:
            continue
        if low not in terms:
            terms.append(low)
    return terms


def _tokenize_match_text(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-zÀ-ÿ0-9-]+", text)]


def _count_exact_term_matches(terms: list[str], text: str) -> int:
    if not terms or not text:
        return 0
    token_set = set(_tokenize_match_text(text))
    return sum(1 for term in terms if term in token_set)


def _extract_subject_phrase(text: str) -> str | None:
    normalized = _normalize_user_query_for_search(text)
    subject_tokens: list[str] = []
    for raw_token in re.findall(r"[A-Za-zÀ-ÿ0-9-]+", normalized):
        low = raw_token.lower().strip("-_")
        if not low or low in _QUERY_STOPWORDS or low in _QUERY_ASPECT_TERMS or low.isdigit():
            continue
        if len(low) < 3:
            continue
        subject_tokens.append(raw_token.strip())
    if 2 <= len(subject_tokens) <= 4:
        return " ".join(subject_tokens)
    return None


def _is_short_entity_query(text: str) -> bool:
    normalized = _normalize_user_query_for_search(text)
    focus_terms = _extract_focus_terms(normalized)
    if not focus_terms or len(focus_terms) > 4:
        return False
    if any(term.lower() in _QUERY_ASPECT_TERMS for term in focus_terms):
        return False
    if any(term.isdigit() for term in focus_terms):
        return False
    return len(normalized.split()) <= 5


def _flatten_related_topics(items: list[dict]) -> list[dict]:
    flattened: list[dict] = []
    for item in items:
        if item.get("FirstURL") and item.get("Text"):
            flattened.append(item)
            continue
        nested = item.get("Topics")
        if isinstance(nested, list):
            flattened.extend(_flatten_related_topics(nested))
    return flattened


def _build_instant_answer_results(payload: dict, *, max_results: int = 3) -> list[dict]:
    results: list[dict] = []
    heading = (payload.get("Heading") or "").strip()
    abstract = (payload.get("AbstractText") or "").strip()
    abstract_url = (payload.get("AbstractURL") or "").strip()
    abstract_source = (payload.get("AbstractSource") or "DuckDuckGo").strip()

    if heading and abstract and abstract_url:
        results.append(
            {
                "title": f"{heading} - {abstract_source}",
                "href": abstract_url,
                "body": abstract,
            }
        )

    for item in _flatten_related_topics(payload.get("RelatedTopics") or []):
        text = (item.get("Text") or "").strip()
        href = (item.get("FirstURL") or "").strip()
        if not text or not href:
            continue
        title = text.split(" - ", 1)[0].strip()
        results.append(
            {
                "title": title or text[:80],
                "href": href,
                "body": text,
            }
        )
        if len(results) >= max_results:
            break

    deduped: list[dict] = []
    seen_urls: set[str] = set()
    for item in results:
        href = item.get("href", "")
        if href in seen_urls:
            continue
        seen_urls.add(href)
        deduped.append(item)
        if len(deduped) >= max_results:
            break
    return deduped


def _ddg_instant_answer_search(query: str, max_results: int = 3) -> list[dict]:
    if not _is_short_entity_query(query):
        return []
    try:
        params = urllib.parse.urlencode(
            {
                "q": query,
                "format": "json",
                "no_html": "1",
                "no_redirect": "1",
                "skip_disambig": "0",
            }
        )
        request = urllib.request.Request(
            f"https://api.duckduckgo.com/?{params}",
            headers={"User-Agent": _DDG_USER_AGENT},
        )
        with urllib.request.urlopen(request, timeout=_DDG_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
        results = _build_instant_answer_results(payload, max_results=max_results)
        logger.info(
            f"WebSearch DDG instant answer: requête={query!r} {len(results)} résultats"
        )
        return results
    except Exception as exc:
        logger.debug(f"WebSearch DDG instant answer error: {exc}")
        return []


def _merge_search_results(*result_sets: list[dict], max_results: int = 5) -> list[dict]:
    merged: list[dict] = []
    seen_urls: set[str] = set()
    for result_set in result_sets:
        for item in result_set:
            href = item.get("href", "")
            if not href or href in seen_urls:
                continue
            seen_urls.add(href)
            merged.append(item)
            if len(merged) >= max_results:
                return merged
    return merged


def _keywordize_query(text: str, *, max_terms: int = 6) -> str:
    """Construit une requête web réduite à des mots-clés, sans formulation question/rédactionnelle."""
    normalized = _normalize_user_query_for_search(text)
    subject_tokens: list[str] = []
    aspect_tokens: list[str] = []
    numeric_tokens: list[str] = []
    seen_lowers: set[str] = set()

    for raw_token in re.findall(r"[A-Za-zÀ-ÿ0-9-]+", normalized):
        low = raw_token.lower().strip("-_")
        if not low or low in _QUERY_STOPWORDS:
            continue
        if len(low) < 3 and not low.isdigit():
            continue
        if low in seen_lowers:
            continue
        seen_lowers.add(low)

        clean_token = raw_token.strip()
        if low.isdigit():
            numeric_tokens.append(clean_token)
        elif low in _QUERY_ASPECT_TERMS:
            aspect_tokens.append(clean_token)
        else:
            subject_tokens.append(clean_token)

        if len(subject_tokens) + len(aspect_tokens) + len(numeric_tokens) >= max_terms:
            break

    keyword_tokens = (subject_tokens + aspect_tokens + numeric_tokens)[:max_terms]

    if keyword_tokens:
        return " ".join(keyword_tokens)

    focus_terms = _extract_focus_terms(normalized)
    if focus_terms:
        return " ".join(focus_terms[:max_terms])

    return normalized


def _is_generic_subject_request(user_question: str) -> bool:
    """Détecte une demande générale de présentation d'un sujet."""
    return bool(_GENERIC_REQUEST_RE.search(user_question.strip()))


def _build_disambiguation_query(user_question: str, llm) -> str | None:
    """Pour une demande générique sur un sujet court/ambigu, demande une requête
    web de présentation générale plutôt qu'une requête d'actualité."""
    normalized = _normalize_user_query_for_search(user_question)
    focus_terms = _extract_focus_terms(normalized)
    if not _is_generic_subject_request(user_question):
        return None
    if len(focus_terms) != 1:
        return None

    subject = normalized.strip()
    prompt = (
        f"Sujet demandé : « {subject} »\n\n"
        "L'utilisateur demande une présentation générale d'un sujet, pas une actualité ni une comparaison.\n"
        "Produis UNE requête web courte qui vise une vue d'ensemble encyclopédique du sujet le plus probable.\n"
        "RÈGLES STRICTES :\n"
        "- 3 à 6 mots maximum.\n"
        "- Oriente vers une présentation générale, pas vers des news, tickets, trailers, rumeurs ou produits dérivés.\n"
        "- Si le sujet est ambigu, choisis le référent culturel/public le plus probable et ajoute un mot de cadrage comme overview, franchise, novel, film, science fiction, wikipedia, biography selon le cas.\n"
        "- Réponds UNIQUEMENT avec la requête.\n\n"
        "Exemples :\n"
        "Sujet : Dune\n"
        "→ Dune science fiction franchise overview\n"
        "Sujet : Foundation\n"
        "→ Foundation science fiction series overview\n"
        "Sujet : Ada Lovelace\n"
        "→ Ada Lovelace biography overview\n"
    )
    try:
        q = llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=20,
            operation="web_query_disambiguation",
        ).strip()
        q = q.strip('"\'«»→-').strip()
        if len(q) >= 5:
            return q
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# Reformulation de la requête de recherche
# ---------------------------------------------------------------------------

def _build_search_query(user_question: str, llm) -> str:
    """
    Reformule la question en mots-clés de recherche précis, sans dériver
    vers des termes génériques comme 'recherche', 'trouver', 'comment chercher'.
    """
    prompt = (
        f"Question : « {user_question} »\n\n"
        "Extrais les mots-clés factuels essentiels de cette question pour une recherche web. "
        "RÈGLES STRICTES :\n"
        "- Garde uniquement les entités, noms propres, termes techniques et faits recherchés.\n"
        "- N'inclus PAS les mots : recherche, chercher, trouver, savoir, comment, pourquoi, "
        "quelle, quels, définition, signification.\n"
        "- 3 à 6 mots-clés maximum, séparés par des espaces.\n"
        "- Utilise l'anglais pour les sujets scientifiques, techniques ou internationaux.\n"
        "- Pour les sigles ou termes ambigus, ajoute le domaine pour lever l'ambigüité "
        "(exemple : BIG = Big Bang cosmologie, pas un registre ; GRACE = satellite gravity).\n"
        "- Réponds UNIQUEMENT avec les mots-clés, sans ponctuation ni explication.\n\n"
        "Exemples :\n"
        "Question : Quelle altitude maximale atteindra la capsule Orion lors d'Artemis II ?\n"
        "→ Orion capsule Artemis II maximum altitude\n"
        "Question : Quel est le PIB de la France en 2024 ?\n"
        "→ PIB France 2024\n"
        "Question : Comment fonctionne un moteur à hydrogène ?\n"
        "→ hydrogen engine how it works\n"
        "Question : Le 1er big bang a eu lieu il y a combien de temps ?\n"
        "→ Big Bang age universe cosmology billion years\n"
        "Question : Quelle est la durée de vie d'une étoile naine rouge ?\n"
        "→ red dwarf star lifespan astronomy\n"
    )
    try:
        normalized_question = _normalize_user_query_for_search(user_question)
        keyword_fallback = _keywordize_query(user_question)
        disambiguated_query = _build_disambiguation_query(user_question, llm)
        if disambiguated_query:
            logger.info(
                f"WebSearch requête désambiguïsée : {disambiguated_query!r} (original: {user_question[:60]!r})"
            )
            return disambiguated_query
        focus_terms = _extract_focus_terms(normalized_question)
        if len(focus_terms) == 1 and len(normalized_question.split()) <= 2:
            logger.info(
                f"WebSearch requête courte conservée : {normalized_question!r} (original: {user_question[:60]!r})"
            )
            return normalized_question
        q = llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=30,
            operation="web_query",
        ).strip()
        # Nettoyer ponctuation et guillemets résiduels
        q = q.strip('"\'«»→-').strip()
        # Détection de dérive : si la requête contient des mots méta, utiliser question originale
        _PLACEHOLDER_QUERIES = {"unused", "none", "null", "n/a", "na", "todo", "test"}
        _META_WORDS = {"recherche", "chercher", "trouver", "comment", "search", "find",
                       "look", "how", "to", "do"}
        first_words = {w.lower() for w in q.split()[:3]}
        q_terms = _extract_focus_terms(q)
        exact_focus_overlap = len(set(q_terms) & set(focus_terms))
        is_short_but_valid = (
            len(q) >= 3
            and len(q.split()) <= 3
            and exact_focus_overlap > 0
        )
        if (
            not q
            or q.lower() in _PLACEHOLDER_QUERIES
            or ((len(q) < 5 or len(q.split()) == 1) and not is_short_but_valid and len(focus_terms) >= 2)
            or first_words & _META_WORDS
        ):
            fallback_query = keyword_fallback
            logger.warning(f"WebSearch requête reformulée rejetée : {q!r} → fallback sur {fallback_query!r}")
            return fallback_query
        logger.info(f"WebSearch requête reformulée : {q!r} (original: {user_question[:60]!r})")
        return q
    except Exception:
        return _keywordize_query(user_question)


# ---------------------------------------------------------------------------
# Moteur de recherche DuckDuckGo
# ---------------------------------------------------------------------------

def _is_latin_text(text: str) -> bool:
    """Retourne True si le texte est majoritairement en alphabet latin (pas chinois, etc.)."""
    if not text:
        return True
    non_latin = sum(1 for c in text if ord(c) > 0x2E7F)  # au-delà du latin étendu
    return non_latin / len(text) < 0.15  # tolérance 15%


def _ddg_search(query: str, max_results: int = 5) -> list[dict]:
    """Retourne une liste de {title, href, body} depuis DuckDuckGo.
    Utilise la région fr-fr et filtre les résultats non-latins.
    """
    candidate_queries = [query]
    subject_phrase = _extract_subject_phrase(query)
    if subject_phrase and '"' not in query:
        candidate_queries.append(f'"{subject_phrase}"')
    if "知乎" not in query:
        candidate_queries.append(f"{query} -知乎")
    if subject_phrase and "wikipedia" not in query.lower():
        candidate_queries.append(f'"{subject_phrase}" wikipedia')
    if "wikipedia" not in query.lower() and len(query.split()) <= 3:
        candidate_queries.append(f"{query} wikipedia")
    candidate_queries = list(dict.fromkeys(candidate_queries))

    def _run_one(candidate_query: str) -> tuple[str, list[dict], int]:
        try:
            from ddgs import DDGS
            with DDGS(timeout=_DDG_TIMEOUT_SECONDS) as ddgs:
                raw = list(ddgs.text(
                    candidate_query,
                    region="fr-fr",
                    safesearch="off",
                    max_results=max_results + 3,
                ))
            filtered = [
                r for r in raw
                if _is_latin_text(r.get("title", "")) and _is_latin_text(r.get("body", ""))
            ]
            result = filtered[:max_results]
            score = _score_search_results(query, candidate_query, result)
            logger.info(
                f"WebSearch DDG: requête={candidate_query!r} {len(raw)} résultats bruts, {len(result)} après filtrage, score={score}"
            )
            return candidate_query, result, score
        except Exception as exc:
            logger.warning(f"WebSearch DDG error ({candidate_query!r}): {exc}")
            return candidate_query, [], -10**9

    _OUTER_TIMEOUT = _DDG_TIMEOUT_SECONDS + 2  # marge pour DNS + connection
    outcomes: list = []
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=min(len(candidate_queries), 4))
    try:
        futures = [executor.submit(_run_one, cq) for cq in candidate_queries]
        for f in concurrent.futures.as_completed(futures, timeout=_OUTER_TIMEOUT):
            try:
                outcomes.append(f.result(timeout=1))
            except Exception:
                pass
    except concurrent.futures.TimeoutError:
        logger.warning("WebSearch DDG timeout global — résultats partiels seulement")
    except Exception as exc:
        logger.warning(f"WebSearch DDG error: {exc}")
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    best_results: list[dict] = []
    best_score = -10**9
    for _cq, result, score in outcomes:
        if result and (not best_results or score > best_score):
            best_score = score
            best_results = result
    return best_results


def _score_search_results(original_query: str, candidate_query: str, results: list[dict]) -> int:
    if not results:
        return -1

    focus_terms = _extract_focus_terms(original_query)
    corpus = " ".join(
        f"{item.get('title', '')} {item.get('body', '')} {item.get('href', '')}"
        for item in results
    )
    overlap = _count_exact_term_matches(focus_terms, corpus)
    subject_phrase = _extract_subject_phrase(original_query)
    normalized_subject_phrase = subject_phrase.lower() if subject_phrase else None

    encyclopedic_hits = sum(
        1
        for item in results
        if any(marker in f"{item.get('title', '')} {item.get('href', '')}".lower() for marker in (
            "wikipedia",
            "britannica",
            "larousse",
            "universalis",
        ))
    )
    candidate_bonus = 2 if "wikipedia" in candidate_query.lower() else 0
    title_hits = sum(
        _count_exact_term_matches(focus_terms, item.get('title', '') or '')
        for item in results
    )
    phrase_hits = 0
    if normalized_subject_phrase:
        phrase_hits = sum(
            1
            for item in results
            if normalized_subject_phrase in " ".join(
                _tokenize_match_text(
                    f"{item.get('title', '')} {item.get('body', '')} {item.get('href', '')}"
                )
            )
        )
    weak_multi_term_penalty = 0
    if len(focus_terms) >= 2 and overlap < 2:
        weak_multi_term_penalty = -8
    return (
        overlap * 8
        + encyclopedic_hits * 4
        + title_hits * 3
        + phrase_hits * 8
        + min(len(results), 3)
        + candidate_bonus
        + weak_multi_term_penalty
    )


# ---------------------------------------------------------------------------
# Synthèse LLM
# ---------------------------------------------------------------------------

def _build_snippets(results: list[dict]) -> str:
    """Construit le bloc de snippets web utilisé pour synthèse et contrôle qualité."""
    return "\n\n".join(
        f"**{r.get('title', '')}** ({r.get('href', '')})\n{r.get('full_text') or r.get('body', '')}"
        for r in results
    )


def build_query_overview_from_results_sync(
    query: str,
    search_query: str,
    results: list[dict],
    llm,
    *,
    max_results: int = 8,
) -> dict:
    """Construit une vue d'ensemble à partir de résultats web déjà récupérés."""
    if not results:
        return {}

    limited_results = [item for item in results if isinstance(item, dict) and item.get("href")][:max_results]
    if not limited_results:
        return {}

    summary = _synthesize_ai_overview(query, search_query, limited_results, llm)
    if not summary:
        return {}

    return {
        "query": query,
        "search_query": search_query,
        "summary": summary,
        "sources": limited_results,
    }

def _synthesize(query: str, results: list[dict], llm) -> str | None:
    """Synthétise les résultats web avec le LLM. Retourne le texte ou None."""
    if not results:
        return None

    snippets = _build_snippets(results)

    prompt = (
        f"Voici des extraits de sources web en réponse à la question : « {query} »\n\n"
        f"{snippets}\n\n"
        "Synthétise ces informations en une réponse claire, précise et structurée en français. "
        "Cite les sources entre [crochets]. "
        "Si les sources sont contradictoires ou incomplètes, le signale. "
        "Réponds uniquement avec la synthèse, sans introduction."
    )

    try:
        return llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
            operation="web_insight",
        ).strip()
    except Exception as exc:
        logger.error(f"WebSearch synthèse LLM erreur: {exc}")
        return None


def _synthesize_ai_overview(query: str, search_query: str, results: list[dict], llm) -> str | None:
    """Construit une vue d'ensemble enrichie de la question à partir des résultats DDG."""
    if not results:
        return None

    snippets = _build_snippets(results[:8])
    prompt = (
        f"Question initiale : « {query} »\n"
        f"Requête DuckDuckGo utilisée : « {search_query} »\n\n"
        f"Extraits web :\n{snippets}\n\n"
        "Produis une vue d'ensemble riche en français, dans l'esprit d'un AI overview. "
        "Apporte des faits saillants, du contexte, les points clés, et si pertinent des éléments "
        "de cadrage ou de désambiguïsation. "
        "Format attendu :\n"
        "- un court paragraphe d'ensemble\n"
        "- puis 3 à 5 puces factuelles\n"
        "- cite les sources entre [crochets]\n"
        "- n'invente rien au-delà des extraits fournis."
    )

    try:
        return llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=900,
            operation="web_ai_overview",
        ).strip()
    except Exception as exc:
        logger.error(f"WebSearch AI overview erreur: {exc}")
        return None


def _save_insight(query: str, answer: str, results: list[dict]) -> Path:
    """Écrit l'insight web dans obsirag/insights/."""
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _safe_filename(query)
    filename = f"web_{slug}_{date_str}.md"
    out_path = _insights_artifacts_dir() / filename

    sources_md = "\n".join(
        f"- [{r.get('title', r.get('href',''))}]({r.get('href','')})"
        for r in results
    )

    content = (
        "---\n"
        "tags:\n"
        "  - insight\n"
        "  - web_insight\n"
        "  - ddg_enrichment\n"
        "  - obsirag\n"
        f"date: {datetime.now().strftime('%Y-%m-%d')}\n"
        "---\n\n"
        f"# Question\n\n{query}\n\n"
        f"# Réponse\n\n{answer}\n\n"
        f"# Sources web\n\n{sources_md}\n"
    )

    out_path.write_text(content, encoding="utf-8")
    logger.info(f"WebInsight créé : {out_path.name}")
    return out_path


def _format_query_overview_markdown(query_overview: dict) -> str:
    if not query_overview:
        return ""

    lines: list[str] = ["# Vue d'ensemble DDG", ""]
    summary = str(query_overview.get("summary") or "").strip()
    if summary:
        lines.extend([summary, ""])

    search_query = str(query_overview.get("search_query") or "").strip()
    if search_query:
        lines.extend([f"**Requête DDG :** `{search_query}`", ""])

    sources = query_overview.get("sources") or []
    if sources:
        lines.append("## Sources overview")
        lines.append("")
        lines.extend(
            f"- [{item.get('title', item.get('href', 'Source'))}]({item.get('href', '')})"
            for item in sources
            if item.get("href")
        )
        lines.append("")

    return "\n".join(lines).strip()


def _format_entity_contexts_markdown(entity_contexts: list[dict]) -> str:
    if not entity_contexts:
        return ""

    lines: list[str] = ["# Entités détectées", ""]
    for context in entity_contexts:
        entity_name = str(context.get("value") or "").strip()
        if not entity_name:
            continue
        lines.extend([f"## {entity_name}", ""])
        lines.append(f"- Type : {context.get('type_label') or context.get('type') or 'Entité'}")
        if context.get("mentions"):
            lines.append(f"- Mentions WUDD.AI : {int(context.get('mentions') or 0)}")
        if context.get("tag"):
            lines.append(f"- Tag Obsidian : `{context['tag']}`")
        if context.get("image_url"):
            lines.extend([f"- Image : ![{entity_name}]({context['image_url']})", ""])
        else:
            lines.append("")

        notes = context.get("notes") or []
        filtered_notes = [
            note for note in notes
            if not str(note.get("file_path") or "").replace("\\", "/").startswith("obsirag/")
        ]
        if filtered_notes:
            lines.append("### Notes liées")
            lines.append("")
            for note in filtered_notes:
                note_title = note.get("title") or note.get("file_path") or "Note"
                note_path = note.get("file_path") or ""
                if note_path:
                    lines.append(f"- [[{note_path.removesuffix('.md')}|{note_title}]]")
                else:
                    lines.append(f"- {note_title}")
            lines.append("")

        ddg_knowledge = context.get("ddg_knowledge") or {}
        if ddg_knowledge:
            lines.append("### Connaissance DuckDuckGo")
            lines.append("")
            for key in ("abstract_text", "answer", "definition"):
                value = str(ddg_knowledge.get(key) or "").strip()
                if value:
                    lines.append(f"- {value}")
            infobox = ddg_knowledge.get("infobox") or []
            for item in infobox[:8]:
                label = str(item.get("label") or "").strip()
                value = str(item.get("value") or "").strip()
                if label and value:
                    lines.append(f"- {label} : {value}")
            related = ddg_knowledge.get("related_topics") or []
            if related:
                lines.append("")
                lines.append("### Sujets liés")
                lines.append("")
                for item in related[:5]:
                    text = str(item.get("text") or "").strip()
                    url = str(item.get("url") or "").strip()
                    if text and url:
                        lines.append(f"- [{text}]({url})")
            lines.append("")

    return "\n".join(lines).strip()


def _upsert_markdown_section(content: str, heading: str, section_markdown: str) -> str:
    if not section_markdown:
        return content

    escaped_heading = re.escape(heading)
    pattern = re.compile(
        rf"{escaped_heading}\n.*?(?=\n# |\Z)",
        flags=re.DOTALL,
    )
    section_block = section_markdown.strip() + "\n\n"
    if pattern.search(content):
        return pattern.sub(section_block, content, count=1)
    return content.rstrip() + "\n\n" + section_block


def _merge_frontmatter_tags(content: str, tags: list[str]) -> str:
    if not tags:
        return content
    tag_lines = [tag for tag in tags if tag]
    if not tag_lines:
        return content

    if content.startswith("---\n"):
        end = content.find("\n---\n", 4)
        if end != -1:
            frontmatter = content[4:end]
            body = content[end + 5:]
            existing_tags = re.findall(r"^\s*-\s+(.+)$", frontmatter, flags=re.MULTILINE)
            merged = list(dict.fromkeys(existing_tags + tag_lines))
            if re.search(r"^tags:\n(?:\s+-\s+.+\n?)+", frontmatter, flags=re.MULTILINE):
                frontmatter = re.sub(
                    r"tags:\n(?:\s+-\s+.+\n?)+",
                    "tags:\n" + "".join(f"  - {tag}\n" for tag in merged),
                    frontmatter,
                    count=1,
                )
            else:
                frontmatter = frontmatter.rstrip() + "\n" + "tags:\n" + "".join(f"  - {tag}\n" for tag in merged)
            return f"---\n{frontmatter}\n---\n{body}"

    frontmatter = "---\ntags:\n" + "".join(f"  - {tag}\n" for tag in tag_lines) + "---\n\n"
    return frontmatter + content.lstrip()


def save_chat_enrichment_insight(
    query: str,
    answer: str,
    *,
    entity_contexts: list[dict] | None = None,
    query_overview: dict | None = None,
    path: Path | None = None,
) -> Path | None:
    entity_contexts = entity_contexts or []
    query_overview = query_overview or {}
    if not entity_contexts and not query_overview:
        return path

    target_path = path
    if target_path is None:
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = _safe_filename(query)
        target_path = _insights_artifacts_dir() / f"chat_{slug}_{date_str}.md"

    overview_md = _format_query_overview_markdown(query_overview)
    entities_md = _format_entity_contexts_markdown(entity_contexts)
    entity_tags = _entity_context_tags(entity_contexts)

    if target_path.exists():
        content = target_path.read_text(encoding="utf-8")
        content = _merge_frontmatter_tags(
            content,
            ["insight", "web_insight", "chat_enrichment", "ddg_overview", "entity_enrichment", "obsirag", *entity_tags],
        )
        content = _upsert_markdown_section(content, "# Vue d'ensemble DDG", overview_md)
        content = _upsert_markdown_section(content, "# Entités détectées", entities_md)
    else:
        frontmatter = "".join([
            "---\n",
            "tags:\n",
            "  - insight\n",
            "  - web_insight\n",
            "  - chat_enrichment\n",
            "  - ddg_overview\n",
            "  - entity_enrichment\n",
            "  - obsirag\n",
            *(f"  - {tag}\n" for tag in entity_tags),
            f"date: {datetime.now().strftime('%Y-%m-%d')}\n",
            "---\n\n",
        ])
        content = frontmatter + (
            f"# Question\n\n{query}\n\n"
            f"# Réponse\n\n{answer}\n\n"
        )
        content = _upsert_markdown_section(content, "# Vue d'ensemble DDG", overview_md)
        content = _upsert_markdown_section(content, "# Entités détectées", entities_md)

    target_path.write_text(content.rstrip() + "\n", encoding="utf-8")
    logger.info(f"Chat enrichment sauvegardé : {target_path.name}")
    return target_path


def build_query_overview_sync(query: str, llm, *, max_results: int = 8) -> dict:
    """Construit une vue d'ensemble DDG enrichie pour la question initiale."""
    search_query = _build_search_query(query, llm)
    instant_results = _ddg_instant_answer_search(search_query, max_results=min(4, max_results))
    ddg_results = _ddg_search(search_query, max_results=max_results)
    results = _merge_search_results(instant_results, ddg_results, max_results=max_results)
    return build_query_overview_from_results_sync(query, search_query, results, llm, max_results=max_results)


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------

def _check_quality(query: str, answer: str, results: list[dict], llm) -> bool:
    """Vérifie par LLM la qualité d'une synthèse web à partir des mêmes extraits
    que ceux utilisés pour générer l'insight."""
    focus_terms = _extract_focus_terms(query)
    if focus_terms:
        corpus = " ".join(
            f"{r.get('title', '')} {r.get('body', '')}" for r in results
        ).lower()
        overlap = sum(1 for term in focus_terms if term in corpus)
        if overlap == 0:
            logger.warning(
                f"WebSearch qualité insuffisante : aucun recouvrement lexical avec le sujet {focus_terms}"
            )
            return False

    if _has_authoritative_exact_match(query, results):
        logger.info(f"WebSearch qualité acceptée par heuristique autoritative pour : {query!r}")
        return True

    snippets = _build_snippets(results)
    prompt = (
        f"Question posée : « {query} »\n\n"
        f"Extraits web utilisés :\n{snippets}\n\n"
        f"Réponse synthétisée :\n{answer}\n\n"
        "En te basant UNIQUEMENT sur les extraits web ci-dessus, évalue la réponse synthétisée.\n"
        "La réponse doit être fidèle aux sources, dans le bon champ sémantique, et utile pour répondre à la question.\n"
        "Si les sources elles-mêmes sont hors sujet par rapport à la question, la réponse doit être considérée mauvaise.\n"
        "Réponds UNIQUEMENT par GOOD si la réponse est satisfaisante, "
        "ou par POOR si elle est hors sujet, vague ou insuffisante."
    )
    try:
        verdict = llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=10,
            operation="web_quality_check",
        ).strip().upper()
        return verdict.startswith("GOOD")
    except Exception as exc:
        logger.warning(f"WebSearch quality check échoué : {exc}")
        return True  # en cas d'erreur, on affiche quand même


def _has_authoritative_exact_match(query: str, results: list[dict]) -> bool:
    focus_terms = _extract_focus_terms(query)
    if len(focus_terms) != 1:
        return False

    subject = focus_terms[0]
    authoritative_markers = ("wikipedia.org", "britannica.com", "larousse.fr", "universalis.fr")
    for result in results:
        title = (result.get("title") or "").lower()
        href = (result.get("href") or "").lower()
        if not any(marker in href for marker in authoritative_markers):
            continue
        if subject in title:
            return True
    return False


def enrich_sync(query: str, llm) -> tuple[str | None, Path | None, list[dict], bool]:
    """
    Recherche web synchrone.
    Retourne (answer, insight_path, sources_list, quality_ok).
    """
    search_query = _build_search_query(query, llm)
    instant_results = _ddg_instant_answer_search(search_query)
    ddg_results = _ddg_search(search_query)
    results = _merge_search_results(instant_results, ddg_results)
    if not results:
        return None, None, [], False
    answer = _synthesize(query, results, llm)
    if not answer:
        return None, None, results, False
    quality_ok = _check_quality(query, answer, results, llm)
    if not quality_ok:
        logger.warning(f"WebSearch qualité insuffisante pour : {query!r:.60} — résultat rejeté")
        return None, None, results, False
    path = _save_insight(query, answer, results)
    return answer, path, results, quality_ok


def enrich_async(query: str, llm, on_done=None) -> None:
    """
    Lance la recherche+synthèse en arrière-plan (thread daemon).
    `on_done(answer, path, results, quality_ok)` est appelé à la fin.
    """
    def _run():
        answer, path, results, quality_ok = enrich_sync(query, llm)
        if on_done:
            try:
                on_done(answer, path, results, quality_ok)
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True, name="web-enrich").start()
