from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException

from src.ai.mermaid_sanitizer import sanitize_mermaid_blocks
from src.api.app import (
    _build_source_models,
    _build_graph_filter_options,
    _sanitize_assistant_answer_text,
    get_graph_subgraph as api_get_graph_subgraph,
    get_note as api_get_note,
    search_notes as api_search_notes,
    system_status as api_system_status,
)
from src.api.runtime import get_service_manager

_SENTINEL_ANSWER = "Cette information n'est pas dans ton coffre."


class _WebSearchEuriaClient:
    """Wrapper autour d'EuriaClient qui active enable_web_search=True sur chaque appel chat()."""

    def __init__(self, inner) -> None:
        self._inner = inner

    def __getattr__(self, name: str):
        return getattr(self._inner, name)

    def chat(self, messages, **kwargs):
        kwargs.setdefault("enable_web_search", True)
        return self._inner.chat(messages, **kwargs)


def _build_rag(*, use_euria: bool, web_search: bool):
    """Retourne le RAGPipeline approprié selon les options demandées."""
    svc = get_service_manager()
    if not use_euria:
        return svc.rag
    from src.ai.euria_client import EuriaClient
    from src.ai.rag import RAGPipeline
    llm = EuriaClient()
    if web_search:
        llm = _WebSearchEuriaClient(llm)
    return RAGPipeline(svc.chroma, llm, metrics=svc.metrics)


def _euria_web_fallback(
    question: str,
    normalized_history: list[dict[str, str]],
    *,
    exclude_obsirag_generated: bool,
) -> dict[str, Any] | None:
    """Retry avec EurIA+web quand la sentinelle Ollama s'est déclenchée.

    Retourne None si EurIA n'est pas configuré ou si l'appel échoue,
    afin de laisser le caller retourner la réponse sentinel originale.
    """
    try:
        from src.ai.euria_client import EuriaClient
        from src.ai.rag import RAGPipeline
        svc = get_service_manager()
        rag = RAGPipeline(svc.chroma, _WebSearchEuriaClient(EuriaClient()), metrics=svc.metrics)
        answer, sources = rag.query(
            question,
            chat_history=normalized_history,
            exclude_obsirag_generated=exclude_obsirag_generated,
        )
        source_models = _build_source_models(list(sources or []))
        primary = next((s for s in source_models if s.isPrimary), None)
        sanitized = sanitize_mermaid_blocks(_sanitize_assistant_answer_text(str(answer or "")))
        return {
            "question": question,
            "answer": sanitized,
            "sentinel": sanitized.strip().lower() == _SENTINEL_ANSWER.lower(),
            "suggestEuriaWebSearch": False,
            "web_search_performed": True,
            "provider": "euria+web",
            "sourceCount": len(source_models),
            "sources": [s.model_dump(mode="json") for s in source_models],
            "primarySource": primary.model_dump(mode="json") if primary is not None else None,
        }
    except Exception:
        return None


def _to_json(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_to_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_json(item) for key, item in value.items()}
    return value


def _detail_to_text(detail: Any) -> str:
    if isinstance(detail, str):
        return detail
    return json.dumps(detail, ensure_ascii=False)


def _raise_mcp_error(exc: HTTPException) -> None:
    detail = _detail_to_text(exc.detail)
    if exc.status_code < 500:
        raise ValueError(detail) from exc
    raise RuntimeError(detail) from exc


def _normalize_history(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if role and content:
            normalized.append({"role": role, "content": content})
    return normalized


def get_system_status_payload() -> dict[str, Any]:
    try:
        return _to_json(api_system_status())
    except HTTPException as exc:
        _raise_mcp_error(exc)


def search_notes_payload(query: str, limit: int = 10) -> dict[str, Any]:
    safe_query = str(query or "").strip()
    safe_limit = max(1, min(int(limit), 20))
    try:
        notes = api_search_notes(safe_query)
    except HTTPException as exc:
        _raise_mcp_error(exc)
    sliced = notes[:safe_limit]
    return {
        "query": safe_query,
        "count": len(sliced),
        "notes": _to_json(sliced),
    }


def get_note_payload(note_path: str) -> dict[str, Any]:
    safe_note_path = str(note_path or "").strip()
    if not safe_note_path:
        raise ValueError("note_path must not be empty")
    try:
        return _to_json(api_get_note(safe_note_path))
    except HTTPException as exc:
        _raise_mcp_error(exc)


def ask_rag_payload(
    question: str,
    history: list[dict[str, str]] | None = None,
    *,
    exclude_obsirag_generated: bool = False,
    use_euria: bool = False,
    web_search: bool = False,
) -> dict[str, Any]:
    safe_question = str(question or "").strip()
    if not safe_question:
        raise ValueError("question must not be empty")

    get_service_manager().signal_ui_active()
    normalized_history = _normalize_history(history)
    euria_failed = False
    try:
        rag = _build_rag(use_euria=use_euria, web_search=web_search)
        answer, sources = rag.query(
            safe_question,
            chat_history=normalized_history,
            exclude_obsirag_generated=exclude_obsirag_generated,
        )
    except Exception as _euria_exc:
        if not use_euria:
            raise
        import logging as _logging
        _logging.getLogger(__name__).warning(f"EurIA indisponible, fallback Ollama : {_euria_exc}")
        euria_failed = True
        rag = get_service_manager().rag
        answer, sources = rag.query(
            safe_question,
            chat_history=normalized_history,
            exclude_obsirag_generated=exclude_obsirag_generated,
        )
    source_models = _build_source_models(list(sources or []))
    primary_source = next((item for item in source_models if item.isPrimary), None)
    sanitized_answer = sanitize_mermaid_blocks(_sanitize_assistant_answer_text(str(answer or "")))

    is_sentinel = sanitized_answer.strip().lower() == _SENTINEL_ANSWER.lower()

    # When Euria returned no local sources, supplement with Ollama retrieval so the
    # caller always gets vault references regardless of which LLM generated the answer.
    if use_euria and not euria_failed and not source_models:
        try:
            local_rag = get_service_manager().rag
            _, local_sources = local_rag.query(
                safe_question,
                chat_history=normalized_history,
                exclude_obsirag_generated=exclude_obsirag_generated,
            )
            local_source_models = _build_source_models(list(local_sources or []))
            if local_source_models:
                source_models = local_source_models
                primary_source = next((s for s in source_models if s.isPrimary), None)
                # If local RAG finds matching sources, the sentinel is no longer valid
                if is_sentinel:
                    is_sentinel = False
        except Exception:
            pass

    # Fallback automatique EurIA+web quand la sentinelle Ollama se déclenche.
    # Gardé uniquement pour les requêtes non-personnelles : les requêtes possessives
    # (mes projets, mon coffre…) doivent rester dans le corpus local.
    _PERSONAL_QUERY_RE = re.compile(
        r"\b(mes\s+\w+|mon\s+\w+|ma\s+\w+|mes\s+projets?|j.ai|je\s+\w+)\b", re.I
    )
    euria_fallback_allowed = not _PERSONAL_QUERY_RE.search(safe_question)
    if is_sentinel and not use_euria and euria_fallback_allowed:
        fallback = _euria_web_fallback(
            safe_question,
            normalized_history,
            exclude_obsirag_generated=exclude_obsirag_generated,
        )
        if fallback is not None:
            return fallback

    suggest_conversation = None
    if is_sentinel or len(source_models) < 3:
        reason = "sentinel" if is_sentinel else "low_source_count"
        suggest_conversation = {
            "reason": reason,
            "suggestedFollowup": safe_question[:120],
        }

    if euria_failed:
        provider_field = "ollama (euria unavailable)"
    elif use_euria:
        provider_field = "euria+web" if web_search else "euria"
    else:
        provider_field = "ollama"

    return {
        "question": safe_question,
        "answer": sanitized_answer,
        "sentinel": is_sentinel,
        "suggestEuriaWebSearch": is_sentinel,
        "suggestStartConversation": suggest_conversation,
        "web_search_performed": use_euria and web_search and not euria_failed,
        "provider": provider_field,
        "sourceCount": len(source_models),
        "sources": [item.model_dump(mode="json") for item in source_models],
        "primarySource": primary_source.model_dump(mode="json") if primary_source is not None else None,
    }


def conversation_start_payload(
    title: str,
    triggering_question: str,
    trigger_reason: str,
    trigger_explanation: str,
    initial_rag_response: dict,
    first_followup_question: str,
) -> dict[str, Any]:
    from src.mcp.investigation import start_conversation
    try:
        return start_conversation(
            title=title,
            triggering_question=triggering_question,
            trigger_reason=trigger_reason,
            trigger_explanation=trigger_explanation,
            initial_rag_response=initial_rag_response,
            first_followup_question=first_followup_question,
        )
    except (ValueError, RuntimeError) as exc:
        raise ValueError(str(exc)) from exc


def conversation_continue_payload(
    conversation_id: str,
    question: str,
    reasoning: str,
) -> dict[str, Any]:
    from src.mcp.investigation import continue_conversation
    try:
        return continue_conversation(
            conversation_id=conversation_id,
            question=question,
            reasoning=reasoning,
        )
    except (ValueError, RuntimeError, LookupError) as exc:
        raise ValueError(str(exc)) from exc


def conversation_finalize_payload(
    conversation_id: str,
    final_synthesis: str,
    resolved: bool,
) -> dict[str, Any]:
    from src.mcp.investigation import finalize_conversation
    try:
        return finalize_conversation(
            conversation_id=conversation_id,
            final_synthesis=final_synthesis,
            resolved=resolved,
        )
    except (ValueError, RuntimeError, LookupError) as exc:
        raise ValueError(str(exc)) from exc


def browse_notes_by_date_payload(
    limit: int = 10,
    date_from: str | None = None,
    date_to: str | None = None,
    folders: list[str] | None = None,
    tags: list[str] | None = None,
    exclude_obsirag_generated: bool = True,
) -> dict[str, Any]:
    from src.database.lance_store import _is_obsirag_generated_path, _note_type_for_path
    from pathlib import Path

    safe_limit = max(1, min(int(limit), 100))

    # Normalise date_from / date_to en préfixes ISO comparables à date_modified ("YYYY-MM-DDThh:mm:ss")
    iso_from: str | None = None
    iso_to: str | None = None
    if date_from:
        s = str(date_from).strip()[:10]  # garde YYYY-MM-DD
        iso_from = s  # comparaison lexicographique fonctionne sur ISO
    if date_to:
        s = str(date_to).strip()[:10]
        iso_to = s + "T23:59:59"

    folder_prefixes = [f.strip("/") for f in (folders or []) if f.strip()]
    tag_filter = {t.lower().strip().lstrip("#") for t in (tags or []) if t.strip()}

    svc = get_service_manager()
    # list_notes() retourne déjà trié par date_modified DESC et est mis en cache
    notes = svc.chroma.list_notes()

    results = []
    for note in notes:
        fp: str = note.get("file_path", "")
        dm: str = note.get("date_modified", "")

        if exclude_obsirag_generated and _is_obsirag_generated_path(fp):
            continue

        if folder_prefixes:
            parent = str(Path(fp).parent).strip("/")
            if not any(parent == pf or parent.startswith(pf + "/") for pf in folder_prefixes):
                continue

        if tag_filter:
            note_tags = {t.lower().lstrip("#") for t in note.get("tags", []) if t}
            # Tolerance: exact match OR note tag starts with the requested tag prefix
            # e.g. filter "IA" matches "IA", "ia", "IA-generative", "intelligence-artificielle" won't,
            # but "ia-generative" would match prefix "ia".
            def _tag_matches(req_tag: str, note_tags: set) -> bool:
                if req_tag in note_tags:
                    return True
                return any(nt == req_tag or nt.startswith(req_tag + "-") or req_tag.startswith(nt + "-") for nt in note_tags)
            if not any(_tag_matches(rt, note_tags) for rt in tag_filter):
                continue

        if iso_from and dm and dm < iso_from:
            continue
        if iso_to and dm and dm > iso_to:
            continue

        results.append({
            "filePath": fp,
            "title": note.get("title") or Path(fp).stem,
            "dateModified": dm or None,
            "dateCreated": note.get("date_created") or None,
            "noteType": _note_type_for_path(fp),
            "tags": note.get("tags", []),
        })

        if len(results) >= safe_limit:
            break

    return {
        "count": len(results),
        "limit": safe_limit,
        "dateFrom": date_from or None,
        "dateTo": date_to or None,
        "notes": results,
    }


def _is_wikilink_heavy(text: str) -> bool:
    """True when more than half the non-empty lines are wikilink list items."""
    import re as _re
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return True
    wiki_lines = sum(1 for l in lines if _re.match(r"^-?\s*\[\[", l))
    return wiki_lines / len(lines) > 0.5


def search_notes_semantic_payload(
    query: str,
    limit: int = 10,
    exclude_obsirag_generated: bool = True,
) -> dict[str, Any]:
    from pathlib import Path
    from src.database.lance_store import _is_obsirag_generated_path

    safe_query = str(query or "").strip()
    if not safe_query:
        raise ValueError("query must not be empty")

    safe_limit = max(1, min(int(limit), 50))
    svc = get_service_manager()
    chunks = svc.chroma.search(safe_query, top_k=safe_limit * 5)

    seen: dict[str, dict] = {}
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        fp = meta.get("file_path", "")
        if not fp:
            continue
        if exclude_obsirag_generated and _is_obsirag_generated_path(fp):
            continue
        score = chunk.get("score", 0.0)
        text = (chunk.get("text") or "").strip()
        heavy = _is_wikilink_heavy(text)

        if fp not in seen:
            seen[fp] = {
                "filePath": fp,
                "title": meta.get("note_title") or Path(fp).stem,
                "score": round(score, 4),
                "excerpt": text[:300],
                "dateModified": meta.get("date_modified") or None,
                "tags": [t for t in (meta.get("tags") or "").split(",") if t],
                "_prose": not heavy,
            }
        else:
            existing = seen[fp]
            # Upgrade to a higher-scoring chunk
            if score > existing["score"]:
                existing["score"] = round(score, 4)
            # Replace excerpt with a prose chunk even if its score is slightly lower
            if not existing["_prose"] and not heavy:
                existing["excerpt"] = text[:300]
                existing["_prose"] = True

    results = sorted(seen.values(), key=lambda x: x["score"], reverse=True)[:safe_limit]
    for r in results:
        r.pop("_prose", None)
    return {"query": safe_query, "count": len(results), "notes": results}


def get_entity_stats_payload(
    top_n: int = 30,
    entity_type: str = "all",
) -> dict[str, Any]:
    svc = get_service_manager()
    entity_map = svc.chroma.get_entity_map(top_n=top_n)

    allowed = {"persons", "orgs", "locations", "misc"}
    if entity_type != "all" and entity_type in allowed:
        filtered = {entity_type: entity_map.get(entity_type, [])}
    else:
        filtered = {k: entity_map.get(k, []) for k in allowed}

    total = sum(len(v) for v in filtered.values())
    return {"entityType": entity_type, "topN": top_n, "totalEntities": total, "entities": filtered}


def list_folder_payload(
    folder_path: str,
    limit: int = 50,
    exclude_obsirag_generated: bool = True,
) -> dict[str, Any]:
    safe_folder = str(folder_path or "").strip().strip("/")
    if not safe_folder:
        raise ValueError("folder_path must not be empty")

    # Navigating explicitly into obsirag/ shows obsirag content by default —
    # the user knows what they're browsing.
    effective_exclude = exclude_obsirag_generated
    if safe_folder == "obsirag" or safe_folder.startswith("obsirag/"):
        effective_exclude = False

    result = browse_notes_by_date_payload(
        limit=limit,
        folders=[safe_folder],
        exclude_obsirag_generated=effective_exclude,
    )
    result["folder"] = safe_folder
    return result


def get_graph_filters_payload() -> dict[str, Any]:
    """Retourne les options de filtre du graphe (dossiers, tags, types).

    À appeler une seule fois en début de session. Evite ~10 000 tokens de
    nomenclature dans chaque réponse de sous-graphe.
    """
    svc = get_service_manager()
    opts = _build_graph_filter_options(svc)
    return _to_json(opts)


def get_graph_subgraph_payload(
    note_id: str,
    depth: int = 1,
    *,
    folders: list[str] | None = None,
    tags: list[str] | None = None,
    note_types: list[str] | None = None,
    search_text: str = "",
    recency_days: int | None = None,
) -> dict[str, Any]:
    safe_note_id = str(note_id or "").strip()
    if not safe_note_id:
        raise ValueError("note_id must not be empty")

    safe_depth = max(1, min(int(depth), 3))
    try:
        payload = api_get_graph_subgraph(
            noteId=safe_note_id,
            depth=safe_depth,
            folders=list(folders or []),
            tags=list(tags or []),
            noteTypes=list(note_types or []),
            searchText=str(search_text or ""),
            recencyDays=recency_days,
        )
    except HTTPException as exc:
        _raise_mcp_error(exc)
    result = _to_json(payload)
    # noteOptions (~1180 entrées) et filterOptions (~500 tags) ne sont pas utiles pour l'appelant MCP.
    # Utiliser obsirag_get_graph_filters pour récupérer la nomenclature du coffre.
    if isinstance(result, dict):
        result.pop("noteOptions", None)
        result.pop("filterOptions", None)
    return result
