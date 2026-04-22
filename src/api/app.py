from __future__ import annotations

import asyncio
import json
import queue
import re
import sqlite3
import subprocess
import sys
import time
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

import frontmatter
import networkx as nx
from loguru import logger
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.ai.euria_client import EuriaClient
from src.ai.mermaid_sanitizer import sanitize_mermaid_blocks
from src.ai.web_search import (
    _ddg_instant_answer_search,
    _ddg_search,
    _format_query_overview_markdown,
    _keywordize_query,
    _merge_search_results,
    build_query_overview_from_results_sync,
    build_query_overview_sync,
    is_not_in_vault,
)
from src.api.conversation_store import ApiConversationStore
from src.api.runtime import ensure_service_manager_started, get_service_manager
from src.api.schemas import (
    AutolearnStatusModel,
    ChatMessageModel,
    ConversationDetailModel,
    ConversationSummaryModel,
    CreateConversationRequest,
    DdgKnowledgeModel,
    DetectSynapsesResponseModel,
    EntityContextModel,
    GraphDataModel,
    GraphEdgeModel,
    GraphFilterOptionsModel,
    GraphLegendItemModel,
    GraphMetricsModel,
    GraphNoteOptionModel,
    GraphNodeModel,
    GraphSpotlightItemModel,
    GraphSummaryCountModel,
    GraphTopNodeModel,
    HealthResponse,
    InsightItemModel,
    MessageCreateRequest,
    NoteDetailModel,
    QueryOverviewModel,
    RelatedNoteModel,
    ReindexResponseModel,
    RuntimeInfoModel,
    SaveConversationResponse,
    SessionRequest,
    SessionResponse,
    SourceRefModel,
    StartupStatusModel,
    SystemAlertModel,
    SystemStatusResponse,
    WebSearchRequestModel,
    WebSearchResponseModel,
)
from src.config import settings
from src.graph.builder import GraphBuilder
from src.learning.runtime_state import load_autolearn_runtime_state
from src.storage.json_state import JsonStateStore
from src.storage.safe_read import read_text_file
from src.ui import brain_explorer
from src.ui.note_badges import get_note_type, get_note_type_options
from src.ui.note_viewer import extract_note_outline, strip_frontmatter
from src.ui.path_resolver import normalize_vault_relative_path, resolve_vault_path

app = FastAPI(title="ObsiRAG API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

conversation_store = ApiConversationStore()

STREAM_PREPARATION_STEPS: list[tuple[str, str]] = [
    ("analysis", "Analyse de la requete"),
    ("context", "Preparation du contexte"),
    ("generation", "Generation de la reponse"),
]

STREAM_ENRICHMENT_STEPS: list[tuple[str, str]] = [
    ("entities", "Extraction des entites NER"),
    ("web", "Recherche sur le web en cours..."),
    ("finalize", "Finalisation de la reponse"),
]

_TRAILING_MARKDOWN_ARTIFACT_LINE_RE = re.compile(
    r"^\s*(?:[>\-–—→]+\s*)?(?:\*{2,}|_{2,}|`{3,}|~{3,})\s*$"
)
_SIMPLE_ITALIC_WITH_EXTRA_CLOSING_STARS_RE = re.compile(r"(?<!\*)\*([^*\n]+?)\*{3}(?=$|[\s\).,;:!?])")
_GLUED_UPPERCASE_TITLE_PREFIX_RE = re.compile(r"\b(DE|DU|DES|LE|LA|LES|ET)(?=[A-ZÀ-ÖØ-Þ]{3,})")


def _collapse_repeated_line_blocks(text: str, *, max_block_size: int = 4) -> str:
    lines = text.split("\n")
    if len(lines) < 2:
        return text

    normalized = [re.sub(r"\s+", " ", line).strip() for line in lines]
    kept: list[str] = []
    kept_normalized: list[str] = []
    index = 0

    while index < len(lines):
        collapsed = False
        for block_size in range(min(max_block_size, (len(lines) - index) // 2), 0, -1):
            current_block = normalized[index:index + block_size]
            next_block = normalized[index + block_size:index + (2 * block_size)]
            if not current_block or current_block != next_block:
                continue
            kept.extend(lines[index:index + block_size])
            kept_normalized.extend(current_block)
            index += block_size * 2
            while index + block_size <= len(lines) and normalized[index:index + block_size] == current_block:
                index += block_size
            collapsed = True
            break
        if collapsed:
            continue
        kept.append(lines[index])
        kept_normalized.append(normalized[index])
        index += 1

    deduped_lines: list[str] = []
    previous_normalized = None
    for raw_line, normalized_line in zip(kept, kept_normalized, strict=False):
        if normalized_line and normalized_line == previous_normalized:
            continue
        deduped_lines.append(raw_line)
        previous_normalized = normalized_line or None
    return "\n".join(deduped_lines)


class _SinglePageAppFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
        return await super().get_response("index.html", scope)


def _slugify_note_candidate(value: str) -> str:
    normalized = unicodedata.normalize("NFD", str(value or "").strip().lower())
    normalized = "".join(character for character in normalized if unicodedata.category(character) != "Mn")
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    return normalized.strip("-")


def _resolve_note_path_identifier(note_path: str, svc) -> tuple[str, dict[str, Any] | None]:
    normalized = normalize_vault_relative_path(note_path)
    if not normalized:
        return normalized, None

    exact_candidates = [normalized]
    if not normalized.endswith(".md"):
        exact_candidates.append(f"{normalized}.md")

    for candidate in exact_candidates:
        note = svc.chroma.get_note_by_file_path(candidate)
        if note is not None:
            return candidate, note

    target_stem = Path(normalized).stem.lower()
    target_slug = _slugify_note_candidate(Path(normalized).stem)
    matches: list[tuple[str, dict[str, Any]]] = []

    for note in svc.chroma.list_notes():
        file_path = normalize_vault_relative_path(str(note.get("file_path") or ""))
        if not file_path:
            continue

        stem = Path(file_path).stem
        title = str(note.get("title") or stem)
        aliases = {
            file_path.lower(),
            stem.lower(),
            _slugify_note_candidate(stem),
            _slugify_note_candidate(title),
        }
        if target_stem in aliases or target_slug in aliases:
            matches.append((file_path, note))

    if len(matches) == 1:
        return matches[0]

    exact_stem_matches = [match for match in matches if Path(match[0]).stem.lower() == target_stem]
    if len(exact_stem_matches) == 1:
        return exact_stem_matches[0]

    exact_slug_matches = [match for match in matches if _slugify_note_candidate(Path(match[0]).stem) == target_slug]
    if len(exact_slug_matches) == 1:
        return exact_slug_matches[0]

    return normalized, None


def _build_generation_stats(answer: str, started_at: float, *, ttft: float = 0.0) -> dict[str, float | int]:
    elapsed = max(time.perf_counter() - started_at, 0.001)
    token_count = len(answer.split())
    return {
        "tokens": token_count,
        "ttft": round(ttft, 3),
        "total": round(elapsed, 3),
        "tps": round(token_count / elapsed, 3),
    }


def _normalize_assistant_provenance(provenance: str | None) -> str:
    value = str(provenance or "").strip().lower()
    if value in {"web + coffre", "coffre + web", "coffre et web", "hybrid"}:
        return "hybrid"
    if value == "web":
        return "web"
    return "vault"


def _should_attempt_web_answer(answer: str, svc) -> bool:
    if is_not_in_vault(answer):
        return True

    learner = getattr(svc, "learner", None)
    is_weak_answer = getattr(learner, "_is_weak_answer", None)
    if callable(is_weak_answer):
        try:
            result = is_weak_answer(answer)
            return result if isinstance(result, bool) else False
        except Exception:
            return False
    return False


def _lookup_autolearn_web_results(user_text: str, svc) -> tuple[str, list[dict[str, Any]]]:
    if not user_text or len(user_text.strip()) < 3:
        return user_text, []

    learner = getattr(svc, "learner", None)
    autolearn_web_search = getattr(learner, "_web_search", None)
    if not callable(autolearn_web_search):
        return user_text, []

    search_query_builder = getattr(learner, "_build_web_search_query", None)
    search_query = user_text
    if callable(search_query_builder):
        built_query = str(search_query_builder(user_text) or "").strip()
        if built_query:
            search_query = built_query

    try:
        autolearn_results = autolearn_web_search(user_text)
    except Exception:
        return search_query, []
    return search_query, autolearn_results if isinstance(autolearn_results, list) else []


def _sanitize_assistant_answer_text(answer: str) -> str:
    original = str(answer or "")
    cleaned = original.replace("\r\n", "\n")
    lines = cleaned.split("\n")
    while lines and _TRAILING_MARKDOWN_ARTIFACT_LINE_RE.fullmatch(lines[-1] or ""):
        lines.pop()
    cleaned = "\n".join(lines)
    cleaned = re.sub(
        r"(?:\s+(?:[>\-–—→]+\s*)?(?:\*{2,}|_{2,}|`{3,}|~{3,})\s*)+$",
        "",
        cleaned,
    )
    cleaned = re.sub(r"(?<=[0-9A-Za-zÀ-ÖØ-öø-ÿ])\(", " (", cleaned)
    cleaned = re.sub(r"\)(?=[0-9A-Za-zÀ-ÖØ-öø-ÿ])", ") ", cleaned)
    cleaned = re.sub(r"(?<=[a-zà-öø-ÿ])(?=[A-ZÀ-ÖØ-Þ])", " ", cleaned)
    cleaned = _GLUED_UPPERCASE_TITLE_PREFIX_RE.sub(r"\1 ", cleaned)
    cleaned = re.sub(r"\b(leurs?)(?=[a-zà-öø-ÿ]{4,})", r"\1 ", cleaned)
    cleaned = _SIMPLE_ITALIC_WITH_EXTRA_CLOSING_STARS_RE.sub(r"*\1*", cleaned)
    cleaned = _collapse_repeated_line_blocks(cleaned)
    cleaned = re.sub(r" {2,}", " ", cleaned)
    cleaned = cleaned.strip()
    return cleaned or original.strip()


def _build_web_result_snippets(results: list[dict[str, Any]], *, max_results: int = 5) -> str:
    snippets: list[str] = []
    for item in results[:max_results]:
        href = str(item.get("href") or "").strip()
        title = str(item.get("title") or href or "Source web").strip()
        body = str(item.get("full_text") or item.get("body") or "").strip()
        if not body:
            continue
        snippets.append(f"**{title}** ({href})\n{body}")
    return "\n\n".join(snippets)


def _try_euria_native_web_answer(query: str, llm) -> str | None:
    if not isinstance(llm, EuriaClient):
        return None

    prompt = (
        f"Question : « {query} »\n\n"
        "Fais une recherche web et donne une première réponse utile en français. "
        "Reste factuel, signale l'incertitude si les résultats sont incomplets, et réponds uniquement avec la réponse."
    )
    try:
        answer = llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=900,
            operation="euria_native_web",
            enable_web_search=True,
        )
    except Exception as exc:
        logger.warning("Euria native web search unavailable for {!r}: {}", query, exc)
        return None

    cleaned = _sanitize_assistant_answer_text(answer)
    return cleaned or None


def _merge_euria_native_answer_with_ddg(
    *,
    query: str,
    native_answer: str,
    search_query: str,
    web_results: list[dict[str, Any]],
    rag_context: str,
    llm,
) -> str | None:
    snippets = _build_web_result_snippets(web_results)
    if not snippets:
        return native_answer

    prompt = (
        f"Question initiale : « {query} »\n"
        f"Requête DDG : « {search_query} »\n\n"
        "Première réponse issue de la recherche web native Euria :\n"
        f"{native_answer}\n\n"
        "Contexte du coffre (à utiliser seulement s'il apporte un complément pertinent) :\n"
        f"{rag_context or 'Aucun contexte utile du coffre.'}\n\n"
        "Résultats DDG complémentaires :\n"
        f"{snippets}\n\n"
        "Réécris une réponse finale en français. "
        "Conserve les éléments déjà corrects de la réponse Euria, complète-la avec les résultats DDG, "
        "corrige ce qui doit l'être, et cite les sources web entre [crochets]. "
        "N'invente rien au-delà des éléments fournis. Réponds uniquement avec la version finale."
    )
    try:
        answer = llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1100,
            operation="euria_ddg_completion",
            enable_web_search=False,
        )
    except Exception as exc:
        logger.warning("Euria DDG completion failed for {!r}: {}", query, exc)
        return None

    cleaned = _sanitize_assistant_answer_text(answer)
    return cleaned or None


def _merge_euria_native_overview(
    query: str,
    native_answer: str | None,
    overview: dict[str, Any],
    llm,
) -> dict[str, Any]:
    normalized_overview = dict(overview or {})
    if not native_answer:
        if normalized_overview.get("summary"):
            normalized_overview["summary"] = _sanitize_assistant_answer_text(str(normalized_overview.get("summary") or ""))
        return normalized_overview

    if not isinstance(llm, EuriaClient):
        if not normalized_overview:
            return {
                "query": query,
                "search_query": query,
                "summary": native_answer,
                "sources": [],
            }
        normalized_overview["summary"] = _sanitize_assistant_answer_text(str(normalized_overview.get("summary") or native_answer))
        return normalized_overview

    if not normalized_overview:
        return {
            "query": query,
            "search_query": query,
            "summary": native_answer,
            "sources": [],
        }

    sources_block = "\n".join(
        f"- {item.get('title') or item.get('href') or 'Source'} ({item.get('href') or ''})"
        for item in (normalized_overview.get("sources") or [])[:8]
        if item.get("href") or item.get("title")
    )
    prompt = (
        f"Question initiale : « {query} »\n"
        f"Première réponse web native Euria :\n{native_answer}\n\n"
        "Vue d'ensemble DDG actuelle :\n"
        f"{normalized_overview.get('summary') or ''}\n\n"
        "Sources DDG disponibles :\n"
        f"{sources_block or '- aucune source exploitable'}\n\n"
        "Fusionne ces deux apports en une vue d'ensemble finale en français. "
        "Format attendu : un court paragraphe d'ensemble puis 3 à 5 puces factuelles. "
        "Quand une information vient des sources DDG, cite-la entre [crochets]. "
        "Réponds uniquement avec la vue d'ensemble finale."
    )
    try:
        merged_summary = llm.chat(
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=950,
            operation="euria_ddg_overview_merge",
            enable_web_search=False,
        )
    except Exception as exc:
        logger.warning("Euria overview merge failed for {!r}: {}", query, exc)
        normalized_overview["summary"] = _sanitize_assistant_answer_text(str(normalized_overview.get("summary") or native_answer))
        return normalized_overview

    normalized_overview["summary"] = _sanitize_assistant_answer_text(merged_summary)
    return normalized_overview


def _build_query_overview_from_autolearn_results(
    user_text: str,
    svc,
    web_results: list[dict[str, Any]] | None = None,
    llm=None,
) -> dict[str, Any]:
    search_query, autolearn_results = _lookup_autolearn_web_results(user_text, svc)
    candidate_results = web_results if isinstance(web_results, list) and web_results else autolearn_results
    if not candidate_results:
        return {}

    try:
        result = build_query_overview_from_results_sync(
            user_text,
            search_query,
            candidate_results,
            llm or svc.llm,
        )
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


def _compose_assistant_web_answer(
    *,
    prompt: str,
    answer: str,
    sources: list[dict],
    svc,
    force: bool = False,
    llm=None,
) -> dict[str, Any]:
    payload = {
        "answer": _sanitize_assistant_answer_text(answer),
        "sources": list(sources or []),
        "query_overview": {},
        "provenance": "vault",
        "enrichment_path": None,
    }

    def _apply_native_web_fallback(*, overview: dict[str, Any] | None = None, search_query: str | None = None) -> dict[str, Any]:
        if not native_web_answer:
            return payload
        payload["answer"] = native_web_answer
        payload["provenance"] = "web"
        payload["query_overview"] = overview or {
            "query": prompt,
            "search_query": search_query or prompt,
            "summary": native_web_answer,
            "sources": [],
        }
        payload["enrichment_path"] = (
            f"euria-native+ddg:{search_query}"
            if search_query and search_query != prompt
            else "euria-native-web"
        )
        return payload

    if not force and not _should_attempt_web_answer(answer, svc):
        return payload

    native_web_answer = _try_euria_native_web_answer(prompt, llm)
    search_query, web_results = _lookup_autolearn_web_results(prompt, svc)
    if native_web_answer and not web_results:
        return _apply_native_web_fallback()
    if not web_results:
        return payload

    learner = getattr(svc, "learner", None)
    snippets_relevant = getattr(learner, "_snippets_relevant", None)
    question_answering = getattr(learner, "_question_answering", None)
    build_rag_context = getattr(question_answering, "_build_rag_context", None)
    compose_web_answer = getattr(question_answering, "_compose_web_answer", None)
    grounded_check = getattr(question_answering, "_is_grounded_web_answer", None)
    is_weak_answer = getattr(learner, "_is_weak_answer", None)

    snippets = [
        str(item.get("full_text") or item.get("body") or "").strip()
        for item in web_results
        if str(item.get("full_text") or item.get("body") or "").strip()
    ]
    payload["query_overview"] = _merge_euria_native_overview(
        prompt,
        native_web_answer,
        _build_query_overview_from_autolearn_results(prompt, svc, web_results, llm=llm),
        llm,
    )

    if not snippets:
        return _apply_native_web_fallback(overview=payload["query_overview"], search_query=search_query)

    if callable(snippets_relevant):
        try:
            if not snippets_relevant(prompt, snippets):
                return _apply_native_web_fallback(overview=payload["query_overview"], search_query=search_query)
        except Exception:
            return _apply_native_web_fallback(overview=payload["query_overview"], search_query=search_query)

    if not callable(build_rag_context) or not callable(compose_web_answer):
        return _apply_native_web_fallback(overview=payload["query_overview"], search_query=search_query)

    try:
        rag_context, rag_sources = build_rag_context(prompt)
        compose_sources = list(sources or rag_sources or [])
        if native_web_answer and isinstance(llm, EuriaClient):
            enriched_answer = _merge_euria_native_answer_with_ddg(
                query=prompt,
                native_answer=native_web_answer,
                search_query=search_query,
                web_results=web_results,
                rag_context=rag_context,
                llm=llm,
            )
            enriched_sources = compose_sources
            used_web_results = web_results
            provenance = "Web + Coffre" if compose_sources else "Web"
        else:
            enriched_answer, enriched_sources, used_web_results, provenance = compose_web_answer(
                prompt,
                rag_context,
                compose_sources,
                snippets,
                web_results,
            )
    except Exception:
        return _apply_native_web_fallback(overview=payload["query_overview"], search_query=search_query)

    if not str(enriched_answer or "").strip():
        return _apply_native_web_fallback(overview=payload["query_overview"], search_query=search_query)

    enriched_answer = _sanitize_assistant_answer_text(str(enriched_answer))
    if not enriched_answer:
        return _apply_native_web_fallback(overview=payload["query_overview"], search_query=search_query)

    if callable(grounded_check):
        try:
            if str(provenance or "").strip() != "Coffre" and not grounded_check(enriched_answer, snippets):
                return _apply_native_web_fallback(overview=payload["query_overview"], search_query=search_query)
        except Exception:
            return _apply_native_web_fallback(overview=payload["query_overview"], search_query=search_query)

    if callable(is_weak_answer):
        try:
            if is_weak_answer(enriched_answer):
                return _apply_native_web_fallback(overview=payload["query_overview"], search_query=search_query)
        except Exception:
            return _apply_native_web_fallback(overview=payload["query_overview"], search_query=search_query)

    final_web_results = used_web_results if isinstance(used_web_results, list) and used_web_results else web_results
    payload["query_overview"] = _merge_euria_native_overview(
        prompt,
        native_web_answer,
        _build_query_overview_from_autolearn_results(prompt, svc, final_web_results, llm=llm),
        llm,
    )
    payload["answer"] = enriched_answer
    payload["sources"] = list(enriched_sources or sources or [])
    payload["provenance"] = _normalize_assistant_provenance(provenance)
    payload["enrichment_path"] = (
        f"euria-native+ddg:{search_query}"
        if native_web_answer and isinstance(llm, EuriaClient)
        else f"autolearn-web:{search_query}"
    )
    return payload


def _can_build_local_rag_context(svc) -> bool:
    learner = getattr(svc, "learner", None)
    question_answering = getattr(learner, "_question_answering", None)
    build_rag_context = getattr(question_answering, "_build_rag_context", None)
    return callable(build_rag_context)


def _build_local_rag_context(prompt: str, svc) -> tuple[str, list[dict[str, Any]]]:
    learner = getattr(svc, "learner", None)
    question_answering = getattr(learner, "_question_answering", None)
    build_rag_context = getattr(question_answering, "_build_rag_context", None)
    if not callable(build_rag_context):
        return "", []

    try:
        rag_context, rag_sources = build_rag_context(prompt)
    except Exception:
        return "", []

    return str(rag_context or "").strip(), list(rag_sources or [])


def _should_skip_euria_rag(prompt: str) -> bool:
    normalized = str(prompt or "").strip().lower()
    if not normalized or len(normalized) < 8:
        return True

    return bool(re.fullmatch(r"(?:salut|bonjour|bonsoir|merci|hello|hey|ok|merci beaucoup)[ !?.]*", normalized))


def _build_rag_source_titles(rag_sources: list[dict[str, Any]]) -> str:
    titles: list[str] = []
    for item in rag_sources:
        metadata = item.get("metadata") if isinstance(item, dict) else None
        title = ""
        if isinstance(metadata, dict):
            title = str(metadata.get("note_title") or Path(str(metadata.get("file_path") or "")).stem).strip()
        if title and title not in titles:
            titles.append(title)
    return ", ".join(f"[{title}]" for title in titles[:8])


def _generate_euria_rag_answer(
    *,
    prompt: str,
    history: list[dict[str, str]],
    llm,
    rag_context: str,
    rag_sources: list[dict[str, Any]],
) -> dict[str, Any]:
    source_titles = _build_rag_source_titles(rag_sources)
    messages = [
        {
            "role": "system",
            "content": (
                "Tu réponds en français, avec du Markdown valide et propre. "
                "Appuie-toi d'abord sur le contexte du coffre fourni. "
                "N'invente aucune information absente du contexte. "
                "Si l'information demandée n'est pas dans le contexte, réponds exactement : "
                '"Cette information n\'est pas dans ton coffre." '
                "Quand tu utilises une note du coffre, cite son titre entre crochets. "
                "Ne répète jamais une ligne, un paragraphe ou une section."
            ),
        },
        *[
            {"role": str(item.get("role") or "user"), "content": str(item.get("content") or "")}
            for item in history
            if str(item.get("content") or "").strip()
        ],
        {
            "role": "user",
            "content": (
                "Contexte du coffre :\n"
                f"{rag_context}\n\n"
                f"Notes disponibles : {source_titles or 'non precisees'}\n\n"
                f"Question : {prompt}"
            ),
        },
    ]
    answer = llm.chat(
        messages,
        temperature=0.2,
        max_tokens=1700,
        operation="conversation_euria_rag",
        enable_web_search=False,
    )
    cleaned_answer = _sanitize_assistant_answer_text(answer)
    if not cleaned_answer:
        raise RuntimeError("Euria n'a renvoyé aucune réponse exploitable.")
    return {
        "answer": cleaned_answer,
        "sources": list(rag_sources or []),
        "provenance": "vault",
        "query_overview": {},
        "entity_contexts": [],
        "enrichment_path": "euria-rag",
        "rag_lookup_attempted": True,
        "rag_context_used": True,
    }


def _maybe_upgrade_euria_result_with_web_fallback(*, prompt: str, result: dict[str, Any], llm, svc) -> dict[str, Any]:
    answer = str(result.get("answer") or "")
    if not _should_attempt_web_answer(answer, svc):
        return result

    web_result = _compose_assistant_web_answer(
        prompt=prompt,
        answer=answer,
        sources=[],
        svc=svc,
        force=True,
        llm=llm,
    )
    normalized_provenance = _normalize_assistant_provenance(str(web_result.get("provenance") or ""))
    web_answer = _sanitize_assistant_answer_text(str(web_result.get("answer") or ""))
    if not web_answer or normalized_provenance not in {"web", "hybrid"} or is_not_in_vault(web_answer):
        return result

    web_result["answer"] = web_answer
    web_result["provenance"] = "web"
    web_result["sources"] = []
    web_result["rag_lookup_attempted"] = True
    web_result["rag_context_used"] = False
    return web_result


def _build_post_answer_reference_query(prompt: str, answer: str) -> str:
    normalized_prompt = str(prompt or "").strip()
    normalized_answer = re.sub(r"\s+", " ", str(answer or "")).strip()
    if len(normalized_answer) > 600:
        normalized_answer = normalized_answer[:600].rstrip()
    return "\n\n".join(part for part in (normalized_prompt, normalized_answer) if part)


def _maybe_attach_local_vault_references(*, prompt: str, answer: str, result: dict[str, Any], svc) -> dict[str, Any]:
    if list(result.get("sources") or []):
        return result
    if _should_skip_euria_rag(prompt):
        return result

    reference_query = _build_post_answer_reference_query(prompt, answer)
    if not reference_query:
        return result

    _rag_context, rag_sources = _build_local_rag_context(reference_query, svc)
    if not rag_sources:
        return result

    enriched_result = dict(result)
    enriched_result["sources"] = list(rag_sources)
    enriched_result["rag_lookup_attempted"] = True
    enriched_result.setdefault("rag_context_used", False)
    return enriched_result


def _has_post_response_vault_references(*, payload, assistant_message: ChatMessageModel) -> bool:
    return bool(
        not payload.useRag
        and assistant_message.provenance == "web"
        and assistant_message.enrichmentPath == "euria-direct-web"
        and assistant_message.sources
    )


def _generate_euria_answer_with_optional_rag(*, prompt: str, history: list[dict[str, str]], llm, svc) -> dict[str, Any]:
    if _should_skip_euria_rag(prompt):
        result = _generate_euria_direct_answer(prompt=prompt, history=history, llm=llm)
        result.setdefault("rag_lookup_attempted", False)
        result.setdefault("rag_context_used", False)
        return _maybe_upgrade_euria_result_with_web_fallback(prompt=prompt, result=result, llm=llm, svc=svc)

    rag_context, rag_sources = _build_local_rag_context(prompt, svc)
    if rag_context:
        rag_result = _generate_euria_rag_answer(
            prompt=prompt,
            history=history,
            llm=llm,
            rag_context=rag_context,
            rag_sources=rag_sources,
        )
        web_fallback_result = _maybe_upgrade_euria_result_with_web_fallback(prompt=prompt, result=rag_result, llm=llm, svc=svc)
        if web_fallback_result is not rag_result:
            return web_fallback_result
        rag_result.setdefault("rag_lookup_attempted", True)
        rag_result.setdefault("rag_context_used", True)
        return rag_result

    result = _generate_euria_direct_answer(prompt=prompt, history=history, llm=llm)
    result.setdefault("rag_lookup_attempted", _can_build_local_rag_context(svc))
    result.setdefault("rag_context_used", False)
    return _maybe_upgrade_euria_result_with_web_fallback(prompt=prompt, result=result, llm=llm, svc=svc)


def _can_build_local_rag_context(svc) -> bool:
    learner = getattr(svc, "learner", None)
    question_answering = getattr(learner, "_question_answering", None)
    build_rag_context = getattr(question_answering, "_build_rag_context", None)
    return callable(build_rag_context)


def _build_local_rag_context(prompt: str, svc) -> tuple[str, list[dict[str, Any]]]:
    learner = getattr(svc, "learner", None)
    question_answering = getattr(learner, "_question_answering", None)
    build_rag_context = getattr(question_answering, "_build_rag_context", None)
    if not callable(build_rag_context):
        return "", []

    try:
        rag_context, rag_sources = build_rag_context(prompt)
    except Exception:
        return "", []

    return str(rag_context or "").strip(), list(rag_sources or [])


def _should_skip_euria_rag(prompt: str) -> bool:
    normalized = str(prompt or "").strip().lower()
    if not normalized or len(normalized) < 8:
        return True

    return bool(re.fullmatch(r"(?:salut|bonjour|bonsoir|merci|hello|hey|ok|merci beaucoup)[ !?.]*", normalized))


def _build_rag_source_titles(rag_sources: list[dict[str, Any]]) -> str:
    titles: list[str] = []
    for item in rag_sources:
        metadata = item.get("metadata") if isinstance(item, dict) else None
        title = ""
        if isinstance(metadata, dict):
            title = str(metadata.get("note_title") or Path(str(metadata.get("file_path") or "")).stem).strip()
        if title and title not in titles:
            titles.append(title)
    return ", ".join(f"[{title}]" for title in titles[:8])


def _generate_euria_rag_answer(
    *,
    prompt: str,
    history: list[dict[str, str]],
    llm,
    rag_context: str,
    rag_sources: list[dict[str, Any]],
) -> dict[str, Any]:
    source_titles = _build_rag_source_titles(rag_sources)
    messages = [
        {
            "role": "system",
            "content": (
                "Tu réponds en français, avec du Markdown valide et propre. "
                "Appuie-toi d'abord sur le contexte du coffre fourni. "
                "N'invente aucune information absente du contexte. "
                "Si l'information demandée n'est pas dans le contexte, réponds exactement : "
                '"Cette information n\'est pas dans ton coffre." '
                "Quand tu utilises une note du coffre, cite son titre entre crochets. "
                "Ne répète jamais une ligne, un paragraphe ou une section."
            ),
        },
        *[
            {"role": str(item.get("role") or "user"), "content": str(item.get("content") or "")}
            for item in history
            if str(item.get("content") or "").strip()
        ],
        {
            "role": "user",
            "content": (
                "Contexte du coffre :\n"
                f"{rag_context}\n\n"
                f"Notes disponibles : {source_titles or 'non precisees'}\n\n"
                f"Question : {prompt}"
            ),
        },
    ]
    answer = llm.chat(
        messages,
        temperature=0.2,
        max_tokens=1700,
        operation="conversation_euria_rag",
        enable_web_search=False,
    )
    cleaned_answer = _sanitize_assistant_answer_text(answer)
    if not cleaned_answer:
        raise RuntimeError("Euria n'a renvoyé aucune réponse exploitable.")
    return {
        "answer": cleaned_answer,
        "sources": list(rag_sources or []),
        "provenance": "vault",
        "query_overview": {},
        "entity_contexts": [],
        "enrichment_path": "euria-rag",
        "rag_lookup_attempted": True,
        "rag_context_used": True,
    }


def _generate_euria_answer_with_optional_rag(*, prompt: str, history: list[dict[str, str]], llm, svc) -> dict[str, Any]:
    if _should_skip_euria_rag(prompt):
        result = _generate_euria_direct_answer(prompt=prompt, history=history, llm=llm)
        result.setdefault("rag_lookup_attempted", False)
        result.setdefault("rag_context_used", False)
        return _maybe_upgrade_euria_result_with_web_fallback(prompt=prompt, result=result, llm=llm, svc=svc)

    rag_context, rag_sources = _build_local_rag_context(prompt, svc)
    if rag_context:
        rag_result = _generate_euria_rag_answer(
            prompt=prompt,
            history=history,
            llm=llm,
            rag_context=rag_context,
            rag_sources=rag_sources,
        )
        web_fallback_result = _maybe_upgrade_euria_result_with_web_fallback(prompt=prompt, result=rag_result, llm=llm, svc=svc)
        if web_fallback_result is not rag_result:
            return web_fallback_result
        rag_result.setdefault("rag_lookup_attempted", True)
        rag_result.setdefault("rag_context_used", True)
        return rag_result

    result = _generate_euria_direct_answer(prompt=prompt, history=history, llm=llm)
    result.setdefault("rag_lookup_attempted", _can_build_local_rag_context(svc))
    result.setdefault("rag_context_used", False)
    return _maybe_upgrade_euria_result_with_web_fallback(prompt=prompt, result=result, llm=llm, svc=svc)


def _load_processing_status() -> dict[str, Any]:
    default = {"active": False, "note": "", "step": "", "log": []}
    return JsonStateStore(settings.processing_status_file).load(default)


def _load_indexing_status() -> dict[str, Any]:
    default = {"running": False, "processed": 0, "total": 0, "current": ""}
    payload = JsonStateStore(settings.data_dir / "stats" / "service_manager_status.json").load(default)
    return _normalize_indexing_status(payload)


def _normalize_indexing_status(payload: dict[str, Any] | None) -> dict[str, Any]:
    status = dict(payload or {})
    running = bool(status.get("running", False))
    processed = int(status.get("processed") or 0)
    total = int(status.get("total") or 0)
    current = str(status.get("current") or "").strip()

    if not running:
        current = "Indexation terminee" if total > 0 or processed > 0 else ""

    return {
        "running": running,
        "processed": processed,
        "total": total,
        "current": current,
    }


def _conversation_size_bytes(conversation: ConversationDetailModel) -> int:
    return len(conversation.model_dump_json().encode("utf-8"))


def _artifact_size_bytes(file_path: str) -> int | None:
    if not file_path:
        return None

    try:
        return resolve_vault_path(file_path, vault_root=settings.vault).stat().st_size
    except OSError:
        return None


def _with_conversation_size(conversation: ConversationDetailModel) -> ConversationDetailModel:
    return conversation.model_copy(update={"sizeBytes": _conversation_size_bytes(conversation)})


def _load_index_state() -> dict[str, str]:
    return JsonStateStore(settings.index_state_file).load({})


def _load_startup_status() -> dict[str, Any]:
    default = {"ready": False, "steps": [], "current_step": "", "error": None, "updated_at": None}
    return JsonStateStore(settings.startup_status_file).load(default)


def _has_meaningful_startup_payload(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("ready")
        or payload.get("steps")
        or str(payload.get("current_step") or "").strip()
        or str(payload.get("error") or "").strip()
        or str(payload.get("updated_at") or "").strip()
    )


def _infer_ready_startup_payload(indexing_status: dict[str, Any], index_state: dict[str, str]) -> dict[str, Any] | None:
    has_runtime_evidence = bool(
        index_state
        or int(indexing_status.get("processed") or 0) > 0
        or int(indexing_status.get("total") or 0) > 0
        or str(indexing_status.get("current") or "").strip()
    )
    if not has_runtime_evidence:
        return None

    updated_at = None
    status_file = settings.data_dir / "stats" / "service_manager_status.json"
    try:
        updated_at = datetime.fromtimestamp(status_file.stat().st_mtime, UTC).isoformat()
    except Exception:
        updated_at = None

    return {
        "ready": True,
        "steps": ["Initialisation du runtime ObsiRAG", "Préparation des services applicatifs", "Tous les services sont opérationnels"],
        "current_step": "Tous les services sont opérationnels",
        "error": None,
        "updated_at": updated_at,
    }


def _count_chunks_fast() -> int:
    db_path = settings.data_dir / "chroma" / "chroma.sqlite3"
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            row = con.execute(
                """
                SELECT COUNT(*)
                FROM embeddings e
                INNER JOIN segments s ON s.id = e.segment_id
                INNER JOIN collections c ON c.id = s.collection
                WHERE c.name = ?
                """,
                (settings.chroma_collection,),
            ).fetchone()
            return int(row[0] or 0) if row else 0
        finally:
            con.close()
    except Exception:
        return 0


def _resolve_autolearn_status(svc: Any | None = None) -> AutolearnStatusModel:
    processing_status = _load_processing_status()
    runtime_status = load_autolearn_runtime_state()

    next_run = runtime_status.get("nextRunAt")
    if not next_run and svc is not None:
        try:
            job = svc.learner._scheduler.get_job("autolearn_cycle")
            if job and job.next_run_time:
                next_run = job.next_run_time.isoformat()
        except Exception:
            next_run = None

    return AutolearnStatusModel(
        active=bool(processing_status.get("active", False)),
        managedBy=str(runtime_status.get("managedBy", "none")),
        running=bool(runtime_status.get("running", False)),
        pid=runtime_status.get("pid") if isinstance(runtime_status.get("pid"), int) else None,
        note=str(processing_status.get("note", "")),
        step=str(processing_status.get("step", "")),
        log=list(processing_status.get("log", []) or []),
        startedAt=runtime_status.get("startedAt"),
        updatedAt=runtime_status.get("updatedAt"),
        nextRunAt=next_run,
    )


def _resolve_startup_status() -> StartupStatusModel:
    payload = _load_startup_status()
    if not _has_meaningful_startup_payload(payload):
        inferred = _infer_ready_startup_payload(_load_indexing_status(), _load_index_state())
        if inferred is not None:
            payload = inferred
    return StartupStatusModel(
        ready=bool(payload.get("ready", False)),
        steps=[str(item) for item in (payload.get("steps") or []) if str(item).strip()],
        currentStep=str(payload.get("current_step") or ""),
        error=str(payload.get("error") or "").strip() or None,
        updatedAt=str(payload.get("updated_at") or "").strip() or None,
    )


def require_api_auth(authorization: str | None = Header(default=None)) -> None:
    expected = (settings.api_access_token or "").strip()
    if not expected:
        return

    provided = _extract_bearer_token(authorization)
    if provided != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session token")


@app.get("/api/v1/health", response_model=HealthResponse)
def health() -> HealthResponse:
    vector_available = True
    try:
        vector_available = get_service_manager().chroma.native_api_available()
    except Exception:
        vector_available = False
    return HealthResponse(
        status="ok",
        version="0.1.0",
        llmAvailable=True,
        vectorStoreAvailable=vector_available,
    )


@app.post("/api/v1/session", response_model=SessionResponse)
def create_session(payload: SessionRequest) -> SessionResponse:
    expected = (settings.api_access_token or "").strip()
    provided = (payload.accessToken or "").strip()
    if expected and provided != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session token")
    return SessionResponse(
        authenticated=True,
        requiresAuth=bool(expected),
        tokenPreview=_token_preview(provided or expected),
        backendUrlHint=settings.api_public_base_url,
        mode="token" if expected else "open",
    )


@app.get("/api/v1/session", response_model=SessionResponse)
def get_session(_: None = Depends(require_api_auth)) -> SessionResponse:
    expected = (settings.api_access_token or "").strip()
    return SessionResponse(
        authenticated=True,
        requiresAuth=bool(expected),
        tokenPreview=_token_preview(expected),
        backendUrlHint=settings.api_public_base_url,
        mode="token" if expected else "open",
    )


@app.get("/api/v1/system/status", response_model=SystemStatusResponse)
def system_status(_: None = Depends(require_api_auth)) -> SystemStatusResponse:
    ensure_service_manager_started()
    indexing_status = _load_indexing_status()
    index_state = _load_index_state()

    return SystemStatusResponse(
        backendReachable=True,
        llmAvailable=True,
        notesIndexed=len(index_state),
        chunksIndexed=_count_chunks_fast(),
        indexing=indexing_status,
        autolearn=_resolve_autolearn_status(),
        startup=_resolve_startup_status(),
        runtime=RuntimeInfoModel(
            llmProvider="MLX",
            llmModel=settings.mlx_chat_model,
            embeddingModel=settings.embedding_model,
            vectorStore="ChromaDB",
            nerModel=settings.ner_model,
            autolearnMode="worker" if settings.autolearn_enabled else "disabled",
            euriaProvider="Infomaniak" if settings.euria_url else None,
            euriaModel=EuriaClient.DEFAULT_MODEL if settings.euria_url else None,
            euriaEnabled=bool(settings.euria_url and settings.euria_bearer),
        ),
        alerts=[
            SystemAlertModel(
                id="api-runtime",
                level="info",
                title="API FastAPI active",
                description="Le backend Expo est demarre et peut servir le client mobile/web.",
            )
        ],
    )


@app.post("/api/v1/system/reindex", response_model=ReindexResponseModel)
def system_reindex(_: None = Depends(require_api_auth)) -> ReindexResponseModel:
    service_manager = get_service_manager()

    if bool(service_manager.indexing_status.get("running")):
        raise HTTPException(status_code=409, detail="Indexation deja en cours")

    persist_indexing_status = getattr(service_manager, "_persist_indexing_status", None)

    def _persist_status() -> None:
        if callable(persist_indexing_status):
            persist_indexing_status()

    def _on_progress(current: str, processed: int, total: int) -> None:
        service_manager.indexing_status.update({
            "running": True,
            "processed": processed,
            "total": total,
            "current": current,
        })
        _persist_status()

    service_manager.indexing_status.update({
        "running": True,
        "processed": 0,
        "total": 0,
        "current": "Reindexation demandee depuis Expo",
    })
    _persist_status()

    try:
        stats = service_manager.indexer.index_vault(on_progress=_on_progress)
    except Exception as exc:
        service_manager.indexing_status.update({
            "running": False,
            "current": f"Erreur d'indexation: {exc}",
        })
        _persist_status()
        raise HTTPException(status_code=500, detail=f"Reindexation impossible: {exc}") from exc

    notes_indexed = int(service_manager.chroma.count_notes())
    chunks_indexed = int(service_manager.chroma.count())
    service_manager.indexing_status.update({
        "running": False,
        "processed": notes_indexed,
        "total": notes_indexed,
        "current": "Indexation terminee",
    })
    _persist_status()

    return ReindexResponseModel(
        added=int(stats.get("added", 0)),
        updated=int(stats.get("updated", 0)),
        deleted=int(stats.get("deleted", 0)),
        skipped=int(stats.get("skipped", 0)),
        notesIndexed=notes_indexed,
        chunksIndexed=chunks_indexed,
        indexing=_normalize_indexing_status(service_manager.indexing_status),
    )


@app.get("/api/v1/conversations", response_model=list[ConversationSummaryModel])
def list_conversations(_: None = Depends(require_api_auth)) -> list[ConversationSummaryModel]:
    items = conversation_store.list()
    return [
        ConversationSummaryModel(
            id=item.id,
            title=item.title,
            preview=_conversation_preview(item),
            updatedAt=item.updatedAt,
            sizeBytes=_conversation_size_bytes(item),
            turnCount=len([message for message in item.messages if message.role == "user"]),
            messageCount=len(item.messages),
        )
        for item in sorted(items, key=lambda conv: conv.updatedAt, reverse=True)
    ]


@app.post("/api/v1/conversations", response_model=ConversationDetailModel)
def create_conversation(payload: CreateConversationRequest, _: None = Depends(require_api_auth)) -> ConversationDetailModel:
    return _with_conversation_size(conversation_store.create(payload.title))


@app.get("/api/v1/conversations/{conversation_id}", response_model=ConversationDetailModel)
def get_conversation(conversation_id: str, _: None = Depends(require_api_auth)) -> ConversationDetailModel:
    item = conversation_store.repair_unanswered_tail(conversation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return _with_conversation_size(item)


@app.delete("/api/v1/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, _: None = Depends(require_api_auth)) -> dict[str, bool]:
    deleted = conversation_store.delete(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"deleted": True}


@app.delete("/api/v1/conversations/{conversation_id}/messages/{message_id}", response_model=ConversationDetailModel)
def delete_conversation_message(
    conversation_id: str,
    message_id: str,
    _: None = Depends(require_api_auth),
) -> ConversationDetailModel:
    updated = conversation_store.delete_message(conversation_id, message_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return _with_conversation_size(updated)


@app.post("/api/v1/conversations/{conversation_id}/save", response_model=SaveConversationResponse)
def save_conversation(conversation_id: str, _: None = Depends(require_api_auth)) -> SaveConversationResponse:
    try:
        path = conversation_store.save_markdown(conversation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    return SaveConversationResponse(path=str(path.relative_to(settings.vault)))


@app.post("/api/v1/conversations/{conversation_id}/report", response_model=SaveConversationResponse)
def generate_conversation_report(conversation_id: str, _: None = Depends(require_api_auth)) -> SaveConversationResponse:
    svc = get_service_manager()
    svc.signal_ui_active()

    conversation = conversation_store.get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    title = _conversation_report_title(conversation)
    markdown = _generate_conversation_report_markdown(conversation, svc, default_title=title)

    try:
        path = conversation_store.save_report_markdown(conversation_id, markdown, title=title)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc

    try:
        svc.indexer.index_note(path)
        svc.chroma.invalidate_list_notes_cache()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Report created but indexing failed: {exc}") from exc

    return SaveConversationResponse(path=str(path.relative_to(settings.vault)))


@app.post("/api/v1/conversations/{conversation_id}/messages", response_model=ChatMessageModel)
async def create_message(
    conversation_id: str,
    payload: MessageCreateRequest,
    _: None = Depends(require_api_auth),
) -> ChatMessageModel:
    svc = get_service_manager()
    try:
        llm = _conversation_llm(svc, payload.useEuria)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    llm_provider = _conversation_llm_provider(payload.useEuria)
    user_message, history = _prepare_user_message(conversation_id, payload.prompt)
    conversation_store.append_messages(conversation_id, [user_message])

    started_at = time.perf_counter()
    if payload.useEuria:
        try:
            result = (
                _generate_euria_answer_with_optional_rag(prompt=payload.prompt, history=history, llm=llm, svc=svc)
                if payload.useRag
                else _generate_euria_direct_answer_with_options(
                    prompt=payload.prompt,
                    history=history,
                    llm=llm,
                    enable_web_search=True,
                )
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        answer = str(result.get("answer") or "")
        if not payload.useRag:
            result = _maybe_attach_local_vault_references(prompt=payload.prompt, answer=answer, result=result, svc=svc)
        sources = list(result.get("sources") or [])
        provenance = str(result.get("provenance") or "vault")
        enrichment_path = str(result.get("enrichment_path") or "") or None
        source_models = _build_source_models(sources)
        primary_source = next((item for item in source_models if item.isPrimary), None)
        entity_contexts = _enrich_entity_contexts(
            user_text=payload.prompt,
            answer=answer,
            entity_contexts=_lookup_conversation_entity_contexts(payload.prompt, answer, svc),
            sources=source_models,
            primary_source=primary_source,
            svc=svc,
            llm=llm,
        )
        query_overview = result.get("query_overview") or {}
    else:
        try:
            result = _run_chat_generation_worker(prompt=payload.prompt, history=history, use_euria=payload.useEuria)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        answer = str(result.get("answer") or "")
        sources = list(result.get("sources") or [])
        enriched_result = _compose_assistant_web_answer(
            prompt=payload.prompt,
            answer=answer,
            sources=sources,
            svc=svc,
            llm=llm,
        )
        answer = str(enriched_result.get("answer") or answer)
        sources = list(enriched_result.get("sources") or sources)
        provenance = str(enriched_result.get("provenance") or "vault")
        enrichment_path = str(enriched_result.get("enrichment_path") or "") or None
        sentinel = is_not_in_vault(answer)
        source_models = _build_source_models(sources)
        primary_source = next((item for item in source_models if item.isPrimary), None)
        entity_contexts = _enrich_entity_contexts(
            user_text=payload.prompt,
            answer=answer,
            entity_contexts=_lookup_conversation_entity_contexts(payload.prompt, answer, svc),
            sources=source_models,
            primary_source=primary_source,
            svc=svc,
            llm=llm,
        )
        query_overview = enriched_result.get("query_overview") or (_lookup_query_overview(payload.prompt, svc, llm=llm) if sentinel else {})
    assistant_message = _build_assistant_message(
        answer=answer,
        sources=sources,
        started_at=started_at,
        timeline=[],
        query_overview=query_overview,
        entity_contexts=entity_contexts,
        provenance=provenance,
        llm_provider=llm_provider,
        enrichment_path=enrichment_path,
    )
    conversation_store.append_messages(
        conversation_id,
        [assistant_message],
        last_generation_stats=assistant_message.stats,
    )
    return assistant_message


@app.post("/api/v1/conversations/{conversation_id}/messages/stream")
async def stream_message(
    conversation_id: str,
    payload: MessageCreateRequest,
    _: None = Depends(require_api_auth),
) -> StreamingResponse:
    svc = get_service_manager()
    try:
        llm = _conversation_llm(svc, payload.useEuria)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    llm_provider = _conversation_llm_provider(payload.useEuria)
    user_message, history = _prepare_user_message(conversation_id, payload.prompt)
    conversation_store.append_messages(conversation_id, [user_message])
    started_at = time.perf_counter()
    worker_task = None if payload.useEuria else asyncio.create_task(asyncio.to_thread(_run_chat_generation_worker, prompt=payload.prompt, history=history, use_euria=payload.useEuria))

    async def _event_stream():
        timeline: list[str] = []
        yield _sse_event("message_start", {"conversationId": conversation_id, "messageId": user_message.id})
        result: dict[str, Any] | None = None
        emitted_preparation_steps: set[str] = set()

        if payload.useEuria:
            euria_steps: list[tuple[str, str]] = [("analysis", "Analyse de la requete")]
            if payload.useRag and _can_build_local_rag_context(svc) and not _should_skip_euria_rag(payload.prompt):
                euria_steps.append(("context", "Recherche dans le coffre"))
            euria_steps.append(("generation", "Generation via Euria + web" if not payload.useRag else "Generation via Euria"))
            euria_steps.append(("entities", "Extraction des entites NER"))
            euria_steps.append(("finalize", "Finalisation de la reponse"))
            for phase, status_message in euria_steps:
                _append_timeline_step(timeline, status_message)
                yield _sse_event("retrieval_status", {"phase": phase, "message": status_message})

            try:
                stream_plan = await asyncio.to_thread(
                    _prepare_euria_stream_plan,
                    prompt=payload.prompt,
                    history=history,
                    use_rag=payload.useRag,
                    svc=svc,
                )
                raw_stream = llm.stream(
                    stream_plan["messages"],
                    temperature=float(stream_plan["temperature"]),
                    max_tokens=int(stream_plan["max_tokens"]),
                    operation=str(stream_plan["operation"]),
                    enable_web_search=bool(stream_plan["enable_web_search"]),
                )
                streamed_parts: list[str] = []
                ttft = 0.0
                while True:
                    token = await asyncio.to_thread(_next_stream_value, raw_stream)
                    if token is _STREAM_ITERATION_END:
                        break
                    token_text = str(token or "")
                    if not token_text:
                        continue
                    if ttft == 0.0 and token_text.strip():
                        ttft = max(time.perf_counter() - started_at, 0.001)
                    streamed_parts.append(token_text)
                    yield _sse_event("token", {"token": token_text})
            except RuntimeError as exc:
                yield _sse_event("message_error", {"detail": str(exc)})
                return

            answer = _sanitize_assistant_answer_text("".join(streamed_parts))
            result = dict(stream_plan["result"])
            result["answer"] = answer
            if payload.useRag:
                result = _maybe_upgrade_euria_result_with_web_fallback(prompt=payload.prompt, result=result, llm=llm, svc=svc)
                answer = _sanitize_assistant_answer_text(str(result.get("answer") or answer))
            else:
                result = await asyncio.to_thread(
                    _maybe_attach_local_vault_references,
                    prompt=payload.prompt,
                    answer=answer,
                    result=result,
                    svc=svc,
                )
            sources = list(result.get("sources") or [])
            source_models = _build_source_models(sources)
            primary_source = next((item for item in source_models if item.isPrimary), None)
            _prompt, _answer, _source_models, _primary_source, _svc, _llm = (
                payload.prompt, answer, source_models, primary_source, svc, llm
            )
            entity_contexts = await asyncio.to_thread(
                lambda: _enrich_entity_contexts(
                    user_text=_prompt,
                    answer=_answer,
                    entity_contexts=_lookup_conversation_entity_contexts(_prompt, _answer, _svc),
                    sources=_source_models,
                    primary_source=_primary_source,
                    svc=_svc,
                    llm=_llm,
                )
            )
            assistant_message = _build_assistant_message(
                answer=answer,
                sources=sources,
                started_at=started_at,
                timeline=timeline,
                query_overview=result.get("query_overview") or {},
                entity_contexts=entity_contexts,
                provenance=str(result.get("provenance") or "vault"),
                llm_provider=llm_provider,
                enrichment_path=str(result.get("enrichment_path") or "") or None,
                ttft=ttft,
            )
            if assistant_message.provenance == "web":
                _append_timeline_step(timeline, "Recherche web via Euria")
                assistant_message.timeline = timeline
            if _has_post_response_vault_references(payload=payload, assistant_message=assistant_message):
                _append_timeline_step(timeline, "Références du coffre associées")
                assistant_message.timeline = timeline
                yield _sse_event("retrieval_status", {"phase": "references", "message": "Références du coffre associées"})
            yield _sse_event("sources_ready", {"sources": [item.model_dump(mode="json") for item in assistant_message.sources]})
            conversation_store.append_messages(
                conversation_id,
                [assistant_message],
                last_generation_stats=assistant_message.stats,
            )
            yield _sse_event("message_complete", assistant_message.model_dump(mode="json"))
            return

        for phase, status_message in STREAM_PREPARATION_STEPS:
            _append_timeline_step(timeline, status_message)
            emitted_preparation_steps.add(status_message)
            yield _sse_event("retrieval_status", {"phase": phase, "message": status_message})
            try:
                result = await asyncio.wait_for(asyncio.shield(worker_task), timeout=0.55)
                break
            except asyncio.TimeoutError:
                continue
            except RuntimeError as exc:
                yield _sse_event("message_error", {"detail": str(exc)})
                return

        if result is None:
            try:
                result = await worker_task
            except RuntimeError as exc:
                yield _sse_event("message_error", {"detail": str(exc)})
                return

        for phase, status_message in STREAM_PREPARATION_STEPS:
            if status_message in emitted_preparation_steps:
                continue
            _append_timeline_step(timeline, status_message)
            yield _sse_event("retrieval_status", {"phase": phase, "message": status_message})

        answer = str(result.get("answer") or "")
        sources = list(result.get("sources") or [])
        sentinel = is_not_in_vault(answer)
        provenance = "vault"
        enrichment_path: str | None = None
        source_models = _build_source_models(sources)
        primary_source = next((item for item in source_models if item.isPrimary), None)

        _append_timeline_step(timeline, "Réponse générée par le worker API")
        yield _sse_event("retrieval_status", {"phase": "generation", "message": "Réponse générée par le worker API"})

        entity_contexts: list[dict[str, Any]] = []
        query_overview: dict[str, Any] = {}
        should_attempt_web = _should_attempt_web_answer(answer, svc)
        enrichment_steps = [
            *([("web", "Recherche DDG")] if should_attempt_web else []),
            ("entities", "Extraction des entites NER"),
            ("finalize", "Finalisation de la reponse"),
        ]
        for phase, status_message in enrichment_steps:
            _append_timeline_step(timeline, status_message)
            yield _sse_event("retrieval_status", {"phase": phase, "message": status_message})
            if phase == "web":
                enriched_result = await asyncio.to_thread(
                    _compose_assistant_web_answer,
                    prompt=payload.prompt,
                    answer=answer,
                    sources=sources,
                    svc=svc,
                    force=should_attempt_web,
                    llm=llm,
                )
                answer = str(enriched_result.get("answer") or answer)
                sources = list(enriched_result.get("sources") or sources)
                provenance = str(enriched_result.get("provenance") or "vault")
                enrichment_path = str(enriched_result.get("enrichment_path") or "") or None
                sentinel = is_not_in_vault(answer)
                query_overview = enriched_result.get("query_overview") or query_overview
                source_models = _build_source_models(sources)
                primary_source = next((item for item in source_models if item.isPrimary), None)
            elif phase == "entities":
                _prompt, _answer, _source_models, _primary_source, _svc, _llm = (
                    payload.prompt, answer, source_models, primary_source, svc, llm
                )
                entity_contexts = await asyncio.to_thread(
                    lambda: _enrich_entity_contexts(
                        user_text=_prompt,
                        answer=_answer,
                        entity_contexts=_lookup_conversation_entity_contexts(_prompt, _answer, _svc),
                        sources=_source_models,
                        primary_source=_primary_source,
                        svc=_svc,
                        llm=_llm,
                    )
                )
                if sentinel and not query_overview:
                    query_overview = await asyncio.to_thread(
                        _lookup_query_overview, payload.prompt, svc, llm=llm
                    )

        for token in _iter_answer_tokens(answer):
            yield _sse_event("token", {"token": token})

        yield _sse_event("sources_ready", {"sources": [item.model_dump(mode="json") for item in source_models]})

        assistant_message = _build_assistant_message(
            answer=answer,
            sources=sources,
            started_at=started_at,
            timeline=timeline,
            query_overview=query_overview,
            entity_contexts=entity_contexts,
            provenance=provenance,
            llm_provider=llm_provider,
            enrichment_path=enrichment_path,
        )
        conversation_store.append_messages(
            conversation_id,
            [assistant_message],
            last_generation_stats=assistant_message.stats,
        )
        yield _sse_event("message_complete", assistant_message.model_dump(mode="json"))

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


def _append_timeline_step(timeline: list[str], value: str) -> None:
    if timeline and timeline[-1] == value:
        return
    timeline.append(value)


@app.get("/api/v1/notes", response_model=list[RelatedNoteModel])
def list_notes(_: None = Depends(require_api_auth)) -> list[RelatedNoteModel]:
    svc = get_service_manager()
    return [
        RelatedNoteModel(
            title=note.get("title") or Path(note["file_path"]).stem,
            filePath=note["file_path"],
            dateModified=note.get("date_modified"),
            sizeBytes=_artifact_size_bytes(note["file_path"]),
        )
        for note in svc.chroma.list_notes_sorted_by_title()
    ]


@app.get("/api/v1/notes/search", response_model=list[RelatedNoteModel])
def search_notes(q: str, _: None = Depends(require_api_auth)) -> list[RelatedNoteModel]:
    svc = get_service_manager()
    search = q.strip().lower()
    if not search:
        return []
    matches = [
        note for note in svc.chroma.list_notes_sorted_by_title()
        if search in str(note.get("title") or "").lower() or search in str(note.get("file_path") or "").lower()
    ]
    return [
        RelatedNoteModel(
            title=note.get("title") or Path(note["file_path"]).stem,
            filePath=note["file_path"],
            dateModified=note.get("date_modified"),
            sizeBytes=_artifact_size_bytes(note["file_path"]),
        )
        for note in matches[:20]
    ]


@app.get("/api/v1/notes/{note_path:path}", response_model=NoteDetailModel)
def get_note(note_path: str, _: None = Depends(require_api_auth)) -> NoteDetailModel:
    svc = get_service_manager()
    normalized, note = _resolve_note_path_identifier(note_path, svc)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    abs_path = resolve_vault_path(normalized)
    content = read_text_file(abs_path, default="", errors="replace")
    metadata = frontmatter.loads(content) if content else frontmatter.Post("")
    backlinks = svc.chroma.get_backlinks(normalized)
    return NoteDetailModel(
        id=normalized,
        filePath=normalized,
        title=note.get("title") or abs_path.stem,
        bodyMarkdown=strip_frontmatter(content),
        tags=list(note.get("tags", []) or []),
        frontmatter=dict(metadata.metadata),
        backlinks=[_related_note_from_note(item) for item in backlinks],
        links=[_related_note_from_link(link, svc) for link in note.get("wikilinks", [])],
        dateModified=note.get("date_modified"),
        sizeBytes=_artifact_size_bytes(normalized),
        noteType=get_note_type(normalized),
        outline=extract_note_outline(content),
    )


@app.post("/api/v1/notes/{note_path:path}/synapses/discover", response_model=DetectSynapsesResponseModel)
def detect_note_synapses(note_path: str, _: None = Depends(require_api_auth)) -> DetectSynapsesResponseModel:
    svc = get_service_manager()
    svc.signal_ui_active()

    normalized, note = _resolve_note_path_identifier(note_path, svc)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")

    existing_links = {str(wikilink).lower() for wikilink in note.get("wikilinks", [])}
    candidates = svc.chroma.find_similar_notes(
        source_fp=normalized,
        existing_links=existing_links,
        top_k=max(1, settings.autolearn_synapse_per_run),
        threshold=settings.autolearn_synapse_threshold,
    )

    if not candidates:
        return DetectSynapsesResponseModel(
            sourceNotePath=normalized,
            createdCount=0,
            created=[],
            message="Aucune synapse pertinente detectee pour cet element.",
        )

    created: list[RelatedNoteModel] = []
    synapse_index = svc.learner._load_synapse_index()

    for candidate in candidates:
        pair_key = svc.learner._synapse_pair_key(normalized, candidate["file_path"])
        if pair_key in synapse_index:
            continue

        created_path = svc.learner._create_synapse_artifact(note, candidate)
        synapse_index.add(pair_key)
        svc.indexer.index_note(created_path)
        relative_path = str(created_path.relative_to(settings.vault))
        created.append(
            RelatedNoteModel(
                title=created_path.stem.replace("_", " "),
                filePath=relative_path,
                dateModified=datetime.now(UTC).isoformat(),
                sizeBytes=_artifact_size_bytes(relative_path),
            )
        )

    svc.learner._save_synapse_index(synapse_index)
    svc.chroma.invalidate_list_notes_cache()

    if not created:
        return DetectSynapsesResponseModel(
            sourceNotePath=normalized,
            createdCount=0,
            created=[],
            message="Les synapses candidates existent deja pour cet element.",
        )

    return DetectSynapsesResponseModel(
        sourceNotePath=normalized,
        createdCount=len(created),
        created=created,
        message=f"{len(created)} synapse(s) detectee(s) pour cet element.",
    )


@app.get("/api/v1/insights", response_model=list[InsightItemModel])
def list_insights(_: None = Depends(require_api_auth)) -> list[InsightItemModel]:
    svc = get_service_manager()
    entries: list[InsightItemModel] = []
    for note in svc.chroma.list_generated_notes():
        file_path = note.get("file_path", "")
        kind = _artifact_kind(file_path)
        entries.append(
            InsightItemModel(
                id=file_path,
                title=note.get("title") or Path(file_path).stem,
                filePath=file_path,
                kind=kind,
                provenance="vault",
                tags=list(note.get("tags", []) or []),
                dateModified=note.get("date_modified"),
                sizeBytes=_artifact_size_bytes(file_path),
                excerpt=_note_excerpt(file_path),
            )
        )
    return entries


@app.get("/api/v1/insights/{artifact_path:path}", response_model=NoteDetailModel)
def get_insight(artifact_path: str, _: None = Depends(require_api_auth)) -> NoteDetailModel:
    return get_note(artifact_path)


@app.get("/api/v1/graph", response_model=GraphDataModel)
def get_graph(
    folders: list[str] = Query(default_factory=list),
    tags: list[str] = Query(default_factory=list),
    noteTypes: list[str] = Query(default_factory=list),
    searchText: str = Query(default=""),
    recencyDays: int | None = Query(default=None, ge=1, le=3650),
    _: None = Depends(require_api_auth),
) -> GraphDataModel:
    return _build_graph_payload(
        selected_folders=folders,
        selected_tags=tags,
        selected_types=noteTypes,
        search_text=searchText,
        recency_days=recencyDays,
    )


@app.get("/api/v1/graph/subgraph", response_model=GraphDataModel)
def get_graph_subgraph(
    noteId: str = Query(..., min_length=1),
    depth: int = Query(1, ge=1, le=3),
    folders: list[str] = Query(default_factory=list),
    tags: list[str] = Query(default_factory=list),
    noteTypes: list[str] = Query(default_factory=list),
    searchText: str = Query(default=""),
    recencyDays: int | None = Query(default=None, ge=1, le=3650),
    _: None = Depends(require_api_auth),
) -> GraphDataModel:
    payload = _build_graph_payload(
        selected_folders=folders,
        selected_tags=tags,
        selected_types=noteTypes,
        search_text=searchText,
        recency_days=recencyDays,
    )
    graph = _graph_from_model(payload)
    note_id = normalize_vault_relative_path(noteId)
    if note_id not in graph:
        raise HTTPException(status_code=404, detail="Note not found in graph")

    frontier = {note_id}
    visited = {note_id}
    for _ in range(depth):
        neighbors: set[str] = set()
        for current in frontier:
            neighbors.update(graph.predecessors(current))
            neighbors.update(graph.successors(current))
        frontier = neighbors - visited
        visited.update(frontier)

    subgraph = graph.subgraph(visited).copy()
    return _graph_to_model(
        subgraph,
        filtered_notes=_graph_records_from_nodes(payload.nodes, subgraph.nodes),
        all_notes=payload.noteOptions,
        filter_options=payload.filterOptions,
        total_note_count=payload.metrics.totalNoteCount or len(payload.noteOptions),
    )


@app.post("/api/v1/web-search", response_model=WebSearchResponseModel)
def explicit_web_search(
    payload: WebSearchRequestModel,
    _: None = Depends(require_api_auth),
) -> WebSearchResponseModel:
    svc = get_service_manager()
    try:
        llm = _conversation_llm(svc, payload.useEuria)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    svc.signal_ui_active()
    started_at = time.perf_counter()
    overview = _lookup_query_overview(payload.query, svc, llm=llm)
    if not overview:
        raise HTTPException(status_code=404, detail="No web results found")

    query_overview = QueryOverviewModel(
        query=str(overview.get("query") or payload.query),
        searchQuery=str(overview.get("search_query") or payload.query),
        summary=str(overview.get("summary") or ""),
        sources=[_web_source_model(item) for item in (overview.get("sources") or []) if item.get("href")],
    )
    content = _sanitize_assistant_answer_text(_format_query_overview_markdown(overview))
    content = sanitize_mermaid_blocks(content)
    entity_contexts = _enrich_entity_contexts(
        user_text=payload.query,
        answer=content,
        entity_contexts=_lookup_conversation_entity_contexts(payload.query, content, svc),
        sources=[],
        primary_source=None,
        svc=svc,
        llm=llm,
    )
    return WebSearchResponseModel(
        content=content,
        llmProvider=_conversation_llm_provider(payload.useEuria),
        queryOverview=query_overview,
        entityContexts=_entity_context_models(entity_contexts),
        stats=_build_generation_stats(content, started_at),
        provenance="web",
    )


def _web_source_model(item: dict) -> dict[str, str]:
    href = str(item.get("href") or "")
    parsed = urlparse(href)
    hostname = parsed.netloc.lower().removeprefix("www.") if parsed.netloc else ""
    published_at = next(
        (
            str(item.get(key)).strip()
            for key in ("date", "published", "published_at", "publishedAt")
            if item.get(key)
        ),
        "",
    )
    return {
        "title": str(item.get("title") or href or "Source"),
        "href": href,
        **({"body": str(item.get("body"))} if item.get("body") else {}),
        **({"domain": hostname} if hostname else {}),
        **({"publishedAt": published_at} if published_at else {}),
    }


def _conversation_preview(item: ConversationDetailModel) -> str:
    if not item.messages:
        return "Fil vide"
    content = item.messages[-1].content.strip()
    return content[:120] + ("…" if len(content) > 120 else "")


def _conversation_report_title(conversation: ConversationDetailModel) -> str:
    base_title = conversation.title.strip() or ApiConversationStore._derive_title(conversation.messages)
    return f"Rapport {base_title}".strip()


def _conversation_report_sources(conversation: ConversationDetailModel) -> list[str]:
    sources: list[str] = []
    for message in conversation.messages:
        for source in message.sources or []:
            file_path = str(source.filePath or "").strip()
            if file_path and file_path not in sources:
                sources.append(file_path)
    return sources


def _format_conversation_report_transcript(conversation: ConversationDetailModel) -> str:
    lines = [f"Titre de la conversation : {conversation.title}", ""]
    for index, message in enumerate(conversation.messages, start=1):
        role = "Utilisateur" if message.role == "user" else "Assistant" if message.role == "assistant" else "Systeme"
        content = message.content.strip()
        if not content:
            continue
        lines.append(f"{role} {index}:")
        lines.append(content)
        if message.sources:
            source_labels = [source.noteTitle or source.filePath for source in message.sources if source.filePath or source.noteTitle]
            if source_labels:
                lines.append(f"Sources mentionnees : {', '.join(source_labels[:6])}")
        lines.append("")
    return "\n".join(lines).strip()


def _fallback_conversation_report_markdown(conversation: ConversationDetailModel, *, default_title: str) -> str:
    sources = _conversation_report_sources(conversation)
    user_questions = [message.content.strip() for message in conversation.messages if message.role == "user" and message.content.strip()]
    assistant_answers = [message.content.strip() for message in conversation.messages if message.role == "assistant" and message.content.strip()]
    body_lines = [
        f"# {default_title}",
        "",
        "> [!info] Synthese creee automatiquement a partir de la conversation courante.",
        "",
        "## Contexte",
        "",
        "La conversation a ete transformee en rapport markdown Obsidian a partir des echanges entre l'utilisateur et l'assistant.",
        "",
        "## Analyse",
        "",
    ]

    for question, answer in zip(user_questions, assistant_answers, strict=False):
        body_lines.extend([
            f"### {question[:90]}",
            "",
            answer,
            "",
        ])

    if not assistant_answers:
        body_lines.extend([
            "Aucune reponse assistant exploitable n'etait disponible au moment de la generation du rapport.",
            "",
        ])

    body_lines.extend([
        "## Entites NER - Index complet",
        "",
        "### PERSON",
        "A completer.",
        "",
        "### ORG",
        "A completer.",
        "",
        "### GPE",
        "A completer.",
        "",
        "### LOC",
        "A completer.",
        "",
        "### EVENT",
        "A completer.",
        "",
        "### SUBSTANCE",
        "A completer.",
        "",
        "### DATE",
        "A completer.",
        "",
        "*Sources :* " + (", ".join(sources) if sources else "Conversation uniquement"),
    ])
    return "\n".join(body_lines)


_DEFAULT_NER_LABELS = ("PERSON", "ORG", "GPE", "LOC", "WORK_OF_ART", "EVENT", "SUBSTANCE", "DATE")
_NER_NUMBER_ALIASES = {
    "one": "1",
    "first": "1",
    "un": "1",
    "une": "1",
    "premier": "1",
    "premiere": "1",
    "deux": "2",
    "second": "2",
    "seconde": "2",
    "two": "2",
    "seconds": "2",
    "three": "3",
    "trois": "3",
    "troisieme": "3",
    "troisiemes": "3",
    "third": "3",
    "quatre": "4",
    "quatrieme": "4",
    "four": "4",
    "cinq": "5",
    "cinquieme": "5",
    "five": "5",
}
_WORK_OF_ART_NOISE_TOKENS = {
    "affiche",
    "affiches",
    "poster",
    "posters",
    "trailer",
    "trailers",
    "teaser",
    "teasers",
    "bande",
    "annonce",
    "photo",
    "photos",
    "image",
    "images",
    "visuel",
    "visuels",
    "sombre",
    "sombres",
    "dark",
    "review",
    "critique",
    "critiques",
    "rumeur",
    "rumeurs",
}


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _normalize_heading_key(value: str) -> str:
    lowered = _strip_accents(value).lower()
    lowered = re.sub(r"[^a-z0-9\s-]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def _is_ner_section_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith("#"):
        return False
    heading_text = stripped.lstrip("#").strip()
    return "entites ner" in _normalize_heading_key(heading_text) and "index complet" in _normalize_heading_key(heading_text)


def _normalize_ner_label(value: str) -> str:
    normalized = _strip_accents(str(value).strip()).upper().replace(" ", "_").replace("-", "_")
    normalized = re.sub(r"[^A-Z0-9_]+", "", normalized)
    aliases = {
        "PERSONNE": "PERSON",
        "PERSONNES": "PERSON",
        "PEOPLE": "PERSON",
        "ORGANIZATION": "ORG",
        "ORGANISATION": "ORG",
        "ORGANISATIONS": "ORG",
        "LOCATION": "LOC",
        "LIEU": "LOC",
        "LIEUX": "LOC",
        "OEUVRE": "WORK_OF_ART",
        "WORK": "WORK_OF_ART",
        "WORKOFART": "WORK_OF_ART",
        "WORKS_OF_ART": "WORK_OF_ART",
        "ARTWORK": "WORK_OF_ART",
        "ART": "WORK_OF_ART",
    }
    return aliases.get(normalized, normalized)


def _canonical_ner_entity_key(entity_name: str, label: str) -> str:
    normalized_name = _normalize_heading_key(entity_name)
    if not normalized_name:
        return ""

    tokens = normalized_name.split()
    normalized_label = _normalize_ner_label(label)
    if normalized_label != "WORK_OF_ART":
        return normalized_name

    canonical_tokens: list[str] = []
    for token in tokens:
        canonical_tokens.append(_NER_NUMBER_ALIASES.get(token, token))

    canonical_tokens = ["part" if token == "partie" else token for token in canonical_tokens]
    canonical_tokens = [token for token in canonical_tokens if token not in _WORK_OF_ART_NOISE_TOKENS]

    for index, token in enumerate(canonical_tokens):
        if token.isdigit():
            title_tokens = [item for item in canonical_tokens[:index] if item != "part"]
            return " ".join([*title_tokens, token])

    for index, token in enumerate(canonical_tokens):
        if token == "part" and index + 1 < len(canonical_tokens) and canonical_tokens[index + 1].isdigit():
            title_tokens = [item for item in canonical_tokens[:index] if item != "part"]
            return " ".join([*title_tokens, canonical_tokens[index + 1]])

    return " ".join(token for token in canonical_tokens if token != "part")


def _parse_ner_entries(lines: list[str]) -> dict[str, list[str]]:
    entries: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()
    current_label: str | None = None

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            continue
        if _is_ner_section_heading(stripped):
            current_label = None
            continue
        if stripped.startswith("### "):
            current_label = _normalize_ner_label(stripped[4:]) or None
            continue
        if stripped.lower() == "a completer.":
            continue
        if not stripped.startswith("-"):
            continue

        content = stripped[1:].strip()
        inline_match = re.match(r"(?P<name>.+?)\s*\((?P<label>[A-Za-z_ -]+)\)\s*$", content)
        broken_inline_match = re.match(r"(?P<name>.+?)\s*\((?P<label>[A-Za-z_ -]+)\s*$", content)
        if inline_match:
            entity_name = inline_match.group("name").strip()
            label = _normalize_ner_label(inline_match.group("label"))
        elif broken_inline_match:
            entity_name = broken_inline_match.group("name").strip()
            label = _normalize_ner_label(broken_inline_match.group("label"))
        else:
            entity_name = content
            label = current_label or "MISC"

        entity_name = re.sub(r"\s+", " ", entity_name).strip(" -\t")
        entity_name = entity_name.replace("[[", "").replace("]]", "")
        entity_name = re.sub(r"^\*\*(.+)\*\*$", r"\1", entity_name)
        entity_name = re.sub(r"^`(.+)`$", r"\1", entity_name)
        entity_name = re.sub(r"\s*\([A-Za-z_ -]+\s*$", "", entity_name).strip()
        entity_name = entity_name.strip("*#_`[](){}:; ")
        if not entity_name or entity_name.lower() == "a completer.":
            continue
        if _normalize_ner_label(label) == "MISC":
            continue

        dedupe_key = (_normalize_ner_label(label), _canonical_ner_entity_key(entity_name, label))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        entries.setdefault(label, []).append(entity_name)

    return entries


def _render_ner_section(entries: dict[str, list[str]]) -> str:
    ordered_labels = [label for label in _DEFAULT_NER_LABELS if entries.get(label)]
    extra_labels = sorted(label for label in entries if label not in _DEFAULT_NER_LABELS)
    lines = ["## Entites NER - Index complet", ""]

    if not ordered_labels and not extra_labels:
        lines.append("Aucune entite NER exploitable detectee.")
        return "\n".join(lines)

    for label in [*ordered_labels, *extra_labels]:
        lines.append(f"### {label}")
        values = entries.get(label, [])
        lines.extend(f"- **{value}** ({label})" for value in values)
        lines.append("")

    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _normalize_ner_section(body: str) -> str:
    lines = body.splitlines()
    cleaned_lines: list[str] = []
    ner_lines: list[str] = []
    in_ner_section = False

    for line in lines:
        stripped = line.strip()
        if _is_ner_section_heading(line):
            in_ner_section = True
            ner_lines.append(line)
            continue
        if in_ner_section and re.match(r"^#{1,2}\s+", stripped) and not _is_ner_section_heading(line):
            in_ner_section = False
        if in_ner_section:
            ner_lines.append(line)
            continue
        cleaned_lines.append(line)

    cleaned_body = "\n".join(cleaned_lines).strip()
    parsed_entries = _parse_ner_entries(ner_lines)
    ner_section = _render_ner_section(parsed_entries)

    if "*Sources :*" in cleaned_body:
        prefix, suffix = cleaned_body.split("*Sources :*", 1)
        prefix = prefix.rstrip()
        suffix_text = suffix.strip()
        sources_block = "*Sources :*" if not suffix_text else f"*Sources :* {suffix_text}"
        return f"{prefix}\n\n{ner_section}\n\n{sources_block}".strip()

    return f"{cleaned_body}\n\n{ner_section}".strip()


def _extract_embedded_markdown_document(text: str) -> str | None:
    if not text:
        return None

    matches = re.findall(r"```markdown\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    for candidate in matches:
        stripped = candidate.strip()
        if stripped.startswith("---") or "## Entites NER - Index complet" in stripped or "### Entités NER - Index complet" in stripped:
            return stripped

    fence_match = re.search(r"```markdown\s*", text, flags=re.IGNORECASE)
    if fence_match:
        stripped = text[fence_match.end():].strip()
        if stripped.startswith("---") or "## Entites NER - Index complet" in stripped or "### Entités NER - Index complet" in stripped:
            return stripped
    return None


def _normalize_report_markdown(raw_markdown: str, *, default_title: str, sources: list[str]) -> str:
    cleaned = (raw_markdown or "").strip()
    if cleaned.startswith("```markdown") and cleaned.endswith("```"):
        cleaned = cleaned[len("```markdown"): -3].strip()
    elif cleaned.startswith("```") and cleaned.endswith("```"):
        cleaned = cleaned[3:-3].strip()

    embedded_document = _extract_embedded_markdown_document(cleaned)
    if embedded_document:
        cleaned = embedded_document

    if not cleaned:
        cleaned = _fallback_conversation_report_markdown(
            ConversationDetailModel(id="", title=default_title, updatedAt=datetime.now(UTC).isoformat(), draft="", messages=[]),
            default_title=default_title,
        )

    post = frontmatter.loads(cleaned) if cleaned else frontmatter.Post("")

    metadata = dict(post.metadata)
    metadata["title"] = str(metadata.get("title") or default_title).strip() or default_title
    metadata["date"] = str(metadata.get("date") or datetime.now(UTC).strftime("%Y-%m-%d"))
    metadata["type"] = "rapport"
    metadata["statut"] = str(metadata.get("statut") or "finalise")
    metadata["domaine"] = _coerce_frontmatter_list(metadata.get("domaine"))
    metadata["tags"] = _merge_unique_values(["insight", "rapport", "conversation", "obsirag"], _coerce_frontmatter_list(metadata.get("tags")))
    metadata["aliases"] = _merge_unique_values([default_title], _coerce_frontmatter_list(metadata.get("aliases")))
    metadata["sources"] = _merge_unique_values(sources, _coerce_frontmatter_list(metadata.get("sources")))
    metadata["champ-semantique"] = _coerce_frontmatter_list(metadata.get("champ-semantique"))
    post.metadata.clear()
    post.metadata.update(metadata)

    body = (post.content or "").strip()
    if not body:
        body = _fallback_conversation_report_markdown(
            ConversationDetailModel(id="", title=default_title, updatedAt=datetime.now(UTC).isoformat(), draft="", messages=[]),
            default_title=default_title,
        )
    elif not re.search(r"^#\s+", body, flags=re.MULTILINE):
        body = f"# {metadata['title']}\n\n{body}"

    body = _normalize_ner_section(body)

    if "*Sources :*" not in body:
        body = body.rstrip() + "\n\n*Sources :* " + (", ".join(sources) if sources else "Conversation uniquement")

    post.content = sanitize_mermaid_blocks(body)
    return frontmatter.dumps(post).strip() + "\n"


def _coerce_frontmatter_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _merge_unique_values(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    for group in groups:
        for item in group:
            value = str(item).strip()
            if value and value not in merged:
                merged.append(value)
    return merged


def _extract_remote_image_links(text: str, *, default_alt: str = "Illustration") -> list[tuple[str, str]]:
    if not text:
        return []

    matches = re.findall(r"!\[([^\]]*)\]\((https?://[^\s)]+)(?:\s+\"[^\"]*\")?\)", text, flags=re.IGNORECASE)
    images: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    for alt, url in matches:
        normalized_url = str(url or "").strip()
        if not normalized_url or normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)
        normalized_alt = str(alt or "").strip() or default_alt
        images.append((normalized_alt, normalized_url))
    return images


def _load_source_note_report_images(source_path: str, *, note_title: str | None = None) -> list[tuple[str, str]]:
    normalized_path = normalize_vault_relative_path(source_path, vault_root=settings.vault)
    if not normalized_path:
        return []

    resolved_path = resolve_vault_path(normalized_path, vault_root=settings.vault)
    if not resolved_path.exists() or not resolved_path.is_file():
        return []

    content = read_text_file(resolved_path, default="", errors="replace")
    if not content:
        return []

    default_alt = str(note_title or Path(normalized_path).stem or "Illustration").strip() or "Illustration"
    return _extract_remote_image_links(strip_frontmatter(content), default_alt=default_alt)


def _build_theme_image_section(
    messages: list[ChatMessageModel],
    *,
    seen_urls: set[str],
    max_images: int = 4,
) -> str:
    image_entries: list[tuple[str, str, str | None]] = []

    def append_image(alt: str, url: str, caption: str | None = None) -> None:
        normalized_url = str(url or "").strip()
        if not normalized_url or normalized_url in seen_urls:
            return
        seen_urls.add(normalized_url)
        image_entries.append((str(alt or "").strip() or "Illustration", normalized_url, caption))

    for message in messages:
        for context in message.entityContexts:
            image_url = str(context.imageUrl or "").strip()
            if not image_url:
                continue
            append_image(
                context.value,
                image_url,
                f"Image associee a {context.value} ({context.typeLabel}).",
            )
            if len(image_entries) >= max_images:
                break

        if len(image_entries) >= max_images:
            break

        for source in message.sources:
            source_label = str(source.noteTitle or source.filePath or "Source").strip() or "Source"
            for alt, url in _load_source_note_report_images(source.filePath, note_title=source.noteTitle):
                append_image(alt, url, f"Image extraite de [[{source_label}]].")
                if len(image_entries) >= max_images:
                    break
            if len(image_entries) >= max_images:
                break

        if len(image_entries) >= max_images:
            break

    if not image_entries:
        return ""

    lines = [
        "#### Illustrations associees",
        "",
    ]
    for alt, url, caption in image_entries:
        lines.append(f"![{alt}]({url})")
        if caption:
            lines.append(f"*{caption}*")
        lines.append("")

    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _theme_heading_from_text(text: str, *, fallback: str) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if not compact:
        return fallback
    if len(compact) <= 140:
        heading = compact.rstrip(" .,:;!?-")
        return heading or fallback

    boundary = compact.rfind(" ", 0, 140)
    if boundary < 60:
        boundary = 140
    heading = compact[:boundary].rstrip(" .,:;!?-")
    return (heading + "...") if heading else fallback


def _build_conversation_theme_coverage_section(conversation: ConversationDetailModel) -> str:
    themes: list[tuple[str, list[ChatMessageModel]]] = []
    current_title = "Ouverture"
    current_messages: list[ChatMessageModel] = []
    seen_theme_image_urls: set[str] = set()

    for message in conversation.messages:
        content = str(message.content or "").strip()
        if not content:
            continue

        if message.role == "user":
            if current_messages:
                themes.append((current_title, current_messages))
            current_title = _theme_heading_from_text(content, fallback=f"Theme {len(themes) + 1}")
            current_messages = [message]
            continue

        if not current_messages:
            current_messages = [message]
        else:
            current_messages.append(message)

    if current_messages:
        themes.append((current_title, current_messages))

    if not themes:
        return "## Corpus complet par themes\n\nAucun message exploitable n'etait disponible dans la conversation."

    lines = [
        "## Corpus complet par themes",
        "",
        "> [!note] Reprise integrale des messages de la conversation, reorganises par theme sans perte de contenu.",
        "",
    ]

    for index, (title, messages) in enumerate(themes, start=1):
        lines.extend([f"### Theme {index} - {title}", ""])
        for message in messages:
            role_label = "Utilisateur" if message.role == "user" else "Assistant" if message.role == "assistant" else "Systeme"
            lines.extend([f"#### {role_label}", "", str(message.content).strip(), ""])

        image_section = _build_theme_image_section(messages, seen_urls=seen_theme_image_urls)
        if image_section:
            lines.extend([image_section, ""])

    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _inject_theme_coverage_section(markdown: str, conversation: ConversationDetailModel) -> str:
    post = frontmatter.loads(markdown) if markdown else frontmatter.Post("")
    body = (post.content or "").strip()
    theme_section = _build_conversation_theme_coverage_section(conversation)

    if "## Entites NER - Index complet" in body:
        prefix, suffix = body.split("## Entites NER - Index complet", 1)
        body = f"{prefix.rstrip()}\n\n{theme_section}\n\n## Entites NER - Index complet{suffix}"
    elif "*Sources :*" in body:
        prefix, suffix = body.split("*Sources :*", 1)
        body = f"{prefix.rstrip()}\n\n{theme_section}\n\n*Sources :* {suffix.strip()}"
    else:
        body = f"{body.rstrip()}\n\n{theme_section}".strip()

    post.content = sanitize_mermaid_blocks(body.strip()) + "\n"
    return frontmatter.dumps(post).strip() + "\n"


def _generate_conversation_report_markdown(conversation: ConversationDetailModel, svc: Any, *, default_title: str) -> str:
    transcript = _format_conversation_report_transcript(conversation)
    sources = _conversation_report_sources(conversation)
    prompt = (
        "Tu rediges un rapport Markdown pour Obsidian a partir d'une conversation.\n"
        "Reponds uniquement avec du Markdown valide, sans texte introductif hors document.\n\n"
        "Contraintes obligatoires :\n"
        "- Inclure un frontmatter YAML avec les cles : title, date, type, statut, domaine, tags, aliases, sources, champ-semantique.\n"
        "- Fixer type: rapport et statut: finalise.\n"
        "- Rediger en francais, avec une prose analytique.\n"
        "- Structurer le document avec un chapeau callout info, puis des sections Contexte, Analyse, Synthese, Corpus complet par themes et Entites NER - Index complet.\n"
        "- Reprendre l'integralite du texte de la conversation: aucun message utilisateur ou assistant ne doit etre omis.\n"
        "- Regrouper ce contenu integral par themes explicites, sans perdre les formulations originales.\n"
        "- Annoter les entites nommees dans le corps sous la forme **Nom** (*TYPE*).\n"
        "- Pour PERSON, ORG, GPE, LOC, EVENT, utiliser des wikilinks Obsidian [[Nom]].\n"
        "- Utiliser des callouts Obsidian quand ils apportent un contexte utile.\n"
        "- Tu peux inclure jusqu'a 2 diagrammes Mermaid si cela clarifie vraiment le contenu.\n"
        "- Si tu produis du Mermaid, le code Mermaid doit utiliser uniquement des caracteres ASCII simples, sans accents ni emojis.\n"
        "- N'invente aucune source externe absente de la conversation.\n"
        "- Eviter les listes a puces dans le corps du texte hors index NER, tableaux, callouts ou diagrammes.\n\n"
        f"Titre attendu : {default_title}\n"
        f"Sources deja mentionnees : {', '.join(sources) if sources else 'Aucune source explicite'}\n\n"
        "Conversation a analyser :\n"
        f"{transcript}\n"
    )

    try:
        raw_markdown = str(
            svc.llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=2200,
                operation="conversation_report",
            )
        ).strip()
    except Exception:
        raw_markdown = ""

    if not raw_markdown:
        raw_markdown = _fallback_conversation_report_markdown(conversation, default_title=default_title)

    normalized = _normalize_report_markdown(raw_markdown, default_title=default_title, sources=sources)
    return _inject_theme_coverage_section(normalized, conversation)


def _prepare_user_message(conversation_id: str, prompt: str) -> tuple[ChatMessageModel, list[dict[str, str]]]:
    existing = conversation_store.get(conversation_id)
    history = [{"role": item.role, "content": item.content} for item in (existing.messages if existing else [])]
    user_message = ChatMessageModel(
        id=f"user-{datetime.now(UTC).timestamp()}",
        role="user",
        content=prompt,
        createdAt=datetime.now(UTC).isoformat(),
    )
    return user_message, history


def _build_assistant_message(
    *,
    answer: str,
    sources: list[dict],
    started_at: float,
    ttft: float = 0.0,
    timeline: list[str],
    query_overview: dict[str, Any] | None = None,
    entity_contexts: list[dict[str, Any]] | None = None,
    provenance: str = "vault",
    llm_provider: str | None = None,
    enrichment_path: str | None = None,
) -> ChatMessageModel:
    source_models = _build_source_models(sources)
    answer = _sanitize_assistant_answer_text(answer)
    answer = _linkify_answer_note_citations(answer, source_models)
    primary_source = next((item for item in source_models if item.isPrimary), None)
    normalized_provenance = _normalize_assistant_provenance(provenance)
    sentinel = is_not_in_vault(answer)
    allow_query_overview = normalized_provenance == "web" or sentinel
    return ChatMessageModel(
        id=f"assistant-{datetime.now(UTC).timestamp()}",
        role="assistant",
        content=answer,
        createdAt=datetime.now(UTC).isoformat(),
        llmProvider=llm_provider,
        sources=source_models,
        primarySource=primary_source,
        timeline=timeline,
        queryOverview=_query_overview_model(query_overview) if allow_query_overview else None,
        entityContexts=_entity_context_models(entity_contexts),
        enrichmentPath=enrichment_path,
        provenance=normalized_provenance,
        sentinel=sentinel,
        stats=_build_generation_stats(answer, started_at, ttft=ttft),
    )


def _lookup_conversation_entity_contexts(user_text: str, assistant_text: str, svc) -> list[dict[str, Any]]:
    combined = "\n\n".join(part for part in (user_text, assistant_text) if part and str(part).strip())
    if not combined.strip():
        return []
    try:
        result = svc.learner.lookup_wuddai_entity_contexts(combined, max_entities=10, max_notes=3)
        return result if isinstance(result, list) else []
    except Exception:
        return []


def _lookup_query_overview(user_text: str, svc, llm=None) -> dict[str, Any]:
    if not user_text or len(user_text.strip()) < 3:
        return {}

    native_web_answer = _try_euria_native_web_answer(user_text, llm)
    autolearn_overview = _build_query_overview_from_autolearn_results(user_text, svc, llm=llm)
    if autolearn_overview:
        return _merge_euria_native_overview(user_text, native_web_answer, autolearn_overview, llm)

    try:
        result = build_query_overview_sync(user_text, llm or svc.llm)
        normalized_result = result if isinstance(result, dict) else {}
        return _merge_euria_native_overview(user_text, native_web_answer, normalized_result, llm)
    except Exception:
        if native_web_answer:
            return {
                "query": user_text,
                "search_query": user_text,
                "summary": native_web_answer,
                "sources": [],
            }
        return {}


def _query_overview_model(value: dict[str, Any] | None) -> QueryOverviewModel | None:
    overview = value or {}
    summary = str(overview.get("summary") or "").strip()
    sources = [_web_source_model(item) for item in (overview.get("sources") or []) if item.get("href")]
    search_query = str(overview.get("search_query") or overview.get("query") or "").strip()
    query = str(overview.get("query") or search_query).strip()
    if not summary and not sources:
        return None
    return QueryOverviewModel(
        query=query,
        searchQuery=search_query or query,
        summary=summary,
        sources=sources,
    )


def _entity_context_models(values: list[dict[str, Any]] | None) -> list[EntityContextModel]:
    return [_entity_context_model(item) for item in (values or []) if item.get("value")]


def _entity_context_model(value: dict[str, Any]) -> EntityContextModel:
    return EntityContextModel(
        type=str(value.get("type") or "unknown"),
        typeLabel=str(value.get("type_label") or value.get("type") or "Entité"),
        value=str(value.get("value") or "Entité"),
        mentions=int(value.get("mentions") or 0) or None,
        lineNumber=int(value.get("line_number") or 0) or None,
        relationExplanation=str(value.get("relation_explanation") or "").strip() or None,
        imageUrl=str(value.get("image_url") or "") or None,
        tag=str(value.get("tag") or "") or None,
        notes=[_related_note_from_note(item) for item in (value.get("notes") or []) if item.get("file_path")],
        ddgKnowledge=_ddg_knowledge_model(value.get("ddg_knowledge") or {}),
    )


def _enrich_entity_contexts(
    *,
    user_text: str,
    answer: str,
    entity_contexts: list[dict[str, Any]] | None,
    sources: list[SourceRefModel],
    primary_source: SourceRefModel | None,
    svc,
    llm=None,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []

    for context in entity_contexts or []:
        value = str(context.get("value") or "").strip()
        if not value:
            continue

        clone = dict(context)
        evidence = _find_entity_source_evidence(clone, sources=sources, primary_source=primary_source)
        if evidence.get("line_number"):
            clone["line_number"] = evidence["line_number"]
        enriched.append(clone)
        evidence_rows.append(
            {
                "entity": value,
                "type": str(context.get("type_label") or context.get("type") or "Entité"),
                "source_title": evidence.get("source_title") or (primary_source.noteTitle if primary_source else ""),
                "source_path": evidence.get("source_path") or (primary_source.filePath if primary_source else ""),
                "line_number": evidence.get("line_number"),
                "snippet": evidence.get("snippet") or "",
            }
        )

    explanations = _generate_entity_relation_explanations(user_text, answer, evidence_rows, svc, llm=llm)
    for context, evidence in zip(enriched, evidence_rows, strict=False):
        context["relation_explanation"] = explanations.get(str(context.get("value") or "")) or _fallback_entity_relation_explanation(evidence)

    return enriched


def _find_entity_source_evidence(
    context: dict[str, Any],
    *,
    sources: list[SourceRefModel],
    primary_source: SourceRefModel | None,
) -> dict[str, Any]:
    entity_name = str(context.get("value") or "").strip()
    if not entity_name:
        return {}

    candidate_paths: list[tuple[str, str]] = []
    source_paths = {normalize_vault_relative_path(item.filePath): item for item in sources if item.filePath}
    note_candidates = [item for item in (context.get("notes") or []) if item.get("file_path") or item.get("filePath")]

    for note in note_candidates:
        normalized = normalize_vault_relative_path(str(note.get("file_path") or note.get("filePath") or ""), vault_root=settings.vault)
        if normalized in source_paths:
            source = source_paths[normalized]
            candidate_paths.append((source.filePath, source.noteTitle))

    if primary_source and primary_source.filePath:
        candidate_paths.append((primary_source.filePath, primary_source.noteTitle))

    for source in sources:
        candidate_paths.append((source.filePath, source.noteTitle))

    for note in note_candidates:
        note_path = str(note.get("file_path") or note.get("filePath") or "")
        candidate_paths.append((note_path, str(note.get("title") or note_path or "")))

    seen_paths: set[str] = set()
    for raw_path, raw_title in candidate_paths:
        normalized = normalize_vault_relative_path(raw_path, vault_root=settings.vault)
        if not normalized or normalized in seen_paths:
            continue
        seen_paths.add(normalized)
        resolved = resolve_vault_path(normalized, vault_root=settings.vault)
        content = read_text_file(resolved, default="", errors="replace")
        if not content:
            continue
        match = _find_entity_line_match(content, entity_name)
        if not match:
            continue
        return {
            "source_path": normalized,
            "source_title": raw_title or Path(normalized).stem,
            "line_number": int(match.get("line") or 0) or None,
            "snippet": str(match.get("snippet") or "").strip(),
        }

    return {}


def _find_entity_line_match(content: str, entity_name: str) -> dict[str, Any] | None:
    search = entity_name.strip().lower()
    if not search:
        return None

    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        if search not in raw_line.lower():
            continue
        return {
            "line": line_number,
            "snippet": raw_line.strip(),
        }

    return None


def _generate_entity_relation_explanations(
    user_text: str,
    answer: str,
    evidence_rows: list[dict[str, Any]],
    svc,
    llm=None,
) -> dict[str, str]:
    if not evidence_rows:
        return {}

    selected_llm = llm or getattr(svc, "llm", None)
    chat = getattr(selected_llm, "chat", None)
    if not callable(chat):
        return {}

    prompt_lines = [
        "Tu expliques pourquoi chaque entité détectée est liée au sujet demandé.",
        "Réponds uniquement en JSON valide au format {\"items\":[{\"entity\":\"...\",\"reason\":\"...\"}]}",
        "Chaque explication doit être une phrase courte, factuelle, en français.",
        "N'invente rien et appuie-toi seulement sur la question, la réponse et l'extrait de source.",
        "",
        f"Question: {user_text.strip()}",
        f"Réponse: {answer.strip()[:800]}",
        "",
        "Entités:",
    ]

    for index, row in enumerate(evidence_rows, start=1):
        prompt_lines.extend(
            [
                f"{index}. entity={row['entity']}",
                f"   type={row.get('type') or 'Entité'}",
                f"   source_title={row.get('source_title') or '-'}",
                f"   source_path={row.get('source_path') or '-'}",
                f"   line_number={row.get('line_number') or '-'}",
                f"   snippet={row.get('snippet') or '-'}",
            ]
        )

    try:
        raw = chat(
            [
                {
                    "role": "system",
                    "content": (
                        "/no_think\n"
                        "Tu produis des explications relationnelles d'entités, précises et très concises. "
                        "Réponds uniquement avec le JSON demandé, sans texte supplémentaire."
                    ),
                },
                {"role": "user", "content": "\n".join(prompt_lines)},
            ],
            temperature=0.0,
            max_tokens=1200,
            operation="entity_relation_explanations",
        )
    except Exception:
        return {}

    if not isinstance(raw, str) or not raw.strip():
        return {}

    payload = _extract_first_json_object(raw)
    if not isinstance(payload, dict):
        return {}

    explanations: dict[str, str] = {}
    for item in payload.get("items") or []:
        entity = str((item or {}).get("entity") or "").strip()
        reason = str((item or {}).get("reason") or "").strip()
        if entity and reason:
            explanations[entity] = reason
    return explanations


def _extract_first_json_object(raw: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for start, char in enumerate(raw):
        if char != "{":
            continue
        try:
            parsed, _end = decoder.raw_decode(raw[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _fallback_entity_relation_explanation(evidence: dict[str, Any]) -> str:
    entity = str(evidence.get("entity") or "Cette entité").strip() or "Cette entité"
    source_title = str(evidence.get("source_title") or "la source associée").strip() or "la source associée"
    snippet = str(evidence.get("snippet") or "").strip()
    if snippet:
        compact = re.sub(r"\s+", " ", snippet).strip()
        return f"{entity} est cité dans {source_title} car l'extrait associé le mentionne directement: {compact}"
    return f"{entity} est cité car il apparaît dans {source_title} parmi les éléments reliés au sujet demandé."


def _ddg_knowledge_model(value: dict[str, Any]) -> DdgKnowledgeModel | None:
    if not value:
        return None
    related_topics = [
        {
            "text": str(item.get("text") or "").strip(),
            "url": str(item.get("url") or "").strip(),
        }
        for item in (value.get("related_topics") or [])
        if item.get("text") and item.get("url")
    ]
    infobox = [
        {
            "label": str(item.get("label") or "").strip(),
            "value": str(item.get("value") or "").strip(),
        }
        for item in (value.get("infobox") or [])
        if item.get("label") and item.get("value")
    ]
    compact = DdgKnowledgeModel(
        heading=str(value.get("heading") or "").strip() or None,
        entity=str(value.get("entity") or "").strip() or None,
        abstractText=str(value.get("abstract_text") or "").strip() or None,
        answer=str(value.get("answer") or "").strip() or None,
        answerType=str(value.get("answer_type") or "").strip() or None,
        definition=str(value.get("definition") or "").strip() or None,
        infobox=infobox[:6],
        relatedTopics=related_topics[:4],
    )
    if not compact.model_dump(exclude_none=True, exclude_defaults=True):
        return None
    return compact


def _extract_bearer_token(authorization: str | None) -> str:
    raw = (authorization or "").strip()
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw


def _token_preview(value: str | None) -> str | None:
    token = (value or "").strip()
    if not token:
        return None
    if len(token) <= 6:
        return "*" * len(token)
    return f"{token[:2]}***{token[-2:]}"


def _sse_event(name: str, payload: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _iter_answer_tokens(answer: str) -> list[str]:
    if not answer:
        return []
    return re.findall(r"\S+\s*|\s+", answer)


_STREAM_ITERATION_END = object()


def _next_stream_value(iterator):
    try:
        return next(iterator)
    except StopIteration:
        return _STREAM_ITERATION_END


def _decode_worker_payload(stdout: str) -> dict[str, Any]:
    payload = (stdout or "").strip()
    if not payload:
        raise RuntimeError("Le worker de génération n'a renvoyé aucune réponse exploitable.")

    decoder = json.JSONDecoder()
    start_offsets = [index for index, char in enumerate(payload) if char == "{"]
    parsed_candidates: list[dict[str, Any]] = []
    for start in start_offsets:
        candidate = payload[start:].lstrip()
        try:
            parsed, _end = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            parsed_candidates.append(parsed)

    for parsed in parsed_candidates:
        if "answer" in parsed or "detail" in parsed:
            return parsed

    if parsed_candidates:
        return parsed_candidates[-1]

    raise RuntimeError("Le worker de génération a renvoyé une réponse invalide.")


def _conversation_llm(svc, use_euria: bool):
    if not use_euria:
        return getattr(svc, "llm", None)
    try:
        return EuriaClient()
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc


def _conversation_llm_provider(use_euria: bool) -> str:
    return "Euria" if use_euria else "MLX"


def _build_euria_direct_messages(prompt: str, history: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Tu réponds UNIQUEMENT et EXCLUSIVEMENT en français, quelle que soit la langue de la question. "
                "Utilise du Markdown valide et propre. "
                "N'écris pas de balisage incomplet. "
                "Si tu produis un tableau, utilise un vrai tableau Markdown avec des pipes. "
                "Ne répète jamais une ligne, une ligne de tableau, un paragraphe ou une section. "
                "Termine toujours proprement la réponse, sans couper un mot ni une emphase Markdown. "
                "Tu as accès à une recherche web en temps réel. "
                "Pour toute question portant sur des produits, prix, actualités, événements récents ou faits susceptibles d'avoir évolué, "
                "effectue une recherche web avant de répondre et base ta réponse sur les résultats obtenus. "
                "Ne te fie jamais à tes données d'entraînement pour des informations récentes ou factuelles : vérifie toujours sur le web."
            ),
        },
        *[
            {"role": str(item.get("role") or "user"), "content": str(item.get("content") or "")}
            for item in history
            if str(item.get("content") or "").strip()
        ],
        {"role": "user", "content": prompt},
    ]


def _fetch_ddg_snippets(prompt: str, max_results: int = 5) -> list[dict]:
    search_query = _keywordize_query(prompt)
    instant = _ddg_instant_answer_search(search_query, max_results=3)
    ddg = _ddg_search(search_query, max_results=max_results)
    return _merge_search_results(instant, ddg, max_results=max_results)


def _build_euria_web_messages(
    prompt: str,
    history: list[dict[str, str]],
    web_results: list[dict],
) -> list[dict[str, str]]:
    snippets = "\n\n".join(
        f"**{r.get('title', '')}** ({r.get('href', '')})\n{r.get('body', '')}"
        for r in web_results
        if r.get("body")
    )
    user_content = (
        f"Résultats de recherche web récents :\n\n{snippets}\n\n"
        f"Question : {prompt}"
    ) if snippets else prompt
    return [
        {
            "role": "system",
            "content": (
                "Tu réponds UNIQUEMENT et EXCLUSIVEMENT en français, quelle que soit la langue des sources ou de la question. "
                "Même si les résultats de recherche web sont en anglais, ta réponse doit être entièrement rédigée en français. "
                "Utilise du Markdown valide et propre. "
                "N'écris pas de balisage incomplet. "
                "Si tu produis un tableau, utilise un vrai tableau Markdown avec des pipes. "
                "Ne répète jamais une ligne, une ligne de tableau, un paragraphe ou une section. "
                "Termine toujours proprement la réponse, sans couper un mot ni une emphase Markdown. "
                "Des résultats de recherche web récents te sont fournis comme contexte. "
                "Appuie-toi dessus pour répondre avec précision et cite les sources entre crochets. "
                "Priorité absolue aux informations du contexte web sur tes données d'entraînement."
            ),
        },
        *[
            {"role": str(item.get("role") or "user"), "content": str(item.get("content") or "")}
            for item in history
            if str(item.get("content") or "").strip()
        ],
        {"role": "user", "content": user_content},
    ]


def _build_euria_rag_messages(
    prompt: str,
    history: list[dict[str, str]],
    rag_context: str,
    rag_sources: list[dict[str, Any]],
) -> list[dict[str, str]]:
    source_titles = _build_rag_source_titles(rag_sources)
    return [
        {
            "role": "system",
            "content": (
                "Tu réponds en français, avec du Markdown valide et propre. "
                "Appuie-toi d'abord sur le contexte du coffre fourni. "
                "N'invente aucune information absente du contexte. "
                "Si l'information demandée n'est pas dans le contexte, réponds exactement : "
                '"Cette information n\'est pas dans ton coffre." '
                "Quand tu utilises une note du coffre, cite son titre entre crochets. "
                "Ne répète jamais une ligne, un paragraphe ou une section."
            ),
        },
        *[
            {"role": str(item.get("role") or "user"), "content": str(item.get("content") or "")}
            for item in history
            if str(item.get("content") or "").strip()
        ],
        {
            "role": "user",
            "content": (
                "Contexte du coffre :\n"
                f"{rag_context}\n\n"
                f"Notes disponibles : {source_titles or 'non precisees'}\n\n"
                f"Question : {prompt}"
            ),
        },
    ]


def _prepare_euria_stream_plan(*, prompt: str, history: list[dict[str, str]], use_rag: bool, svc) -> dict[str, Any]:
    if not use_rag:
        try:
            web_results = _fetch_ddg_snippets(prompt)
        except Exception:
            web_results = []
        messages = (
            _build_euria_web_messages(prompt, history, web_results)
            if web_results
            else _build_euria_direct_messages(prompt, history)
        )
        search_query = _keywordize_query(prompt)
        query_overview = {
            "query": prompt,
            "search_query": search_query,
            "summary": "",
            "sources": web_results,
        } if web_results else {}
        try:
            _, vault_sources = _build_local_rag_context(prompt, svc)
        except Exception:
            vault_sources = []
        return {
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 4096,
            "operation": "conversation_euria_fast_web",
            "enable_web_search": True,
            "result": {
                "sources": list(vault_sources) if vault_sources else [],
                "provenance": "web",
                "query_overview": query_overview,
                "entity_contexts": [],
                "enrichment_path": "euria-direct-web",
                "rag_lookup_attempted": True,
                "rag_context_used": False,
            },
        }

    if _should_skip_euria_rag(prompt):
        return {
            "messages": _build_euria_direct_messages(prompt, history),
            "temperature": 0.3,
            "max_tokens": 1700,
            "operation": "conversation_euria_fast",
            "enable_web_search": False,
            "result": {
                "sources": [],
                "provenance": "vault",
                "query_overview": {},
                "entity_contexts": [],
                "enrichment_path": "euria-direct",
                "rag_lookup_attempted": False,
                "rag_context_used": False,
            },
        }

    rag_context, rag_sources = _build_local_rag_context(prompt, svc)
    if rag_context:
        return {
            "messages": _build_euria_rag_messages(prompt, history, rag_context, rag_sources),
            "temperature": 0.2,
            "max_tokens": 1700,
            "operation": "conversation_euria_rag",
            "enable_web_search": False,
            "result": {
                "sources": list(rag_sources or []),
                "provenance": "vault",
                "query_overview": {},
                "entity_contexts": [],
                "enrichment_path": "euria-rag",
                "rag_lookup_attempted": True,
                "rag_context_used": True,
            },
        }

    return {
        "messages": _build_euria_direct_messages(prompt, history),
        "temperature": 0.3,
        "max_tokens": 1700,
        "operation": "conversation_euria_fast",
        "enable_web_search": False,
        "result": {
            "sources": [],
            "provenance": "vault",
            "query_overview": {},
            "entity_contexts": [],
            "enrichment_path": "euria-direct",
            "rag_lookup_attempted": _can_build_local_rag_context(svc),
            "rag_context_used": False,
        },
    }


def _generate_euria_direct_answer(*, prompt: str, history: list[dict[str, str]], llm) -> dict[str, Any]:
    return _generate_euria_direct_answer_with_options(prompt=prompt, history=history, llm=llm, enable_web_search=False)


def _generate_euria_direct_answer_with_options(
    *,
    prompt: str,
    history: list[dict[str, str]],
    llm,
    enable_web_search: bool,
) -> dict[str, Any]:
    if enable_web_search:
        web_results = _fetch_ddg_snippets(prompt)
        messages = (
            _build_euria_web_messages(prompt, history, web_results)
            if web_results
            else _build_euria_direct_messages(prompt, history)
        )
    else:
        messages = _build_euria_direct_messages(prompt, history)
    answer = llm.chat(
        messages,
        temperature=0.3,
        max_tokens=4096 if enable_web_search else 1700,
        operation="conversation_euria_fast_web" if enable_web_search else "conversation_euria_fast",
        enable_web_search=enable_web_search,
    )
    cleaned_answer = _sanitize_assistant_answer_text(answer)
    if not cleaned_answer:
        raise RuntimeError("Euria n'a renvoyé aucune réponse exploitable.")
    return {
        "answer": cleaned_answer,
        "sources": [],
        "provenance": "web" if enable_web_search else "vault",
        "query_overview": {},
        "entity_contexts": [],
        "enrichment_path": "euria-direct-web" if enable_web_search else "euria-direct",
    }


def _run_chat_generation_worker(*, prompt: str, history: list[dict[str, str]], use_euria: bool = False) -> dict[str, Any]:
    payload = json.dumps({"prompt": prompt, "history": history, "useEuria": use_euria}, ensure_ascii=False)
    project_root = str(Path(__file__).resolve().parents[2])
    primary_detail: str | None = None
    workers = [
        ("src.api.chat_worker", "Le worker MLX a planté pendant la génération du message."),
        ("src.api.chat_fallback_worker", "Le fallback lexical a échoué pendant la génération du message."),
    ]

    for index, (module_name, crash_detail) in enumerate(workers):
        try:
            completed = subprocess.run(
                [sys.executable, "-m", module_name],
                input=payload,
                text=True,
                capture_output=True,
                cwd=project_root,
                timeout=300,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            if index == 0:
                primary_detail = "Le worker de génération a dépassé le délai autorisé."
                continue
            raise RuntimeError(primary_detail or "Le worker de génération a dépassé le délai autorisé.") from exc

        if completed.returncode == 0:
            stdout = (completed.stdout or "").strip()
            try:
                return _decode_worker_payload(stdout)
            except RuntimeError as exc:
                if index == 0:
                    primary_detail = str(exc)
                    continue
                raise RuntimeError(primary_detail or str(exc)) from exc

        stderr = (completed.stderr or "").strip()
        if completed.returncode < 0 or completed.returncode in {138, 139}:
            detail = crash_detail
        else:
            detail = stderr.splitlines()[-1] if stderr else crash_detail

        if index == 0:
            primary_detail = detail
            continue
        raise RuntimeError(primary_detail or detail)

    raise RuntimeError(primary_detail or "Le worker de génération a échoué pendant la génération du message.")




def _source_from_chunk(chunk: dict) -> SourceRefModel:
    metadata = chunk.get("metadata") or {}
    return SourceRefModel(
        filePath=str(metadata.get("file_path") or ""),
        noteTitle=str(metadata.get("note_title") or metadata.get("file_path") or "Source"),
        dateModified=str(metadata.get("date_modified") or "") or None,
        score=float(chunk.get("score", 0.0) or 0.0),
        isPrimary=bool(metadata.get("is_primary")),
    )


def _build_source_models(sources: list[dict]) -> list[SourceRefModel]:
    deduped: dict[str, SourceRefModel] = {}
    for chunk in sources:
        source = _source_from_chunk(chunk)
        source_key = _source_identity_key(source)
        if not source_key:
            continue
        current = deduped.get(source_key)
        if current is None:
            deduped[source_key] = source
            continue
        deduped[source_key] = _merge_source_refs(current, source)
    return list(deduped.values())


def _linkify_answer_note_citations(answer: str, sources: list[SourceRefModel]) -> str:
    if not answer or not sources:
        return answer

    citation_map = _build_citation_source_map(sources)
    if not citation_map:
        return answer

    pattern = re.compile(r"(?<!\[)\[([^\[\]\n]{2,200})\](?!\(|\])")

    def _replace(match: re.Match[str]) -> str:
        label = str(match.group(1) or "").strip()
        if not label:
            return match.group(0)
        source = citation_map.get(_normalize_citation_key(label))
        if source is None or not source.filePath:
            return match.group(0)
        target = source.filePath[:-3] if source.filePath.endswith(".md") else source.filePath
        return f"[[{target}|{label}]]"

    return pattern.sub(_replace, answer)


def _build_citation_source_map(sources: list[SourceRefModel]) -> dict[str, SourceRefModel]:
    mapping: dict[str, SourceRefModel] = {}
    for source in sources:
        if not source.filePath:
            continue
        candidates = {
            _normalize_citation_key(str(source.noteTitle or "")),
            _normalize_citation_key(Path(source.filePath).stem),
        }
        for candidate in candidates:
            if candidate and candidate not in mapping:
                mapping[candidate] = source
    return mapping


def _normalize_citation_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    normalized = normalized.replace("_", " ")
    return " ".join(normalized.split())


def _source_identity_key(source: SourceRefModel) -> str:
    normalized_path = ""
    if source.filePath:
        normalized_path = normalize_vault_relative_path(source.filePath, vault_root=settings.vault).lower()
    note_title = " ".join(str(source.noteTitle or "").lower().split())
    if normalized_path and note_title:
        return f"{normalized_path}|{note_title}"
    if normalized_path:
        return normalized_path
    if note_title:
        return f"title:{note_title}"
    return ""


def _merge_source_refs(current: SourceRefModel, incoming: SourceRefModel) -> SourceRefModel:
    merged_score: float | None = None
    if current.score is not None and incoming.score is not None:
        merged_score = max(current.score, incoming.score)
    elif current.score is not None:
        merged_score = current.score
    elif incoming.score is not None:
        merged_score = incoming.score

    merged_date = current.dateModified or incoming.dateModified
    if current.dateModified and incoming.dateModified:
        merged_date = max(current.dateModified, incoming.dateModified)

    return SourceRefModel(
        filePath=current.filePath or incoming.filePath,
        noteTitle=current.noteTitle or incoming.noteTitle or incoming.filePath or current.filePath or "Source",
        dateModified=merged_date,
        score=merged_score,
        isPrimary=bool(current.isPrimary or incoming.isPrimary),
    )


def _related_note_from_note(item: dict) -> RelatedNoteModel:
    return RelatedNoteModel(
        title=item.get("title") or Path(item.get("file_path", "")).stem,
        filePath=item.get("file_path", ""),
        dateModified=item.get("date_modified"),
        sizeBytes=_artifact_size_bytes(item.get("file_path", "")),
    )


def _related_note_from_link(link: str, svc) -> RelatedNoteModel:
    matched = next(
        (
            note
            for note in svc.chroma.list_notes_sorted_by_title()
            if str(note.get("title") or "").lower() == str(link).lower()
        ),
        None,
    )
    if matched is None:
        return RelatedNoteModel(title=link, filePath=link)
    return _related_note_from_note(matched)


def _artifact_kind(file_path: str) -> str:
    normalized = file_path.replace("\\", "/").lower()
    if "/obsirag/synapses/" in normalized or normalized.startswith("obsirag/synapses/"):
        return "synapse"
    if "/obsirag/synthesis/" in normalized or normalized.startswith("obsirag/synthesis/"):
        return "synthesis"
    if "/obsirag/conversations/" in normalized or normalized.startswith("obsirag/conversations/"):
        return "conversation"
    return "insight"


def _note_excerpt(file_path: str) -> str | None:
    text = read_text_file(resolve_vault_path(file_path), default="", errors="replace")
    cleaned = strip_frontmatter(text).strip()
    if not cleaned:
        return None
    compact = " ".join(cleaned.split())
    return compact[:180] + ("…" if len(compact) > 180 else "")


def _build_graph_payload(
    *,
    selected_folders: list[str],
    selected_tags: list[str],
    selected_types: list[str],
    search_text: str,
    recency_days: int | None,
) -> GraphDataModel:
    svc = get_service_manager()
    all_notes = _notes_with_graph_context(svc.chroma.list_notes_sorted_by_title())
    filtered_notes = brain_explorer.filter_brain_notes(
        all_notes,
        selected_folders=selected_folders or ["Tous"],
        selected_tags=selected_tags,
        selected_types=selected_types or None,
        search_text=search_text,
        modified_within_days=recency_days,
        now=datetime.now(),
    )
    graph = GraphBuilder().build(filtered_notes)
    filter_options = GraphFilterOptionsModel(
        folders=list(svc.chroma.list_note_folders()),
        tags=list(svc.chroma.list_note_tags()),
        types=[option["key"] for option in get_note_type_options()],
    )
    return _graph_to_model(
        graph,
        filtered_notes=filtered_notes,
        all_notes=all_notes,
        filter_options=filter_options,
        total_note_count=len(all_notes),
    )


def _graph_to_model(
    graph: nx.DiGraph,
    *,
    filtered_notes: list[dict] | list[GraphNoteOptionModel],
    all_notes: list[dict] | list[GraphNoteOptionModel],
    filter_options: GraphFilterOptionsModel,
    total_note_count: int,
) -> GraphDataModel:
    node_items = list(graph.nodes(data=True))
    edge_items = list(graph.edges())
    builder = GraphBuilder()
    stats = builder.get_stats(graph)
    filtered_note_records = _normalize_graph_note_records(filtered_notes)
    all_note_records = _normalize_graph_note_records(all_notes)
    spotlight = [
        GraphSpotlightItemModel(
            filePath=item["file_path"],
            title=item["title"],
            score=float(item["score"]),
            dateModified=item.get("date_modified") or None,
            tags=list(item.get("tags") or []),
            noteType=item.get("note_type") or get_note_type(item["file_path"]),
        )
        for item in brain_explorer.build_centrality_spotlight(filtered_note_records, stats.get("top_connected", []), limit=6)
    ]
    recent_notes = [
        GraphNoteOptionModel(
            title=item.get("title") or Path(item["file_path"]).stem,
            filePath=item["file_path"],
            dateModified=item.get("date_modified") or None,
            noteType=item.get("note_type") or get_note_type(item["file_path"]),
        )
        for item in brain_explorer.build_recent_notes(filtered_note_records, limit=6)
    ]
    folder_summary = [
        GraphSummaryCountModel(label=str(item["folder"]), count=int(item["count"]))
        for item in brain_explorer.build_folder_summary(filtered_note_records, limit=6)
    ]
    tag_summary = [
        GraphSummaryCountModel(label=str(item["tag"]), count=int(item["count"]))
        for item in brain_explorer.build_tag_summary(filtered_note_records, limit=8)
    ]
    type_summary = [
        GraphSummaryCountModel(label=str(item["type"]), count=int(item["count"]))
        for item in brain_explorer.build_type_summary(filtered_note_records)
    ]
    note_lookup = {item["file_path"]: item for item in filtered_note_records}
    top_nodes = sorted(
        [
            GraphTopNodeModel(
                id=item["file_path"],
                label=str((note_lookup.get(item["file_path"]) or {}).get("title") or item["file_path"]),
                degree=int(graph.degree(item["file_path"])) if item["file_path"] in graph else 0,
            )
            for item in stats.get("top_connected", [])
            if item.get("file_path") in graph
        ],
        key=lambda item: item.degree,
        reverse=True,
    )[:8]
    return GraphDataModel(
        nodes=[
            GraphNodeModel(
                id=node_id,
                label=str(data.get("label") or node_id),
                group=str(data.get("folder") or "root"),
                degree=int(graph.degree(node_id)),
                tags=list(data.get("tags") or []),
                noteType=str(data.get("note_type") or "user"),
                dateModified=str(data.get("date_modified") or "") or None,
            )
            for node_id, data in node_items
        ],
        edges=[
            GraphEdgeModel(id=f"edge-{index}", source=source, target=target)
            for index, (source, target) in enumerate(edge_items)
        ],
        metrics=GraphMetricsModel(
            nodeCount=graph.number_of_nodes(),
            edgeCount=graph.number_of_edges(),
            density=round(nx.density(graph), 4) if graph.number_of_nodes() > 1 else 0.0,
            filteredNoteCount=len(filtered_note_records),
            totalNoteCount=total_note_count,
        ),
        topNodes=top_nodes,
        filterOptions=filter_options,
        noteOptions=[
            GraphNoteOptionModel(
                title=item.get("title") or Path(item["file_path"]).stem,
                filePath=item["file_path"],
                dateModified=item.get("date_modified") or None,
                noteType=item.get("note_type") or get_note_type(item["file_path"]),
            )
            for item in all_note_records
        ],
        spotlight=spotlight,
        recentNotes=recent_notes,
        folderSummary=folder_summary,
        tagSummary=tag_summary,
        typeSummary=type_summary,
        legend=[
            GraphLegendItemModel(
                key=option["key"],
                label=option["label"],
                color=option["graph_fill"],
            )
            for option in get_note_type_options()
        ],
    )


def _mount_expo_web_if_available() -> None:
    dist_dir = settings.expo_web_dist_dir
    if not dist_dir.exists():
        return
    app.mount("/", _SinglePageAppFiles(directory=str(dist_dir), html=True), name="expo-web")


_mount_expo_web_if_available()


def _notes_with_graph_context(notes: list[dict]) -> list[dict]:
    return [
        {
            **note,
            "folder": str(Path(note["file_path"]).parent),
            "note_type": get_note_type(note["file_path"]),
        }
        for note in notes
    ]


def _normalize_graph_note_records(notes: list[dict] | list[GraphNoteOptionModel]) -> list[dict]:
    normalized: list[dict] = []
    for note in notes:
        if isinstance(note, GraphNoteOptionModel):
            normalized.append(
                {
                    "title": note.title,
                    "file_path": note.filePath,
                    "date_modified": note.dateModified or "",
                    "note_type": note.noteType or get_note_type(note.filePath),
                    "folder": str(Path(note.filePath).parent),
                    "tags": [],
                }
            )
            continue
        normalized.append(note)
    return normalized


def _graph_from_model(payload: GraphDataModel) -> nx.DiGraph:
    graph = nx.DiGraph()
    for node in payload.nodes:
        graph.add_node(
            node.id,
            label=node.label,
            folder=node.group,
            tags=list(node.tags),
            note_type=node.noteType,
            date_modified=node.dateModified,
        )
    for edge in payload.edges:
        if edge.source in graph and edge.target in graph:
            graph.add_edge(edge.source, edge.target)
    return graph


def _graph_records_from_nodes(nodes: list[GraphNodeModel], kept_ids) -> list[dict]:
    allowed_ids = set(kept_ids)
    return [
        {
            "title": node.label,
            "file_path": node.id,
            "date_modified": node.dateModified or "",
            "note_type": node.noteType or get_note_type(node.id),
            "folder": node.group,
            "tags": list(node.tags),
        }
        for node in nodes
        if node.id in allowed_ids
    ]
