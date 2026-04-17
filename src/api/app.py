from __future__ import annotations

import json
import queue
import sqlite3
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
    DetectSynapsesResponseModel,
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
    return HealthResponse(
        status="ok",
        version="0.1.0",
        llmAvailable=True,
        vectorStoreAvailable=True,
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


@app.post("/api/v1/conversations/{conversation_id}/save", response_model=SaveConversationResponse)
def save_conversation(conversation_id: str, _: None = Depends(require_api_auth)) -> SaveConversationResponse:
    try:
        path = conversation_store.save_markdown(conversation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    return SaveConversationResponse(path=str(path.relative_to(settings.vault)))


@app.post("/api/v1/conversations/{conversation_id}/messages", response_model=ChatMessageModel)
def create_message(
    conversation_id: str,
    payload: MessageCreateRequest,
    _: None = Depends(require_api_auth),
) -> ChatMessageModel:
    svc = get_service_manager()
    svc.signal_ui_active()

    user_message, history = _prepare_user_message(conversation_id, payload.prompt)
    conversation_store.append_messages(conversation_id, [user_message])

    started_at = time.perf_counter()
    answer, sources = svc.rag.query(payload.prompt, chat_history=history)
    assistant_message = _build_assistant_message(answer=answer, sources=sources, started_at=started_at, timeline=[])
    conversation_store.append_messages(
        conversation_id,
        [assistant_message],
        last_generation_stats=assistant_message.stats,
    )
    return assistant_message


@app.post("/api/v1/conversations/{conversation_id}/messages/stream")
def stream_message(
    conversation_id: str,
    payload: MessageCreateRequest,
    _: None = Depends(require_api_auth),
) -> StreamingResponse:
    svc = get_service_manager()
    svc.signal_ui_active()

    user_message, history = _prepare_user_message(conversation_id, payload.prompt)
    conversation_store.append_messages(conversation_id, [user_message])
    progress_queue: queue.SimpleQueue[dict[str, Any]] = queue.SimpleQueue()
    started_at = time.perf_counter()

    def _on_progress(update: dict[str, Any]) -> None:
        progress_queue.put(update)

    stream, sources = svc.rag.query_stream(payload.prompt, chat_history=history, progress_callback=_on_progress)

    def _event_stream():
        timeline: list[str] = []
        chunks: list[str] = []
        yield _sse_event("message_start", {"conversationId": conversation_id, "messageId": user_message.id})
        try:
            while True:
                while True:
                    try:
                        update = progress_queue.get_nowait()
                    except queue.Empty:
                        break
                    message = str(update.get("message") or "").strip()
                    if message:
                        timeline.append(message)
                    yield _sse_event("retrieval_status", update)

                try:
                    token = next(stream)
                except StopIteration:
                    break

                chunks.append(token)
                yield _sse_event("token", {"token": token})

            while True:
                try:
                    update = progress_queue.get_nowait()
                except queue.Empty:
                    break
                message = str(update.get("message") or "").strip()
                if message:
                    timeline.append(message)
                yield _sse_event("retrieval_status", update)

            source_models = [_source_from_chunk(chunk) for chunk in sources]
            yield _sse_event("sources_ready", {"sources": [item.model_dump(mode="json") for item in source_models]})

            assistant_message = _build_assistant_message(
                answer="".join(chunks),
                sources=sources,
                started_at=started_at,
                timeline=timeline,
            )
            conversation_store.append_messages(
                conversation_id,
                [assistant_message],
                last_generation_stats=assistant_message.stats,
            )
            yield _sse_event("message_complete", assistant_message.model_dump(mode="json"))
        except Exception as exc:
            yield _sse_event("message_error", {"detail": str(exc)})

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


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
    return WebSearchResponseModel(
        content=_format_query_overview_markdown(overview),
        queryOverview=query_overview,
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
        provenance="vault",
        sentinel=is_not_in_vault(answer),
        stats={
            "tokens": token_count,
            "ttft": 0.0,
            "total": round(elapsed, 3),
            "tps": round(token_count / elapsed, 3),
        },
    )


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
