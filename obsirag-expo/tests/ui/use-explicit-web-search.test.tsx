import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import renderer, { act } from 'react-test-renderer';

import { useExplicitWebSearch } from '../../features/chat/use-chat';
import { ConversationDetail } from '../../types/domain';

const mockWebSearch = jest.fn();
const mockInvalidateQueries = jest.spyOn(QueryClient.prototype, 'invalidateQueries');

jest.mock('../../features/auth/use-server-config', () => ({
  useServerConfig: () => ({
    api: {
      webSearch: mockWebSearch,
    },
  }),
}));

jest.mock('../../store/app-store', () => ({
  useAppStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      setDraft: jest.fn(),
      drafts: {},
    }),
}));

describe('useExplicitWebSearch', () => {
  let queryClient: QueryClient | null = null;
  let testRenderer: renderer.ReactTestRenderer | null = null;

  beforeEach(() => {
    mockWebSearch.mockReset();
    mockInvalidateQueries.mockClear();
  });

  afterEach(() => {
    if (testRenderer) {
      testRenderer.unmount();
      testRenderer = null;
    }
    queryClient?.clear();
    queryClient = null;
  });

  afterAll(() => {
    mockInvalidateQueries.mockRestore();
  });

  it('keeps the explicit web-search question immediately before the web response', async () => {
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
          content: 'Contexte precedent',
          createdAt: '2026-04-19T11:59:00Z',
          provenance: 'vault',
        },
      ],
    });

    mockWebSearch.mockResolvedValue({
      content: 'Ada Lovelace est une pionniere de l informatique.',
      stats: { tokens: 8, ttft: 0.2, total: 0.8, tps: 10 },
      queryOverview: null,
      entityContexts: [],
    });

    let mutation: ReturnType<typeof useExplicitWebSearch> | null = null;

    function Harness() {
      mutation = useExplicitWebSearch('conv-1');
      return null;
    }

    testRenderer = renderer.create(
      <QueryClientProvider client={queryClient}>
        <Harness />
      </QueryClientProvider>,
    );

    await act(async () => {
      await mutation?.mutateAsync('Ada Lovelace');
    });

    const conversation = queryClient.getQueryData<ConversationDetail>(['conversation', 'conv-1']);
    expect(conversation?.messages.map((message) => ({ role: message.role, content: message.content }))).toEqual([
      { role: 'assistant', content: 'Contexte precedent' },
      { role: 'user', content: '🌐 Recherche sur le web : Ada Lovelace' },
      { role: 'assistant', content: 'Ada Lovelace est une pionniere de l informatique.' },
    ]);
    expect(conversation?.messages.at(-1)?.timeline).toEqual(['Réponse en préparation', 'Recherche sur le web en cours...']);
  });
});