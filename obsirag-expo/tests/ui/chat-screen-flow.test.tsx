import React from 'react';
import renderer, { act } from 'react-test-renderer';
import { Text } from 'react-native';

const mockRouterPush = jest.fn();
const mockSaveConversationMutate = jest.fn();
const mockExplicitWebSearchMutate = jest.fn();
const mockStreamMessageMutate = jest.fn();
const mockSetDraft = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockRouterPush }),
  useLocalSearchParams: () => ({ conversationId: 'conv-1' }),
}));

jest.mock('../../features/chat/use-chat', () => ({
  useConversation: () => ({
    data: {
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
        },
      ],
    },
    isLoading: false,
    isRefetching: false,
    refetch: jest.fn(),
  }),
  useSaveConversation: () => ({ mutate: mockSaveConversationMutate }),
  useExplicitWebSearch: () => ({ mutate: mockExplicitWebSearchMutate, isPending: false }),
  useStreamMessage: () => ({ mutate: mockStreamMessageMutate, isPending: false, error: null }),
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

describe('ConversationDetailScreen', () => {
  beforeEach(() => {
    mockRouterPush.mockReset();
    mockSaveConversationMutate.mockReset();
    mockExplicitWebSearchMutate.mockReset();
    mockStreamMessageMutate.mockReset();
    mockSetDraft.mockReset();
  });

  it('shows and closes the web-search prompt from a sentinel answer', () => {
    const tree = renderer.create(<ConversationDetailScreen />);

    expect(tree.root.findAllByType(Text).some((node) => node.props.children === 'Recherche web explicite')).toBe(false);

    act(() => {
      findPressableByLabel(tree, 'Preparer une recherche web')?.props.onPress();
    });

    expect(tree.root.findAllByType(Text).some((node) => node.props.children === 'Recherche web explicite')).toBe(true);

    act(() => {
      findPressableByLabel(tree, 'Utiliser dans le chat')?.props.onPress();
    });

    expect(mockSetDraft).toHaveBeenCalledWith('conv-1', 'Ada Lovelace');
    expect(tree.root.findAllByType(Text).some((node) => node.props.children === 'Recherche web explicite')).toBe(false);

    act(() => {
      findPressableByLabel(tree, 'Relancer')?.props.onPress();
    });

    expect(mockSetDraft).toHaveBeenCalledWith('conv-1', 'Ada Lovelace');
  });
});