import React from 'react';
import renderer, { act } from 'react-test-renderer';
import { Alert, Text, TextInput } from 'react-native';

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
const mockDeleteConversationMessageMutate = jest.fn();
const mockExplicitWebSearchMutate = jest.fn();
const mockStreamMessageMutate = jest.fn();
const mockSetDraft = jest.fn();
const alertSpy = jest.spyOn(Alert, 'alert');
const originalConfirm = globalThis.confirm;
const mockConfirm = jest.fn();
let mockStreamMessageState = { mutate: mockStreamMessageMutate, isPending: false, error: null as Error | null };
let mockConversationData = {
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
  useExplicitWebSearch: () => ({ mutate: mockExplicitWebSearchMutate, isPending: false }),
  useSaveConversation: () => ({ mutate: mockSaveConversationMutate }),
  useStreamMessage: () => mockStreamMessageState,
}));

jest.mock('../../store/app-store', () => ({
  useAppStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      drafts: { 'conv-1': '' },
      setDraft: mockSetDraft,
    }),
}));

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
        tps: 42,
      },
    };
    mockRouterPush.mockReset();
    mockSaveConversationMutate.mockReset();
    mockDeleteConversationMessageMutate.mockReset();
    mockExplicitWebSearchMutate.mockReset();
    mockStreamMessageMutate.mockReset();
    mockSetDraft.mockReset();
    alertSpy.mockReset();
    mockConfirm.mockReset();
    mockStreamMessageState = { mutate: mockStreamMessageMutate, isPending: false, error: null };
  });

  it('renders save in the composer area and keeps the per-response web search action', () => {
    const tree = renderer.create(<ConversationDetailScreen />);

    expect(textTreeContains(tree, 'Rechercher sur le web')).toBe(true);
    expect(tree.root.findByProps({ testID: 'message-composer-secondary-action' })).toBeTruthy();

    act(() => {
      findPressableByLabel(tree, 'Sauvegarder')?.props.onPress();
    });

    expect(mockSaveConversationMutate).toHaveBeenCalled();
    expect(mockSaveConversationMutate.mock.calls[0][0]).toBe('conv-1');
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

  it('expands generic subject questions into enrichment-oriented DDG queries', () => {
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

    expect(mockExplicitWebSearchMutate).toHaveBeenCalledWith('SpaceX company overview latest');
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

  it('offers web search from a regular assistant response too', () => {
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

    expect(mockExplicitWebSearchMutate).toHaveBeenCalledWith('SpaceX company overview latest');
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

    expect(mockRouterPush).toHaveBeenCalledWith('/(tabs)/note/Notes%2FAda.md');
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
    mockStreamMessageState = { mutate: mockStreamMessageMutate, isPending: true, error: null };

    const tree = renderer.create(<ConversationDetailScreen />);

    expect(textTreeContains(tree, 'Progression du traitement')).toBe(true);
    expect(textTreeContains(tree, 'Analyse de la requete')).toBe(true);
    expect(textTreeContains(tree, 'Recherche dans le coffre')).toBe(true);
    expect(textTreeContains(tree, 'Generation MLX')).toBe(true);
    expect(textTreeContains(tree, 'Generation en cours...')).toBe(false);
  });
});