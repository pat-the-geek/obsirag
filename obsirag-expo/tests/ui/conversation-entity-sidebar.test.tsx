import React from 'react';
import renderer, { act } from 'react-test-renderer';
import { Text } from 'react-native';

import { aggregateConversationEntityContexts, buildCompactNoteLabel, ConversationEntitySidebar } from '../../components/chat/conversation-entity-sidebar';
import { ChatMessage } from '../../types/domain';

describe('ConversationEntitySidebar', () => {
  it('aggregates, deduplicates and sorts entity contexts across the conversation', () => {
    const messages: ChatMessage[] = [
      {
        id: 'assistant-1',
        role: 'assistant',
        content: 'Reponse',
        createdAt: '2026-04-16T12:00:00Z',
        entityContexts: [
          {
            type: 'person',
            typeLabel: 'Personne',
            value: 'Zulu',
            mentions: 1,
            notes: [{ title: 'Zeta Knowledge Base', filePath: 'Notes/Zeta-Knowledge-Base.md' }],
          },
        ],
      },
      {
        id: 'assistant-2',
        role: 'assistant',
        content: 'Reponse',
        createdAt: '2026-04-16T12:00:01Z',
        entityContexts: [
          {
            type: 'person',
            typeLabel: 'Personne',
            value: 'Alpha',
            mentions: 2,
            notes: [{ title: 'Alpha Research Notebook', filePath: 'Notes/Alpha-Research-Notebook.md' }],
          },
          {
            type: 'person',
            typeLabel: 'Personne',
            value: 'Zulu',
            mentions: 3,
            notes: [{ title: 'Zulu Field Notes', filePath: 'Notes/Zulu-Field-Notes.md' }],
          },
        ],
      },
    ];

    const entities = aggregateConversationEntityContexts(messages);

    expect(entities.map((entity) => entity.value)).toEqual(['Alpha', 'Zulu']);
    expect(entities[1]?.mentions).toBe(4);
    expect(entities[1]?.notes.map((note) => note.filePath)).toEqual(['Notes/Zeta-Knowledge-Base.md', 'Notes/Zulu-Field-Notes.md']);
  });

  it('truncates related note labels from the start of the note name', () => {
    expect(buildCompactNoteLabel({ title: 'Alpha Research Notebook', filePath: 'Notes/Alpha-Research-Notebook.md' }, 112)).toBe('Alpha Research Not…');
  });

  it('renders related note pills that open the linked note', () => {
    const noteCalls: string[] = [];
    const tree = renderer.create(
      <ConversationEntitySidebar
        entities={[
          {
            type: 'person',
            typeLabel: 'Personne',
            value: 'Alpha',
            imageUrl: 'https://example.com/alpha.png',
            notes: [{ title: 'Alpha Research Notebook', filePath: 'Notes/Alpha-Research-Notebook.md' }],
          },
        ]}
        onOpenNote={(path) => noteCalls.push(path)}
      />,
    );

    act(() => {
      tree.root.findByProps({ testID: 'entity-note-pill' }).props.onPress();
    });

    expect(noteCalls).toEqual(['Notes/Alpha-Research-Notebook.md']);
  });

  it('renders metadata for related notes when available', () => {
    const tree = renderer.create(
      <ConversationEntitySidebar
        entities={[
          {
            type: 'person',
            typeLabel: 'Personne',
            value: 'Alpha',
            notes: [
              {
                title: 'Alpha Research Notebook',
                filePath: 'Notes/Alpha-Research-Notebook.md',
                dateModified: '2026-04-19T14:35:00Z',
                sizeBytes: 4096,
              },
            ],
          },
        ]}
      />,
    );

    const renderedText = tree.root
      .findAllByType(Text)
      .map((node) => {
        const children = node.props.children;
        return Array.isArray(children) ? children.join('') : String(children ?? '');
      })
      .join('\n');

    expect(renderedText).toContain('4 ko');
  });

  it('renders the entity cards inside a dedicated scroll container', () => {
    const tree = renderer.create(
      <ConversationEntitySidebar
        entities={[
          {
            type: 'person',
            typeLabel: 'Personne',
            value: 'Alpha',
            notes: [],
          },
        ]}
        maxHeight={420}
      />,
    );

    expect(tree.root.findByProps({ testID: 'conversation-entity-sidebar-scroll' })).toBeTruthy();
  });

  it('remains visible when all entities are hidden so the user can unhide them', () => {
    const tree = renderer.create(
      <ConversationEntitySidebar
        entities={[]}
        hiddenEntities={[
          {
            type: 'person',
            typeLabel: 'Personne',
            value: 'Alpha',
            notes: [],
          },
        ]}
        onUnhideEntity={() => {}}
      />,
    );

    expect(tree.root.findByProps({ testID: 'conversation-entity-sidebar' })).toBeTruthy();
    expect(tree.root.findByProps({ testID: 'entity-unhide-action' })).toBeTruthy();
  });

  it('returns null when both entities and hiddenEntities are empty', () => {
    const tree = renderer.create(
      <ConversationEntitySidebar entities={[]} hiddenEntities={[]} />,
    );

    expect(tree.toJSON()).toBeNull();
  });
});