import React from 'react';
import renderer, { act } from 'react-test-renderer';
import { Text } from 'react-native';

const mockRouterPush = jest.fn();
const mockCreateConversationMutateAsync = jest.fn();
const mockDeleteConversationMutateAsync = jest.fn();
const mockSetActiveConversationId = jest.fn();
const mockClearDraft = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockRouterPush }),
}));

jest.mock('../../components/chat/conversation-list-item', () => {
  const React = require('react');
  const { Pressable, Text, View } = require('react-native');

  return {
    ConversationListItem: ({ item, onPress, onDelete }: { item: { title: string }; onPress: () => void; onDelete?: () => void }) => (
      React.createElement(View, {}, [
        React.createElement(Pressable, { key: 'open', testID: 'conversation-open', onPress }, React.createElement(Text, {}, item.title)),
        onDelete ? React.createElement(Pressable, { key: 'delete', testID: 'conversation-delete', onPress: onDelete }, React.createElement(Text, {}, 'Supprimer')) : null,
      ])
    ),
  };
});

jest.mock('../../features/chat/use-chat', () => ({
  useConversations: () => ({
    data: [
      {
        id: 'conv-1',
        title: 'Fil Ada',
        preview: 'Resume de la conversation Ada',
        updatedAt: '2026-04-17T10:00:00Z',
        turnCount: 2,
        messageCount: 4,
        isCurrent: true,
      },
    ],
    isLoading: false,
    isRefetching: false,
    refetch: jest.fn(),
  }),
  useCreateConversation: () => ({
    mutateAsync: mockCreateConversationMutateAsync,
  }),
  useDeleteConversation: () => ({
    mutateAsync: mockDeleteConversationMutateAsync,
    isPending: false,
    variables: undefined,
  }),
}));

jest.mock('../../store/app-store', () => ({
  useAppStore: (selector: (state: Record<string, unknown>) => unknown) =>
    selector({
      activeConversationId: 'conv-1',
      setActiveConversationId: mockSetActiveConversationId,
      clearDraft: mockClearDraft,
    }),
}));

import ConversationsScreen from '../../app/(tabs)/chat/index';

describe('ConversationsScreen', () => {
  const initialConfirm = globalThis.confirm;

  beforeEach(() => {
    mockRouterPush.mockReset();
    mockCreateConversationMutateAsync.mockReset();
    mockDeleteConversationMutateAsync.mockReset();
    mockSetActiveConversationId.mockReset();
    mockClearDraft.mockReset();
    globalThis.confirm = jest.fn(() => true);
  });

  afterAll(() => {
    globalThis.confirm = initialConfirm;
  });

  it('deletes a conversation from the list on web confirmation', async () => {
    const tree = renderer.create(<ConversationsScreen />);
    const deleteButton = tree.root.findByProps({ testID: 'conversation-delete' });

    await act(async () => {
      deleteButton.props.onPress();
    });

    expect(globalThis.confirm).toHaveBeenCalledWith('Cette suppression affectera le stockage backend de ce fil.');
    expect(mockDeleteConversationMutateAsync).toHaveBeenCalledWith('conv-1');
    expect(mockClearDraft).toHaveBeenCalledWith('conv-1');
    expect(mockSetActiveConversationId).toHaveBeenCalledWith(undefined);
  });
});