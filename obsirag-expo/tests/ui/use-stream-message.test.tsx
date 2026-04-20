import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import renderer, { act } from 'react-test-renderer';

import { useStreamMessage } from '../../features/chat/use-chat';
import { ChatMessage, ConversationDetail } from '../../types/domain';

const mockSetDraft = jest.fn();
const mockInvalidateQueries = jest.spyOn(QueryClient.prototype, 'invalidateQueries');
const mockStreamConversationResponse = jest.fn();

jest.mock('../../features/auth/use-server-config', () => ({
  useServerConfig: () => ({
    api: {
      streamConversationResponse: mockStreamConversationResponse,
    },
  }),
}));

jest.mock('../../store/app-store', () => ({
  useAppStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      setDraft: mockSetDraft,
    }),
}));

describe('useStreamMessage', () => {
  let queryClient: QueryClient | null = null;
  let testRenderer: renderer.ReactTestRenderer | null = null;

  beforeEach(() => {
    mockSetDraft.mockReset();
    mockStreamConversationResponse.mockReset();
    mockInvalidateQueries.mockClear();
  });

  afterEach(() => {
    if (testRenderer) {
      act(() => {
        testRenderer?.unmount();
      });
      testRenderer = null;
    }
    queryClient?.clear();
    queryClient = null;
  });

  afterAll(() => {
    mockInvalidateQueries.mockRestore();
  });

  it('keeps streamed content when the completion payload is empty', async () => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: Infinity },
        mutations: { retry: false, gcTime: Infinity },
      },
    });

    queryClient.setQueryData<ConversationDetail>(['conversation', 'conv-1'], {
      id: 'conv-1',
      title: 'Conversation test',
      updatedAt: '2026-04-18T12:00:00Z',
      draft: '',
      messages: [],
    });

    mockStreamConversationResponse.mockImplementation(async (_conversationId: string, _prompt: string, handlers: Record<string, Function>) => {
      handlers.onStatus?.('Generation MLX');
      handlers.onToken?.('Bonjour');
      handlers.onToken?.(' monde');
      const finalMessage: ChatMessage = {
        id: 'assistant-3',
        role: 'assistant',
        content: '',
        createdAt: '2026-04-18T12:00:05Z',
        provenance: 'vault',
        timeline: [],
      };
      handlers.onComplete?.(finalMessage);
      return finalMessage;
    });

    let mutation: ReturnType<typeof useStreamMessage> | null = null;

    function Harness() {
      mutation = useStreamMessage('conv-1');
      return null;
    }

    testRenderer = renderer.create(
      <QueryClientProvider client={queryClient}>
        <Harness />
      </QueryClientProvider>,
    );

    await act(async () => {
      await mutation?.mutateAsync('Presente le deroulement du tournage du film dans un diagramme mermaid de type gantt');
    });

    const conversation = queryClient.getQueryData<ConversationDetail>(['conversation', 'conv-1']);
    expect(conversation?.messages.at(-1)?.content).toBe('Bonjour monde');
    expect(conversation?.messages.at(-1)?.timeline).toEqual(['Réponse en préparation', 'Generation MLX']);
    expect(mockSetDraft).toHaveBeenCalledWith('conv-1', '');
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ['conversation', 'conv-1'] });
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ['conversations'] });
  });

  it('restores the optimistic user question ahead of the streamed assistant after a refetch overwrites local state', async () => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: Infinity },
        mutations: { retry: false, gcTime: Infinity },
      },
    });

    queryClient.setQueryData<ConversationDetail>(['conversation', 'conv-1'], {
      id: 'conv-1',
      title: 'Conversation test',
      updatedAt: '2026-04-18T12:00:00Z',
      draft: '',
      messages: [
        {
          id: 'assistant-1',
          role: 'assistant',
          content: 'Historique',
          createdAt: '2026-04-18T11:59:00Z',
          provenance: 'vault',
        },
      ],
    });

    mockStreamConversationResponse.mockImplementation(async (_conversationId: string, _prompt: string, handlers: Record<string, Function>) => {
      queryClient?.setQueryData<ConversationDetail>(['conversation', 'conv-1'], {
        id: 'conv-1',
        title: 'Conversation test',
        updatedAt: '2026-04-18T12:00:01Z',
        draft: '',
        messages: [
          {
            id: 'assistant-1',
            role: 'assistant',
            content: 'Historique',
            createdAt: '2026-04-18T11:59:00Z',
            provenance: 'vault',
          },
        ],
      });
      handlers.onStatus?.('Generation Euria');
      handlers.onToken?.('Bonjour');
      const finalMessage: ChatMessage = {
        id: 'assistant-4',
        role: 'assistant',
        content: 'Bonjour',
        createdAt: '2026-04-18T12:00:05Z',
        provenance: 'vault',
        timeline: ['Réponse en préparation', 'Generation Euria'],
      };
      handlers.onComplete?.(finalMessage);
      return finalMessage;
    });

    let mutation: ReturnType<typeof useStreamMessage> | null = null;

    function Harness() {
      mutation = useStreamMessage('conv-1');
      return null;
    }

    testRenderer = renderer.create(
      <QueryClientProvider client={queryClient}>
        <Harness />
      </QueryClientProvider>,
    );

    await act(async () => {
      await mutation?.mutateAsync('Parle-moi de Dune');
    });

    const conversation = queryClient.getQueryData<ConversationDetail>(['conversation', 'conv-1']);
    expect(conversation?.messages.map((message) => ({ role: message.role, content: message.content }))).toEqual([
      { role: 'assistant', content: 'Historique' },
      { role: 'user', content: 'Parle-moi de Dune' },
      { role: 'assistant', content: 'Bonjour' },
    ]);
  });
});