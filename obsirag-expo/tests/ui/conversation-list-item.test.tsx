import React from 'react';
import renderer from 'react-test-renderer';
import { Text } from 'react-native';

import { ConversationListItem } from '../../components/chat/conversation-list-item';
import { ConversationSummary } from '../../types/domain';

describe('ConversationListItem', () => {
  it('renders modified date, size, and counters in the metadata line', () => {
    const item: ConversationSummary = {
      id: 'conv-1',
      title: 'Fil Artemis',
      preview: 'Resume rapide',
      updatedAt: '2026-04-19T14:35:00Z',
      sizeBytes: 4096,
      turnCount: 2,
      messageCount: 5,
      isCurrent: true,
    };

    const tree = renderer.create(<ConversationListItem item={item} onPress={() => undefined} />);
    const joined = tree.root.findAllByType(Text).map((node) => String(Array.isArray(node.props.children) ? node.props.children.join('') : node.props.children ?? '')).join(' ');

    expect(joined).toContain('Modifie le');
    expect(joined).toContain('4 ko');
    expect(joined).toContain('2 tours');
    expect(joined).toContain('5 messages');
  });
});