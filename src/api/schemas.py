from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str
    version: str
    llmAvailable: bool
    vectorStoreAvailable: bool


class IndexingStatusModel(BaseModel):
    running: bool
    processed: int
    total: int
    current: str = ""


class AutolearnStatusModel(BaseModel):
    active: bool
    managedBy: Literal["none", "worker", "api"] = "none"
    running: bool = False
    pid: int | None = None
    note: str = ""
    step: str = ""
    log: list[str] = Field(default_factory=list)
    startedAt: str | None = None
    updatedAt: str | None = None
    nextRunAt: str | None = None


class SystemAlertModel(BaseModel):
    id: str
    level: Literal["info", "warning", "error"]
    title: str
    description: str


class StartupStatusModel(BaseModel):
    ready: bool = False
    steps: list[str] = Field(default_factory=list)
    currentStep: str = ""
    error: str | None = None
    updatedAt: str | None = None


class RuntimeInfoModel(BaseModel):
    llmProvider: str
    llmModel: str
    embeddingModel: str
    vectorStore: str
    nerModel: str
    autolearnMode: str
    euriaProvider: str | None = None
    euriaModel: str | None = None
    euriaEnabled: bool = False


class SystemStatusResponse(BaseModel):
    backendReachable: bool
    llmAvailable: bool
    notesIndexed: int
    chunksIndexed: int
    indexing: IndexingStatusModel
    autolearn: AutolearnStatusModel
    startup: StartupStatusModel
    runtime: RuntimeInfoModel
    alerts: list[SystemAlertModel] = Field(default_factory=list)


class ReindexResponseModel(BaseModel):
    status: Literal["ok"] = "ok"
    added: int
    updated: int
    deleted: int
    skipped: int
    notesIndexed: int
    chunksIndexed: int
    indexing: IndexingStatusModel


class SourceRefModel(BaseModel):
    filePath: str
    noteTitle: str
    dateModified: str | None = None
    score: float | None = None
    isPrimary: bool | None = None


class GenerationStatsModel(BaseModel):
    tokens: int
    ttft: float
    total: float
    tps: float


class WebSourceModel(BaseModel):
    title: str
    href: str
    body: str | None = None
    domain: str | None = None
    publishedAt: str | None = None


class QueryOverviewModel(BaseModel):
    query: str
    searchQuery: str
    summary: str
    sources: list[WebSourceModel] = Field(default_factory=list)


class WebSearchRequestModel(BaseModel):
    query: str = Field(min_length=1)
    useEuria: bool = False


class WebSearchResponseModel(BaseModel):
    content: str
    llmProvider: str | None = None
    queryOverview: QueryOverviewModel
    entityContexts: list[EntityContextModel] = Field(default_factory=list)
    stats: GenerationStatsModel | None = None
    provenance: Literal["web"] = "web"


class RelatedNoteModel(BaseModel):
    title: str
    filePath: str
    dateModified: str | None = None
    sizeBytes: int | None = None


class DdgKnowledgeModel(BaseModel):
    heading: str | None = None
    entity: str | None = None
    abstractText: str | None = None
    answer: str | None = None
    answerType: str | None = None
    definition: str | None = None
    infobox: list[dict[str, str]] = Field(default_factory=list)
    relatedTopics: list[dict[str, str]] = Field(default_factory=list)


class EntityContextModel(BaseModel):
    type: str
    typeLabel: str
    value: str
    mentions: int | None = None
    lineNumber: int | None = None
    relationExplanation: str | None = None
    imageUrl: str | None = None
    tag: str | None = None
    notes: list[RelatedNoteModel] = Field(default_factory=list)
    ddgKnowledge: DdgKnowledgeModel | None = None


class ChatMessageModel(BaseModel):
    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    createdAt: str
    llmProvider: str | None = None
    sources: list[SourceRefModel] = Field(default_factory=list)
    primarySource: SourceRefModel | None = None
    stats: GenerationStatsModel | None = None
    timeline: list[str] = Field(default_factory=list)
    queryOverview: QueryOverviewModel | None = None
    entityContexts: list[EntityContextModel] = Field(default_factory=list)
    hiddenEntityValues: list[str] = Field(default_factory=list)
    enrichmentPath: str | None = None
    provenance: Literal["vault", "web", "hybrid", "unknown"] = "unknown"
    sentinel: bool = False


class ConversationSummaryModel(BaseModel):
    id: str
    title: str
    preview: str
    updatedAt: str
    sizeBytes: int | None = None
    turnCount: int
    messageCount: int
    isCurrent: bool | None = None


class ConversationDetailModel(BaseModel):
    id: str
    title: str
    updatedAt: str
    sizeBytes: int | None = None
    draft: str = ""
    messages: list[ChatMessageModel] = Field(default_factory=list)
    lastGenerationStats: GenerationStatsModel | None = None
    hiddenEntityValues: list[str] = Field(default_factory=list)


class CreateConversationRequest(BaseModel):
    title: str | None = None


class MessageCreateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    useEuria: bool = False
    useRag: bool = True


class PatchConversationEntityRequest(BaseModel):
    entityValue: str = Field(min_length=1)
    action: Literal["add", "remove"] = "add"


class SaveConversationResponse(BaseModel):
    path: str


class SessionRequest(BaseModel):
    accessToken: str | None = None


class SessionResponse(BaseModel):
    authenticated: bool
    requiresAuth: bool
    tokenPreview: str | None = None
    backendUrlHint: str | None = None
    mode: Literal["open", "token"]


class NoteDetailModel(BaseModel):
    id: str
    filePath: str
    title: str
    bodyMarkdown: str
    tags: list[str] = Field(default_factory=list)
    frontmatter: dict = Field(default_factory=dict)
    backlinks: list[RelatedNoteModel] = Field(default_factory=list)
    links: list[RelatedNoteModel] = Field(default_factory=list)
    dateModified: str | None = None
    sizeBytes: int | None = None
    noteType: str | None = None
    outline: list[dict[str, int | str]] = Field(default_factory=list)


class DetectSynapsesResponseModel(BaseModel):
    sourceNotePath: str
    createdCount: int
    created: list[RelatedNoteModel] = Field(default_factory=list)
    message: str


class InsightItemModel(BaseModel):
    id: str
    title: str
    filePath: str
    kind: Literal["insight", "synapse", "synthesis", "conversation"]
    provenance: Literal["vault", "web", "hybrid"] | None = None
    tags: list[str] = Field(default_factory=list)
    dateModified: str | None = None
    sizeBytes: int | None = None
    excerpt: str | None = None


class GraphNodeModel(BaseModel):
    id: str
    label: str
    group: str
    degree: int
    tags: list[str] = Field(default_factory=list)
    noteType: str | None = None
    dateModified: str | None = None


class GraphEdgeModel(BaseModel):
    id: str
    source: str
    target: str


class GraphMetricsModel(BaseModel):
    nodeCount: int
    edgeCount: int
    density: float
    filteredNoteCount: int | None = None
    totalNoteCount: int | None = None


class GraphTopNodeModel(BaseModel):
    id: str
    label: str
    degree: int


class GraphFilterOptionsModel(BaseModel):
    folders: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    types: list[str] = Field(default_factory=list)


class GraphLegendItemModel(BaseModel):
    key: str
    label: str
    color: str


class GraphSummaryCountModel(BaseModel):
    label: str
    count: int


class GraphSpotlightItemModel(BaseModel):
    filePath: str
    title: str
    score: float
    dateModified: str | None = None
    tags: list[str] = Field(default_factory=list)
    noteType: str | None = None


class GraphNoteOptionModel(BaseModel):
    title: str
    filePath: str
    dateModified: str | None = None
    noteType: str | None = None


class GraphDataModel(BaseModel):
    nodes: list[GraphNodeModel] = Field(default_factory=list)
    edges: list[GraphEdgeModel] = Field(default_factory=list)
    metrics: GraphMetricsModel
    topNodes: list[GraphTopNodeModel] = Field(default_factory=list)
    filterOptions: GraphFilterOptionsModel = Field(default_factory=GraphFilterOptionsModel)
    noteOptions: list[GraphNoteOptionModel] = Field(default_factory=list)
    spotlight: list[GraphSpotlightItemModel] = Field(default_factory=list)
    recentNotes: list[GraphNoteOptionModel] = Field(default_factory=list)
    folderSummary: list[GraphSummaryCountModel] = Field(default_factory=list)
    tagSummary: list[GraphSummaryCountModel] = Field(default_factory=list)
    typeSummary: list[GraphSummaryCountModel] = Field(default_factory=list)
    legend: list[GraphLegendItemModel] = Field(default_factory=list)


class StoredConversationModel(ConversationDetailModel):
    model_config = ConfigDict(extra="ignore")


class StoredConversationCollectionModel(BaseModel):
    conversations: list[StoredConversationModel] = Field(default_factory=list)
    updatedAt: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
