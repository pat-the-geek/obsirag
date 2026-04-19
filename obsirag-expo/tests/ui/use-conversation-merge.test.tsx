import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import renderer, { act } from 'react-test-renderer';

import { useConversation } from '../../features/chat/use-chat';
import { ConversationDetail } from '../../types/domain';

const mockGetConversation = jest.fn();

jest.mock('../../features/auth/use-server-config', () => ({
  useServerConfig: () => ({
    api: {
      getConversation: mockGetConversation,
    },
  }),
}));

jest.mock('../../store/app-store', () => ({
  useAppStore: (selector: (state: Record<string, unknown>) => unknown) => selector({ setDraft: jest.fn(), drafts: {} }),
}));

describe('useConversation', () => {
  let queryClient: QueryClient | null = null;
  let testRenderer: renderer.ReactTestRenderer | null = null;
  let latestResult: ReturnType<typeof useConversation> | null = null;

  beforeEach(() => {
    mockGetConversation.mockReset();
    latestResult = null;
  });

  afterEach(() => {
    if (testRenderer) {
      testRenderer.unmount();
      testRenderer = null;
    }
    queryClient?.clear();
    queryClient = null;
  });

  it('keeps explicit web search question and pending message when the backend conversation is refetched', async () => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: Infinity },
        mutations: { retry: false, gcTime: Infinity },
      },
    });

    queryClient.setQueryData<ConversationDetail>(['conversation', 'conv-1'], {
      id: 'conv-1',
      title: 'Conversation test',
      updatedAt: '2026-04-19T12:00:00Z',
      draft: '',
      messages: [
        {
          id: 'assistant-1',
          role: 'assistant',
          content: 'Contexte coffre',
          createdAt: '2026-04-19T11:59:00Z',
          provenance: 'vault',
        },
        {
          id: 'web-user-1',
          role: 'user',
          content: '🌐 Recherche sur le web : Ada Lovelace',
          createdAt: '2026-04-19T12:00:01Z',
        },
        {
          id: 'pending-web-assistant',
          role: 'assistant',
          content: '',
          createdAt: '2026-04-19T12:00:02Z',
          provenance: 'web',
          timeline: ['Réponse en préparation', 'Recherche sur le web en cours...'],
        },
      ],
    });

    mockGetConversation.mockResolvedValue({
      id: 'conv-1',
      title: 'Conversation test',
      updatedAt: '2026-04-19T12:00:03Z',
      draft: '',
      messages: [
        {
          id: 'assistant-1',
          role: 'assistant',
          content: 'Contexte coffre',
          createdAt: '2026-04-19T11:59:00Z',
          provenance: 'vault',
        },
      ],
    });

    function Harness() {
      latestResult = useConversation('conv-1');
      return null;
    }

    await act(async () => {
      testRenderer = renderer.create(
        <QueryClientProvider client={queryClient as QueryClient}>
          <Harness />
        </QueryClientProvider>,
      );
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(latestResult?.data?.messages.map((message) => ({ id: message.id, content: message.content }))).toEqual([
      { id: 'assistant-1', content: 'Contexte coffre' },
      { id: 'web-user-1', content: '🌐 Recherche sur le web : Ada Lovelace' },
      { id: 'pending-web-assistant', content: '' },
    ]);
    expect(latestResult?.data?.messages.at(-1)?.timeline).toEqual(['Réponse en préparation', 'Recherche sur le web en cours...']);
  });
});