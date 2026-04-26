import React from 'react';
import renderer, { act } from 'react-test-renderer';
import { Alert, Text, TextInput } from 'react-native';

import { ConversationDetail } from '../../types/domain';

jest.mock('../../components/chat/conversation-entity-sidebar', () => {
  const ReactLocal = require('react');
  const { Text: TextLocal, View: ViewLocal } = require('react-native');

  return {
    ConversationEntitySidebar: ({ entities }: { entities: Array<{ value: string }> }) =>
      ReactLocal.createElement(
        ViewLocal,
        { testID: 'conversation-entity-sidebar' },
        entities.map((entity) => ReactLocal.createElement(TextLocal, { key: entity.value }, entity.value)),
      ),
    aggregateConversationEntityContexts: (messages: Array<{ entityContexts?: Array<{ value: string; tag?: string; notes: unknown[]; type: string; typeLabel: string }> }>) => {
      const map = new Map<string, { value: string; tag?: string; notes: unknown[]; type: string; typeLabel: string }>();
      for (const message of messages) {
        for (const entity of message.entityContexts ?? []) {
          map.set((entity.tag || entity.value).toLowerCase(), entity);
        }
      }
      return [...map.values()].sort((left, right) => left.value.localeCompare(right.value));
    },
  };
});

const mockRouterPush = jest.fn();
const mockSaveConversationMutate = jest.fn();
const mockGenerateConversationReportMutate = jest.fn();
const mockDeleteConversationMessageMutate = jest.fn();
const mockExplicitWebSearchMutate = jest.fn();
const mockStreamMessageMutate = jest.fn();
const mockToggleConversationEntityMutate = jest.fn();
const mockCancelStream = jest.fn();
const mockSetDraft = jest.fn();
const mockSetUseEuriaForConversation = jest.fn();
const mockSetUseRagForConversation = jest.fn();
const mockScrollToEnd = jest.fn();
const alertSpy = jest.spyOn(Alert, 'alert');
const originalConfirm = globalThis.confirm;
const mockConfirm = jest.fn();
let mockDraftValue = '';
let mockUseEuriaForConversation = false;
let mockUseRagForConversation = true;
let mockStreamMessageState = { mutate: mockStreamMessageMutate, isPending: false, error: null as Error | null, cancelStream: mockCancelStream };
let mockExplicitWebSearchState = { mutate: mockExplicitWebSearchMutate, isPending: false };
let mockConversationData: ConversationDetail | undefined = {
  id: 'conv-1',
  title: 'Conversation test',
  updatedAt: '2026-04-16T12:00:00Z',
  sizeBytes: 4096,
  draft: '',
  messages: [
    {
      id: 'user-1',
      role: 'user',
      content: 'Ada Lovelace',
      createdAt: '2026-04-16T12:00:00Z',
    },
    {
      id: 'assistant-1',
      role: 'assistant',
      content: "Cette information n'est pas dans ton coffre.",
      createdAt: '2026-04-16T12:00:01Z',
      sentinel: true,
      provenance: 'vault',
      primarySource: {
        filePath: 'Notes/Ada.md',
        noteTitle: 'Ada',
      },
      sources: [
        {
          filePath: 'Notes/Ada.md',
          noteTitle: 'Ada',
        },
        {
          filePath: 'Notes/Charles-Babbage.md',
          noteTitle: 'Charles Babbage',
        },
      ],
      timeline: ['Recherche dans le coffre', 'Verification des sources'],
    },
  ],
  lastGenerationStats: {
    tokens: 321,
    ttft: 1.4,
    total: 7.6,
    tps: 42,
  },
};

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockRouterPush }),
  useLocalSearchParams: () => ({ conversationId: 'conv-1' }),
}));

jest.mock('../../features/chat/use-chat', () => ({
  useConversation: () => ({
    data: mockConversationData,
    isLoading: false,
    isRefetching: false,
    refetch: jest.fn(),
  }),
  useDeleteConversationMessage: () => ({ mutate: mockDeleteConversationMessageMutate, isPending: false }),
  useExplicitWebSearch: () => mockExplicitWebSearchState,
  useGenerateConversationReport: () => ({ mutate: mockGenerateConversationReportMutate, isPending: false }),
  useSaveConversation: () => ({ mutate: mockSaveConversationMutate }),
  useStreamMessage: () => mockStreamMessageState,
  useToggleConversationEntity: () => ({ mutate: mockToggleConversationEntityMutate, isPending: false }),
}));

jest.mock('../../store/app-store', () => ({
  useAppStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      drafts: { 'conv-1': mockDraftValue },
      useEuriaForConversation: mockUseEuriaForConversation,
      useRagForConversation: mockUseRagForConversation,
      setDraft: (conversationId: string, value: string) => {
        mockSetDraft(conversationId, value);
        if (conversationId === 'conv-1') {
          mockDraftValue = value;
        }
      },
      setUseEuriaForConversation: (value: boolean) => {
        mockSetUseEuriaForConversation(value);
        mockUseEuriaForConversation = value;
      },
      setUseRagForConversation: (value: boolean) => {
        mockSetUseRagForConversation(value);
        mockUseRagForConversation = value;
      },
    }),
}));

jest.mock('../../components/ui/screen', () => {
  const ReactLocal = require('react');
  const { View: ViewLocal } = require('react-native');

  return {
    Screen: ({ children, scrollRef }: { children: React.ReactNode; scrollRef?: { current: { scrollToEnd: (options?: unknown) => void } | null } }) => {
      if (scrollRef) {
        scrollRef.current = { scrollToEnd: mockScrollToEnd };
      }
      return ReactLocal.createElement(ViewLocal, { testID: 'mock-screen' }, children);
    },
  };
});

import ConversationDetailScreen from '../../app/(tabs)/chat/[conversationId]';

function findPressableByLabel(tree: renderer.ReactTestRenderer, label: string) {
  return tree.root.findAll((node) => {
    if (typeof node.props.onPress !== 'function') {
      return false;
    }
    const texts = node.findAllByType(Text).flatMap((textNode) => {
      const value = textNode.props.children;
      return Array.isArray(value) ? value : [value];
    });
    return texts.includes(label);
  })[0];
}

function findPressablesByLabel(tree: renderer.ReactTestRenderer, label: string) {
  return tree.root.findAll((node) => {
    if (typeof node.props.onPress !== 'function') {
      return false;
    }
    const texts = node.findAllByType(Text).flatMap((textNode) => {
      const value = textNode.props.children;
      return Array.isArray(value) ? value : [value];
    });
    return texts.includes(label);
  });
}

function textTreeContains(tree: renderer.ReactTestRenderer, expected: string) {
  return tree.root.findAllByType(Text).some((node) => {
    const value = node.props.children;
    const parts = Array.isArray(value) ? value : [value];
    return parts.join('').includes(expected);
  });
}

describe('ConversationDetailScreen', () => {
  beforeAll(() => {
    globalThis.confirm = mockConfirm;
  });

  afterAll(() => {
    globalThis.confirm = originalConfirm;
  });

  beforeEach(() => {
    mockConversationData = {
      id: 'conv-1',
      title: 'Conversation test',
      updatedAt: '2026-04-16T12:00:00Z',
      sizeBytes: 4096,
      draft: '',
      messages: [
        {
          id: 'user-1',
          role: 'user',
          content: 'Ada Lovelace',
          createdAt: '2026-04-16T12:00:00Z',
        },
        {
          id: 'assistant-1',
          role: 'assistant',
          content: "Cette information n'est pas dans ton coffre. Voir aussi #Dune.",
          createdAt: '2026-04-16T12:00:01Z',
          sentinel: true,
          provenance: 'vault',
          primarySource: {
            filePath: 'Notes/Ada.md',
            noteTitle: 'Ada',
          },
          sources: [
            {
              filePath: 'Notes/Ada.md',
              noteTitle: 'Ada',
            },
            {
              filePath: 'Notes/Charles-Babbage.md',
              noteTitle: 'Charles Babbage',
            },
          ],
          timeline: ['Recherche dans le coffre', 'Verification des sources'],
        },
      ],
      lastGenerationStats: {
        tokens: 321,
        ttft: 1.4,
        total: 7.6,
        tps: 42,
      },
    };
    mockRouterPush.mockReset();
    mockSaveConversationMutate.mockReset();
    mockGenerateConversationReportMutate.mockReset();
    mockDeleteConversationMessageMutate.mockReset();
    mockExplicitWebSearchMutate.mockReset();
    mockStreamMessageMutate.mockReset();
    mockToggleConversationEntityMutate.mockReset();
    mockCancelStream.mockReset();
    mockSetDraft.mockReset();
    mockSetUseEuriaForConversation.mockReset();
    mockSetUseRagForConversation.mockReset();
    mockScrollToEnd.mockReset();
    mockDraftValue = '';
    mockUseEuriaForConversation = false;
    mockUseRagForConversation = true;
    alertSpy.mockReset();
    mockConfirm.mockReset();
    mockStreamMessageState = { mutate: mockStreamMessageMutate, isPending: false, error: null, cancelStream: mockCancelStream };
    mockExplicitWebSearchState = { mutate: mockExplicitWebSearchMutate, isPending: false };
  });

  it('renders save in the composer area and keeps the per-response web search action', () => {
    const tree = renderer.create(<ConversationDetailScreen />);

    expect(textTreeContains(tree, 'Rechercher sur le web')).toBe(true);
    expect(textTreeContains(tree, 'Modifie le')).toBe(true);
    expect(textTreeContains(tree, '4 ko')).toBe(true);
    expect(textTreeContains(tree, 'Provider actif')).toBe(true);
    expect(textTreeContains(tree, 'Local (MLX)')).toBe(true);
    expect(tree.root.findByProps({ testID: 'message-composer-secondary-action' })).toBeTruthy();
    expect(tree.root.findByProps({ testID: 'message-composer-tertiary-action' })).toBeTruthy();

    act(() => {
      findPressableByLabel(tree, 'Sauvegarder')?.props.onPress();
    });

    expect(mockSaveConversationMutate).toHaveBeenCalled();
    expect(mockSaveConversationMutate.mock.calls[0][0]).toBe('conv-1');
  });

  it('shows Euria as the active provider when the conversation toggle is enabled', () => {
    mockUseEuriaForConversation = true;

    const tree = renderer.create(<ConversationDetailScreen />);

    expect(textTreeContains(tree, 'Provider actif')).toBe(true);
    expect(textTreeContains(tree, 'Euria')).toBe(true);
    expect(tree.root.findByProps({ testID: 'message-composer-rag-toggle' })).toBeTruthy();
  });

  it('updates the conversation provider when the checkbox is toggled', () => {
    const tree = renderer.create(<ConversationDetailScreen />);

    act(() => {
      tree.root.findByProps({ testID: 'message-composer-euria-toggle' }).props.onPress();
    });

    expect(mockSetUseEuriaForConversation).toHaveBeenCalledWith(true);
  });

  it('shows the RAG toggle only when Euria is enabled and updates it independently', () => {
    const tree = renderer.create(<ConversationDetailScreen />);

    expect(() => tree.root.findByProps({ testID: 'message-composer-rag-toggle' })).toThrow();

    mockUseEuriaForConversation = true;
    const euriaTree = renderer.create(<ConversationDetailScreen />);

    const ragToggle = euriaTree.root.findByProps({ testID: 'message-composer-rag-toggle' });
    expect(ragToggle).toBeTruthy();

    act(() => {
      ragToggle.props.onPress();
    });

    expect(mockSetUseRagForConversation).toHaveBeenCalledWith(false);
  });

  it('clears the draft immediately and scrolls to the bottom when sending a question', () => {
    const tree = renderer.create(<ConversationDetailScreen />);
    const input = tree.root.findByProps({ testID: 'message-composer-input' });

    act(() => {
      input.props.onChangeText('Nouvelle question sur Artemis II');
    });

    act(() => {
      tree.root.findByProps({ testID: 'message-composer-submit' }).props.onPress();
    });

    expect(mockSetDraft).toHaveBeenCalledWith('conv-1', '');
    expect(mockScrollToEnd).toHaveBeenCalled();
    expect(mockStreamMessageMutate).toHaveBeenCalledWith('Nouvelle question sur Artemis II');
    const lastDraftCallOrder = mockSetDraft.mock.invocationCallOrder.at(-1);
    const firstStreamCallOrder = mockStreamMessageMutate.mock.invocationCallOrder[0];

    expect(lastDraftCallOrder).toBeDefined();
    expect(firstStreamCallOrder).toBeDefined();
    expect(lastDraftCallOrder!).toBeLessThan(firstStreamCallOrder!);
  });

  it('generates a report insight and opens it in the note viewer', () => {
    mockGenerateConversationReportMutate.mockImplementation((_conversationId: string, options?: { onSuccess?: (result: { path: string }) => void }) => {
      options?.onSuccess?.({ path: 'obsirag/insights/2026-04/rapport_test.md' });
    });

    const tree = renderer.create(<ConversationDetailScreen />);

    const [saveButton, reportButton] = findPressablesByLabel(tree, 'Sauvegarder').concat(findPressablesByLabel(tree, 'Rapport')).filter(Boolean);
    expect(saveButton).toBeTruthy();
    expect(reportButton).toBeTruthy();

    act(() => {
      findPressableByLabel(tree, 'Rapport')?.props.onPress();
    });

    expect(mockGenerateConversationReportMutate).toHaveBeenCalled();
    expect(mockGenerateConversationReportMutate.mock.calls[0][0]).toBe('conv-1');
    expect(mockRouterPush).toHaveBeenCalledWith(`/(tabs)/note/${encodeURIComponent('obsirag/insights/2026-04/rapport_test.md')}?returnTo=${encodeURIComponent('/(tabs)/chat/conv-1')}`);
  });

  it('asks for confirmation before deleting an assistant response', () => {
    mockConfirm.mockReturnValue(true);
    const tree = renderer.create(<ConversationDetailScreen />);

    act(() => {
      findPressableByLabel(tree, 'Supprimer la réponse')?.props.onPress();
    });

    expect(mockConfirm).toHaveBeenCalledWith('Cette question et sa réponse seront retirées définitivement de la conversation.');
    expect(alertSpy).not.toHaveBeenCalled();
    expect(mockDeleteConversationMessageMutate).toHaveBeenCalled();
    expect(mockDeleteConversationMessageMutate.mock.calls[0][0]).toBe('assistant-1');
  });

  it('does not delete an assistant response when confirmation is cancelled', () => {
    mockConfirm.mockReturnValue(false);
    const tree = renderer.create(<ConversationDetailScreen />);

    act(() => {
      findPressableByLabel(tree, 'Supprimer la réponse')?.props.onPress();
    });

    expect(mockConfirm).toHaveBeenCalledWith('Cette question et sa réponse seront retirées définitivement de la conversation.');
    expect(mockDeleteConversationMessageMutate).not.toHaveBeenCalled();
  });

  it('launches a contextual DDG search from a not-in-vault response', () => {
    mockConversationData = {
      id: 'conv-1',
      title: 'Conversation test',
      updatedAt: '2026-04-16T12:00:00Z',
      draft: '',
      messages: [
        {
          id: 'assistant-context',
          role: 'assistant',
          content: 'Elon Musk dirige Tesla.',
          createdAt: '2026-04-16T11:59:00Z',
          entityContexts: [
            { value: 'Elon Musk', type: 'person', typeLabel: 'Personne', notes: [] },
          ],
        },
        {
          id: 'user-1',
          role: 'user',
          content: 'Quel est son salaire ?',
          createdAt: '2026-04-16T12:00:00Z',
        },
        {
          id: 'assistant-1',
          role: 'assistant',
          content: "Cette information n'est pas dans ton coffre.",
          createdAt: '2026-04-16T12:00:01Z',
          sentinel: true,
          provenance: 'vault',
          entityContexts: [],
        },
      ],
    };

    const tree = renderer.create(<ConversationDetailScreen />);

    act(() => {
      findPressablesByLabel(tree, 'Rechercher sur le web').at(-1)?.props.onPress();
    });

    expect(mockExplicitWebSearchMutate).toHaveBeenCalledWith(`Elon Musk salary ${new Date().getFullYear()}`);
  });

  it('bases explicit web search on the current subject question', () => {
    mockConversationData = {
      id: 'conv-1',
      title: 'Conversation test',
      updatedAt: '2026-04-16T12:00:00Z',
      draft: '',
      messages: [
        {
          id: 'assistant-context',
          role: 'assistant',
          content: 'SpaceX est une entreprise spatiale.',
          createdAt: '2026-04-16T11:59:00Z',
          entityContexts: [
            { value: 'SpaceX', type: 'organization', typeLabel: 'Organisation', notes: [] },
          ],
        },
        {
          id: 'user-1',
          role: 'user',
          content: 'Parle moi de SpaceX',
          createdAt: '2026-04-16T12:00:00Z',
        },
        {
          id: 'assistant-1',
          role: 'assistant',
          content: "Cette information n'est pas dans ton coffre.",
          createdAt: '2026-04-16T12:00:01Z',
          sentinel: true,
          provenance: 'vault',
        },
      ],
    };

    const tree = renderer.create(<ConversationDetailScreen />);

    act(() => {
      findPressablesByLabel(tree, 'Rechercher sur le web').at(-1)?.props.onPress();
    });

    expect(mockExplicitWebSearchMutate).toHaveBeenCalledWith('SpaceX');
  });

  it('falls back to the primary source title when no recent entity is available', () => {
    mockConversationData = {
      id: 'conv-1',
      title: 'Conversation test',
      updatedAt: '2026-04-16T12:00:00Z',
      draft: '',
      messages: [
        {
          id: 'assistant-context',
          role: 'assistant',
          content: 'Resume de sujet.',
          createdAt: '2026-04-16T11:59:00Z',
          primarySource: {
            filePath: 'People/Elon-Musk.md',
            noteTitle: 'Elon Musk',
          },
        },
        {
          id: 'user-1',
          role: 'user',
          content: 'Quel est son age ?',
          createdAt: '2026-04-16T12:00:00Z',
        },
        {
          id: 'assistant-1',
          role: 'assistant',
          content: "Cette information n'est pas dans ton coffre.",
          createdAt: '2026-04-16T12:00:01Z',
          sentinel: true,
          provenance: 'vault',
        },
      ],
    };

    const tree = renderer.create(<ConversationDetailScreen />);

    act(() => {
      findPressablesByLabel(tree, 'Rechercher sur le web').at(-1)?.props.onPress();
    });

    expect(mockExplicitWebSearchMutate).toHaveBeenCalledWith(`Elon Musk age ${new Date().getFullYear()}`);
  });

  it('keeps web search tied to the latest user question on regular assistant responses too', () => {
    mockConversationData = {
      id: 'conv-1',
      title: 'Conversation test',
      updatedAt: '2026-04-16T12:00:00Z',
      draft: '',
      messages: [
        {
          id: 'user-1',
          role: 'user',
          content: 'Parle moi de SpaceX',
          createdAt: '2026-04-16T12:00:00Z',
        },
        {
          id: 'assistant-1',
          role: 'assistant',
          content: 'SpaceX est une entreprise spatiale fondee par Elon Musk.',
          createdAt: '2026-04-16T12:00:01Z',
          provenance: 'vault',
          entityContexts: [
            { value: 'SpaceX', type: 'organization', typeLabel: 'Organisation', notes: [] },
          ],
        },
      ],
    };

    const tree = renderer.create(<ConversationDetailScreen />);

    act(() => {
      findPressablesByLabel(tree, 'Rechercher sur le web').at(-1)?.props.onPress();
    });

    expect(mockExplicitWebSearchMutate).toHaveBeenCalledWith('SpaceX');
  });

  it('prioritizes the explicit subject from the user query over previous detected entities', () => {
    mockConversationData = {
      id: 'conv-1',
      title: 'Conversation test',
      updatedAt: '2026-04-16T12:00:00Z',
      draft: '',
      messages: [
        {
          id: 'assistant-context',
          role: 'assistant',
          content: 'Alpha Impulsion partage certains projets suivis aussi par Alphabet.',
          createdAt: '2026-04-16T11:59:00Z',
          provenance: 'vault',
          entityContexts: [
            { value: 'Alphabet', type: 'organization', typeLabel: 'Organisation', mentions: 19, notes: [] },
          ],
          primarySource: {
            filePath: 'Space/Alpha-Impulsion.md',
            noteTitle: "Alpha Impulsion révolutionne l'espace",
          },
        },
        {
          id: 'user-1',
          role: 'user',
          content: 'recherche sur le web des informations sur alpha impulsion',
          createdAt: '2026-04-16T12:00:00Z',
        },
        {
          id: 'assistant-1',
          role: 'assistant',
          content: 'Voici une réponse locale sur Alpha Impulsion.',
          createdAt: '2026-04-16T12:00:01Z',
          provenance: 'vault',
        },
      ],
    };

    const tree = renderer.create(<ConversationDetailScreen />);

    act(() => {
      findPressablesByLabel(tree, 'Rechercher sur le web').at(-1)?.props.onPress();
    });

    expect(mockExplicitWebSearchMutate).toHaveBeenCalledWith('alpha impulsion');
  });

  it('keeps the source access available from the message bubble', () => {
    const tree = renderer.create(<ConversationDetailScreen />);

    expect(textTreeContains(tree, 'Synthese de generation')).toBe(false);

    act(() => {
      tree.root.findByProps({ testID: 'sources-panel-toggle' }).props.onPress();
    });

    const sourcePressable = tree.root.findAll((node) => typeof node.props.onPress === 'function').find((node) =>
      node.findAllByType(Text).some((textNode) => textNode.props.children === 'Notes/Ada.md'),
    );

    act(() => {
      sourcePressable?.props.onPress();
    });

    expect(mockCancelStream).toHaveBeenCalled();
    expect(mockRouterPush).toHaveBeenCalledWith(`/(tabs)/note/${encodeURIComponent('Notes/Ada.md')}?returnTo=${encodeURIComponent('/(tabs)/chat/conv-1')}`);
  });

  it('keeps sources collapsed by default and toggles them on demand', () => {
    const tree = renderer.create(<ConversationDetailScreen />);

    expect(textTreeContains(tree, 'Sources')).toBe(true);
    expect(textTreeContains(tree, '2 sources')).toBe(true);
    expect(() => tree.root.findByProps({ testID: 'sources-panel-content' })).toThrow();

    act(() => {
      tree.root.findByProps({ testID: 'sources-panel-toggle' }).props.onPress();
    });

    expect(textTreeContains(tree, 'Notes/Ada.md')).toBe(true);
    expect(textTreeContains(tree, 'Notes/Charles-Babbage.md')).toBe(true);
  });

  it('uses the compact composer without plus button or reply hint', () => {
    const tree = renderer.create(<ConversationDetailScreen />);

    expect(textTreeContains(tree, 'Repondre...')).toBe(false);
    expect(textTreeContains(tree, '+')).toBe(false);
    expect(tree.root.findByType(TextInput).props.placeholder).toBe('Posez une question sur votre coffre...');
  });

  it('opens the graph filtered by tag when a markdown hashtag is pressed', () => {
    const tree = renderer.create(<ConversationDetailScreen />);

    act(() => {
      tree.root.findByProps({ testID: 'markdown-inline-tag' }).props.onPress();
    });

    expect(mockRouterPush).toHaveBeenCalledWith('/(tabs)/graph?tag=Dune');
  });

  it('offers quick-start suggestions when the thread is empty', () => {
    mockConversationData = {
      id: 'conv-1',
      title: 'Conversation vide',
      updatedAt: '2026-04-16T12:00:00Z',
      draft: '',
      messages: [],
    };

    const tree = renderer.create(<ConversationDetailScreen />);

    expect(textTreeContains(tree, 'Exemples de questions')).toBe(true);

    act(() => {
      findPressableByLabel(tree, 'Resume la note principale sur Artemis II')?.props.onPress();
    });

    expect(mockSetDraft).toHaveBeenCalledWith('conv-1', 'Resume la note principale sur Artemis II');
  });

  it('does not crash while conversation data is still undefined', () => {
    mockConversationData = undefined as unknown as typeof mockConversationData;

    expect(() => renderer.create(<ConversationDetailScreen />)).not.toThrow();
  });

  it('renders an aggregated entity sidebar from conversation messages', () => {
    mockConversationData = {
      id: 'conv-1',
      title: 'Conversation test',
      updatedAt: '2026-04-16T12:00:00Z',
      draft: '',
      messages: [
        {
          id: 'assistant-1',
          role: 'assistant',
          content: 'Reponse 1',
          createdAt: '2026-04-16T12:00:00Z',
          entityContexts: [
            { value: 'Zulu', tag: 'Zulu', type: 'concept', typeLabel: 'Concept', notes: [] },
          ],
        },
        {
          id: 'assistant-2',
          role: 'assistant',
          content: 'Reponse 2',
          createdAt: '2026-04-16T12:00:01Z',
          entityContexts: [
            { value: 'Alpha', tag: 'Alpha', type: 'concept', typeLabel: 'Concept', notes: [] },
            { value: 'Zulu', tag: 'Zulu', type: 'concept', typeLabel: 'Concept', notes: [] },
          ],
        },
      ],
    };

    const tree = renderer.create(<ConversationDetailScreen />);
    const sidebar = tree.root.findByProps({ testID: 'conversation-entity-sidebar' });
    const values = sidebar.findAllByType(Text).map((node) => node.props.children);

    expect(values).toEqual(['Alpha', 'Zulu']);
  });

  it('shows detailed prompt progress steps while generation is pending', () => {
    mockConversationData = {
      id: 'conv-1',
      title: 'Conversation test',
      updatedAt: '2026-04-16T12:00:00Z',
      draft: '',
      messages: [
        {
          id: 'user-1',
          role: 'user',
          content: 'Ada Lovelace',
          createdAt: '2026-04-16T12:00:00Z',
        },
        {
          id: 'streaming-assistant',
          role: 'assistant',
          content: '',
          createdAt: '2026-04-16T12:00:01Z',
          timeline: ['Analyse de la requete', 'Recherche dans le coffre', 'Generation MLX'],
        },
      ],
    };
    mockStreamMessageState = { mutate: mockStreamMessageMutate, isPending: true, error: null, cancelStream: mockCancelStream };

    const tree = renderer.create(<ConversationDetailScreen />);

    expect(textTreeContains(tree, 'Réponse en préparation')).toBe(true);
    expect(textTreeContains(tree, 'Analyse de la requete')).toBe(false);
    expect(textTreeContains(tree, 'Recherche dans le coffre')).toBe(false);
    expect(textTreeContains(tree, 'Generation MLX')).toBe(true);
    expect(textTreeContains(tree, 'Generation en cours...')).toBe(false);
  });

  it('shows a response preparation indicator for pending explicit web search', () => {
    mockConversationData = {
      id: 'conv-1',
      title: 'Conversation test',
      updatedAt: '2026-04-16T12:00:00Z',
      draft: '',
      messages: [
        {
          id: 'web-user-1',
          role: 'user',
          content: '🌐 Recherche sur le web : Ada Lovelace',
          createdAt: '2026-04-16T12:00:00Z',
        },
        {
          id: 'pending-web-assistant',
          role: 'assistant',
          content: '',
          createdAt: '2026-04-16T12:00:01Z',
          timeline: ['Réponse en préparation', 'Recherche sur le web en cours...'],
          provenance: 'web',
        },
      ],
    };
    mockExplicitWebSearchState = { mutate: mockExplicitWebSearchMutate, isPending: true };

    const tree = renderer.create(<ConversationDetailScreen />);

    expect(textTreeContains(tree, 'Réponse en préparation')).toBe(true);
    expect(textTreeContains(tree, 'Réponse en préparation')).toBe(true);
    expect(textTreeContains(tree, 'Recherche sur le web en cours...')).toBe(true);
  });

});