import {
  ChatMessage,
  ConversationDetail,
  ConversationSummary,
  DetectSynapsesResult,
  EntityContext,
  GraphData,
  InsightItem,
  LogEntry,
  NoteDetail,
  ReindexResult,
  RelatedNote,
  SaveConversationResult,
  ServerConfig,
  SessionState,
  SourceRef,
  SystemStatus,
  WebSearchResponse,
} from '../../types/domain';
import { NativeModules } from 'react-native';
import {
  mockConversations,
  mockConversationSummaries,
  mockGraphData,
  mockInsights,
  mockNotes,
  mockSystemStatus,
} from './mock-data';
import { normalizeBackendUrlInput } from '../../features/auth/backend-url';

type StreamHandlers = {
  onStatus?: (value: string) => void;
  onToken?: (value: string) => void;
  onSources?: (message: Pick<ChatMessage, 'sources' | 'primarySource'>) => void;
  onComplete?: (message: ChatMessage) => void;
  onEntityContexts?: (messageId: string, entityContexts: EntityContext[]) => void;
  onEnrichmentStarted?: (messageId: string, total: number) => void;
  onEntityContextPartial?: (messageId: string, entityContext: EntityContext, index: number, total: number) => void;
};

type ConversationRequestOptions = {
  useEuria?: boolean;
  useRag?: boolean;
  signal?: AbortSignal;
};

type GraphQueryFilters = {
  folders?: string[];
  tags?: string[];
  noteTypes?: string[];
  searchText?: string;
  recencyDays?: number;
};

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export class ObsiRagApi {
  constructor(private readonly config: ServerConfig) {}

  async createSession(accessToken?: string): Promise<SessionState> {
    if (this.config.useMockServer) {
      return {
        authenticated: true,
        requiresAuth: false,
        tokenPreview: null,
        backendUrlHint: this.config.backendUrl,
        mode: 'open',
      };
    }

    return this.requestJson<SessionState>('/api/v1/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ accessToken: accessToken ?? this.config.accessToken ?? '' }),
    });
  }

  async getSession(): Promise<SessionState> {
    if (this.config.useMockServer) {
      return {
        authenticated: true,
        requiresAuth: false,
        tokenPreview: null,
        backendUrlHint: this.config.backendUrl,
        mode: 'open',
      };
    }

    return this.requestJson<SessionState>('/api/v1/session');
  }

  async getHealth(): Promise<{ status: string; version: string; llmAvailable: boolean }> {
    if (this.config.useMockServer) {
      return {
        status: 'ok',
        version: 'mock-1.0.0',
        llmAvailable: true,
      };
    }

    return this.requestJson<{ status: string; version: string; llmAvailable: boolean }>('/api/v1/health');
  }

  async getSystemStatus(): Promise<SystemStatus> {
    if (this.config.useMockServer) {
      return mockSystemStatus;
    }

    return this.requestJson<SystemStatus>('/api/v1/system/status');
  }

  async reindexData(): Promise<ReindexResult> {
    if (this.config.useMockServer) {
      return {
        status: 'ok',
        added: 3,
        updated: 1,
        deleted: 0,
        skipped: 732,
        notesIndexed: mockSystemStatus.notesIndexed,
        chunksIndexed: mockSystemStatus.chunksIndexed,
        indexing: {
          running: false,
          processed: mockSystemStatus.notesIndexed,
          total: mockSystemStatus.notesIndexed,
          current: 'Indexation terminee',
        },
      };
    }

    return this.requestJson<ReindexResult>('/api/v1/system/reindex', {
      method: 'POST',
    });
  }

  async getLogs(limit = 200): Promise<LogEntry[]> {
    if (this.config.useMockServer) return [];
    return this.requestJson<LogEntry[]>(`/api/v1/system/logs?limit=${limit}`);
  }

  async getConversations(): Promise<ConversationSummary[]> {
    if (this.config.useMockServer) {
      return mockConversationSummaries;
    }

    return this.requestJson<ConversationSummary[]>('/api/v1/conversations');
  }

  async createConversation(): Promise<ConversationDetail> {
    if (this.config.useMockServer) {
      return {
        id: `conv-${Date.now()}`,
        title: 'Nouveau fil',
        updatedAt: new Date().toISOString(),
        draft: '',
        messages: [],
      };
    }

    return this.requestJson<ConversationDetail>('/api/v1/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
  }

  async getConversation(conversationId: string): Promise<ConversationDetail> {
    if (this.config.useMockServer) {
      const found = mockConversations.find((item) => item.id === conversationId) ?? mockConversations[0];
      if (!found) {
        throw new Error('No mock conversations available.');
      }
      return {
        ...found,
        draft: found.draft,
      };
    }

    return this.requestJson<ConversationDetail>(`/api/v1/conversations/${encodeURIComponent(conversationId)}`);
  }

  async deleteConversation(conversationId: string): Promise<void> {
    if (this.config.useMockServer) {
      return;
    }

    await this.requestJson<{ deleted: boolean }>(`/api/v1/conversations/${encodeURIComponent(conversationId)}`, {
      method: 'DELETE',
    });
  }

  async deleteConversationMessage(conversationId: string, messageId: string): Promise<ConversationDetail> {
    if (this.config.useMockServer) {
      const found = mockConversations.find((item) => item.id === conversationId) ?? mockConversations[0];
      if (!found) {
        throw new Error('No mock conversations available.');
      }
      return {
        ...found,
        messages: found.messages.filter((message) => message.id !== messageId),
      };
    }

    return this.requestJson<ConversationDetail>(
      `/api/v1/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}`,
      {
        method: 'DELETE',
      },
    );
  }

  async toggleConversationEntity(
    conversationId: string,
    entityValue: string,
    action: 'add' | 'remove',
  ): Promise<ConversationDetail> {
    if (this.config.useMockServer) {
      const found = mockConversations.find((item) => item.id === conversationId) ?? mockConversations[0];
      if (!found) {
        throw new Error('No mock conversations available.');
      }

      const existing = new Set(found.hiddenEntityValues ?? []);
      if (action === 'remove') {
        existing.delete(entityValue);
      } else {
        existing.add(entityValue);
      }

      return {
        ...found,
        hiddenEntityValues: [...existing].sort((left, right) => left.localeCompare(right, 'fr')),
      };
    }

    return this.requestJson<ConversationDetail>(`/api/v1/conversations/${encodeURIComponent(conversationId)}/entities`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entityValue, action }),
    });
  }

  async saveConversation(conversationId: string): Promise<SaveConversationResult> {
    if (this.config.useMockServer) {
      return { path: `obsirag/conversations/mock/${conversationId}.md` };
    }

    return this.requestJson<SaveConversationResult>(`/api/v1/conversations/${encodeURIComponent(conversationId)}/save`, {
      method: 'POST',
    });
  }

  async generateConversationReport(conversationId: string): Promise<SaveConversationResult> {
    if (this.config.useMockServer) {
      return { path: 'obsirag/insights/2026-04/web_artemis_ii.md' };
    }

    return this.requestJson<SaveConversationResult>(`/api/v1/conversations/${encodeURIComponent(conversationId)}/report`, {
      method: 'POST',
    });
  }

  async getNote(noteId: string): Promise<NoteDetail> {
    if (this.config.useMockServer) {
      const found = mockNotes.find((item) => item.id === noteId) ?? mockNotes[0];
      if (!found) {
        throw new Error('No mock notes available.');
      }
      return found;
    }

    return this.requestJson<NoteDetail>(`/api/v1/notes/${this.encodePath(noteId)}`);
  }

  async detectNoteSynapses(noteId: string): Promise<DetectSynapsesResult> {
    if (this.config.useMockServer) {
      return {
        sourceNotePath: noteId,
        createdCount: 1,
        created: [
          {
            title: 'Synapse mock',
            filePath: 'obsirag/synapses/mock/synapse-note.md',
            dateModified: new Date().toISOString(),
          },
        ],
        message: '1 synapse mock detectee pour cet element.',
      };
    }

    return this.requestJson<DetectSynapsesResult>(`/api/v1/notes/${this.encodePath(noteId)}/synapses/discover`, {
      method: 'POST',
    });
  }

  async searchNotes(query: string): Promise<RelatedNote[]> {
    if (this.config.useMockServer) {
      const search = query.trim().toLowerCase();
      return mockNotes
        .filter((item) => item.title.toLowerCase().includes(search) || item.filePath.toLowerCase().includes(search))
        .map((item) => ({
          title: item.title,
          filePath: item.filePath,
          ...(item.dateModified ? { dateModified: item.dateModified } : {}),
        }));
    }

    return this.requestJson<RelatedNote[]>(`/api/v1/notes/search?q=${encodeURIComponent(query)}`);
  }

  async getInsights(): Promise<InsightItem[]> {
    if (this.config.useMockServer) {
      return mockInsights;
    }

    return this.requestJson<InsightItem[]>('/api/v1/insights');
  }

  async getInsight(insightId: string): Promise<NoteDetail> {
    if (this.config.useMockServer) {
      const found = mockNotes.find((item) => item.id === insightId || item.filePath === insightId) ?? mockNotes[0];
      if (!found) {
        throw new Error('No mock insight details available.');
      }
      return found;
    }

    return this.requestJson<NoteDetail>(`/api/v1/insights/${this.encodePath(insightId)}`);
  }

  async getGraph(filters?: GraphQueryFilters): Promise<GraphData> {
    if (this.config.useMockServer) {
      return mockGraphData;
    }

    return this.requestJson<GraphData>(`/api/v1/graph${this.buildGraphQuery(filters)}`);
  }

  async getGraphSubgraph(noteId: string, depth = 1, filters?: GraphQueryFilters): Promise<GraphData> {
    if (this.config.useMockServer) {
      return mockGraphData;
    }

    const params = new URLSearchParams();
    params.set('noteId', noteId);
    params.set('depth', String(depth));
    this.appendGraphFilters(params, filters);
    return this.requestJson<GraphData>(`/api/v1/graph/subgraph?${params.toString()}`);
  }

  async webSearch(query: string, options?: ConversationRequestOptions): Promise<WebSearchResponse> {
    if (this.config.useMockServer) {
      return {
        provenance: 'web',
        content: `# Vue d'ensemble DDG\n\nResultat mock pour \"${query}\".\n\n## Sources overview\n\n- [DuckDuckGo](https://duckduckgo.com)`,
        queryOverview: {
          query,
          searchQuery: query,
          summary: `Resultat mock pour \"${query}\".`,
          sources: [
            {
              title: 'DuckDuckGo',
              href: 'https://duckduckgo.com',
              body: 'Resultat mock de demonstration.',
              domain: 'duckduckgo.com',
            },
          ],
        },
        entityContexts: [
          {
            type: 'concept',
            typeLabel: 'Concept',
            value: query,
            mentions: 1,
            notes: [],
          },
        ],
        stats: {
          tokens: query.trim().split(/\s+/).length + 12,
          ttft: 0.0,
          total: 0.4,
          tps: 30,
        },
      };
    }

    return this.requestJson<WebSearchResponse>('/api/v1/web-search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, useEuria: options?.useEuria ?? false }),
    });
  }

  async streamConversationResponse(
    conversationId: string,
    prompt: string,
    handlers: StreamHandlers,
    options?: ConversationRequestOptions,
  ): Promise<ChatMessage> {
    if (this.config.useMockServer) {
      handlers.onStatus?.('Analyse de la requete');
      await wait(250);
      handlers.onStatus?.('Recherche dans le coffre');
      await wait(400);
      handlers.onStatus?.('Generation MLX');

      const content = [
        '### Apercu de la question',
        '',
        `La question "${prompt}" a ete traitee via le backend mock d\'ObsiRAG Expo.`,
        '',
        '### Details utiles',
        '',
        '- Le projet Expo est pret a etre branche a une vraie API',
        '- Le streaming temps reel doit ensuite etre remplace par SSE ou WebSocket',
        '- Les sources et la note principale sont deja prevues dans les DTO',
      ].join('\n');

      let streamed = '';
      for (const token of content.split(' ')) {
        streamed += `${streamed ? ' ' : ''}${token}`;
        handlers.onToken?.(`${token} `);
        await wait(30);
      }

      const message: ChatMessage = {
        id: `assistant-${conversationId}-${Date.now()}`,
        role: 'assistant',
        content: streamed.trim(),
        createdAt: new Date().toISOString(),
        provenance: 'vault',
        sources: [
          {
            filePath: 'Space/Artemis II.md',
            noteTitle: 'Artemis II',
            isPrimary: true,
            score: 0.92,
          },
        ],
        primarySource: {
          filePath: 'Space/Artemis II.md',
          noteTitle: 'Artemis II',
          isPrimary: true,
          score: 0.92,
        },
        timeline: ['Analyse de la requete', 'Recherche dans le coffre', 'Generation MLX'],
        stats: {
          tokens: content.split(' ').length,
          ttft: 0.7,
          total: 3.1,
          tps: 58.0,
        },
      };

      handlers.onComplete?.(message);
      return message;
    }

    const fallbackToStandardMessage = async () => {
      const fallbackMessage = await this.requestJson<ChatMessage>(
        `/api/v1/conversations/${encodeURIComponent(conversationId)}/messages`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt, useEuria: options?.useEuria ?? false, useRag: options?.useRag ?? true }),
        },
      );
      handlers.onComplete?.(fallbackMessage);
      return fallbackMessage;
    };

    let response: Response;
    const backendUrl = this.getResolvedBackendUrl();
    try {
      response = await fetch(`${backendUrl}/api/v1/conversations/${encodeURIComponent(conversationId)}/messages/stream`, {
        method: 'POST',
        headers: {
          ...this.getAuthHeaders(),
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify({ prompt, useEuria: options?.useEuria ?? false, useRag: options?.useRag ?? true }),
        signal: options?.signal ?? null,
      });
    } catch (error) {
      if (this.isAbortError(error)) {
        throw error;
      }
      return fallbackToStandardMessage();
    }

    if (!response.ok) {
      throw await this.toRequestError(response, 'Unable to stream conversation response.');
    }

    if (!response.body || typeof response.body.getReader !== 'function') {
      return fallbackToStandardMessage();
    }

    const decoder = new TextDecoder();
    const reader = response.body.getReader();
    let buffer = '';
    let completedMessage: ChatMessage | null = null;
    let sawStreamBytes = false;

    while (true) {
      let value: Uint8Array | undefined;
      let done = false;
      try {
        ({ value, done } = await reader.read());
      } catch (error) {
        if (this.isAbortError(error)) {
          throw error;
        }
        if (!sawStreamBytes) {
          return fallbackToStandardMessage();
        }
        throw this.toNetworkError(error, 'Le flux de reponse a ete interrompu avant la fin du message.');
      }
      if (done) {
        break;
      }

      if (value && value.length > 0) {
        sawStreamBytes = true;
      }

      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split('\n\n');
      buffer = frames.pop() ?? '';

      for (const frame of frames) {
        const parsed = this.parseSseFrame(frame);
        if (!parsed) {
          continue;
        }
        const data = parsed.data;

        if (parsed.event === 'retrieval_status') {
          const status = typeof data.message === 'string' ? data.message : '';
          if (status) {
            handlers.onStatus?.(status);
          }
        }

        if (parsed.event === 'token') {
          const token = typeof data.token === 'string' ? data.token : '';
          if (token) {
            handlers.onToken?.(token);
          }
        }

        if (parsed.event === 'sources_ready') {
          const sources = Array.isArray(data.sources) ? (data.sources as SourceRef[]) : [];
          handlers.onSources?.({
            sources,
            primarySource: sources.find((item) => Boolean(item.isPrimary)) ?? null,
          });
        }

        if (parsed.event === 'message_complete') {
          completedMessage = data as ChatMessage;
          handlers.onComplete?.(completedMessage);
        }

        if (parsed.event === 'entity_enrichment_started') {
          const messageId = typeof data.messageId === 'string' ? data.messageId : '';
          const total = typeof data.total === 'number' ? data.total : 0;
          if (messageId && total > 0) {
            handlers.onEnrichmentStarted?.(messageId, total);
          }
        }

        if (parsed.event === 'entity_context_partial') {
          const messageId = typeof data.messageId === 'string' ? data.messageId : '';
          const index = typeof data.index === 'number' ? data.index : 0;
          const total = typeof data.total === 'number' ? data.total : 0;
          const entityContext = data.entityContext as EntityContext | undefined;
          if (messageId && entityContext?.value) {
            handlers.onEntityContextPartial?.(messageId, entityContext, index, total);
          }
        }

        if (parsed.event === 'entity_contexts_ready') {
          const messageId = typeof data.messageId === 'string' ? data.messageId : '';
          const entityContexts = Array.isArray(data.entityContexts) ? (data.entityContexts as EntityContext[]) : [];
          if (messageId && entityContexts.length > 0) {
            handlers.onEntityContexts?.(messageId, entityContexts);
          }
        }

        if (parsed.event === 'message_error') {
          throw new Error(typeof data.detail === 'string' ? data.detail : 'Streaming failed.');
        }
      }
    }

    if (!completedMessage) {
      throw new Error('Streaming ended before a completion event was received.');
    }

    return completedMessage;
  }

  private async requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
    let response: Response;
    const backendUrl = this.getResolvedBackendUrl();
    try {
      response = await fetch(`${backendUrl}${path}`, {
        ...init,
        headers: {
          ...this.getAuthHeaders(),
          ...(init.headers ?? {}),
        },
      });
    } catch (error) {
      throw this.toNetworkError(error, `Connexion au backend impossible pour ${path}.`);
    }
    if (!response.ok) {
      throw await this.toRequestError(response, `Request failed for ${path}.`);
    }
    return response.json() as Promise<T>;
  }

  private isAbortError(error: unknown): boolean {
    return Boolean(error) && typeof error === 'object' && (error as { name?: string }).name === 'AbortError';
  }

  private toNetworkError(error: unknown, fallbackMessage: string): Error {
    if (error instanceof Error) {
      const rawMessage = error.message.trim();
      if (rawMessage && rawMessage.toLowerCase() !== 'load failed') {
        return new Error(rawMessage);
      }
    }
    return new Error(fallbackMessage);
  }

  private getResolvedBackendUrl(): string {
    const rawBackendUrl = normalizeBackendUrlInput(this.config.backendUrl);
    if (!rawBackendUrl) {
      return rawBackendUrl;
    }

    try {
      const backendUrl = new URL(rawBackendUrl);
      if (!this.isLoopbackHost(backendUrl.hostname)) {
        return rawBackendUrl;
      }

      if (typeof window !== 'undefined' && typeof window.location?.origin === 'string' && window.location.origin) {
        return window.location.origin.replace(/\/$/, '');
      }

      const scriptUrl = NativeModules?.SourceCode?.scriptURL;
      if (typeof scriptUrl !== 'string' || !scriptUrl) {
        return rawBackendUrl;
      }

      const bundleUrl = new URL(scriptUrl);
      if (!bundleUrl.hostname || this.isLoopbackHost(bundleUrl.hostname)) {
        return rawBackendUrl;
      }

      backendUrl.hostname = bundleUrl.hostname;
      return backendUrl.toString().replace(/\/$/, '');
    } catch {
      return rawBackendUrl;
    }
  }

  private isLoopbackHost(hostname: string): boolean {
    return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '0.0.0.0' || hostname === '::1';
  }

  private getAuthHeaders(): Record<string, string> {
    const token = this.config.accessToken?.trim();
    if (!token) {
      return {};
    }
    return {
      Authorization: `Bearer ${token}`,
    };
  }

  private parseSseFrame(frame: string): { event: string; data: Record<string, unknown> } | null {
    const lines = frame
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);
    const eventLine = lines.find((line) => line.startsWith('event:'));
    const dataLines = lines.filter((line) => line.startsWith('data:'));
    if (!eventLine || dataLines.length === 0) {
      return null;
    }
    const event = eventLine.slice('event:'.length).trim();
    const rawData = dataLines.map((line) => line.slice('data:'.length).trim()).join('\n');
    try {
      const data = JSON.parse(rawData) as Record<string, unknown>;
      return {
        event,
        data,
      };
    } catch {
      return null;
    }
  }

  private async toRequestError(response: Response, fallbackMessage: string): Promise<Error> {
    try {
      const payload = (await response.json()) as { detail?: string };
      const detail = payload.detail?.trim();
      if (response.status === 404) {
        return new Error(
          detail === 'Not Found'
            ? 'Endpoint introuvable (404). Verifiez l\'URL backend: utilisez uniquement la base, par ex. http://127.0.0.1:8000, sans /server-config ni /api/v1.'
            : detail ?? fallbackMessage,
        );
      }
      return new Error(detail ?? fallbackMessage);
    } catch {
      return new Error(fallbackMessage);
    }
  }

  private encodePath(path: string): string {
    return path
      .split('/')
      .map((segment) => encodeURIComponent(segment))
      .join('/');
  }

  private buildGraphQuery(filters?: GraphQueryFilters): string {
    const params = new URLSearchParams();
    this.appendGraphFilters(params, filters);
    const query = params.toString();
    return query ? `?${query}` : '';
  }

  private appendGraphFilters(params: URLSearchParams, filters?: GraphQueryFilters): void {
    for (const folder of filters?.folders ?? []) {
      params.append('folders', folder);
    }
    for (const tag of filters?.tags ?? []) {
      params.append('tags', tag);
    }
    for (const noteType of filters?.noteTypes ?? []) {
      params.append('noteTypes', noteType);
    }
    if (filters?.searchText?.trim()) {
      params.set('searchText', filters.searchText.trim());
    }
    if (filters?.recencyDays) {
      params.set('recencyDays', String(filters.recencyDays));
    }
  }
}
