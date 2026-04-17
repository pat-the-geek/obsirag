import {
  ChatMessage,
  ConversationDetail,
  ConversationSummary,
  DetectSynapsesResult,
  GraphData,
  InsightItem,
  NoteDetail,
  RelatedNote,
  SaveConversationResult,
  ServerConfig,
  SessionState,
  SourceRef,
  SystemStatus,
  WebSearchResponse,
} from '../../types/domain';
import {
  mockConversations,
  mockConversationSummaries,
  mockGraphData,
  mockInsights,
  mockNotes,
  mockSystemStatus,
} from './mock-data';

type StreamHandlers = {
  onStatus?: (value: string) => void;
  onToken?: (value: string) => void;
  onSources?: (message: Pick<ChatMessage, 'sources' | 'primarySource'>) => void;
  onComplete?: (message: ChatMessage) => void;
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

  async saveConversation(conversationId: string): Promise<SaveConversationResult> {
    if (this.config.useMockServer) {
      return { path: `obsirag/conversations/mock/${conversationId}.md` };
    }

    return this.requestJson<SaveConversationResult>(`/api/v1/conversations/${encodeURIComponent(conversationId)}/save`, {
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

  async webSearch(query: string): Promise<WebSearchResponse> {
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
      };
    }

    return this.requestJson<WebSearchResponse>('/api/v1/web-search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });
  }

  async streamConversationResponse(
    conversationId: string,
    prompt: string,
    handlers: StreamHandlers,
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

    const response = await fetch(`${this.config.backendUrl}/api/v1/conversations/${encodeURIComponent(conversationId)}/messages/stream`, {
      method: 'POST',
      headers: {
        ...this.getAuthHeaders(),
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
      body: JSON.stringify({ prompt }),
    });

    if (!response.ok) {
      throw await this.toRequestError(response, 'Unable to stream conversation response.');
    }

    if (!response.body || typeof response.body.getReader !== 'function') {
      const fallbackMessage = await this.requestJson<ChatMessage>(
        `/api/v1/conversations/${encodeURIComponent(conversationId)}/messages`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt }),
        },
      );
      handlers.onComplete?.(fallbackMessage);
      return fallbackMessage;
    }

    const decoder = new TextDecoder();
    const reader = response.body.getReader();
    let buffer = '';
    let completedMessage: ChatMessage | null = null;

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
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
    const response = await fetch(`${this.config.backendUrl}${path}`, {
      ...init,
      headers: {
        ...this.getAuthHeaders(),
        ...(init.headers ?? {}),
      },
    });
    if (!response.ok) {
      throw await this.toRequestError(response, `Request failed for ${path}.`);
    }
    return response.json() as Promise<T>;
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
      return new Error(payload.detail ?? fallbackMessage);
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
