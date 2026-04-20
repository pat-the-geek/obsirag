export type Provenance = 'vault' | 'web' | 'hybrid' | 'unknown';

export type ConversationSummary = {
  id: string;
  title: string;
  preview: string;
  updatedAt: string;
  sizeBytes?: number;
  turnCount: number;
  messageCount: number;
  isCurrent?: boolean;
};

export type GenerationStats = {
  tokens: number;
  ttft: number;
  total: number;
  tps: number;
};

export type SourceRef = {
  filePath: string;
  noteTitle: string;
  dateModified?: string;
  score?: number;
  isPrimary?: boolean;
};

export type WebSource = {
  title: string;
  href: string;
  body?: string;
  domain?: string;
  publishedAt?: string;
};

export type QueryOverview = {
  query: string;
  searchQuery: string;
  summary: string;
  sources: WebSource[];
};

export type RelatedNote = {
  title: string;
  filePath: string;
  dateModified?: string;
  sizeBytes?: number;
};

export type DdgKnowledge = {
  heading?: string;
  entity?: string;
  abstractText?: string;
  answer?: string;
  answerType?: string;
  definition?: string;
  infobox?: Array<{ label: string; value: string }>;
  relatedTopics?: Array<{ text: string; url: string }>;
};

export type EntityContext = {
  type: string;
  typeLabel: string;
  value: string;
  mentions?: number;
  lineNumber?: number;
  relationExplanation?: string;
  imageUrl?: string;
  tag?: string;
  notes: RelatedNote[];
  ddgKnowledge?: DdgKnowledge;
};

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  createdAt: string;
  llmProvider?: string;
  transient?: boolean;
  sources?: SourceRef[];
  primarySource?: SourceRef | null;
  stats?: GenerationStats;
  timeline?: string[];
  queryOverview?: QueryOverview | null;
  entityContexts?: EntityContext[];
  enrichmentPath?: string | null;
  provenance?: Provenance;
  sentinel?: boolean;
};

export type ConversationDetail = {
  id: string;
  title: string;
  updatedAt: string;
  sizeBytes?: number;
  draft: string;
  messages: ChatMessage[];
  lastGenerationStats?: GenerationStats;
};

export type NoteDetail = {
  id: string;
  filePath: string;
  title: string;
  bodyMarkdown: string;
  tags: string[];
  frontmatter: Record<string, unknown>;
  backlinks: RelatedNote[];
  links: RelatedNote[];
  dateModified?: string;
  sizeBytes?: number;
  noteType?: string;
  outline?: Array<{ level: number; title: string; line: number }>;
};

export type DetectSynapsesResult = {
  sourceNotePath: string;
  createdCount: number;
  created: RelatedNote[];
  message: string;
};

export type InsightItem = {
  id: string;
  title: string;
  filePath: string;
  kind: 'insight' | 'synapse' | 'synthesis' | 'conversation';
  provenance?: 'vault' | 'web' | 'hybrid';
  tags: string[];
  dateModified?: string;
  sizeBytes?: number;
  excerpt?: string;
};

export type GraphNode = {
  id: string;
  label: string;
  group: string;
  degree: number;
  tags: string[];
  noteType?: string;
  dateModified?: string;
};

export type GraphEdge = {
  id: string;
  source: string;
  target: string;
};

export type GraphData = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  metrics: {
    nodeCount: number;
    edgeCount: number;
    density: number;
    filteredNoteCount?: number;
    totalNoteCount?: number;
  };
  topNodes: Array<{ id: string; label: string; degree: number }>;
  filterOptions: {
    folders: string[];
    tags: string[];
    types: string[];
  };
  noteOptions: Array<{
    title: string;
    filePath: string;
    dateModified?: string;
    noteType?: string;
  }>;
  spotlight: Array<{
    filePath: string;
    title: string;
    score: number;
    dateModified?: string;
    tags: string[];
    noteType?: string;
  }>;
  recentNotes: Array<{
    title: string;
    filePath: string;
    dateModified?: string;
    noteType?: string;
  }>;
  folderSummary: Array<{ label: string; count: number }>;
  tagSummary: Array<{ label: string; count: number }>;
  typeSummary: Array<{ label: string; count: number }>;
  legend: Array<{ key: string; label: string; color: string }>;
};

export type SaveConversationResult = {
  path: string;
};

export type SystemAlert = {
  id: string;
  level: 'info' | 'warning' | 'error';
  title: string;
  description: string;
};

export type SystemStatus = {
  backendReachable: boolean;
  llmAvailable: boolean;
  notesIndexed: number;
  chunksIndexed: number;
  runtime?: {
    llmProvider: string;
    llmModel: string;
    embeddingModel: string;
    vectorStore: string;
    nerModel: string;
    autolearnMode: string;
  };
  startup?: {
    ready: boolean;
    steps: string[];
    currentStep?: string;
    error?: string | null;
    updatedAt?: string;
  };
  indexing?: {
    running: boolean;
    processed: number;
    total: number;
    current?: string;
    llmProvider?: string;
  };
  autolearn?: {
    active: boolean;
    managedBy?: 'none' | 'worker' | 'api';
    running?: boolean;
    pid?: number | null;
    note?: string;
    step?: string;
    log?: string[];
    startedAt?: string;
    updatedAt?: string;
    nextRunAt?: string;
  };
  alerts?: SystemAlert[];
};

export type ServerConfig = {
  backendUrl: string;
  accessToken?: string;
  useMockServer: boolean;
};

export type SessionState = {
  authenticated: boolean;
  requiresAuth: boolean;
  tokenPreview?: string | null;
  backendUrlHint?: string | null;
  mode: 'open' | 'token';
};

export type WebSearchResponse = {
  content: string;
  llmProvider?: string;
  queryOverview: QueryOverview;
  entityContexts: EntityContext[];
  stats?: GenerationStats;
  provenance: 'web';
};
