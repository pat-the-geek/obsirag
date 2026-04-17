from __future__ import annotations

import asyncio
import json
import queue
import re
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

import frontmatter
import networkx as nx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from src.ai.web_search import _format_query_overview_markdown, build_query_overview_sync, is_not_in_vault
from src.api.conversation_store import ApiConversationStore
from src.api.runtime import get_service_manager
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
    SaveConversationResponse,
    SessionRequest,
    SessionResponse,
    SourceRefModel,
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
    ("web", "Recherche DDG"),
    ("finalize", "Finalisation de la reponse"),
]


def _load_processing_status() -> dict[str, Any]:
    default = {"active": False, "note": "", "step": "", "log": []}
    return JsonStateStore(settings.processing_status_file).load(default)


def _load_indexing_status() -> dict[str, Any]:
    default = {"running": False, "processed": 0, "total": 0, "current": ""}
    return JsonStateStore(settings.data_dir / "stats" / "service_manager_status.json").load(default)


def _load_index_state() -> dict[str, str]:
    return JsonStateStore(settings.index_state_file).load({})


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
        backendUrlHint="http://localhost:8000",
        mode="token" if expected else "open",
    )


@app.get("/api/v1/session", response_model=SessionResponse)
def get_session(_: None = Depends(require_api_auth)) -> SessionResponse:
    expected = (settings.api_access_token or "").strip()
    return SessionResponse(
        authenticated=True,
        requiresAuth=bool(expected),
        tokenPreview=_token_preview(expected),
        backendUrlHint="http://localhost:8000",
        mode="token" if expected else "open",
    )


@app.get("/api/v1/system/status", response_model=SystemStatusResponse)
def system_status(_: None = Depends(require_api_auth)) -> SystemStatusResponse:
    indexing_status = _load_indexing_status()
    index_state = _load_index_state()

    return SystemStatusResponse(
        backendReachable=True,
        llmAvailable=True,
        notesIndexed=len(index_state),
        chunksIndexed=_count_chunks_fast(),
        indexing=indexing_status,
        autolearn=_resolve_autolearn_status(),
        alerts=[
            SystemAlertModel(
                id="api-runtime",
                level="info",
                title="API FastAPI active",
                description="Le backend Expo est demarre et peut servir le client mobile/web.",
            )
        ],
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
            turnCount=len([message for message in item.messages if message.role == "user"]),
            messageCount=len(item.messages),
        )
        for item in sorted(items, key=lambda conv: conv.updatedAt, reverse=True)
    ]


@app.post("/api/v1/conversations", response_model=ConversationDetailModel)
def create_conversation(payload: CreateConversationRequest, _: None = Depends(require_api_auth)) -> ConversationDetailModel:
    return conversation_store.create(payload.title)


@app.get("/api/v1/conversations/{conversation_id}", response_model=ConversationDetailModel)
def get_conversation(conversation_id: str, _: None = Depends(require_api_auth)) -> ConversationDetailModel:
    item = conversation_store.get(conversation_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return item


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
    return updated


@app.post("/api/v1/conversations/{conversation_id}/save", response_model=SaveConversationResponse)
def save_conversation(conversation_id: str, _: None = Depends(require_api_auth)) -> SaveConversationResponse:
    try:
        path = conversation_store.save_markdown(conversation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    return SaveConversationResponse(path=str(path.relative_to(settings.vault)))


@app.post("/api/v1/conversations/{conversation_id}/messages", response_model=ChatMessageModel)
async def create_message(
    conversation_id: str,
    payload: MessageCreateRequest,
    _: None = Depends(require_api_auth),
) -> ChatMessageModel:
    svc = get_service_manager()
    user_message, history = _prepare_user_message(conversation_id, payload.prompt)
    conversation_store.append_messages(conversation_id, [user_message])

    started_at = time.perf_counter()
    try:
        result = _run_chat_generation_worker(prompt=payload.prompt, history=history)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    answer = str(result.get("answer") or "")
    sources = list(result.get("sources") or [])
    sentinel = is_not_in_vault(answer)
    source_models = [_source_from_chunk(chunk) for chunk in sources]
    primary_source = next((item for item in source_models if item.isPrimary), None)
    entity_contexts = _enrich_entity_contexts(
        user_text=payload.prompt,
        answer=answer,
        entity_contexts=_lookup_conversation_entity_contexts(payload.prompt, answer, svc),
        sources=source_models,
        primary_source=primary_source,
        svc=svc,
    )
    query_overview = _lookup_query_overview(payload.prompt, svc) if sentinel else {}
    assistant_message = _build_assistant_message(
        answer=answer,
        sources=sources,
        started_at=started_at,
        timeline=[],
        query_overview=query_overview,
        entity_contexts=entity_contexts,
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
    user_message, history = _prepare_user_message(conversation_id, payload.prompt)
    conversation_store.append_messages(conversation_id, [user_message])
    started_at = time.perf_counter()
    worker_task = asyncio.create_task(asyncio.to_thread(_run_chat_generation_worker, prompt=payload.prompt, history=history))

    async def _event_stream():
        timeline: list[str] = []
        yield _sse_event("message_start", {"conversationId": conversation_id, "messageId": user_message.id})
        result: dict[str, Any] | None = None
        emitted_preparation_steps: set[str] = set()

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
        source_models = [_source_from_chunk(chunk) for chunk in sources]
        primary_source = next((item for item in source_models if item.isPrimary), None)

        _append_timeline_step(timeline, "Réponse générée par le worker API")
        yield _sse_event("retrieval_status", {"phase": "generation", "message": "Réponse générée par le worker API"})

        entity_contexts: list[dict[str, Any]] = []
        query_overview: dict[str, Any] = {}
        enrichment_steps = [
            ("entities", "Extraction des entites NER"),
            *([("web", "Recherche DDG")] if sentinel else []),
            ("finalize", "Finalisation de la reponse"),
        ]
        for phase, status_message in enrichment_steps:
            _append_timeline_step(timeline, status_message)
            yield _sse_event("retrieval_status", {"phase": phase, "message": status_message})
            if phase == "entities":
                entity_contexts = _enrich_entity_contexts(
                    user_text=payload.prompt,
                    answer=answer,
                    entity_contexts=_lookup_conversation_entity_contexts(payload.prompt, answer, svc),
                    sources=source_models,
                    primary_source=primary_source,
                    svc=svc,
                )
            elif phase == "web":
                query_overview = _lookup_query_overview(payload.prompt, svc)

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
        )
        for note in matches[:20]
    ]


@app.get("/api/v1/notes/{note_path:path}", response_model=NoteDetailModel)
def get_note(note_path: str, _: None = Depends(require_api_auth)) -> NoteDetailModel:
    svc = get_service_manager()
    normalized = normalize_vault_relative_path(note_path)
    note = svc.chroma.get_note_by_file_path(normalized)
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
        noteType=get_note_type(normalized),
        outline=extract_note_outline(content),
    )


@app.post("/api/v1/notes/{note_path:path}/synapses/discover", response_model=DetectSynapsesResponseModel)
def detect_note_synapses(note_path: str, _: None = Depends(require_api_auth)) -> DetectSynapsesResponseModel:
    svc = get_service_manager()
    svc.signal_ui_active()

    normalized = normalize_vault_relative_path(note_path)
    note = svc.chroma.get_note_by_file_path(normalized)
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
        kind = _artifact_kind(note.get("file_path", ""))
        entries.append(
            InsightItemModel(
                id=note.get("file_path", ""),
                title=note.get("title") or Path(note.get("file_path", "")).stem,
                filePath=note.get("file_path", ""),
                kind=kind,
                provenance="vault",
                tags=list(note.get("tags", []) or []),
                dateModified=note.get("date_modified"),
                excerpt=_note_excerpt(note.get("file_path", "")),
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
    svc.signal_ui_active()
    overview = build_query_overview_sync(payload.query, svc.llm)
    if not overview:
        raise HTTPException(status_code=404, detail="No web results found")

    query_overview = QueryOverviewModel(
        query=str(overview.get("query") or payload.query),
        searchQuery=str(overview.get("search_query") or payload.query),
        summary=str(overview.get("summary") or ""),
        sources=[_web_source_model(item) for item in (overview.get("sources") or []) if item.get("href")],
    )
    content = _format_query_overview_markdown(overview)
    entity_contexts = _enrich_entity_contexts(
        user_text=payload.query,
        answer=content,
        entity_contexts=_lookup_conversation_entity_contexts(payload.query, content, svc),
        sources=[],
        primary_source=None,
        svc=svc,
    )
    return WebSearchResponseModel(
        content=content,
        queryOverview=query_overview,
        entityContexts=_entity_context_models(entity_contexts),
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
    timeline: list[str],
    query_overview: dict[str, Any] | None = None,
    entity_contexts: list[dict[str, Any]] | None = None,
) -> ChatMessageModel:
    elapsed = max(time.perf_counter() - started_at, 0.001)
    source_models = [_source_from_chunk(chunk) for chunk in sources]
    primary_source = next((item for item in source_models if item.isPrimary), None)
    token_count = len(answer.split())
    return ChatMessageModel(
        id=f"assistant-{datetime.now(UTC).timestamp()}",
        role="assistant",
        content=answer,
        createdAt=datetime.now(UTC).isoformat(),
        sources=source_models,
        primarySource=primary_source,
        timeline=timeline,
        queryOverview=_query_overview_model(query_overview),
        entityContexts=_entity_context_models(entity_contexts),
        provenance="vault",
        sentinel=is_not_in_vault(answer),
        stats={
            "tokens": token_count,
            "ttft": 0.0,
            "total": round(elapsed, 3),
            "tps": round(token_count / elapsed, 3),
        },
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


def _lookup_query_overview(user_text: str, svc) -> dict[str, Any]:
    if not user_text or len(user_text.strip()) < 3:
        return {}
    try:
        result = build_query_overview_sync(user_text, svc.llm)
        return result if isinstance(result, dict) else {}
    except Exception:
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

    explanations = _generate_entity_relation_explanations(user_text, answer, evidence_rows, svc)
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
) -> dict[str, str]:
    if not evidence_rows:
        return {}

    llm = getattr(svc, "llm", None)
    chat = getattr(llm, "chat", None)
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
                {"role": "system", "content": "Tu produis des explications relationnelles d'entités, précises et très concises."},
                {"role": "user", "content": "\n".join(prompt_lines)},
            ],
            temperature=0.0,
            max_tokens=500,
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
    words = answer.split()
    if not words:
        return [answer] if answer else []
    return [f"{word} " for word in words[:-1]] + [words[-1]]


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


def _run_chat_generation_worker(*, prompt: str, history: list[dict[str, str]]) -> dict[str, Any]:
    payload = json.dumps({"prompt": prompt, "history": history}, ensure_ascii=False)
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


def _related_note_from_note(item: dict) -> RelatedNoteModel:
    return RelatedNoteModel(
        title=item.get("title") or Path(item.get("file_path", "")).stem,
        filePath=item.get("file_path", ""),
        dateModified=item.get("date_modified"),
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
