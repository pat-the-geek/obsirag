from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException

from src.ai.mermaid_sanitizer import sanitize_mermaid_blocks
from src.api.app import (
    _build_source_models,
    _sanitize_assistant_answer_text,
    get_graph_subgraph as api_get_graph_subgraph,
    get_note as api_get_note,
    search_notes as api_search_notes,
    system_status as api_system_status,
)
from src.api.runtime import get_service_manager

_SENTINEL_ANSWER = "Cette information n'est pas dans ton coffre."


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
) -> dict[str, Any]:
    safe_question = str(question or "").strip()
    if not safe_question:
        raise ValueError("question must not be empty")

    service_manager = get_service_manager()
    service_manager.signal_ui_active()
    answer, sources = service_manager.rag.query(
        safe_question,
        chat_history=_normalize_history(history),
        exclude_obsirag_generated=exclude_obsirag_generated,
    )
    source_models = _build_source_models(list(sources or []))
    primary_source = next((item for item in source_models if item.isPrimary), None)
    sanitized_answer = sanitize_mermaid_blocks(_sanitize_assistant_answer_text(str(answer or "")))

    return {
        "question": safe_question,
        "answer": sanitized_answer,
        "sentinel": sanitized_answer.strip().lower() == _SENTINEL_ANSWER.lower(),
        "sourceCount": len(source_models),
        "sources": [item.model_dump(mode="json") for item in source_models],
        "primarySource": primary_source.model_dump(mode="json") if primary_source is not None else None,
    }


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
    return _to_json(payload)
