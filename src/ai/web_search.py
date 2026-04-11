"""
Enrichissement web — recherche DuckDuckGo + synthèse LLM + sauvegarde insight.

Déclenché automatiquement quand le RAG répond "Cette information n'est pas dans
ton coffre." : une recherche web est lancée en arrière-plan, le LLM synthétise
les résultats, et un insight Markdown est écrit dans obsirag/web_insights/.
"""
from __future__ import annotations

import re
import threading
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
    "please", "s'il", "te", "plait", "propos",
}
_GENERIC_REQUEST_RE = re.compile(
    r"^\s*(?:parle(?:-?moi)?\s+de|dis(?:-?moi)?\s+.+?\s+sur|dis(?:-?moi)?\s+.+?\s+de|"
    r"que\s+sais[- ]?tu\s+de|que\s+peux[- ]?tu\s+me\s+dire\s+de|présente(?:-?moi)?|"
    r"raconte(?:-?moi)?|explique(?:-?moi)?)\b",
    re.I,
)


def is_not_in_vault(response: str) -> bool:
    """Retourne True uniquement si la réponse est le hard sentinel pur.

    Une réponse mixte qui commence par le sentinel mais contient ensuite une
    synthèse utile du coffre ne doit PAS déclencher la recherche web."""
    low = response.strip().lower().rstrip(".")
    return low == _SENTINEL


def _web_insights_dir() -> Path:
    d = settings.vault_obsirag_dir / "web_insights"
    d.mkdir(parents=True, exist_ok=True)
    return d


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
        _META_WORDS = {"recherche", "chercher", "trouver", "comment", "search", "find",
                       "look", "how", "to", "do"}
        first_words = {w.lower() for w in q.split()[:3]}
        is_short_but_valid = len(q) >= 3 and len(q.split()) <= 3 and any(term in q.lower() for term in focus_terms)
        if (len(q) < 5 and not is_short_but_valid) or first_words & _META_WORDS:
            fallback_query = normalized_question if focus_terms else user_question
            logger.warning(f"WebSearch requête reformulée rejetée : {q!r} → fallback sur {fallback_query!r}")
            return fallback_query
        logger.info(f"WebSearch requête reformulée : {q!r} (original: {user_question[:60]!r})")
        return q
    except Exception:
        return _normalize_user_query_for_search(user_question)


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
    if "知乎" not in query:
        candidate_queries.append(f"{query} -知乎")
    if "wikipedia" not in query.lower() and len(query.split()) <= 3:
        candidate_queries.append(f"{query} wikipedia")

    try:
        from duckduckgo_search import DDGS
        best_results: list[dict] = []
        best_score = -1
        for candidate_query in candidate_queries:
            with DDGS() as ddgs:
                # region=fr-fr : priorité aux sources francophones/européennes
                # safesearch=off : pas de filtre superflu sur un usage personnel
                raw = list(ddgs.text(
                    candidate_query,
                    region="fr-fr",
                    safesearch="off",
                    max_results=max_results + 3,  # marge pour le filtrage
                ))
            filtered = [
                r for r in raw
                if _is_latin_text(r.get('title', '')) and _is_latin_text(r.get('body', ''))
            ]
            result = filtered[:max_results]
            score = _score_search_results(query, candidate_query, result)
            logger.info(
                f"WebSearch DDG: requête={candidate_query!r} {len(raw)} résultats bruts, {len(result)} après filtrage, score={score}"
            )
            if score > best_score:
                best_score = score
                best_results = result
        return best_results
    except Exception as exc:
        logger.warning(f"WebSearch DDG error: {exc}")
        return []


def _score_search_results(original_query: str, candidate_query: str, results: list[dict]) -> int:
    if not results:
        return -1

    focus_terms = _extract_focus_terms(original_query)
    corpus = " ".join(
        f"{item.get('title', '')} {item.get('body', '')} {item.get('href', '')}"
        for item in results
    ).lower()
    overlap = sum(1 for term in focus_terms if term in corpus)

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
        1
        for item in results
        if any(term in (item.get('title', '') or '').lower() for term in focus_terms)
    )
    return overlap * 10 + encyclopedic_hits * 4 + title_hits * 2 + min(len(results), 3) + candidate_bonus


# ---------------------------------------------------------------------------
# Synthèse LLM
# ---------------------------------------------------------------------------

def _build_snippets(results: list[dict]) -> str:
    """Construit le bloc de snippets web utilisé pour synthèse et contrôle qualité."""
    return "\n\n".join(
        f"**{r.get('title', '')}** ({r.get('href', '')})\n{r.get('body', '')}"
        for r in results
    )

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


def _save_insight(query: str, answer: str, results: list[dict]) -> Path:
    """Écrit l'insight web dans obsirag/web_insights/."""
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = _safe_filename(query)
    filename = f"web_{slug}_{date_str}.md"
    out_path = _web_insights_dir() / filename

    sources_md = "\n".join(
        f"- [{r.get('title', r.get('href',''))}]({r.get('href','')})"
        for r in results
    )

    content = (
        "---\n"
        "tags:\n"
        "  - web_insight\n"
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
    results = _ddg_search(search_query)
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
